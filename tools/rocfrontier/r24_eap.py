# EAP r1 - THE EARNINGS-ANNOUNCEMENT PREMIUM in Nasdaq-100 names on PREDICTED release dates: a release's next-year date is PREDICTED as its acceptance date + 364 days (the same weekday, moved to the next session), and only releases
# ACCEPTED BEFORE the rank are inputs. Cell M (MONTHLY): at each month-end rank long the universe names DUE next month (a predicted date in the next month's sessions), short the names not due, each side min($200,000, $10,000 x its count) split
# equally [E8], fewer than 8 names on a side = no trade; fill at the next open, hold to the next fill (RESMOM's engine). Cell W (EVENT WINDOW): $4,000 long from the official open of the 3rd session before each predicted date p to the official open of
# the 2nd session after it, short ES by the name's ex-ante OLS beta over the 252 sessions before the entry (252 ES pairs required [E9]; 0.5 bps a side on the hedge). A leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56) and is reported
# INCREMENTALLY over the S1-restated reference L = #463 + 0.264 x RES [E17]. Pre-registered: tools/rocfrontier/PREREG_EAP_R1.txt (canonical LF sha256 2528a420...2c34 = DRAFT v1 + PRE-DATA ADDENDA 1 [E1]-[E18], 2 [E19]-[E21], 3 [E22]-[E24] and 4 [E25]-[E26], which override the draft wherever they differ).
# Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
# EAP is RESMOM r1's sibling in the same lane on the same data: r17_resmom.py is imported, never copied and never edited (its loaders, the pinned wide corporate-actions calendar, the dividend / spin-off arrays, the monthly schedule, the unit paths with the
# dividends and hygiene edit S1's 'close' cut (rm_units / close_units / l1_pnl_x), the A2 volatility rule, the book checks, the refusals) and through it r15_ddw.py (World, universe, cell statistics, seat, draw_order); r18_divrun.py is imported for the REFERENCE
# book (ref_load / ref_build / ref_at / incremental_pass / a2_report, pointed at the S1-restated line at import, exactly as NETISS r1 does), the rolling 252-session beta and the generic helpers; r19_edrift.py for the pinned earnings calendar's path and sha.
# NETISS r1 (r21_netiss.py, not on this branch) is read as a pattern only: its symbol -> CIK map rules, the one-share-class rule, DD5, the judged / report readings. What this file adds is the CALENDAR logic: the CIK join, [E2] / [E3], the 364-day prediction, the
# point-in-time Nasdaq-100 membership, the four-releases universe, [E1], [E19]'s predecessor-CIK joins over [E20]'s one table, the DUE lists, the event windows, the ES hedges, the two nulls, the pre-P&L prints ([E5] accuracy with the 80% recall STOP, [E6] turnover,
# [E7] the power line, [E19]'s joined name-months) and the reports.
#   python r24_eap.py selftest    hand-made worlds and calendars, no data: [P] and [E3] (ILMN / REGN / ISRG / DXCM planted), [E2], [E1], the universe, the DUE lists and sizes with [E8], W's events with [E9], every position's path (the S1 close inside an M hold and inside
#                                 a W window) against plain-python recounts, both nulls (seeded, the [E11] shift 27 .. 36), [E5] and the STOP, [E6], [E7], [E10], [E13], [E14], the Stage A checks broken one at a time, the refusals; [E19] / [E20]: the list's rows
#                                 told apart by content, the addendum's changes asserted, the one-table read, the join (window inclusive, FOX / FOXA once, a non-change joins nothing) and every refusal (another sha, the same accession twice ...)
#   python r24_eap.py smoke DIR   offline end-to-end on SYNTHETIC worlds (r5_siporb's fake Alpaca, fake ES / NQ masters, a fake #463, a fake L line, a fake earnings calendar + [E20] predecessors' file, map, [E19] list and members file): a world with a planted announcement premium that Stage A must find and
#                                 a world without one where it must not; a calendar whose recall falls under 80% must STOP before any P&L; DIR's name must contain 'smoke'
#   python r24_eap.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - releases per year and per name, joined / unjoined names by reason, [E19]'s joined name-months per symbol, the universe per rank, DUE / NOT-DUE per rank, the [E1] / [E3] lists, W's events per year and
#                                 open positions per session, [E5] accuracy both ways with the STOP, [E6] turnover and the break-even spread, [E7] the power line - never a price, return, beta or P&L
#   python r24_eap.py stage_a     WF Stage A: the pre-P&L prints FIRST (the run STOPS there if [E5]'s recall is under 80% in a WF year), then the cells, both nulls, the checks (a) - (e) with (c) at p97.5 [E12] and [E13], A2 over L, [E14] SEAT, [E10], [E15], the
#                                 diagnostics -> eap_stageA.json (+ eap_audit_candidates.csv), PRE-LOCKBOX ONLY
#   python r24_eap.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's flag file eap_stageB_GO.flag is on file and a Stage A candidate passed (a)-(e); the pass is the LEG's veto, the book add is only reported
# Reads (never writes) the SIPORB cache through r5_siporb, the ES and NQ 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar, the S1-restated L line file, TV's sha-pinned EDGAR earnings calendar,
# TV's sha-pinned predecessors' releases ([E20], read as ONE table with the calendar), NETISS's sha-pinned symbol -> CIK map, TV's sha-pinned [E4] predecessor-CIK list ([E19]), tools/data/ndx_members.csv and (a report) EDRIFT r1's Stage A file, every one cut at read. Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else, and nothing makes a network call.
import bisect, contextlib, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17            # the sibling harness (RESMOM r1): loaders, the wide calendar, the dividend / spin-off arrays, the schedule, rm_units / close_units / l1_pnl_x (hygiene edit S1), A2, the book checks
import r18_divrun as DV             # the sibling harness (DIVRUN r1): the REFERENCE book, the incremental A2, rolling_beta, the synthetic market of the smoke
import r19_edrift as ED             # the sibling harness (EDRIFT r1): the pinned EDGAR earnings calendar's path and sha
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw (World, cell statistics, seat, draw_order), r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports
from augur_engine.drawdowns import dd5 as _dd5                         # noqa: E402  DD5 beside every ROC (owner rule 2026-10-07, MANAGER #120; the repo root is on the path through r5_siporb)
# [E17] THE REFERENCE IS THE S1-RESTATED L (MANAGER #127): r18_divrun's loader reads the restated line file (the same columns, #463's WF index row for row) and refuses unless its sha256 and its WF numbers are these - set at import exactly as r21_netiss.py
# does; the selftests and the smoke still point the loader at their stubs. r18_divrun itself (DIVRUN r1, closed) keeps its registered file.
DV.REF_CSV = DV.REF_CSV_PINNED = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
DV.REF_SHA = "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18"
DV.REF_FACTS = {"roc": 121.06, "sortino": 3.926, "max_dd": 36526.0}

TS = pd.Timestamp
THIS = sys.modules[__name__]
OUT_DEFAULT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\eap_r1"
OUT = os.environ.get("EDGELOG_EAP_R1", OUT_DEFAULT)                                                       # results, outside git
PREREG = os.path.join(HERE, "PREREG_EAP_R1.txt")
PREREG_SHA = "df4f77495f2d77fa98dacbb3723fe5c1f6cf19b7725692de0d6bbeebbe532c57"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDA 1 ([E1]-[E18]), 2 ([E19]-[E21], the [E4] list pinned), 3 ([E22]-[E24], the lead's review of this harness) and 4 ([E25]-[E26], MANAGER #141); 5 ([E27], the CHOICEs 46-50); supersedes 2528a420
WF0, PRE_END, LB0, LB1 = M17.WF0, M17.PRE_END, M17.LB0, M17.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED, SEED_SHIFT = 500, 20261019, 20261020                         # the random-name null (both cells) and [E11] W's time-shift null
E5_WAIVER = {"by": "MANAGER #141", "years": ("2016-17",), "addendum": "[E25]"}     # [E25] the [E5] stop FIRED (recall 79.8% in the partial first WF year 2016-17): a RECORDED waiver - Stage A goes on ONLY when every failing July-June year is in it; a recall under 80% in any other year still stops
SENS_FROM = TS("2017-07-01")             # [E25] the SENSITIVITY: Stage A again with 2016-17 dropped (the positions / events entered and the days before 2017-07-01 left out); the STRICTER of the two verdicts governs
CELLS = ("M", "W")                                                       # the family: 2 cells
YEARS = D15.YEARS                                                        # the nine July-June WF years 2016-17 .. 2024-25
SUBPERIODS = DV.SUBPERIODS                                               # the halves 2016-07-01 .. 2021-12-31 and 2022-01-01 .. 2025-06-29 (the prereg's '2016-21 / 2022-25')
A2_WIN, A2_TARGET, A2_REPORT = (TS("2017-01-03"), TS("2018-12-31")), 0.25, (0.5, 2.0)   # A2 (a REPORT): c = 25% of #463's daily std over 2017-01-03 .. 2018-12-31 / the cell's; 0.5c and 2c reported
COST_BPS, STRESS_BPS, COST_CURVE = M17.COST_BPS, M17.STRESS_BPS, (0.0, 5.0, 10.0, 20.0)                    # 5 bps a side (stress 10, 20); the diagnostics' cost curve 0 / 5 / 10 / 20
BORROW, BORROW_STRESS, K_STRESS = M17.BORROW, M17.BORROW_STRESS, M17.K_STRESS       # 0.25% a year on short notional (stress 1% and 3% on sessions with k_t > 1.5)
HEDGE_BPS = DV.ES_EXACT_BPS                                              # 0.5 bps a side of the ES hedge's notional (W's hedge, M's [E13] hedge)
AUDIT_N = 50                                                             # (f) the largest single-name contributors audited by hand
BETA_CAP, TILT_CAP = 0.20, 0.20                                          # A2: |realised beta| > 0.20 per $ of one side = reported, never credited; [E10] |NQ - ES loading| > 0.20 per $ long = the tilt-removed ROC printed
REF_DD5 = 34392.0                                                        # [E17] L's registered DD5 (with 121.06 / 3.926 / $36,526: r18_divrun's REF_FACTS) - refused unless it reproduces to the dollar
CAL_CSV = ED.CAL_CSV                                                     # [D1] TV's EDGAR earnings calendar (every 8-K with item 2.02 of the Nasdaq-100 members ever listed) ...
CAL_SHA = ED.CAL_SHA                                                     # ... pinned by the sha256 of its BYTES (8f4f9f4b..., EDRIFT r1's addendum 4; refused if different)
CAL_COLS = ("ticker", "ndx_tickers", "cik", "form", "accepted_et", "reaction_session", "timing", "items", "accession")
AMEND_FORM = "8-K/A"                                                     # [E2] dropped from [P] (counted)
MEMBERS_CSV = os.path.join(os.path.dirname(HERE), "data", "ndx_members.csv")       # [D2] (in THIS draft [D2] is ndx_members.csv): ticker, from, to - month starts, from inclusive, to exclusive, '' = open
EDGAR_DIR = os.environ.get("EDGELOG_EDGAR_DIR", r"C:\EdgeLog\_research_cache\edgar")
MAP_FILES = {"map": os.path.join(EDGAR_DIR, "symbol_cik_map_wide_symbols_siporb_floor_2016_2025.csv"), "map_add": os.path.join(EDGAR_DIR, "symbol_cik_map_wide_additions_reviewed.csv")}
MAP_SHA = {"map": "19adc9badc8e9c2b999d818c9aa4b78f257835e19eacd418cdf55c0fc93f1909", "map_add": "6bf8dfabc0a945bcf6c30f1d6bca201703d8a67d1e8f48daccfba4c6ca23c866"}     # NETISS's pinned map ([A1] / [A8]) and its reviewed additions
MAP_LABEL = {"map": "symbol -> CIK map", "map_add": "reviewed map additions"}
MAP_COLS = ("symbol", "cik", "method")
ALLOWED_METHODS, ADD_METHODS = ("current_ticker", "name_exact"), ("reviewed_same_firm",)    # NETISS [A1] / [A8]: the usable rows
PRED_LIST_PINNED = (os.path.join(EDGAR_DIR, "edgar_predecessor_map.csv"), "87620b86be78d46db10c3b68df3e5f6d03101595c5bc0923bbb6805cce6a3c00")     # [E19] the [E4] predecessor-CIK list (TV's tools/edgar_predecessors.py, 9 rows), pinned by the sha256 of its BYTES
PRED_LIST = PRED_LIST_PINNED       # (path, sha256) - None = not pinned: the run proceeds with the CIK-break name-months unjoined and says so (the selftest's default; a real run reads the pinned file)
PRED_COLS = ("symbol", "predecessor_cik", "predecessor_name", "successor_cik", "first_8k_date", "last_8k_date", "edgar_source_url", "note")   # TV's columns: [E4]'s from / to = first_8k_date / last_8k_date (inclusive), its source = edgar_source_url
PRED_EXPECTED = {"AVGO": "0001649338", "FOX": "0001308161", "FOXA": "0001308161", "MRVL": "0001058057", "CEG": "0001168165"}    # [E19] the list's real CIK changes (symbol: predecessor CIK): the file must hold exactly these, else refused
PRED_HOLES = ("DISH", "NXPI", "SIRI", "TEAM")                             # [E19] its rows that are NOT CIK changes: they join nothing and stay holes (counted, listed); the file must hold exactly these, else refused
NOT_CHANGE = "NOT A CIK CHANGE"                                           # the words TV's note carries on those rows
PRED_CAL_PINNED = (os.path.join(EDGAR_DIR, "earnings_calendar_predecessors.csv"), "5a9c4142966c11067f990615473c2c36ba598376d0276b483194388f9215ba1a")     # [E20] the predecessors' releases (85 rows, the calendar's own columns: AVGO 10, MRVL 75), pinned by the sha256 of its BYTES
PRED_CAL = PRED_CAL_PINNED         # (path, sha256) read as ONE table with the calendar (the same accession in both refuses); None = the calendar alone (the selftest's default)
EDRIFT_JSON = os.environ.get("EDGELOG_EDRIFT_STAGEA", r"C:\EdgeLog\_anatomy_cache\rocfrontier\edrift_r1\edrift_stageA.json")     # the correlation with EDRIFT r1's cells (a report): its Stage A file's monthly nets
EDRIFT_CELLS = ("V3", "V5")
SPEC = {"pred_days": 364,        # [P] p = the acceptance date + 364 days (the same weekday), moved to the next session if it is not one
        "look_days": 400,        # a release counts at a rank r when it was accepted on r - 400 .. r - 1 (calendar days)
        "min_rel": 4,            # the universe: at least FOUR releases in that window (a known reporting rhythm)
        "pair_days": 50,         # [E3] two releases predicting dates less than 50 days apart: the LATER counts
        "side_usd": 200000.0, "name_cap": 10000.0, "min_side": 8,       # M: a side's dollars = min($200,000, $10,000 x its count) [E8], split equally; fewer than 8 names on a side = no trade
        "w_slot": 4000.0, "w_pre": 3, "w_post": 2,                      # W: $4,000 from the open of p - 3 sessions to the open of p + 2 sessions
        "beta_win": 252, "beta_need": 252,                              # [E9] / [E26] W's beta: OLS with an intercept over the 252 most recent sessions before the entry ON WHICH ES HAS A RETURN (reaching back past ES's own holes), the name's own return on ALL 252 (no zero fallback)
        "m_beta_need": 230,                                             # [E13] / [E26] M's ex-ante betas: CHOICE RESMOM's regression convention (>= 230 of the name's returns) over the 252 most recent ES-defined sessions to the rank close - every universe name has them by the universe's own rule
        "shift_lo": 27, "shift_hi": 36,                                 # [E11] the time-shift null: the whole window moves back by 27 .. 36 sessions, uniform, per event and draw
        "near": (3, 7),                                                 # [E5] precision: predicted dates within +-3 / +-7 sessions of an actual release
        "recall_stop": 0.80,                                            # [E5] recall below 80% in any WF July-June year: the run STOPS before any P&L
        "peak_names": 10,                                               # [E13] / [E14] a peak reporting week: at least 10 universe names with an actual release in it
        "path_lo": -10, "path_hi": 10,                                  # the event-time paths: sessions p - 10 .. p + 10 (and a - 10 .. a + 10 around the actual release)
        "dv_n": 20}                                                     # [E1] the class with the higher 20-session raw dollar volume (sessions before the fill) stays
RULES = {"m_reb": 60, "w_events": 500, "roc": 15.0, "pctl": 97.5, "years": 6, "best_pct": 1, "net_pos": True, "stress": True, "null": True, "ex2020": True, "exbest": True, "m_hedged": True,     # Stage A (a) - (e), (c) at p97.5 [E12], [E13]; booleans: switches only smoke() ever turns off
         "a2_roc": D15.RULES["a2_roc"], "a2_sort": D15.RULES["a2_sort"],                                                                                              # the old shadow-line bar (98.5005 / 3.816: the plain book's reported row)
         "b_m_reb": 10, "b_w_events": 100, "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1]}                                                                                 # Stage B: the leg's veto (CHOICE: W needs >= 100 events - DIVRUN's event-cell bar); the book add's reference, reported only
LIT = {"fl_spread_year": 0.07, "mgr_m_spread_month": (0.005, 0.006), "mgr_w_event_net": 0.005, "w_event_sd": 0.07, "mgr_w_events_year": 400}                       # [E7] the literature / MANAGER values the computed needs are printed beside
DD_DRAFT = (15000.0, 30000.0)            # [E7] CHOICE: M's need is computed at the draft's own drawdown range ($15,000 - 30,000 at $200,000 a side): no return is read before the P&L
POWER_SIMS, POWER_SEED = 400, 7          # [E7] W's need: the mean net per event at which the MEDIAN ROC @ $30k of 400 synthetic WF stretches (seeded normal events, no data) is 15
TILT_ROWS = (("2019-21", TS("2019-01-01"), TS("2021-12-31")), ("2022", TS("2022-01-01"), TS("2022-12-31")))     # [E10] the rows shown apart (CHOICE: calendar years)
SEASON_MONTHS = (1, 4, 7, 10)            # the reporting-season months (a diagnostic)
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / L do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = M17.HYG            # the four data-hygiene reasons [T2]
AUD = M17.AUD            # the tag of this harness's M rows in World.aud_hit (r17_resmom's: its unused_audit_rows reads it)
AUD_W = "EW"             # ... and of its W rows (entry session, name)
JUDGED = "close"         # [E16] MANAGER's hygiene edit S1: no in-hold event removes a name - flagged names and splits stay on the split-safe path - and a spin-off / stock-dividend ex-date inside the hold (W: inside the window) CLOSES the position at the official close of the session before it (r17_resmom's post_mode 'close'); the nulls read the same cut paths
REPORT_MODE = "keep"     # [E16] the removal reading ('keep': an announced split or a spin-off / stock-dividend ex-date inside the hold removes the name at the rank) - REPORTED beside the judged one with its count, null-less
LAB_J = "judged [E16] (no in-hold event removes a name: flagged names and splits on the split-safe path; a spin-off / stock-dividend ex-date inside the hold / window closes the position at the close before it)"
LAB_K = "the removal reading [E16] (an announced split or a spin-off / stock-dividend ex-date inside the hold / window removed the name at the rank; REPORTED, never the verdict)"
GO_FLAG, READ_FLAG = "eap_stageB_GO.flag", "eap_stageB_READ.flag"     # Stage B needs the lead's go-flag; the one-shot read flag is written (exclusively) after every load and check
TAIL = "(nothing computed, lockbox NOT read)"


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = M17.file_sha, M17.manifest_sha, M17.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): the file on disk AND the committed blob (git show HEAD:path) must both hash to PREREG_SHA (LF-normalised), else every stage refuses -
    r17_resmom's prereg_ok, with the committed blob REQUIRED (MANAGER: the harness refuses unless the file on disk and the committed blob both match; 'untracked' / no git refuse too)"""
    if not os.path.exists(PREREG):
        refuse(f"refused: PREREG_EAP_R1.txt is not next to this file - the spec cannot be verified {TAIL}")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse(f"refused: PREREG_EAP_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 {TAIL}")
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st != "match":
        refuse("refused: the COMMITTED PREREG_EAP_R1.txt " + {"differs": "differs from the registered sha - the file on disk is not the file in git", "untracked": "is not committed (git show HEAD:path finds no blob) - commit it first",
                                                                "unknown": "cannot be read (git is not available here) - the committed blob must be verified"}.get(st, st) + f" {TAIL}")
    print("prereg check: PREREG_EAP_R1.txt sha256 matches the registered one; the committed blob matches too")
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r17_resmom's / r18_divrun's / r19_edrift's and every harness they import numbers from + the pinned files' shas (wide calendar, earnings calendar and its [E20] predecessors' releases, map, members file, [E19]'s list) + the shared half-day list;
    Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    s7, s8 = M17.stamp(), DV.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r17_sha256": s7["harness_sha256"], "r18_sha256": s8["harness_sha256"], "r19_sha256": R11.sha_lf(ED.__file__), **{k: v for k, v in s7.items() if k != "harness_sha256"},
            "earnings_calendar_sha256": CAL_SHA, "map_sha256": MAP_SHA["map"], "map_add_sha256": MAP_SHA["map_add"], "members_sha256": file_sha(MEMBERS_CSV),
            "pred_list_sha256": None if PRED_LIST is None else PRED_LIST[1], "pred_calendar_sha256": None if PRED_CAL is None else PRED_CAL[1]}


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries (this file's) and r17_resmom.SPEC entries (the 252-session window, the 230 rule) for a block and put them back (the self-tests and the smoke shrink the windows; nothing stays patched)"""
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


def dstr(i):
    """a day number -> 'YYYY-MM-DD'"""
    return str(np.datetime64(int(i), "D"))


def yl(y):
    return f"{y}-{(y + 1) % 100:02d}"


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


# ------------------------------------------------------------------ [D1] the pinned earnings calendar + [E20] the predecessors' releases, ONE table, cut at read; [E2]
CAL_LABEL = {"calendar": "TV's EDGAR earnings calendar", "predecessors": "the [E20] predecessors' releases"}


def cal_file(key, path, sha, enforce):
    """one file of the calendar table -> (raw frame | None, info): refused - nothing computed, lockbox NOT read - (enforce) or reported, not read (the dryload) when it is not on file or its sha256 (of the BYTES) is not the registered one; refused when a column of CAL_COLS
    is missing"""
    lab = CAL_LABEL[key]
    if not os.path.exists(path):
        if enforce:
            refuse(f"refused: {lab} is not on file ({path}) {TAIL}")
        return None, {"present": False, "path": path, "label": lab}
    got = M17.sha_raw(path)
    if got != sha:
        if enforce:
            refuse(f"refused: {lab} {os.path.basename(path)} (sha256 {got}) is not the registered one ({sha}) - the file changed after it was registered {TAIL}")
        return None, {"present": True, "path": path, "sha256": got, "matches": False, "label": lab}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    miss = [c for c in CAL_COLS if c not in df.columns]
    if miss:
        refuse(f"refused: {lab} lacks the column(s) {miss} {TAIL}")
    return df, {"present": True, "path": path, "sha256": got, "matches": True, "label": lab, "rows_on_file": int(len(df))}


def cal_load(cut, path=None, enforce=True):
    """[D1] TV's EDGAR earnings calendar and [E20] the predecessors' releases (PRED_CAL; None = the calendar alone) read as ONE table -> (frame, info). enforce (Stage A / B, the smoke): refuses - nothing computed, lockbox NOT read - when a file is not on file, its sha256 (of the
    bytes) is not the registered one or a column of CAL_COLS is missing; not enforce (the dryload): a missing / other file is reported and the table is not read ((None, info)). [E20] a release present in BOTH files (the same accession) refuses the run (CHOICE: so does an
    accession twice in one file - none is on file - and the check reads the files whole, before the cut, so every stage sees the same refusal). Cut at READ time [E15]: a row ACCEPTED on / after the cut is dropped (CHOICE: a row whose reaction session is on / after the cut is
    dropped too - no date on / after the cut is held in memory; its acceptance is the last session before the cut and its prediction lies a year past the data); both are counted and the frame is asserted to hold none. accepted_et is New York wall-clock time (the house's
    fetch_edgar_calendar converted EDGAR's TRUE-UTC acceptance stamps with utc=True -> US/Eastern; MANAGER's review: the stamps cluster at 16:00 and 06-08:00 ET) - read as it stands, never shifted. A row whose acceptance stamp, reaction session or CIK cannot be read is dropped
    (counted). The frame: cik (10 digits), ticker (EDGAR's current), tickers (the row's ndx_tickers: every members-file ticker the company had), form, acc (the acceptance stamp), d (its DATE = the release date [P] reads; CHOICE: the New York calendar date of the acceptance
    stamp - 'accepted before the rank' = a date before the rank session's date, so a release accepted on the rank day itself waits for the next rank), rs (the reaction session = the ACTUAL [E5] reads), timing, accession, amend ([E2]: form 8-K/A), src (the file: 'calendar' /
    'predecessors')"""
    df, i0 = cal_file("calendar", path or CAL_CSV, CAL_SHA, enforce)
    if df is None:
        return None, i0
    parts, files = [df.assign(_src="calendar")], {"calendar": i0}
    if PRED_CAL is not None:
        dp, i1 = cal_file("predecessors", PRED_CAL[0], PRED_CAL[1], enforce)
        if dp is None:
            return None, i1
        parts.append(dp.assign(_src="predecessors"))
        files["predecessors"] = i1
    df = pd.concat(parts, ignore_index=True)
    accn = df["accession"].str.strip()
    dup = (accn != "") & accn.duplicated(keep=False)
    if dup.any():
        srcs = df.loc[dup, "_src"].groupby(accn[dup]).agg(lambda s: tuple(sorted(set(s))))
        both = sorted(a for a, s in srcs.items() if len(s) > 1)
        refuse("refused: " + (f"the same release (accession) is in both the calendar and the [E20] predecessors' releases ({both[:5]}) - a release counted twice" if both else
                               f"an accession is listed twice in one file ({sorted(srcs.index)[:5]}) - a release counted twice") + f" {TAIL}")
    acc = pd.to_datetime(df["accepted_et"].str.strip(), format="%Y-%m-%d %H:%M", errors="coerce")
    rs = pd.to_datetime(df["reaction_session"].str.strip(), format="%Y-%m-%d", errors="coerce")
    cik = df["cik"].str.strip().str.zfill(10)
    bad = (acc.isna() | rs.isna() | (df["cik"].str.strip() == "")).to_numpy()
    late_a = ~bad & (acc >= TS(cut)).to_numpy()
    late_r = ~bad & ~late_a & (rs >= TS(cut)).to_numpy()
    keep = ~bad & ~late_a & ~late_r
    form = df["form"].str.strip().to_numpy()
    fr = pd.DataFrame({"cik": cik.to_numpy()[keep], "ticker": df["ticker"].str.strip().to_numpy()[keep], "tickers": [[t.strip() for t in str(v).split(";") if t.strip()] for v in df["ndx_tickers"].to_numpy()[keep]],
                       "form": form[keep], "acc": acc.to_numpy()[keep], "rs": rs.to_numpy()[keep], "timing": df["timing"].str.strip().to_numpy()[keep], "accession": accn.to_numpy()[keep], "src": df["_src"].to_numpy()[keep]})
    fr["acc"], fr["rs"] = pd.to_datetime(fr["acc"]), pd.to_datetime(fr["rs"])
    fr["d"] = fr["acc"].dt.normalize()
    fr["amend"] = fr["form"] == AMEND_FORM
    assert_cut("earnings calendar (acceptance)", fr["acc"], cut)
    assert_cut("earnings calendar (reaction session)", fr["rs"], cut)
    srcv = df["_src"].to_numpy()
    for k_, v in files.items():
        v["rows_read"] = int((keep & (srcv == k_)).sum())
    y = fr["d"].dt.year.to_numpy()
    info = {"present": True, "path": i0["path"], "sha256": i0["sha256"], "matches": True, "label": i0["label"], "files": files, "cut": f"{TS(cut):%Y-%m-%d}", "rows_on_file": int(len(df)), "rows_read": int(keep.sum()), "unreadable": int(bad.sum()),
            "dropped_accepted_on_or_after_the_cut": int(late_a.sum()), "dropped_reaction_on_or_after_the_cut": int(late_r.sum()), "forms": {k: int(v) for k, v in Counter(fr["form"]).items()},
            "amendments_dropped_e2": int(fr["amend"].sum()), "first": f"{fr['d'].min():%Y-%m-%d}" if len(fr) else None, "last": f"{fr['d'].max():%Y-%m-%d}" if len(fr) else None,
            "releases_by_year": {int(k): int(v) for k, v in sorted(Counter(y[~fr["amend"].to_numpy()]).items())}, "amendments_by_year": {int(k): int(v) for k, v in sorted(Counter(y[fr["amend"].to_numpy()]).items())},
            "companies": int(fr["cik"].nunique()), "timing": {k: int(v) for k, v in Counter(fr["timing"]).items()}}
    return fr, info


# ------------------------------------------------------------------ NETISS's pinned symbol -> CIK map (read as one table), the members file, [E4]'s predecessor list
def check_pinned(key, files=None, shas=None):
    """the sha256 (of the BYTES) of one pinned map file: refuses - nothing computed, lockbox NOT read - when it is not on file or is another file than the registered one"""
    files, shas = files or MAP_FILES, shas or MAP_SHA
    p = files[key]
    if not os.path.exists(p):
        refuse(f"refused: the pinned {MAP_LABEL[key]} {p} is not on file {TAIL}")
    got = M17.sha_raw(p)
    if got != shas[key]:
        refuse(f"refused: {os.path.basename(p)} (sha256 {got}) is not the registered {MAP_LABEL[key]} ({shas[key]}) - the file changed after it was registered {TAIL}")
    return got


def load_map():
    """NETISS's symbol -> CIK map (its rules [A1] / [A8], read as a pattern - r21_netiss is not imported): the pinned base map (sha 19adc9ba) and TV's reviewed additions (sha 6bf8dfab) read as ONE map, each refused if its sha differs. Usable rows: the base map's
    current-ticker rows that passed TV's name check and its exact former-name rows, and the additions' reviewed rows (a CIK and the method reviewed_same_firm required); every other row (unmapped, ambiguous, mismatched, debenture / preferred / unit) joins
    nothing and is counted by its method. A symbol twice in one file refuses; a symbol with a usable row in BOTH files refuses (NETISS [A15]: an additions row over an unusable base row supersedes it). -> SimpleNamespace(df = one row per symbol: symbol, cik,
    method, source, usable; info = counts)"""
    shas = {k: check_pinned(k) for k in ("map", "map_add")}
    base = pd.read_csv(MAP_FILES["map"], dtype=str, keep_default_na=False)
    add = pd.read_csv(MAP_FILES["map_add"], dtype=str, keep_default_na=False)
    for nm, df in (("map", base), ("map_add", add)):
        miss = [c for c in MAP_COLS if c not in df.columns]
        if miss:
            refuse(f"refused: the {MAP_LABEL[nm]} lacks the column(s) {miss} {TAIL}")
        for c in MAP_COLS:
            df[c] = df[c].str.strip()
        dup = df["symbol"][df["symbol"].duplicated()].tolist()
        if dup:
            refuse(f"refused: the {MAP_LABEL[nm]} lists a symbol more than once ({dup[:5]}) {TAIL}")
    bad_add = add[(add["cik"] == "") | ~add["method"].isin(ADD_METHODS)]
    if len(bad_add):
        refuse(f"refused: the reviewed map additions hold a row without a CIK or with a method outside {list(ADD_METHODS)} ({bad_add['symbol'].tolist()[:5]}) {TAIL}")
    ub = (base["cik"] != "") & base["method"].isin(ALLOWED_METHODS)
    both = set(base["symbol"]) & set(add["symbol"])
    clash = sorted(s for s in both if bool(ub[base["symbol"] == s].iloc[0]))
    if clash:
        refuse(f"refused: the symbol(s) {clash[:5]} have a usable row in BOTH the pinned map and its reviewed additions - no silent overlap {TAIL}")
    keep = base[~base["symbol"].isin(both)].assign(source="base")
    df = pd.concat([keep, add.assign(source="additions")], ignore_index=True)[["symbol", "cik", "method", "source"]]
    df["usable"] = (df["cik"] != "") & df["method"].isin(ALLOWED_METHODS + ADD_METHODS)
    df["cik"] = np.where(df["usable"], df["cik"].str.zfill(10), "")
    info = {"sha256": shas, "base_rows": int(len(base)), "additions_rows": int(len(add)), "rows": int(len(df)), "by_method": dict(Counter(df["method"].tolist())), "usable_symbols": int(df["usable"].sum()),
            "usable_ciks": int(df.loc[df["usable"], "cik"].nunique())}
    return SimpleNamespace(df=df, info=info)


def members_load(cut, path=None):
    """[D2] tools/data/ndx_members.csv (ticker, from, to: month starts, `from` inclusive, `to` exclusive, '' = open; the tickers as the list printed them at the time - FB until 2022-06, PCLN until 2018-03 ...) -> (frame ticker / lo / hi, info). Refuses when the file is
    missing or a column is (the universe cannot be built without it). Cut at READ time: an interval that starts on / after the cut is dropped (counted) and the frame is asserted to hold none"""
    p = path or MEMBERS_CSV
    if not os.path.exists(p):
        refuse(f"refused: the Nasdaq-100 members file is not on file ({p}) {TAIL}")
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    if not {"ticker", "from", "to"} <= set(df.columns):
        refuse(f"refused: the Nasdaq-100 members file lacks a column of (ticker, from, to) {TAIL}")
    lo = pd.to_datetime(df["from"].str.strip(), errors="coerce")
    hi = pd.to_datetime(df["to"].str.strip().replace("", None), errors="coerce")
    if lo.isna().any():
        refuse(f"refused: the Nasdaq-100 members file has an unreadable 'from' date {TAIL}")
    keep = (lo < TS(cut)).to_numpy()
    fr = pd.DataFrame({"ticker": df["ticker"].str.strip().to_numpy()[keep], "lo": lo.to_numpy()[keep], "hi": hi.to_numpy()[keep]})
    assert_cut("Nasdaq-100 members file", fr["lo"], cut)
    return fr, {"path": p, "sha256_lf": R11.sha_lf(p), "rows_on_file": int(len(df)), "rows_read": int(keep.sum()), "tickers": int(fr["ticker"].nunique())}


def members_on(mem, month_start):
    """the tickers that were members on the 1st of a month (`from` <= m < `to`)"""
    m = TS(month_start)
    sel = (mem["lo"] <= m) & (mem["hi"].isna() | (mem["hi"] > m))
    return set(mem.loc[sel, "ticker"])


def pred_load(cut):
    """[E19] the [E4] predecessor-CIK list, PINNED (PRED_LIST = (path, sha256 of its bytes); None = not pinned: the run proceeds with the CIK-break name-months unjoined and says so) -> (frame of its real CIK changes | None, info). Refused - nothing computed, lockbox NOT read - when the
    file is missing, another file, lacks a column of PRED_COLS, names a symbol twice, or a row's content contradicts itself or the addendum. CHOICE (the rows told apart from the file's CONTENT): a REAL CIK CHANGE has a predecessor CIK that is not empty and is not its successor's,
    readable first_8k_date <= last_8k_date and an EDGAR source; a row whose predecessor CIK is empty or equals its successor's is NOT a CIK change - its note must say so ('NOT A CIK CHANGE'), and a change row's must not; any other row refuses. The changes must be exactly the
    addendum's (PRED_EXPECTED: AVGO <- 0001649338, FOX / FOXA <- 0001308161, MRVL <- 0001058057, CEG <- 0001168165) and the other rows exactly PRED_HOLES (TEAM, NXPI, DISH, SIRI: they join nothing - holes, counted and listed). The frame: symbol, pred, succ, lo / hi = the
    first / last 8-K dates (INCLUSIVE; the RELEASES joined - see release_table), name, source = edgar_source_url. Cut at read: a change whose first date is on / after the cut is dropped (counted) and a last date on / after it is clipped to the day before (CHOICE: no date on /
    after the cut is held; the releases after it are not read anyway)"""
    if PRED_LIST is None:
        return None, {"pinned": False, "joins": [], "holes": [], "text": "[E4] the predecessor-CIK list is NOT pinned: the CIK-break name-months (AVGO, FOX / FOXA, TEAM, NXPI, DISH, SIRI, MRVL, CEG ...) stay unjoined - they fall out by the four-releases rule and are counted (about 3% of member-months)"}
    path, sha = PRED_LIST
    if not os.path.exists(path):
        refuse(f"refused: the pinned [E19] predecessor-CIK list {path} is not on file {TAIL}")
    got = M17.sha_raw(path)
    if got != sha:
        refuse(f"refused: the [E19] predecessor-CIK list {os.path.basename(path)} (sha256 {got}) is not the pinned one ({sha}) {TAIL}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    miss = [c for c in PRED_COLS if c not in df.columns]
    if miss:
        refuse(f"refused: the [E19] predecessor-CIK list lacks the column(s) {miss} {TAIL}")
    df = pd.DataFrame({c: df[c].str.strip() for c in PRED_COLS})
    dup = sorted(set(df["symbol"][df["symbol"].duplicated()]))
    if dup:
        refuse(f"refused: the [E19] predecessor-CIK list names a symbol more than once ({dup}) {TAIL}")
    z10 = lambda v: v.zfill(10) if v else ""
    pc, sc = df["predecessor_cik"].map(z10), df["successor_cik"].map(z10)
    change = ((pc != "") & (pc != sc)).to_numpy()
    said = df["note"].str.upper().str.contains(NOT_CHANGE, regex=False).to_numpy()
    lo = pd.to_datetime(df["first_8k_date"], format="%Y-%m-%d", errors="coerce")
    hi = pd.to_datetime(df["last_8k_date"], format="%Y-%m-%d", errors="coerce")
    ok = np.where(change, ~said & lo.notna().to_numpy() & hi.notna().to_numpy() & (lo <= hi).to_numpy() & (df["edgar_source_url"] != "").to_numpy(), said) & (sc != "").to_numpy()
    if not ok.all():
        refuse(f"refused: the [E19] predecessor-CIK list has row(s) whose content does not say what they are ({df['symbol'][~ok].tolist()}): a CIK change needs a predecessor CIK other than its successor's, readable first <= last 8-K dates, an EDGAR source and no "
               f"'{NOT_CHANGE}' note; a row without one must carry that note; every row needs a successor CIK {TAIL}")
    got_j = {s: c for s, c, ch in zip(df["symbol"], pc, change) if ch}
    got_h = sorted(s for s, ch in zip(df["symbol"], change) if not ch)
    if got_j != PRED_EXPECTED or got_h != sorted(PRED_HOLES):
        refuse(f"refused: the [E19] list's CIK changes {got_j} and non-changes {got_h} are not the addendum's {PRED_EXPECTED} / {sorted(PRED_HOLES)} {TAIL}")
    keep = change & (lo < TS(cut)).to_numpy()
    clip = keep & (hi >= TS(cut)).to_numpy()
    hi_c = hi.where(hi < TS(cut), TS(cut) - pd.Timedelta(days=1))
    fr = pd.DataFrame({"symbol": df["symbol"].to_numpy()[keep], "pred": pc.to_numpy()[keep], "succ": sc.to_numpy()[keep], "lo": lo.to_numpy()[keep], "hi": hi_c.to_numpy()[keep], "name": df["predecessor_name"].to_numpy()[keep],
                       "source": df["edgar_source_url"].to_numpy()[keep], "clipped": clip[keep]})
    assert_cut("[E19] predecessor list (first 8-K)", fr["lo"], cut)
    assert_cut("[E19] predecessor list (last 8-K, clipped)", fr["hi"], cut)
    joins = [{"symbol": r.symbol, "predecessor_cik": r.pred, "successor_cik": r.succ, "predecessor_name": r.name, "first_8k_date": f"{TS(r.lo):%Y-%m-%d}", "last_8k_date_read": f"{TS(r.hi):%Y-%m-%d}", "clipped_at_the_cut": bool(r.clipped),
              "source": r.source} for r in fr.itertuples(index=False)]
    holes = [{"symbol": s, "successor_cik": c, "note": n} for s, c, n, ch in zip(df["symbol"], sc, df["note"], change) if not ch]
    text = (f"[E19] the [E4] predecessor-CIK list is pinned ({os.path.basename(path)} sha256 {got[:16]}...): {len(fr)} real CIK changes join their predecessor CIK's releases accepted inside [first_8k_date, last_8k_date] ("
            + ", ".join(f"{j['symbol']} <- {j['predecessor_cik']}" for j in joins) + f"); {len(holes)} rows are NOT CIK changes and join nothing - holes, counted and listed (" + ", ".join(h["symbol"] for h in holes) + ")")
    return fr, {"pinned": True, "path": path, "sha256": got, "rows": int(len(df)), "joins": joins, "holes": holes, "dropped_first_on_or_after_the_cut": int((change & ~keep).sum()), "clipped_at_the_cut": int(clip.sum()), "text": text}


def pred_check(calf, pred, mp, pinfo=None):
    """[E19] x [E20] x the map, read together - refused (nothing computed, lockbox NOT read) when they do not agree: a real CIK change's successor CIK must be the usable map CIK of its symbol (else its joined releases reach no column); every row of the predecessors' file ([E20])
    must be a release of a pinned predecessor CIK under that change's symbol (ticker = ndx_tickers = the member symbol); predecessors' releases without a pinned list refuse. -> pinfo with, per change, its predecessor CIK's releases in the table ([E2]'s 8-K/A apart): joined
    (inside the window) by file, their first / last dates, and those outside the window (not joined)"""
    pinfo = dict(pinfo or {})
    src = calf["src"].to_numpy().astype(str)
    pf = calf[src == "predecessors"]
    if pred is None:
        if len(pf):
            refuse(f"refused: the [E20] predecessors' releases are read but no [E19] predecessor-CIK list is pinned - they would join nothing {TAIL}")
        return pinfo
    dfm = mp.df.set_index("symbol")
    bad = [r.symbol for r in pred.itertuples(index=False) if not (r.symbol in dfm.index and bool(dfm.loc[r.symbol, "usable"]) and str(dfm.loc[r.symbol, "cik"]) == r.succ)]
    if bad:
        refuse(f"refused: the [E19] change(s) {bad} name a successor CIK that is not the symbol's usable CIK in the pinned map - the joined releases would reach no column {TAIL}")
    pairs = {(r.pred, r.symbol) for r in pred.itertuples(index=False)}
    stray = sorted({f"{t} {c}" for c, t, ts in zip(pf["cik"], pf["ticker"], pf["tickers"]) if (c, t) not in pairs or list(ts) != [t]})
    if stray:
        refuse(f"refused: the [E20] predecessors' releases hold rows that are not a pinned [E19] predecessor's releases under its member symbol ({stray[:5]}) {TAIL}")
    joins = []
    for jn, r in zip(pinfo.get("joins", []), pred.itertuples(index=False)):
        m = (calf["cik"] == r.pred).to_numpy() & ~calf["amend"].to_numpy(bool)
        ins = m & (calf["d"] >= TS(r.lo)).to_numpy() & (calf["d"] <= TS(r.hi)).to_numpy()
        dd = calf["d"][ins]
        joins.append({**jn, "releases_joined": int(ins.sum()), "from_calendar": int((ins & (src == "calendar")).sum()), "from_predecessors_file": int((ins & (src == "predecessors")).sum()), "outside_the_window": int((m & ~ins).sum()),
                      "first": f"{dd.min():%Y-%m-%d}" if len(dd) else None, "last": f"{dd.max():%Y-%m-%d}" if len(dd) else None})
    pinfo["joins"] = joins
    return pinfo


# ------------------------------------------------------------------ [E10] the house's NQ continuous masters (read only), found the way the ES masters are
def master_sha(meta):
    """the sha256 of a master's file as it lies in the house's uploads folder (None when it is not on disk - the smoke's fake masters)"""
    try:
        from augur_engine.paths import UPLOADS
        p = os.path.join(UPLOADS, str(meta.get("filename")))
        return M17.sha_raw(p) if os.path.isfile(p) else None
    except Exception:
        return None


def load_nq(t_end):
    """[E10] the NQ 5m RTH masters (r13_attn.load_nq: the unadjusted and the roll-corrected one, found through augur_engine.data's registry exactly as r15_ddw.load_es finds ES's, every bar cut BEFORE t_end and asserted) -> ({'raw', 'adj'} frames, meta with the
    file name and the sha256 of each file)"""
    fr, meta = A13.load_nq(t_end)
    for tag in meta:
        meta[tag]["sha256"] = master_sha(meta[tag])
    return fr, meta


def nq_returns(days, frames):
    """[E10] NQ's close-to-close return on the stock sessions, r15_ddw.es_series' arithmetic: (roll-corrected 16:00 change) / the prior UNADJUSTED 16:00 print; NaN where a print is missing"""
    pa, pr = D15.es_prints(frames["adj"]), D15.es_prints(frames["raw"])
    a, r = pa["close"].reindex(days).to_numpy(float), pr["close"].reindex(days).to_numpy(float)
    ret = np.full(len(days), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        ret[1:] = (a[1:] - a[:-1]) / r[:-1]
    return ret


def es_open_prints(W, es_frames):
    """the ES prints the W hedge (and M's [E13] hedge) trades at, on the stock sessions: the 09:30 print = the OPEN of the 09:30 bar (r13_attn.nq_prints: no 09:30 bar -> the open of the first bar before 10:00) beside the 16:00 print (W.es.c16a / c16r), roll-corrected
    (P&L) and unadjusted (the level the notional is counted on). CHOICE: W enters at the official open, so its hedge trades at ES's 09:30 print and is marked at the 16:00 prints (DIVRUN's entered at the close). CHOICE: the four prints of a session are one chronological sequence (open, close) and a missing print CARRIES the last one (DIVRUN's carry: no hedge change there, the move over a hole is earned at the
    next print). -> W.eso_a, W.esc_a, W.eso_r, W.esc_r (T,), and the counts of carried prints"""
    T = W.T
    oa, orw = A13.nq_prints(es_frames["adj"])["open"].reindex(W.days).to_numpy(float), A13.nq_prints(es_frames["raw"])["open"].reindex(W.days).to_numpy(float)
    ca, cr = np.asarray(W.es.c16a, float), np.asarray(W.es.c16r, float)
    out = {}
    for tag, o_, c_ in (("a", oa, ca), ("r", orw, cr)):
        seq = np.empty(2 * T)
        seq[0::2], seq[1::2] = o_, c_
        bad = ~(np.isfinite(seq) & (seq > 0))
        filled = pd.Series(np.where(bad, np.nan, seq)).ffill().to_numpy()
        out[tag] = (filled[0::2], filled[1::2], int(bad[0::2].sum()), int(bad[1::2].sum()))
    W.eso_a, W.esc_a, W.eso_r, W.esc_r = out["a"][0], out["a"][1], out["r"][0], out["r"][1]
    W.es_carried = {"open_prints_carried_adj": out["a"][2], "close_prints_carried_adj": out["a"][3], "open_prints_carried_raw": out["r"][2], "close_prints_carried_raw": out["r"][3]}
    return W


# ------------------------------------------------------------------ the release table [P] reads: [E2], [E4], the [E3] pair rule (point in time), the 364-day prediction, the actual releases
BIG = 10 ** 9                                                            # 'no next release' (a day number no date reaches)


def release_table(calf, days, pred=None):
    """the releases of the calendar as [P] reads them, on the session list `days` -> SimpleNamespace of arrays sorted by (cik, acceptance stamp, accession): cik, ticker, d (the acceptance DATE as a day number), rs (the reaction session, day number),
    accession, pred (True = a predecessor CIK's release re-keyed to its successor by [E4]'s pinned list), nx (the NEXT release's day of the same CIK; BIG for the last), p_day = d + 364, p_row (the first session on / after p_day; -1 past the data), rs_row (the
    reaction session's row; a date that is not a session moves to the next one, -1 past the data), drop_h ([E3] with hindsight: a later release of the same CIK less than 50 days after it), span = {cik: (start, end)} and the counts. [E2] the 8-K/A rows are not in it
    (counted by the loader). [E19] a REAL CIK CHANGE of the pinned list adds its predecessor CIK's releases ACCEPTED on first_8k_date .. last_8k_date (inclusive) to its successor's list, read at every rank - CHOICE: the window bounds the RELEASES joined (it is the
    predecessor's own 8-K span), so after the change a successor's 400-day look-back keeps reading the predecessor's last releases and [P]'s prediction runs on across the change (the member-month reading - joined only at ranks whose month lies inside the window, which
    leaves a hole of up to a year after each change - is REPORTED in the pre-P&L [E19] block, never used); the predecessor's own rows stay under its own CIK (no World column carries it); a release two rows join to one successor (FOX and FOXA: 21CF's CIK) is added once.
    CHOICE: the pair gap is measured on the acceptance dates - d2 - d1 is exactly the gap of the unsnapped predicted dates (p = d + 364 for both), so it never depends on the session calendar; two releases on one day pair (gap 0) and the one accepted later counts; the [E3]
    rule reads the successor's joined list (a predecessor release less than 50 days before the successor's first counts only until that one is known)"""
    rel = calf[~calf["amend"].to_numpy(bool)].copy()
    rel["pred"] = False
    n_pred = 0
    if pred is not None and len(pred):
        add = []
        for p_ in pred.itertuples(index=False):
            m = (rel["cik"] == p_.pred) & (rel["d"] >= TS(p_.lo)) & (rel["d"] <= TS(p_.hi)) & ~rel["pred"]
            if m.any():
                add.append(rel[m].assign(cik=p_.succ, pred=True))
        if add:
            extra = pd.concat(add, ignore_index=True).drop_duplicates(["cik", "accession"])
            n_pred = int(len(extra))
            rel = pd.concat([rel, extra], ignore_index=True)
    rel = rel.sort_values(["cik", "acc", "accession"], kind="mergesort").reset_index(drop=True)
    dv = day_i(pd.DatetimeIndex(days))
    d = day_i(rel["d"]) if len(rel) else np.zeros(0, np.int64)
    rs = day_i(rel["rs"]) if len(rel) else np.zeros(0, np.int64)
    ck = rel["cik"].to_numpy().astype(str)
    nx = np.full(len(rel), BIG, np.int64)
    same = (ck[1:] == ck[:-1]) if len(ck) > 1 else np.zeros(0, bool)
    nx[:-1][same] = d[1:][same]
    p_day = d + SPEC["pred_days"]
    first = dv[0] if len(dv) else BIG
    p_row = np.searchsorted(dv, p_day, side="left")
    p_row = np.where((p_row >= len(dv)) | (p_day < first), -1, p_row)                 # CHOICE: a date before the World's first session has no row (-1), like one past its last
    rs_row = np.searchsorted(dv, rs, side="left")
    rs_exact = np.isin(rs, dv)
    rs_row = np.where((rs_row >= len(dv)) | (rs < first), -1, rs_row)
    span = {}
    if len(ck):
        starts = np.flatnonzero(np.r_[True, ck[1:] != ck[:-1]])
        ends = np.r_[starts[1:], len(ck)]
        span = {ck[a]: (int(a), int(b)) for a, b in zip(starts, ends)}
    tick = rel["ticker"].to_numpy().astype(str)
    drop_h = (nx - d) < SPEC["pair_days"]
    return SimpleNamespace(n=int(len(rel)), cik=ck, ticker=tick, d=d, rs=rs, accession=rel["accession"].to_numpy().astype(str), pred=rel["pred"].to_numpy(bool), nx=nx, p_day=p_day, p_row=p_row.astype(np.int64),
                           rs_row=rs_row.astype(np.int64), rs_exact=rs_exact, drop_h=drop_h, span=span, timing=rel["timing"].to_numpy().astype(str), n_pred_rows=n_pred)


def kept_at(rt, a, b, R):
    """[E3] CHOICE: the pair rule POINT IN TIME at the rank day R (a day number): the releases a .. b-1 (one CIK's) KNOWN at the rank (accepted on or before R - 1) that COUNT - a release is dropped when a later release of the same CIK, itself known at the rank, lies less than 50 days after it
    (the LATER release counts; a pre-announcement whose real release is not out yet still counts at that rank) -> bool (b - a,)"""
    d, nx = rt.d[a:b], rt.nx[a:b]
    return (d <= R - 1) & ~(((nx - d) < SPEC["pair_days"]) & (nx <= R - 1))


def pairs_list(rt):
    """[E3] every pair of releases of one CIK less than 50 days apart (with hindsight: both in the calendar as read) -> [{ticker, cik, earlier, later, gap_days, joined}] (the earlier one never counts once the later one is known; joined = the earlier is a predecessor's
    release [E19] joined to its successor - its own CIK's list holds the pair again when the later is the predecessor's too)"""
    out = []
    for i in np.flatnonzero(rt.drop_h):
        out.append({"ticker": str(rt.ticker[i]), "cik": str(rt.cik[i]), "earlier": dstr(rt.d[i]), "later": dstr(rt.nx[i]), "gap_days": int(rt.nx[i] - rt.d[i]), "joined": bool(rt.pred[i])})
    return out


# ------------------------------------------------------------------ the World's EAP arrays: the CIK join, the point-in-time membership, the universe per rank, the DUE lists, W's event candidates
JOIN_TEXT = {"joined": "joined (a usable map row with a CIK)", "not_in_map": "symbol not in the map", "map_unmapped": "map: unmapped", "map_name_ambiguous": "map: name ambiguous", "map_current_ticker_name_mismatch": "map: current ticker, name does not agree",
             "map_non_common": "map: debenture / preferred / unit"}
UNI_REASONS = ("short_history", "no_es_pairs", "not_member", "not_joined", "no_release", "few_releases", "second_class")
UNI_TEXT = {"short_history": "under 230 split-safe returns in the 252 sessions", "no_es_pairs": "under 230 ES pairs", "not_member": "not a Nasdaq-100 member on the 1st of the rank's month", "not_joined": "no CIK join (the map)",
            "no_release": "no release accepted before the rank (foreign 6-K filer / no 8-K item 2.02)", "few_releases": "fewer than four releases in the 400 days before the rank", "second_class": "[E1] the other share class of the CIK has the higher dollar volume"}


def _cum(a, dt=np.int32):
    return DV._cum(a, dt)


def win_n(cum, r, win):
    """rows r-win+1 .. r of a running count (T + 1, S) -> (S,)"""
    return cum[r + 1] - cum[max(r - win + 1, 0)]


def join_codes(syms, mp):
    """the CIK of every World column through NETISS's map (usable rows only) and the join code ('joined' / 'not_in_map' / 'map_<method>') -> (cik per column, '' = none; code per column)"""
    df = mp.df.set_index("symbol")
    ciks, codes = [], []
    for s in np.asarray(syms).astype(str):
        if s not in df.index:
            ciks.append("")
            codes.append("not_in_map")
            continue
        row = df.loc[s]
        if bool(row["usable"]):
            ciks.append(str(row["cik"]))
            codes.append("joined")
        else:
            ciks.append("")
            codes.append(f"map_{row['method'] or 'blank'}")
    return np.asarray(ciks, dtype=object), np.asarray(codes, dtype=object)


def ndx_by_cik(calf):
    """every members-file ticker each CIK had (the union of the calendar's ndx_tickers over its rows) -> {cik: set}; and the set of every ticker the calendar names"""
    by = defaultdict(set)
    for c, ts in zip(calf["cik"].to_numpy(), calf["tickers"]):
        by[str(c)].update(ts)
    return dict(by), set().union(*by.values()) if by else set()


def member_matrix(W, mem, months, cikcol, ndx):
    """the point-in-time Nasdaq-100 membership of every World column on the 1st of each month in `months`: (n_months, S) bool. CHOICE: a column is a member when its own symbol is on the month's list, or when a ticker on the list is NOT a symbol of the World and the
    calendar names it among the ndx_tickers of the column's CIK (a renamed member: FB -> META, PCLN -> BKNG, DISCA -> WBD - the cache carries the current symbol); a ticker that is a World symbol only ever stands for itself (GOOG / GOOGL are two members, two columns)"""
    syms = np.asarray(W.syms).astype(str)
    col_of = {s: j for j, s in enumerate(syms)}
    by_cik = defaultdict(list)
    for j, c in enumerate(cikcol):
        if c:
            by_cik[str(c)].append(j)
    alias = defaultdict(set)                                                     # a members-file ticker that is not a World symbol -> the World columns of the CIK(s) whose ndx_tickers name it
    for c, ts in ndx.items():
        for t in ts:
            if t not in col_of:
                alias[t].update(by_cik.get(c, ()))
    out = np.zeros((len(months), W.S), bool)
    for q, m in enumerate(months):
        for t in members_on(mem, m):
            if t in col_of:
                out[q, col_of[t]] = True
            for j in alias.get(t, ()):
                out[q, j] = True
    return out, dict(alias)


def attach_eap(W, calf, mp, mem, pred=None, counts_only=False):
    """everything the cells read besides the World's own arrays -> W.ea: the release table (on the World's sessions), each column's CIK and join code, the CIK -> members-file tickers, the membership on the 1st of every rank's month, the running counts of
    split-safe returns / ES pairs, the 20-session raw dollar volume [E1], the rolling 252-session OLS beta of every name on ES (counts_only: the pair counts only - the dryload computes no regression), the ranks (r17_resmom's month-end schedule), and per rank the
    universe, its first-reason counts, [E1]'s dropped classes and the DUE flags; the W event candidates. The audit's data events (none until apply_audit). [E26] the betas are read over the sessions on which ES has a return (ea.es_idx; ea.cfc = each name's running count of
    its own returns over them; ea.beta row q = the slope over the 252 ES-defined sessions es_idx[q - 251] .. es_idx[q])"""
    T, S_ = W.T, W.S
    ea = SimpleNamespace(counts_only=bool(counts_only), pred=pred)
    ea.rt = release_table(calf, W.days, pred)
    ea.cik, ea.join = join_codes(W.syms, mp)
    ea.ndx, ea.cal_tickers = ndx_by_cik(calf)
    ea.has_rel = np.array([bool(c) and c in ea.rt.span for c in ea.cik], bool)
    win = M17.SPEC["win"]
    fin = np.isfinite(np.asarray(W.Rd, float))
    esok = np.isfinite(np.asarray(W.es.ret, float))
    ea.cret = _cum(fin)
    ea.cpair = _cum(fin & esok[:, None])
    ea.ces = np.r_[0, np.cumsum(esok)].astype(np.int64)
    with np.errstate(invalid="ignore"):
        ea.dv20 = D15.roll_prev(np.asarray(W.Cl, float) * np.asarray(W.Vv, float), SPEC["dv_n"])
    ea.es_idx = np.flatnonzero(esok)                                             # [E26] the sessions on which ES has a return: every beta window counts 252 of THESE, reaching back past ES's own holes
    ea.cfc = _cum(fin[ea.es_idx])                                                # each name's running count of its own returns over them
    if counts_only:
        ea.beta = None
    else:
        Wc = SimpleNamespace(Rd=np.asarray(W.Rd, float)[ea.es_idx], es=SimpleNamespace(ret=np.asarray(W.es.ret, float)[ea.es_idx]))
        with DV.spec(win=SPEC["beta_win"], min_pairs=1):
            ea.beta = DV.rolling_beta(Wc)[0]                                     # row q: the slope over the ES-defined sessions es_idx[q-251] .. es_idx[q] (NaN under 1 pair / no ES variation); the thresholds are applied where it is read
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    keep = r_all >= win - 1                                                      # a rank needs a full 252-session window (the 230 rule's): earlier ranks are warm-up
    ea.r, ea.f, ea.x = r_all[keep], f_all[keep], x_all[keep]
    ea.r_next = np.r_[ea.r[1:], T - 1] if len(ea.r) else np.zeros(0, np.int64)  # the last session of the next month: the DUE window r + 1 .. r_next, W's entries r + 1 .. r_next
    ea.n_warm = int((~keep).sum())
    ea.months = [f"{W.days[r]:%Y-%m}-01" for r in ea.r]                          # CHOICE: 'the 1st of the rank's month' = the 1st of the month the rank session r is in (the list in force at the rank)
    ea.member, ea.alias = member_matrix(W, mem, ea.months, ea.cik, ea.ndx)
    ea.mem = mem
    W.ea = ea
    if getattr(W, "audw", None) is None or W.audw.shape != (T, S_):
        W.audw = np.zeros((T, S_), bool)                                         # the hand audit's W data events (entry session, name): apply_audit sets them
    ranks_build(W)
    ea.cand = w_candidates(W)
    return ea


def universe_rank(W, k):
    """the universe at rank k (the month-end rank r, the fill f = r + 1), only information known before the fill: RESMOM's liquidity screen (r15_ddw's universe at f: prior raw close >= $10, top 500 by 20-session raw dollar volume, volume >= 1M shares, ATR > $0.50, no
    registered split in the 14 sessions before f), >= 230 split-safe returns AND >= 230 ES pairs in the 252 sessions r-251 .. r, a Nasdaq-100 member on the 1st of the rank's month, a CIK join, and at least FOUR releases ([E2] / [E3] point in time) accepted on
    r - 400 .. r - 1; then [E1] ONE LISTING PER CIK: of the names that pass everything else and share a CIK only the class with the higher 20-session raw dollar volume (rows f-20 .. f-1) stays (CHOICE: a tie goes to the lower symbol; an undefined volume ranks last).
    CHOICE: no pre-rank hygiene removal - the signal reads no price (the flags inside the hold / window are [E16]'s; the flagged names in the window are counted, a report); CHOICE: the open at the fill is M's (a name M cannot fill is counted there), not the
    universe's - W enters at its own open. -> (columns, reasons {label: count of first reasons}, first-reason code per base column, [E1]'s (dropped, kept) column pairs, the per-column kept-release counts, the base columns)"""
    ea = W.ea
    s = M17.SPEC
    r, f = int(ea.r[k]), int(ea.f[k])
    R = int(day_i(W.days[r]))
    base = np.flatnonzero(W.U[f])
    n_ret, n_pair = win_n(ea.cret, r, s["win"])[base], win_n(ea.cpair, r, s["win"])[base]
    short_h = n_ret < s["min_n"]
    no_es = ~short_h & (n_pair < s["min_n"])
    not_mem = ~ea.member[k, base]
    joined = np.array([bool(ea.cik[j]) for j in base], bool)
    nrel = np.zeros(len(base), np.int64)
    nany = np.zeros(len(base), np.int64)
    for q, j in enumerate(base):
        if joined[q] and ea.cik[j] in ea.rt.span:
            a, b = ea.rt.span[ea.cik[j]]
            kk = kept_at(ea.rt, a, b, R)
            nany[q] = int(kk.sum())
            nrel[q] = int((kk & (ea.rt.d[a:b] >= R - SPEC["look_days"])).sum())
    reasons = [("short_history", short_h), ("no_es_pairs", no_es), ("not_member", not_mem), ("not_joined", ~joined), ("no_release", nany == 0), ("few_releases", nrel < SPEC["min_rel"])]
    first = D15.attribute(reasons, len(base))
    ok = first < 0
    dropped = []
    cand = base[ok]
    if len(cand) > 1:
        ck = np.asarray([ea.cik[j] for j in cand])
        for c in np.unique(ck):
            m = cand[ck == c]
            if len(m) < 2:
                continue
            dv = ea.dv20[f, m]
            rk = [(-float(dv[q]) if np.isfinite(dv[q]) else math.inf, str(W.syms[m[q]])) for q in range(len(m))]
            win_ = m[min(range(len(m)), key=rk.__getitem__)]
            for j in m:
                if j != win_:
                    dropped.append((int(j), int(win_)))
    second = np.isin(base, [d_ for d_, _k in dropped])
    first = np.where(ok & second, len(reasons), first)
    cnt = Counter({lab: int((first == q).sum()) for q, (lab, _) in enumerate(reasons)})
    cnt["second_class"] = int(second.sum())
    cnt["liquidity"] = int(len(base))
    uni = base[first < 0]
    cnt["universe"] = int(len(uni))
    return uni, cnt, first, dropped, dict(zip(base.tolist(), nrel.tolist())), base


def ranks_build(W):
    """every rank's universe, counts, [E1] drops and DUE flags (W.ea.uni / cnt / drops / due / nrel), and the DUE predicted dates (W.ea.due_p: per rank, (column, release) pairs with p in the window). DUE: a universe name with a release COUNTED at the rank
    ([E3] point in time) whose predicted session p falls in r + 1 .. the next month's last session"""
    ea = W.ea
    ea.uni, ea.cnt, ea.drops, ea.due, ea.due_p, ea.first, ea.nrel, ea.base = [], [], [], [], [], [], [], []
    for k in range(len(ea.r)):
        uni, cnt, first, dropped, nrel, base = universe_rank(W, k)
        r, rn = int(ea.r[k]), int(ea.r_next[k])
        R = int(day_i(W.days[r]))
        due, dp = np.zeros(len(uni), bool), []
        for q, j in enumerate(uni):
            a, b = ea.rt.span[ea.cik[j]]
            kk = kept_at(ea.rt, a, b, R)
            pr = ea.rt.p_row[a:b]
            hit = np.flatnonzero(kk & (pr >= r + 1) & (pr <= rn))
            due[q] = len(hit) > 0
            dp.extend((int(j), int(a + i)) for i in hit)
        ea.uni.append(uni)
        ea.cnt.append(cnt)
        ea.drops.append(dropped)
        ea.due.append(due)
        ea.due_p.append(dp)
        ea.first.append(first)
        ea.nrel.append(nrel)
        ea.base.append(base)


def rank_of_row(W, t):
    """the rank before session t: the index k of the last month-end rank with r < t (t in r + 1 .. r_next); -1 before the first built rank"""
    k = int(np.searchsorted(W.ea.r, t, side="left")) - 1
    return k if k >= 0 and t <= W.ea.r_next[k] else -1


def w_candidates(W):
    """W's event candidates: for every rank k, every universe name and every release COUNTED at the rank ([E3] point in time) whose entry session e = p - 3 sessions falls in r + 1 .. r_next (so the universe is the one 'at the rank before the entry') ->
    SimpleNamespace of arrays (k, col, rel, p, e, x = p + 2; x = -1 when p + 2 is past the data's last session: unresolved). CHOICE: each predicted date belongs to exactly one rank - the one before its entry (the DUE window r + 1 .. r_next holds the entry e = p - 3)"""
    ea = W.ea
    out = defaultdict(list)
    pre, post = SPEC["w_pre"], SPEC["w_post"]
    for k in range(len(ea.r)):
        r, rn = int(ea.r[k]), int(ea.r_next[k])
        R = int(day_i(W.days[r]))
        for j in ea.uni[k]:
            a, b = ea.rt.span[ea.cik[j]]
            kk = kept_at(ea.rt, a, b, R)
            pr = ea.rt.p_row[a:b]
            e = pr - pre
            for i in np.flatnonzero(kk & (pr >= 0) & (e >= r + 1) & (e <= rn)):
                p = int(pr[i])
                out["k"].append(k)
                out["col"].append(int(j))
                out["rel"].append(int(a + i))
                out["p"].append(p)
                out["e"].append(p - pre)
                out["x"].append(p + post if p + post <= W.T - 1 else -1)
    g = lambda key: np.asarray(out[key], np.int64)
    return SimpleNamespace(n=len(out["k"]), k=g("k"), col=g("col"), rel=g("rel"), p=g("p"), e=g("e"), x=g("x"))


def es_window(W, t_end):
    """[E26] the beta window ending at row t_end (arrays, inclusive): the 252 (SPEC beta_win) most recent sessions at or before t_end ON WHICH ES HAS A RETURN - it reaches back past ES's own missing sessions and the count stays 252 -> (q = the index of its last
    session in ea.es_idx, ok = 252 such sessions exist, reached = the window spans more than 252 sessions: it reached back past an ES hole)"""
    ea = W.ea
    win = SPEC["beta_win"]
    t_end = np.atleast_1d(np.asarray(t_end, np.int64))
    q = ea.ces[np.clip(t_end + 1, 0, len(ea.ces) - 1)] - 1
    ok = (t_end >= 0) & (q >= win - 1)
    if len(ea.es_idx) < win:
        return q, np.zeros(len(q), bool), np.zeros(len(q), bool)
    first = ea.es_idx[np.clip(q - win + 1, 0, len(ea.es_idx) - 1)]
    return q, ok, ok & (t_end - first + 1 > win)


def win_pairs(W, q, ok, col):
    """[E26] each name's own returns over the 252 ES-defined sessions of the window ending at index q of ea.es_idx (0 where the window does not exist)"""
    ea = W.ea
    win = SPEC["beta_win"]
    if len(ea.es_idx) < win:
        return np.zeros(len(q), np.int64)
    qq = np.where(ok, q, win - 1)
    return np.where(ok, ea.cfc[qq + 1, col] - ea.cfc[qq + 1 - win, col], 0).astype(np.int64)


def w_beta(W, e, col):
    """[E9] / [E26] the ex-ante hedge beta of names `col` at entries `e` (arrays): the OLS slope (with an intercept) of the name's split-safe TOTAL daily return (r17_resmom's W.Rd) on ES's over the 252 most recent sessions BEFORE the entry (rows <= e - 1: the entry is
    at the open of e) ON WHICH ES HAS A RETURN - ES's own missing sessions are skipped and the window reaches back past them [E26] - with the name's OWN return on every one of them: a name with fewer (230 - 251 included) is no event, no zero-beta fallback ->
    (beta (NaN where the rule fails), the name's returns over the window, reached = the window reached back past an ES hole)"""
    ea = W.ea
    e, col = np.atleast_1d(np.asarray(e, np.int64)), np.atleast_1d(np.asarray(col, np.int64))
    q, ok, reached = es_window(W, e - 1)
    npair = win_pairs(W, q, ok, col)
    good = ok & (npair >= SPEC["beta_need"])
    b = np.full(len(e), np.nan)
    if ea.beta is not None and good.any():
        b[good] = ea.beta[q[good], col[good]]
    return b, npair, reached


def m_betas(W, r, cols):
    """[E13] / [E26] the names' ex-ante ES betas at the rank close r: the OLS slope over the 252 most recent sessions to the rank (r included) ON WHICH ES HAS A RETURN (RESMOM's regression window, reaching back past ES's own holes - [E26]); CHOICE: >= 230 of the name's
    own returns among them (CHOICE 1's count: [E26] moves the window, not the count; every universe name has them by the universe's rule) -> (n,) (NaN under 230)"""
    ea = W.ea
    cols = np.atleast_1d(np.asarray(cols, np.int64))
    q, ok, _ = es_window(W, np.full(len(cols), int(r)))
    n = win_pairs(W, q, ok, cols)
    good = ok & (n >= SPEC["m_beta_need"])
    b = np.full(len(cols), np.nan)
    if ea.beta is not None and good.any():
        b[good] = ea.beta[q[good], cols[good]]
    return b


# ------------------------------------------------------------------ the ES hedge paths (W's hedge, M's [E13] hedge)
def hedge_paths(W, e, x, beta, close=None, bps=HEDGE_BPS):
    """the ES hedge of positions held from the OPEN of e to the OPEN of x (all windows of one length H = x - e + 1), per $1 of the stock's entry notional (pass beta = the hedge's $ notional to get dollars): short beta x $1 of ES at the 09:30 print of e (the contracts
    are counted on the unadjusted print, the P&L runs on the roll-corrected one: DIVRUN's exact hedge), marked at every 16:00 print of rows e .. x-1, bought back at the 09:30 print of x; 0.5 bps a side of the hedge's notional at the entry and of its value at the
    exit. close = [E16] the stock's close row per position (-1 = held to x): CHOICE the hedge is lifted with the stock, at the 16:00 print of that row - nothing after it, the exit cost there. A missing print carries the last one (es_open_prints). -> (n, H)"""
    e, x, beta = np.asarray(e, np.int64), np.asarray(x, np.int64), np.asarray(beta, float)
    n = len(e)
    if not n:
        return np.zeros((0, 0))
    H = int(x[0] - e[0] + 1)
    assert (x - e + 1 == H).all(), "one window length per call"
    q = np.empty((n, H + 1))
    q[:, 0] = W.eso_a[e]
    if H > 1:
        q[:, 1:H] = W.esc_a[e[:, None] + np.arange(H - 1)[None, :]]
    q[:, H] = W.eso_a[x]
    lvl = W.eso_r[e]
    with np.errstate(invalid="ignore", divide="ignore"):
        P = -beta[:, None] * np.diff(q, axis=1) / lvl[:, None]
    xc = np.full(n, H - 1, np.int64)
    ext = W.eso_r[x].copy()
    if close is not None:
        c = np.asarray(close, np.int64)
        m = c >= 0
        if ((c[m] < e[m]) | (c[m] > x[m] - 1)).any():
            raise ValueError("[E16] a close row must lie in e .. x-1")
        xc = np.where(m, c - e, H - 1)
        P = np.where(np.arange(H)[None, :] > xc[:, None], 0.0, P)
        ext = np.where(m, W.esc_r[np.where(m, c, 0)], ext)
    with np.errstate(invalid="ignore", divide="ignore"):
        P[:, 0] -= bps * 1e-4 * np.abs(beta)
        P[np.arange(n), xc] -= bps * 1e-4 * np.abs(beta) * ext / lvl
    return np.nan_to_num(P, nan=0.0)


def close_rows(W, f, x, cols, mode):
    """[E16] the judged reading's close row of each position held from the open of f to the open of x: the session before its FIRST spin-off / stock-dividend ex-date e in f < e <= x (the fill session's own is bought ex; the exit session's is inside), -1 = held to x
    (r17_resmom's rm_one 'close' rule); every other reading holds to x"""
    cols = np.asarray(cols, np.int64)
    out = np.full(len(cols), -1, np.int64)
    if mode != "close" or x <= f or not len(cols):
        return out
    sp = W.SPN[f + 1:x + 1][:, cols]
    return np.where(sp.any(axis=0), f + sp.argmax(axis=0), -1).astype(np.int64)


def in_hold(W, f, x, cols):
    """the hold's events per position (rows f+1 .. x): the four hygiene flags (r15's, rows f .. x as r17_resmom reads them: the fill session through the exit), a spin-off / stock-dividend ex-date, a calendar (announced) split ex-date -> (post (4, n), spin (n,), csplit (n,))"""
    cols = np.asarray(cols, np.int64)
    post = W.hyg(f, x, cols)
    sp = M17.spn_hit(W, f + 1, x, cols)
    cs = M17.csplit_hit(W, f + 1, x, cols) if getattr(W, "cscs", None) is not None else np.zeros(len(cols), bool)
    return post, sp, cs


# ------------------------------------------------------------------ cell M: one rebalance, the leg, the run
def m_one(W, k, mode, units=True):
    """one M rebalance at rank k (rank close r, fill f = r + 1 at the official open, exit x = the next rank's fill): the universe at the rank (W.ea.uni[k]), the DUE flags, the names M can trade - an open at the fill session (CHOICE, r17_resmom's: a name with none cannot be
    filled; counted no_fill) and no hand-audit data event (by fill session, r17_resmom's key) - and, in the REPORTED removal reading [E16] 'keep', no announced (calendar) split or spin-off / stock-dividend ex-date in f < t <= x. LONG the DUE names, SHORT the rest;
    a side's dollars = min($200,000, $10,000 x its count) [E8], split equally; fewer than 8 names on either side = no trade (counted thin). Judged reading 'close' [E16]: every name stays on the split-safe path and a spin-off / stock-dividend ex-date in f < e <= x
    closes the position at the official close of e-1 (rec.close; r17_resmom's rm_units cuts the path). -> (rec, counts)"""
    ea = W.ea
    r, f, x = int(ea.r[k]), int(ea.f[k]), int(ea.x[k])
    uni, due = ea.uni[k], ea.due[k]
    rec = SimpleNamespace(k=k, r=r, f=f, x=x, nu=len(uni), pool=np.zeros(0, np.int64), due=np.zeros(0, bool), nL=0, nS=0, L_usd=0.0, S_usd=0.0, traded=False, close=np.zeros(0, np.int64), beta=None, iL=np.zeros(0, np.int64), iS=np.zeros(0, np.int64))
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    cnt["due"] += int(due.sum())
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    m_fill = np.isfinite(W.Ao[f, uni])
    aud = W.aud1[f, uni]
    W.aud_hit.update((AUD, f, int(c)) for c in uni[aud])
    post, sp, cs = in_hold(W, f, x, uni)
    reasons = [("no_fill", ~m_fill), ("audit", aud)]
    if mode == "keep":
        reasons += [("post_calendar_split", cs), ("post_spin", sp)]
    first = D15.attribute(reasons, len(uni))
    D15.tally(cnt, reasons, first)
    ok = first < 0
    for q, h in enumerate(HYG):
        cnt[f"kept_{h}"] += int((ok & post[q]).sum())
    cnt["kept_flagged"] += int((ok & post.any(axis=0)).sum())
    if mode == "close":
        cnt["kept_calendar_split"] += int((ok & cs).sum())
        cnt["closed_spin"] += int((ok & sp).sum())
    rec.pool, rec.due = uni[ok], due[ok]
    rec.iL, rec.iS = np.flatnonzero(rec.due), np.flatnonzero(~rec.due)
    rec.nL, rec.nS = len(rec.iL), len(rec.iS)
    rec.L_usd, rec.S_usd = side_usd(rec.nL), side_usd(rec.nS)
    rec.close = close_rows(W, f, x, rec.pool, mode)
    if rec.nL >= SPEC["min_side"] and rec.nS >= SPEC["min_side"]:
        rec.traded = True
        cnt["traded"] += 1
        if units:
            rec.U = M17.rm_units(W, f, x, rec.pool, None, rec.close)
        if W.ea.beta is not None:
            rec.beta = m_betas(W, r, rec.pool)
    else:
        cnt["thin"] += 1
    return rec, cnt


def side_usd(n):
    """[E8] a side's dollars: min($200,000, $10,000 x its count) (0 for an empty side)"""
    return float(min(SPEC["side_usd"], SPEC["name_cap"] * n))


def m_build(W, lo, hi, mode=JUDGED, units=True):
    """every M rebalance whose position EXITS inside [lo, hi] (r17_resmom.rm_build's rules: the stretch by exit session, a rank without a full 252-session window is warm-up, a position whose exit is past the stage's data unresolved - out of the cell AND the null,
    counted) -> Leg(kind 'M', recs, cnt by fill year)"""
    ea = W.ea
    recs, cnt = [], defaultdict(Counter)
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()):
        if x >= 0 and lo <= W.days[x] <= hi and r < M17.SPEC["win"] - 1:
            cnt[int(W.days[f].year)]["warmup"] += 1
    for k in range(len(ea.r)):
        x = int(ea.x[k])
        y = int(W.days[ea.f[k]].year)
        if x < 0:
            cnt[y]["unresolved"] += 1
            continue
        if not (lo <= W.days[x] <= hi):
            continue
        rec, c = m_one(W, k, mode, units)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="M", recs=recs, cnt=cnt, mode=mode)


def m_hedge_usd(rec):
    """[E13] the book's ex-ante dollar beta at the rank: long $ x the long side's mean beta - short $ x the short side's (CHOICE: 'the beta gap x the side dollars' read as the dollar beta of the two sides - the same number when the sides hold equal dollars; a thin month
    with unequal sides is hedged for its net dollars too) -> (gap = mean beta long - mean beta short, dollar beta); NaN when a side has no beta"""
    if rec.beta is None or not rec.traded:
        return float("nan"), float("nan")
    bl, bs = rec.beta[rec.iL], rec.beta[rec.iS]
    if not (np.isfinite(bl).all() and np.isfinite(bs).all()):
        return float("nan"), float("nan")
    return float(bl.mean() - bs.mean()), float(rec.L_usd * bl.mean() - rec.S_usd * bs.mean())


def m_run(W, L, cfg, side=0, pos=False, hedged=False):
    """cell M's daily P&L on the stock sessions (T,), the positions held per row and (pos=True) the per-position table: each traded rebalance's longs at L$ / nL and shorts at S$ / nS per name, r17_resmom's l1_pnl_x per $1 (the marks, the cash dividends, 5 bps of the
    notional at the fill and of the exit value at the exit, the shorts' borrow; [E16]'s closed positions exit on their close's row). side +1 / -1: one side alone. hedged = [E13]: plus the ES hedge of the book's ex-ante dollar beta (m_hedge_usd), set at the fill print,
    lifted at the exit print, re-set at each rank, 0.5 bps a side (a rebalance whose hedge is undefined holds none: counted; CHOICE: the hedge is held to the exit even when a position closes early before a spin-off ex-date [E16])"""
    T = W.T
    x, cnt, rows, n_pos, n_units, nh = np.zeros(T), np.zeros(T), [], 0, 0, 0
    for ri, rec in enumerate(L.recs):
        if not rec.traded:
            continue
        kt = W.k[rec.f:rec.x + 1]
        tot = np.zeros(rec.x - rec.f + 1)
        for sd, idx, usd in ((1, rec.iL, rec.L_usd), (-1, rec.iS, rec.S_usd)):
            if side and sd != side:
                continue
            P = M17.l1_pnl_x(rec.U, idx, sd, cfg, kt) * (usd / len(idx))
            tot += P.sum(axis=0)
            cnt[rec.f:rec.x + 1] += len(idx)
            n_pos += len(idx)
            if pos:
                rows.append((np.full(len(idx), ri), rec.pool[idx], np.full(len(idx), sd), P.sum(axis=1), np.full(len(idx), usd / len(idx))))
        if hedged:
            hu = m_hedge_usd(rec)[1]
            if np.isfinite(hu):
                tot += hedge_paths(W, [rec.f], [rec.x], [hu])[0]
            else:
                nh += 1
        x[rec.f:rec.x + 1] += tot
        n_units += 1
    tab = None
    if pos:
        tab = SimpleNamespace(**{k: (np.concatenate([r_[q] for r_ in rows]) if rows else np.zeros(0)) for q, k in enumerate(("rec", "col", "side", "pnl", "usd"))})
    return SimpleNamespace(x=x, cnt=cnt, n_pos=n_pos, n_units=n_units, pos=tab, unhedged_rebalances=nh)


# ------------------------------------------------------------------ cell W: the events, the windows, the run
W_REASONS = ("no_entry_open", "no_beta", "audit", "post_calendar_split", "post_spin")


def w_build(W, lo, hi, mode=JUDGED, units=True):
    """cell W's events whose EXIT session falls in [lo, hi] (CHOICE: the stretch by exit, as the house's stretches are written), from W.ea.cand (one per predicted date of a universe name at the rank before its entry). Each candidate fails at its FIRST reason: no_entry_open
    (no official open at e: it cannot be bought), [E9] / [E26] no beta (the name lacks its own return on one of the 252 most recent sessions before the entry on which ES has a return - the window reaches back past ES's own holes [E26]; no zero-beta fallback; an
    event whose window reached back is counted: beta_reached_back), audit (a hand-audit data event on (entry session, name)), and in the REPORTED removal reading [E16] 'keep' an announced split / a spin-off or stock-dividend ex-date in e < t <= x. Unresolved (p + 2 past the data) and warm-up
    (no built rank before the entry) candidates are counted by entry year. The judged reading closes a window that holds a spin-off / stock-dividend ex-date at the close before it. units: the unit paths of every name the random-name null may draw at each entry
    session (the universe at the rank before the entry with an open at e and a beta at e) - the events index into them. -> Leg(kind 'W', ev arrays, groups, cnt by entry year)"""
    ea, c = W.ea, W.ea.cand
    cnt = defaultdict(Counter)
    yr = np.asarray(W.days.year)[np.clip(c.e, 0, W.T - 1)] if c.n else np.zeros(0, int)
    res = c.x >= 0
    for y in np.unique(yr[~res]):
        cnt[int(y)]["unresolved"] += int(((~res) & (yr == y)).sum())
    inwin = res & (np.asarray(W.days)[np.clip(c.x, 0, W.T - 1)] >= np.datetime64(lo)) & (np.asarray(W.days)[np.clip(c.x, 0, W.T - 1)] <= np.datetime64(hi))
    sel = np.flatnonzero(inwin)
    e, x, col = c.e[sel], c.x[sel], c.col[sel]
    beta, npair, reach = w_beta(W, e, col)
    no_beta = ~(np.isfinite(beta) | ea.counts_only) | (npair < SPEC["beta_need"])
    opn = np.isfinite(W.Ao[e, col]) if len(sel) else np.zeros(0, bool)
    aud = W.audw[e, col] if len(sel) else np.zeros(0, bool)
    for e_, c_ in zip(e[aud].tolist(), col[aud].tolist()):
        W.aud_hit.add((AUD_W, int(e_), int(c_)))
    post = np.zeros((4, len(sel)), bool)
    sp, cs = np.zeros(len(sel), bool), np.zeros(len(sel), bool)
    for q in range(len(sel)):
        p4, s_, c_ = in_hold(W, int(e[q]), int(x[q]), col[q:q + 1])
        post[:, q], sp[q], cs[q] = p4[:, 0], s_[0], c_[0]
    reasons = [("no_entry_open", ~opn), ("no_beta", no_beta), ("audit", aud)]
    if mode == "keep":
        reasons += [("post_calendar_split", cs), ("post_spin", sp)]
    first = D15.attribute(reasons, len(sel))
    yrs = yr[sel]
    labels = [lab for lab, _ in reasons] + ["events"]
    code = np.where(first < 0, len(reasons), first)
    for y in np.unique(yrs):
        m = yrs == y
        b = np.bincount(code[m], minlength=len(labels))
        cnt[int(y)].update({lab: int(v) for lab, v in zip(labels, b) if v})
        cnt[int(y)]["candidates"] += int(m.sum())
        ok_y = m & (first < 0)
        for q, h in enumerate(HYG):
            cnt[int(y)][f"kept_{h}"] += int((ok_y & post[q]).sum())
        cnt[int(y)]["kept_flagged"] += int((ok_y & post.any(axis=0)).sum())
        cnt[int(y)]["beta_reached_back"] += int((ok_y & reach).sum())                # [E26] events whose beta window reached back past an ES hole
        if mode == "close":
            cnt[int(y)]["kept_calendar_split"] += int((ok_y & cs).sum())
            cnt[int(y)]["closed_spin"] += int((ok_y & sp).sum())
    keep = first < 0
    k_ = sel[keep]
    o = np.lexsort((c.col[k_], c.e[k_]))
    k_ = k_[o]
    ev = SimpleNamespace(n=int(len(k_)), cand=k_, k=c.k[k_], col=c.col[k_], rel=c.rel[k_], p=c.p[k_], e=c.e[k_], x=c.x[k_], beta=beta[keep][o], close=np.full(len(k_), -1, np.int64))
    for i in range(ev.n):
        ev.close[i] = close_rows(W, int(ev.e[i]), int(ev.x[i]), ev.col[i:i + 1], mode)[0]
    L = SimpleNamespace(kind="W", ev=ev, cnt=cnt, mode=mode, groups=[], gpos=np.full(ev.n, -1, np.int64), gix=np.full(ev.n, -1, np.int64))
    if units and ev.n:
        w_units(W, L)
    return L


def w_pool(W, k, e):
    """the names W's random-name null may draw for an event entering at e (the rank before it: k): the universe at the rank with an official open at e, a beta at e by [E9]'s rule and no hand-audit data event on (e, name) - the conditions every real event meets (CHOICE: the draw is from the names the hedge rule can apply to, the event's own name included)"""
    uni = W.ea.uni[k]
    if not len(uni):
        return uni
    b, npair, _ = w_beta(W, np.full(len(uni), e), uni)
    ok = np.isfinite(W.Ao[e, uni]) & (np.isfinite(b) | (W.ea.counts_only & (npair >= SPEC["beta_need"]))) & ~W.audw[e, uni]
    return uni[ok]


def w_units(W, L):
    """per entry session: the pool (w_pool), its unit paths (r17_resmom's rm_units over e .. x: split-safe marks, the cash dividends, [E16]'s close rows), its betas and its hedge paths per $1 (hedge_paths); every event is a row of its group's pool (L.gix = the group, L.gpos =
    its row). The removal reading [E16] needs no pool (it has no null): its events alone are pathed"""
    ev = L.ev
    for e in np.unique(ev.e):
        m = np.flatnonzero(ev.e == e)
        k, x = int(ev.k[m[0]]), int(ev.x[m[0]])
        pool = w_pool(W, k, int(e)) if L.mode == JUDGED else np.unique(ev.col[m])
        pool = np.union1d(pool, ev.col[m])
        cl = close_rows(W, int(e), x, pool, L.mode)
        U = M17.rm_units(W, int(e), x, pool, None, cl)
        b = w_beta(W, np.full(len(pool), e), pool)[0]
        Hp = hedge_paths(W, np.full(len(pool), e), np.full(len(pool), x), np.nan_to_num(b), cl)
        g = SimpleNamespace(e=int(e), x=x, k=k, pool=pool, U=U, beta=b, H=Hp, close=cl, ev=m)
        L.gix[m] = len(L.groups)
        L.gpos[m] = np.searchsorted(pool, ev.col[m])
        L.groups.append(g)


def w_run(W, L, cfg, pos=False, hedge=True, stock=True):
    """cell W's daily P&L on the stock sessions (T,), the positions held per row (rows e .. x of every event, r15's count) and (pos=True) the per-event table: $4,000 long per event, r17_resmom's l1_pnl_x per $1 (marks, dividends, 5 bps at the entry open and of the exit value
    at the exit open, [E16]'s close) + the ES hedge (hedge_paths: beta x $4,000, 0.5 bps a side - CHOICE: the cost curve moves the STOCK's cost only, DIVRUN's [X2] convention). hedge=False / stock=False: the unhedged stock leg / the hedge leg alone (reports)"""
    T, slot = W.T, SPEC["w_slot"]
    x, cnt = np.zeros(T), np.zeros(T)
    ev = L.ev
    pnl, sp, hp = np.zeros(ev.n), np.zeros(ev.n), np.zeros(ev.n)
    for gi, g in enumerate(L.groups):
        m = g.ev
        idx = L.gpos[m]
        kt = W.k[g.e:g.x + 1]
        P = M17.l1_pnl_x(g.U, idx, 1, cfg, kt) if stock else np.zeros((len(idx), g.x - g.e + 1))
        Hd = g.H[idx] if hedge else np.zeros_like(P)
        tot = slot * (P + Hd)
        x[g.e:g.x + 1] += tot.sum(axis=0)
        cnt[g.e:g.x + 1] += len(m)
        pnl[m], sp[m], hp[m] = tot.sum(axis=1), slot * P.sum(axis=1), slot * Hd.sum(axis=1)
    tab = SimpleNamespace(rec=np.arange(ev.n), col=ev.col, side=np.ones(ev.n), pnl=pnl, stock=sp, hedge=hp, usd=np.full(ev.n, slot)) if pos else None
    return SimpleNamespace(x=x, cnt=cnt, n_pos=int(ev.n), n_units=int(ev.n), pos=tab)


# ------------------------------------------------------------------ the nulls: random names (both cells) and [E11] W's time shift
def m_null(W, L, nreps, rng):
    """M's random-name null [prereg NULL]: at every traded rebalance the DUE side is replaced by the same number of names drawn uniformly without replacement from that rank's names (the same pool: the universe less the names M cannot fill / the audit's) and the rest is
    the short side - the same sizes (L$ / nL a long, S$ / nS a short), fills, costs, borrow, dividends and [E16] cut paths. -> (nreps, T) P&L by stock session"""
    cfg, acc = D15.l1_cfg(), np.zeros((nreps, W.T))
    for rec in L.recs:
        if not rec.traded:
            continue
        n = len(rec.pool)
        idx, kt = np.arange(n), W.k[rec.f:rec.x + 1]
        PL, PS = M17.l1_pnl_x(rec.U, idx, 1, cfg, kt), M17.l1_pnl_x(rec.U, idx, -1, cfg, kt)
        o = D15.draw_order(rng, nreps, n, rec.nL)
        acc[:, rec.f:rec.x + 1] += (rec.L_usd / rec.nL) * PL[o].sum(axis=1) + (rec.S_usd / rec.nS) * (PS.sum(axis=0)[None, :] - PS[o].sum(axis=1))
    return acc


def w_null(W, L, nreps, rng):
    """W's random-name null [prereg NULL]: every event keeps its dates, its hedge rule (beta x $4,000, the DRAWN name's own beta) and its costs, its name drawn uniformly (with replacement across events, CHOICE: one independent draw per event) from the universe at its
    rank (w_pool: an open at e and a beta - the conditions the rule needs) -> (nreps, T)"""
    cfg, slot, acc = D15.l1_cfg(), SPEC["w_slot"], np.zeros((nreps, W.T))
    for g in L.groups:
        kt = W.k[g.e:g.x + 1]
        tot = slot * (M17.l1_pnl_x(g.U, np.arange(len(g.pool)), 1, cfg, kt) + g.H)
        picks = rng.integers(0, len(g.pool), (len(g.ev), nreps))
        acc[:, g.e:g.x + 1] += tot[picks].sum(axis=0)
    return acc


def shift_paths(W, L, t_min=0):
    """[E11] every event's window moved back by s = 27 .. 36 sessions: the same name, the hedge rule re-applied at the new entry (CHOICE, DIVRUN's placebo convention: the beta known at the moved entry by [E9]'s rule, [E26]'s window), the same costs, [E16]'s close inside the moved
    window. A moved window that starts before the data (or, [E25]'s sensitivity, before its stretch's first session t_min - CHOICE), has no official open at its entry or no beta there is unavailable for that s (CHOICE: the event sits out the draws that pick it,
    counted - no redraw). -> (paths (n, n_s, H) in $ at base cost, valid (n, n_s), entries (n, n_s))"""
    ev, slot, cfg = L.ev, SPEC["w_slot"], D15.l1_cfg()
    ss = np.arange(SPEC["shift_lo"], SPEC["shift_hi"] + 1)
    H = SPEC["w_pre"] + SPEC["w_post"] + 1
    paths, valid = np.zeros((ev.n, len(ss), H)), np.zeros((ev.n, len(ss)), bool)
    E = ev.e[:, None] - ss[None, :]
    for e2 in np.unique(E[E >= max(int(t_min), 0)]):
        ii, qq = np.nonzero(E == e2)
        cols = ev.col[ii]
        x2 = int(e2) + H - 1
        b = w_beta(W, np.full(len(cols), e2), cols)[0]
        ok = np.isfinite(W.Ao[e2, cols]) & np.isfinite(b)
        if not ok.any():
            continue
        ii, qq, cols, b = ii[ok], qq[ok], cols[ok], b[ok]
        uc, inv = np.unique(cols, return_inverse=True)
        cl = close_rows(W, int(e2), x2, uc, JUDGED)
        U = M17.rm_units(W, int(e2), x2, uc, None, cl)
        P = M17.l1_pnl_x(U, inv, 1, cfg, W.k[e2:x2 + 1])
        Hd = hedge_paths(W, np.full(len(ii), e2), np.full(len(ii), x2), b, cl[inv])
        paths[ii, qq] = slot * (P + Hd)
        valid[ii, qq] = True
    return paths, valid, E


def w_shift_null(W, L, nreps, rng, sp=None, block=50, t_min=0):
    """[E11] W's SECOND null (DIVRUN's time shift): per event and draw the whole window moves back by a whole number of sessions drawn uniformly from 27 .. 36 (rng.integers, inclusive) - the middle of the quarter - with its name, hedge rule and costs (shift_paths);
    500 draws, seed 20261020, W's own ROC @ $30k per draw. -> ((nreps, T) P&L, events left out per draw (their drawn shift unavailable))"""
    paths, valid, E = shift_paths(W, L, t_min) if sp is None else sp
    n, H, T = L.ev.n, paths.shape[2], W.T
    acc, left = np.zeros((nreps, T)), np.zeros(nreps, np.int64)
    for b0 in range(0, nreps, block):
        D = min(block, nreps - b0)
        s = rng.integers(SPEC["shift_lo"], SPEC["shift_hi"] + 1, (n, D))
        q = s - SPEC["shift_lo"]
        ii = np.repeat(np.arange(n), D)
        dd = np.tile(np.arange(D), n)
        qf = q.ravel()
        ok = valid[ii, qf]
        left[b0:b0 + D] = np.bincount(dd[~ok], minlength=D)
        ii, dd, qf = ii[ok], dd[ok], qf[ok]
        e2 = E[ii, qf]
        flat = np.zeros(D * T)
        for h in range(H):
            flat += np.bincount(dd * T + e2 + h, weights=paths[ii, qf, h], minlength=D * T)
        acc[b0:b0 + D] = flat.reshape(D, T)
    return acc, left


def null_stats(S12, Sref, acc, rows, nb):
    """a block of null series (D, T) on the stock sessions -> (the WF ROC @ $30k of every draw on #463's stretch, the P&L inside L's drawdown days of every draw - the R-day sum's null)"""
    roc = D15.null_cell(S12, acc, rows, nb)[0]
    Y = np.zeros((acc.shape[0], nb))
    Y[:, rows] = acc
    rday = Y[:, Sref.rows][:, Sref.dd].sum(axis=1) if Sref is not None else np.full(acc.shape[0], np.nan)
    return roc, rday


def pct(a, q):
    return D15.pctl(a, q)


def dist(a):
    return {"p5": pct(a, 5), "p50": pct(a, 50), "p95": pct(a, 95), "p97.5": pct(a, RULES["pctl"]), "finite": int(np.isfinite(np.asarray(a, float)).sum())}


def null_summary(rn_roc, rn_rday, ts_roc=None, ts_rday=None, ts_left=None):
    """the random-name null: the statistic = the MAX over the 2 cells of WF ROC @ $30k per draw (draw i of M beside draw i of W: two independent streams) -> p5 / p50 / p95 / p97.5 ([E12]: (c) is read at p97.5) and each cell's own; the R-day sums per cell. [E11] the
    time-shift null: W's own ROC per draw and its R-day sums"""
    mx = np.fmax.reduce(np.vstack([rn_roc[c] for c in CELLS]), axis=0)
    out = {"draws": int(len(mx)), "seed": SEED, "roc_max": dist(mx), "by_cell": {c: dist(rn_roc[c]) for c in CELLS}, "rday_by_cell": {c: dist(rn_rday[c]) for c in CELLS}}
    if ts_roc is not None:
        out["time_shift"] = {"draws": int(len(ts_roc)), "seed": SEED_SHIFT, "roc": dist(ts_roc), "rday": dist(ts_rday), "left_out_per_draw_mean": float(np.mean(ts_left)) if ts_left is not None and len(ts_left) else 0.0,
                             "left_out_per_draw_max": int(np.max(ts_left)) if ts_left is not None and len(ts_left) else 0}
    return out


# ------------------------------------------------------------------ BEFORE ANY P&L: the counts, [E5] accuracy both ways (and the STOP), [E6] turnover and the break-even spread, [E7] the power line
def wf_ranks(W, lo=None, hi=None):
    """the indices of the built ranks whose M position exits inside [lo, hi] (default WF) - the ranks m_build builds"""
    lo, hi = (WF0 if lo is None else lo), (PRE_END if hi is None else hi)
    ea = W.ea
    return [k for k in range(len(ea.r)) if ea.x[k] >= 0 and lo <= W.days[ea.x[k]] <= hi]


def actual_rows(W):
    """the ACTUAL releases [E5] / [E13] / [E14] read (a REPORT, never an input): the calendar's reaction sessions (rows; a date that is not a session moved to the next) of the releases [P] counts - [E2]'s 8-K/A out and (CHOICE) the earlier of every [E3] pair out, with hindsight (a pre-announcement is not an 'actual' release;
    the calendar is also the 'actual', so a release missing from it is invisible to both measures) -> {cik: sorted rows}"""
    rt = W.ea.rt
    out = defaultdict(list)
    for i in np.flatnonzero(~rt.drop_h & (rt.rs_row >= 0)):
        out[str(rt.cik[i])].append(int(rt.rs_row[i]))
    return {c: np.unique(np.asarray(v, np.int64)) for c, v in out.items()}


def accuracy(W, ranks=None):
    """[E5] ACCURACY BOTH WAYS, before any P&L, by WF July-June year. PRECISION: the share of the predicted dates M and W act on (every (name, p) of a universe name whose p falls in its rank's DUE window - each predicted date once) within +-3 / +-7 sessions of an actual
    release of the same CIK (the calendar's reaction session); CHOICE: by the July-June year of p, and a p within 7 sessions of the data's last session is left out (its actual may lie past the cut; counted). RECALL: the share of the actual releases of universe names
    (the names in the universe at the rank before the release's month, their reaction sessions in that month: r + 1 .. r_next) whose name M assigned DUE in that month; CHOICE: by the July-June year of the reaction session. The run STOPS before any P&L if recall is under
    80% in any WF year (stop = the years that fail). [E25] the stop still FIRES as registered; a year in MANAGER's recorded waiver (E5_WAIVER: 2016-17, MANAGER #141) is waived, and the run HALTS only when a failing year is not in it (halt / halt_years)"""
    ea = W.ea
    ranks = wf_ranks(W) if ranks is None else ranks
    act = actual_rows(W)
    near = SPEC["near"]
    prec, rec_, cut_out = defaultdict(lambda: np.zeros(len(near) + 1, np.int64)), defaultdict(lambda: np.zeros(2, np.int64)), 0
    jy = jyear(W.days)
    for k in ranks:
        for j, i in ea.due_p[k]:
            p = int(ea.rt.p_row[i])
            if p > W.T - 1 - max(near):
                cut_out += 1
                continue
            a = act.get(str(ea.cik[j]))
            dmin = int(np.abs(a - p).min()) if a is not None and len(a) else 10 ** 6
            v = prec[int(jy[p])]
            v[0] += 1
            for q, w_ in enumerate(near):
                v[q + 1] += int(dmin <= w_)
        r, rn = int(ea.r[k]), int(ea.r_next[k])
        uni, due = ea.uni[k], ea.due[k]
        for q, j in enumerate(uni):
            a = act.get(str(ea.cik[j]))
            if a is None:
                continue
            for t in a[(a >= r + 1) & (a <= rn)]:
                v = rec_[int(jy[t])]
                v[0] += 1
                v[1] += int(due[q])
    years = sorted(set(prec) | set(rec_))
    by = {}
    for y in years:
        p_, r_ = prec.get(y, np.zeros(len(near) + 1, np.int64)), rec_.get(y, np.zeros(2, np.int64))
        by[y] = {"predicted": int(p_[0]), **{f"within_{w_}": (float(p_[q + 1] / p_[0]) if p_[0] else float("nan")) for q, w_ in enumerate(near)},
                 "actual": int(r_[0]), "recalled": int(r_[1]), "recall": (float(r_[1] / r_[0]) if r_[0] else float("nan"))}
    wf_years = [y for y in years if y in YEARS]
    stop = [y for y in wf_years if not (by[y]["recall"] >= SPEC["recall_stop"])]
    waived, halt = e5_waive(stop)
    tp = sum(prec[y][0] for y in prec)
    tot = {"predicted": int(tp), **{f"within_{w_}": (float(sum(prec[y][q + 1] for y in prec) / tp) if tp else float("nan")) for q, w_ in enumerate(near)},
           "actual": int(sum(v[0] for v in rec_.values())), "recall": (float(sum(v[1] for v in rec_.values()) / sum(v[0] for v in rec_.values())) if sum(v[0] for v in rec_.values()) else float("nan"))}
    return {"by_year": by, "total": tot, "left_out_near_the_data_end": int(cut_out), "stop_years": stop, "stop": bool(stop), "recall_floor": SPEC["recall_stop"], "waived_years": waived, "halt_years": halt, "halt": bool(halt),
            "waived_by": E5_WAIVER["by"] if waived else None}


def e5_waive(stop_years):
    """[E25] the recorded waiver read against the failing WF years: -> (the waived years - those E5_WAIVER names, the years that still STOP the run - every other failing year)"""
    names = tuple((E5_WAIVER or {}).get("years", ()))
    waived = [y for y in stop_years if yl(y) in names]
    return waived, [y for y in stop_years if y not in waived]


def e5_record(acc):
    """[E25] what Stage A's file keeps of the stop: fired, the failing years with their recall, waived (by whom), halted"""
    return {"fired": bool(acc["stop"]), "recall_floor": acc["recall_floor"], "failing_years": {yl(y): acc["by_year"][y]["recall"] for y in acc["stop_years"]}, "waived_years": [yl(y) for y in acc["waived_years"]],
            "waived_by": acc["waived_by"], "waiver": dict(E5_WAIVER) if acc["waived_years"] else None, "halted": bool(acc["halt"]), "halt_years": [yl(y) for y in acc["halt_years"]]}


def e5_phrase(acc):
    """[E25] the waiver as the result line states it ('' when the stop did not fire, or fired and halts)"""
    if not acc["stop"] or acc["halt"]:
        return ""
    return ("the [E5] recall stop FIRED at " + ", ".join(f"{acc['by_year'][y]['recall']:.1%} ({acc['by_year'][y]['recalled']:,} of {acc['by_year'][y]['actual']:,}) in {yl(y)}" for y in acc["stop_years"])
            + f" and is WAIVED by {acc['waived_by']} [E25]")


def print_accuracy(acc):
    near = SPEC["near"]
    print(f"[E5] ACCURACY OF [P], BOTH WAYS (BEFORE ANY P&L; the calendar is also the 'actual' - a release missing from it is invisible to both measures): precision = the predicted dates within +-{near[0]} / +-{near[1]} sessions of an actual release (reaction session); "
          f"recall = the actual releases of universe names that land in the month M assigned them as DUE. By July-June year (predicted: within {near[0]} / within {near[1]} | actual: recalled):")
    for y, v in acc["by_year"].items():
        print(f"  {yl(y)}: {v['predicted']:,} predicted: {v[f'within_{near[0]}']:.1%} / {v[f'within_{near[1]}']:.1%} | {v['actual']:,} actual: {v['recalled']:,} recalled = {v['recall']:.1%}" + ("   <- RECALL UNDER 80%" if y in acc["stop_years"] else ""))
    t = acc["total"]
    print(f"  all: {t['predicted']:,} predicted, {t[f'within_{near[0]}']:.1%} / {t[f'within_{near[1]}']:.1%}; {t['actual']:,} actual, recall {t['recall']:.1%}; {acc['left_out_near_the_data_end']} predicted dates within {near[1]} sessions of the data's end left out")
    if not acc["stop"]:
        print(f"  [E5] STOP: recall is at or above {acc['recall_floor']:.0%} in every WF July-June year - the run goes on")
    elif acc["halt"]:
        print(f"  [E5] STOP: recall is under {acc['recall_floor']:.0%} in the WF year(s) {', '.join(yl(y) for y in acc['halt_years'])} - THE RUN STOPS BEFORE ANY P&L AND MANAGER RULES"
              + (f" ({', '.join(yl(y) for y in acc['waived_years'])} waived by {acc['waived_by']} [E25]; the waiver covers no other year)" if acc["waived_years"] else ""))
    else:
        print(f"  [E5] STOP: FIRED - {e5_phrase(acc)} (the stop is not rewritten; the waiver covers exactly {', '.join(yl(y) for y in acc['waived_years'])}: a recall under {acc['recall_floor']:.0%} in any other July-June year still stops) - the run goes on")


def turnover(W, L):
    """[E6] TURNOVER FROM THE DUE LISTS ALONE (no return read), before any P&L: between consecutive TRADED rebalances, per side, the one-way turnover = half the sum of |the change of each name's weight| (a side's weights sum to 1: each name holds side$ / count) and its
    dollars (half the sum of |the change of each name's dollars|); a rebalance after a month that traded nothing enters from cash (CHOICE: not a transition - counted apart). The BREAK-EVEN monthly gross spread (the long side's return minus the short side's, on a side's
    mean dollars (L$ + S$) / 2) that pays a month's costs: under the registered convention (r17_resmom's engine: every position pays its entry and its exit every month - a name that stays pays again - plus 0.25% a year of borrow on the short dollars over the hold's
    nights) and, beside it, the cost if only the changes were traded (a report) -> {rows: per transition, by_year, by_month, totals}"""
    rows, prev, cold = [], None, 0
    for rec in L.recs:
        if not rec.traded:
            prev = None
            continue
        cur = {"L": dict(zip(rec.pool[rec.iL].tolist(), [rec.L_usd / rec.nL] * rec.nL)), "S": dict(zip(rec.pool[rec.iS].tolist(), [rec.S_usd / rec.nS] * rec.nS)), "L$": rec.L_usd, "S$": rec.S_usd}
        nights = rec.x - rec.f
        base = {"date": f"{W.days[rec.r]:%Y-%m-%d}", "year": int(W.days[rec.f].year), "month": int(W.days[rec.f].month), "L$": rec.L_usd, "S$": rec.S_usd, "nL": rec.nL, "nS": rec.nS, "nights": int(nights)}
        for b in (5.0, 10.0):
            cost = b * 1e-4 * 2.0 * (rec.L_usd + rec.S_usd) + BORROW * rec.S_usd * nights / 252.0
            base[f"breakeven_{b:g}"] = cost / (0.5 * (rec.L_usd + rec.S_usd))
        if prev is None:
            cold += 1
            base.update({"transition": False})
        else:
            tv = {}
            for sd in ("L", "S"):
                names = set(cur[sd]) | set(prev[sd])
                dw = sum(abs(cur[sd].get(n, 0.0) / cur[f"{sd}$"] - prev[sd].get(n, 0.0) / prev[f"{sd}$"]) for n in names)
                dd = sum(abs(cur[sd].get(n, 0.0) - prev[sd].get(n, 0.0)) for n in names)
                tv[sd] = (0.5 * dw, 0.5 * dd)
            base.update({"transition": True, "turnover_long": tv["L"][0], "turnover_short": tv["S"][0], "traded_usd_long": tv["L"][1], "traded_usd_short": tv["S"][1]})
            for b in (5.0, 10.0):
                cost = b * 1e-4 * 2.0 * (tv["L"][1] + tv["S"][1]) + BORROW * rec.S_usd * nights / 252.0
                base[f"breakeven_changes_only_{b:g}"] = cost / (0.5 * (rec.L_usd + rec.S_usd))
        rows.append(base)
        prev = cur
    tr = [r_ for r_ in rows if r_["transition"]]
    agg = lambda sel, key: float(np.mean([r_[key] for r_ in sel])) if sel else float("nan")
    by_year = {y: {"rebalances": sum(1 for r_ in rows if r_["year"] == y), "transitions": sum(1 for r_ in tr if r_["year"] == y), "turnover_long": agg([r_ for r_ in tr if r_["year"] == y], "turnover_long"),
                   "turnover_short": agg([r_ for r_ in tr if r_["year"] == y], "turnover_short"), "breakeven_5": agg([r_ for r_ in rows if r_["year"] == y], "breakeven_5"), "breakeven_10": agg([r_ for r_ in rows if r_["year"] == y], "breakeven_10"),
                   "breakeven_changes_only_5": agg([r_ for r_ in tr if r_["year"] == y], "breakeven_changes_only_5"), "breakeven_changes_only_10": agg([r_ for r_ in tr if r_["year"] == y], "breakeven_changes_only_10")}
               for y in sorted({r_["year"] for r_ in rows})}
    by_month = {m: {"transitions": sum(1 for r_ in tr if r_["month"] == m), "turnover_long": agg([r_ for r_ in tr if r_["month"] == m], "turnover_long"), "turnover_short": agg([r_ for r_ in tr if r_["month"] == m], "turnover_short")} for m in range(1, 13)}
    return {"rows": rows, "by_year": by_year, "by_month": by_month, "traded_rebalances": len(rows), "transitions": len(tr), "from_cash": cold, "turnover_long": agg(tr, "turnover_long"), "turnover_short": agg(tr, "turnover_short"),
            "breakeven_5": agg(rows, "breakeven_5"), "breakeven_10": agg(rows, "breakeven_10"), "breakeven_changes_only_5": agg(tr, "breakeven_changes_only_5"), "breakeven_changes_only_10": agg(tr, "breakeven_changes_only_10")}


def print_turnover(t):
    pc = lambda v: f"{v:.0%}" if np.isfinite(v) else "-"
    pp = lambda v: f"{100 * v:.3f}%" if np.isfinite(v) else "-"
    print(f"[E6] M's TURNOVER FROM THE DUE LISTS ALONE (no return read; BEFORE ANY P&L): {t['traded_rebalances']} traded rebalances, {t['transitions']} transitions between consecutive traded ones ({t['from_cash']} enter from cash); one-way turnover a month, "
          f"long side {pc(t['turnover_long'])}, short side {pc(t['turnover_short'])}")
    print("  by year (one-way turnover long / short; the break-even monthly gross spread at 5 / 10 bps a side - registered convention: every position pays entry and exit each month + borrow; changes-only beside it): " + "; ".join(
        f"{y}: {pc(v['turnover_long'])} / {pc(v['turnover_short'])}, {pp(v['breakeven_5'])} / {pp(v['breakeven_10'])} ({pp(v['breakeven_changes_only_5'])} / {pp(v['breakeven_changes_only_10'])})" for y, v in t["by_year"].items()))
    print("  by calendar month of the fill (one-way turnover long / short, mean over the years): " + "; ".join(f"{m:02d}: {pc(v['turnover_long'])} / {pc(v['turnover_short'])}" for m, v in t["by_month"].items()))
    print(f"  the break-even monthly gross spread, all WF: {pp(t['breakeven_5'])} at 5 bps, {pp(t['breakeven_10'])} at 10 bps (registered convention); {pp(t['breakeven_changes_only_5'])} / {pp(t['breakeven_changes_only_10'])} if only the changes were traded (a report)")


def power_line(W, Lm, n_events, years):
    """[E7] THE POWER LINE, before any P&L, from the DUE lists, the event count and the cost curve beside the literature / MANAGER values (no return is read). M: ROC @ $30k 15 needs a WF net of 15 / 30 x the worst drawdown a year; CHOICE: at the draft's own drawdown range
    ($15,000 - $30,000), plus the costs a year (the registered convention on the DUE lists' dollars at 5 and 10 bps + borrow), over the traded rebalances a year and their mean side dollars -> the gross monthly spread needed. W: N events a year (the WF count / the
    stretch's years); CHOICE: the per-event sd is the literature value MANAGER used (7%), the mean NET per event at which the MEDIAN ROC @ $30k of 400 synthetic WF stretches (N x years seeded normal events of $4,000, the events' running sum valued like a daily series,
    no data) is 15; the gross need adds the costs (5 / 10 bps a side on $4,000 + 0.5 bps a side on a beta-1 hedge)"""
    recs = [r_ for r_ in Lm.recs if r_.traded]
    nights = lambda r_: r_.x - r_.f
    cost = {b: sum(b * 1e-4 * 2.0 * (r_.L_usd + r_.S_usd) + BORROW * r_.S_usd * nights(r_) / 252.0 for r_ in recs) / years for b in (5.0, 10.0)}
    side = float(np.mean([0.5 * (r_.L_usd + r_.S_usd) for r_ in recs])) if recs else float("nan")
    per_year = len(recs) / years if years else float("nan")
    m = {"traded_rebalances_a_year": per_year, "mean_side_usd": side, "cost_a_year": {f"{b:g}": cost[b] for b in cost}, "need": {}}
    for dd in DD_DRAFT:
        for b in cost:
            g = (0.5 * dd + cost[b]) / per_year / side if per_year and side else float("nan")
            m["need"][f"dd{dd:.0f}_{b:g}bps"] = g
    nyr = n_events / years if years else float("nan")
    w = {"events_a_year": nyr, "event_sd": LIT["w_event_sd"], "net_need": float("nan"), "gross_need": {}}
    if n_events >= 10 and years > 0:
        rng = np.random.default_rng(POWER_SEED)
        Z = rng.standard_normal((POWER_SIMS, int(n_events)))
        sd = LIT["w_event_sd"] * SPEC["w_slot"]

        def med_roc(mu):
            c = np.cumsum(mu + sd * Z, axis=1)
            mdd = (np.maximum.accumulate(np.maximum(c, 0.0), axis=1) - c).max(axis=1)
            with np.errstate(divide="ignore", invalid="ignore"):
                return float(np.median(np.where(mdd > 0, 30.0 * (c[:, -1] / years) / mdd, np.inf)))
        lo_, hi_ = 0.0, 0.2 * SPEC["w_slot"]
        for _ in range(50):
            mid = 0.5 * (lo_ + hi_)
            lo_, hi_ = (mid, hi_) if med_roc(mid) < RULES["roc"] else (lo_, mid)
        w["net_need"] = 0.5 * (lo_ + hi_) / SPEC["w_slot"]
        for b in (5.0, 10.0):
            w["gross_need"][f"{b:g}bps"] = w["net_need"] + 2 * b * 1e-4 + 2 * HEDGE_BPS * 1e-4
    return {"M": m, "W": w, "literature": LIT, "dd_assumed": list(DD_DRAFT)}


def print_power(pw):
    m, w, lit = pw["M"], pw["W"], pw["literature"]
    pp = lambda v: f"{100 * v:.2f}%" if np.isfinite(v) else "-"
    print("[E7] THE POWER LINE (BEFORE ANY P&L; THE EXPECTED VERDICT IS DEAD - the run's value is closing the earnings family on data already held): what ROC @ $30k 15 needs, computed from the DUE lists, the event count and the cost curve:")
    print(f"  M: {m['traded_rebalances_a_year']:.1f} traded rebalances a year at a mean ${m['mean_side_usd']:,.0f} a side; costs ${m['cost_a_year']['5']:,.0f} a year at 5 bps, ${m['cost_a_year']['10']:,.0f} at 10 bps (registered convention, borrow included) -> the gross monthly spread "
          "needed: " + ", ".join(f"{pp(m['need'][f'dd{dd:.0f}_{b}bps'])} (drawdown ${dd:,.0f}, {b} bps)" for dd in pw["dd_assumed"] for b in ("5", "10"))
          + f"; beside: Frazzini & Lamont's all-stock {lit['fl_spread_year']:.0%} a year ({pp(lit['fl_spread_year'] / 12)} a month), MANAGER's {pp(lit['mgr_m_spread_month'][0])}-{pp(lit['mgr_m_spread_month'][1])} a month")
    print(f"  W: {w['events_a_year']:.0f} events a year; at a per-event sd of {w['event_sd']:.0%} the mean NET per 5-session window for a median ROC @ $30k of 15 is {pp(w['net_need'])} (gross {pp(w['gross_need'].get('5bps', float('nan')))} at 5 bps, "
          f"{pp(w['gross_need'].get('10bps', float('nan')))} at 10 bps); beside: MANAGER's ~{pp(lit['mgr_w_event_net'])} net at ~{lit['mgr_w_events_year']} events a year")


def member_months(W, ranks):
    """names joined / not joined BY REASON (counts and names only), over the member-months of the WF ranks: every ticker on the members list of the rank's month, its World column (its own symbol, or the alias of a renamed ticker) and the first reason it is not in
    the universe; a ticker with no World column is either named by the calendar (a domestic filer never in the liquidity universe at all / not cached) or not (no release in the calendar: a foreign 6-K filer, or a company the calendar misses) -> {by_year: {reason: n},
    names: {reason: sorted symbols}, total: {reason: n}}"""
    ea = W.ea
    col_of = {str(s): j for j, s in enumerate(np.asarray(W.syms).astype(str))}
    by_year, names, total = defaultdict(Counter), defaultdict(set), Counter()
    for k in ranks:
        y = int(jyear(W.days[[ea.r[k]]])[0])
        R = int(day_i(W.days[ea.r[k]]))
        bpos = {int(j): q for q, j in enumerate(ea.base[k])}
        for t in sorted(members_on(ea.mem, ea.months[k])):
            js = [col_of[t]] if t in col_of else sorted(ea.alias.get(t, ()))
            if not js:
                why = "no World column: a filer the calendar names, never in the liquidity screen / not cached" if t in ea.cal_tickers else "no World column and no release in the calendar (a foreign 6-K filer [E4], or a company the calendar misses)"
                by_year[y][why] += 1
                total[why] += 1
                names[why].add(t)
                continue
            for j in js:
                q = bpos.get(j)
                if q is None:
                    why = "outside RESMOM's liquidity screen at the rank"
                else:
                    code = int(ea.first[k][q])
                    why = "in the universe" if code < 0 else (UNI_REASONS[code] if code < len(UNI_REASONS) else "second_class")
                    if why == "not_joined":
                        why = f"not_joined: {ea.join[j]}"
                    elif why == "few_releases" and ea.cik[j] in ea.rt.span:
                        a, b = ea.rt.span[ea.cik[j]]
                        why = "few_releases: the CIK's first release is under 400 days before the rank (a CIK break / a new filer - [E4])" if ea.rt.d[a] > R - SPEC["look_days"] else "few_releases: a hole in a CIK that filed before"
                    elif why == "not_member":
                        why = "not_member (an alias of another class)"
                by_year[y][why] += 1
                total[why] += 1
                names[why].add(str(W.syms[j]) if t == str(W.syms[j]) else f"{t}->{W.syms[j]}")
    return {"by_year": {y: dict(v) for y, v in sorted(by_year.items())}, "total": dict(total), "names": {k_: sorted(v) for k_, v in names.items()}}


def print_member_months(mm):
    print("names joined / not joined by reason - the Nasdaq-100 member-months of the WF ranks (each ticker on the rank month's list, its World column, the first reason it is not in the universe):")
    for why, n in sorted(mm["total"].items(), key=lambda kv: -kv[1]):
        nm = mm["names"].get(why, [])
        print(f"  {why}: {n:,} member-months; by July-June year " + ", ".join(f"{yl(y)} {v.get(why, 0)}" for y, v in mm["by_year"].items()) + (f"; names ({len(nm)}): {', '.join(nm[:60])}" + (" ..." if len(nm) > 60 else "") if why != "in the universe" else f"; {len(nm)} names"))


def month_ranges(ms):
    """'YYYY-MM' months -> the runs of consecutive months, 'YYYY-MM..YYYY-MM' (a lone month as itself), comma-separated ('' for none)"""
    out, run = [], []
    for m in sorted(set(ms)):
        if run and (pd.Period(m, "M") - pd.Period(run[-1], "M")).n == 1:
            run.append(m)
            continue
        if run:
            out.append(run)
        run = [m]
    if run:
        out.append(run)
    return ", ".join(r_[0] if len(r_) == 1 else f"{r_[0]}..{r_[-1]}" for r_ in out)


def rel_counts(rt, a, b, R, m=None):
    """the releases of one CIK's span a .. b-1 that COUNT at the rank day R ([E3] point in time, as kept_at), on the subset m (bool (b - a,); default all - the pair rule re-read on the subset) -> (counted before the rank, counted in the 400 days before it)"""
    d = rt.d[a:b] if m is None else rt.d[a:b][m]
    nx = np.r_[d[1:], BIG] if len(d) else d
    kk = (d <= R - 1) & ~(((nx - d) < SPEC["pair_days"]) & (nx <= R - 1))
    return int(kk.sum()), int((kk & (d >= R - SPEC["look_days"])).sum())


def pred_months(W, ranks, pinfo):
    """[E19] THE JOINED NAME-MONTHS PER SYMBOL (before any P&L; counts only) over the WF ranks' member-months (the symbol's World column a Nasdaq-100 member on the 1st of the rank's month). Per real CIK change: its predecessor CIK's releases joined ([E20]: by file), the
    member-months, how many are in the universe, how many READ a joined release (among the releases the rank counts: accepted r - 400 .. r - 1, [E3] point in time) and of those how many are in the universe; the four-releases rule ([P]: a release counted before the rank and
    >= 4 in the 400 days) WITH the join, WITHOUT it (the hole the join closes) and under the member-month reading (CHOICE, a REPORT: the join only at ranks whose month's 1st lies inside [first_8k_date, last_8k_date]), with the months it fails. Per row that is NOT a CIK
    change: its member-months, in the universe, and the first reason of the rest with their months (the holes, counted and listed) -> record"""
    ea = W.ea
    rt = ea.rt
    rec = {"pinned": bool(pinfo.get("pinned")), "text": pinfo.get("text", ""), "joins": [], "holes": []}
    if not rec["pinned"]:
        return rec
    col_of = {str(s): j for j, s in enumerate(np.asarray(W.syms).astype(str))}
    uni = {k: set(ea.uni[k].tolist()) for k in ranks}
    bpos = {k: {int(c): q for q, c in enumerate(ea.base[k])} for k in ranks}
    rule = lambda n_: n_[0] > 0 and n_[1] >= SPEC["min_rel"]
    mon = lambda k: ea.months[k][:7]
    listed = lambda s: [k for k in ranks if s in members_on(ea.mem, ea.months[k])]
    for jn in pinfo.get("joins", []):
        s, j = jn["symbol"], col_of.get(jn["symbol"])
        out = {**jn, "world_column": j is not None, "member_months": 0, "in_universe": 0, "joined_months": [], "joined_in_universe": 0, "fail_with": [], "fail_without": [], "fail_month_reading": []}
        if j is None:
            out["member_months"] = len(listed(s))
            rec["joins"].append(out)
            continue
        span = rt.span.get(str(ea.cik[j]))
        lo, hi = TS(jn["first_8k_date"]), TS(jn["last_8k_date_read"])
        for k in ranks:
            if not ea.member[k, j]:
                continue
            out["member_months"] += 1
            inu = j in uni[k]
            out["in_universe"] += int(inu)
            if span is None:
                for key in ("fail_with", "fail_without", "fail_month_reading"):
                    out[key].append(mon(k))
                continue
            a, b = span
            R = int(day_i(W.days[ea.r[k]]))
            pr = rt.pred[a:b]
            w_, o_ = rule(rel_counts(rt, a, b, R)), rule(rel_counts(rt, a, b, R, ~pr))
            kk = kept_at(rt, a, b, R) & (rt.d[a:b] >= R - SPEC["look_days"])
            if (kk & pr).any():
                out["joined_months"].append(mon(k))
                out["joined_in_universe"] += int(inu)
            for key, ok_ in (("fail_with", w_), ("fail_without", o_), ("fail_month_reading", w_ if lo <= TS(ea.months[k]) <= hi else o_)):
                if not ok_:
                    out[key].append(mon(k))
        rec["joins"].append(out)
    for h in pinfo.get("holes", []):
        s, j = h["symbol"], col_of.get(h["symbol"])
        out = {**h, "world_column": j is not None, "member_months": 0, "in_universe": 0, "out": {}}
        if j is None:
            out["member_months"] = len(listed(s))
            rec["holes"].append(out)
            continue
        why_m = defaultdict(list)
        for k in ranks:
            if not ea.member[k, j]:
                continue
            out["member_months"] += 1
            if j in uni[k]:
                out["in_universe"] += 1
                continue
            q = bpos[k].get(j)
            code = -1 if q is None else int(ea.first[k][q])
            why_m["outside RESMOM's liquidity screen" if q is None else UNI_REASONS[code] if 0 <= code < len(UNI_REASONS) else "second_class"].append(mon(k))
        out["out"] = {w_: {"n": len(v), "months": month_ranges(v)} for w_, v in why_m.items()}
        rec["holes"].append(out)
    return rec


def print_pred_months(pm, cinfo):
    """[E19]'s block: the list's text, [E20]'s file, per real CIK change the releases joined and the joined name-months, per row that is not a CIK change its holes"""
    print("[E19] THE JOINED NAME-MONTHS PER SYMBOL (BEFORE ANY P&L; counts only; the member-months of the WF ranks): " + pm["text"])
    if not pm["pinned"]:
        return
    pf = (cinfo.get("files") or {}).get("predecessors")
    print("  [E20] " + (f"the predecessors' releases {os.path.basename(pf['path'])} (sha256 {pf['sha256'][:16]}...): {pf['rows_on_file']:,} rows on file, {pf['rows_read']:,} read - ONE table with the calendar, no release (accession) in both" if pf else
                        "no predecessors' releases file is read (the calendar alone)"))
    for r_ in pm["joins"]:
        head = f"  {r_['symbol']} <- {r_['predecessor_cik']} {r_['predecessor_name']} (releases accepted {r_['first_8k_date']} .. {r_['last_8k_date_read']}" + (", the window clipped at the cut" if r_["clipped_at_the_cut"] else "") + f") -> {r_['successor_cik']}: "
        n_ = r_.get("releases_joined", 0)
        head += (f"{n_} releases joined ({r_.get('from_predecessors_file', 0)} from the predecessors' file, {r_.get('from_calendar', 0)} from the calendar; {r_.get('first')} .. {r_.get('last')}" + (f"; {r_['outside_the_window']} outside the window, not joined" if r_.get("outside_the_window") else "") + ")"
                 if n_ else "NOTHING TO JOIN (no release under the predecessor CIK in either file: its name-months stay as they were)")
        if not r_["world_column"]:
            print(head + f"; no World column - {r_['member_months']} member-months on the list, never in RESMOM's liquidity screen / not cached")
            continue
        print(head + f"; {r_['member_months']} member-months, {r_['in_universe']} in the universe; {len(r_['joined_months'])} read a joined release ({month_ranges(r_['joined_months']) or 'none'}), {r_['joined_in_universe']} of them in the universe; the four-releases rule "
              f"fails in {len(r_['fail_with'])} with the join ({month_ranges(r_['fail_with']) or 'none'}), {len(r_['fail_without'])} without it ({month_ranges(r_['fail_without']) or 'none'}), {len(r_['fail_month_reading'])} under the member-month reading "
              f"(a REPORT, never used: {month_ranges(r_['fail_month_reading']) or 'none'})")
    print("  NOT CIK changes - they join nothing and stay holes ([E19]; counted and listed): " + "; ".join(
        f"{h['symbol']} ({h['note']}): " + (f"no World column - {h['member_months']} member-months on the list, never in RESMOM's liquidity screen / not cached" if not h["world_column"] else
                                            f"{h['member_months']} member-months, {h['in_universe']} in the universe" + "".join(f"; {w_} {v['n']} ({v['months']})" for w_, v in sorted(h["out"].items(), key=lambda kv: -kv[1]["n"])))
        for h in pm["holes"]))


def universe_table(W, ranks):
    """per rank (counts only): the liquidity screen, the full window, the members, the joined, four releases, [E1], the universe, DUE / NOT-DUE, [E1]'s dropped classes by symbol"""
    ea = W.ea
    out = []
    for k in ranks:
        c = ea.cnt[k]
        out.append({"rank": f"{W.days[ea.r[k]]:%Y-%m-%d}", "year": int(jyear(W.days[[ea.r[k]]])[0]), "liquidity": c["liquidity"], **{lab: int(c.get(lab, 0)) for lab in UNI_REASONS}, "universe": c["universe"], "due": int(ea.due[k].sum()),
                    "not_due": int((~ea.due[k]).sum()), "second_class_dropped": [f"{W.syms[d]} (for {W.syms[kk]})" for d, kk in ea.drops[k]]})
    return out


def print_universe(tab):
    print("the universe per rank (BEFORE ANY P&L; first reasons of the liquidity-screen names: " + ", ".join(f"{lab} = {UNI_TEXT[lab]}" for lab in UNI_REASONS) + "):")
    by = defaultdict(list)
    for t in tab:
        by[t["year"]].append(t)
    for y, v in sorted(by.items()):
        u, d, n = [t["universe"] for t in v], [t["due"] for t in v], [t["not_due"] for t in v]
        print(f"  {yl(y)}: {len(v)} ranks, universe min / median / max {min(u)} / {int(np.median(u))} / {max(u)}, DUE {min(d)} / {int(np.median(d))} / {max(d)}, NOT-DUE {min(n)} / {int(np.median(n))} / {max(n)}")
    for t in tab:
        print(f"    {t['rank']}: liquidity {t['liquidity']}, -" + ", -".join(f"{t[lab]} {lab}" for lab in UNI_REASONS if t[lab]) + f" -> universe {t['universe']}: DUE {t['due']} / NOT-DUE {t['not_due']}"
              + (f"; [E1] dropped {', '.join(t['second_class_dropped'])}" if t["second_class_dropped"] else ""))


def print_calendar(info, W, pairs, ranks):
    """[D1] the calendar as read (counts): releases per year, [E2]'s 8-K/A, the timing, per name (the names ever in a WF universe: releases accepted before the cut), [E3]'s pairs by name"""
    ea = W.ea
    fl = info.get("files") or {}
    print(f"[D1] TV's EDGAR earnings calendar {os.path.basename(info['path'])} sha256 {info['sha256'][:16]}... (the registered file)" + (f" + [E20] the predecessors' releases {os.path.basename(fl['predecessors']['path'])} sha256 {fl['predecessors']['sha256'][:16]}..., ONE table"
          if "predecessors" in fl else "") + f"; {info['rows_on_file']:,} rows on file" + (" (" + " + ".join(f"{v['rows_on_file']:,}" for v in fl.values()) + ")" if len(fl) > 1 else "") + f", {info['rows_read']:,} read (accepted {info['first']} .. {info['last']}; "
          f"{info['dropped_accepted_on_or_after_the_cut']:,} accepted on / after the cut and {info['dropped_reaction_on_or_after_the_cut']:,} more reacting on / after it dropped at read [E15]; {info['unreadable']} unreadable), {info['companies']} CIKs; forms {info['forms']}; "
          f"timing {info['timing']}")
    print("  releases per year (8-K item 2.02, [E2] the 8-K/A rows apart - dropped from [P]): " + "; ".join(f"{y}: {n:,}" + (f" (+{info['amendments_by_year'][y]} 8-K/A)" if info["amendments_by_year"].get(y) else "") for y, n in info["releases_by_year"].items())
          + f"; {info['amendments_dropped_e2']} 8-K/A rows dropped [E2]")
    seen = sorted({int(j) for k in ranks for j in ea.uni[k]})
    rows = []
    for j in seen:
        a, b = ea.rt.span[ea.cik[j]]
        rows.append(f"{W.syms[j]} {b - a}")
    print(f"  releases per name (the {len(seen)} names ever in a WF universe: releases [P] reads, accepted before the cut): " + ", ".join(rows))
    print(f"  [E3] the pairs of releases less than {SPEC['pair_days']} days apart - the LATER counts ({len(pairs)}): " + "; ".join(f"{p['ticker']} {p['earlier']} -> {p['later']} ({p['gap_days']}d" + (", joined [E19]" if p.get("joined") else "") + ")" for p in pairs))
    if ea.rt.n_pred_rows:
        print(f"  [E19] {ea.rt.n_pred_rows} predecessor-CIK releases joined to their successors through the pinned list (each once; the joined name-months per symbol below)")


def print_events(W, Lw, years):
    """W's events per year (entry year) with every first reason, the open positions per session (min / median / max by July-June year), [E26]: ES's own sessions without a return (printed) and the events whose beta window reached back past them"""
    keys = ("candidates", "unresolved") + W_REASONS + ("events", "beta_reached_back")
    print("W's events per year of the entry session (BEFORE ANY P&L; candidates = the predicted dates of universe names at the rank before the entry whose window exits in WF; first reasons: " + " / ".join(keys[2:-2]) + "; [E9] / [E26] no beta = the name lacks its own return on "
          "one of the 252 most recent sessions before the entry on which ES has a return, no zero-beta fallback; beta_reached_back = events whose window reached back past an ES hole):")
    for y, c in sorted(Lw.cnt.items()):
        print(f"  {y}: " + ", ".join(f"{k_} {c.get(k_, 0):,}" for k_ in keys))
    tot = sum((Counter(c) for c in Lw.cnt.values()), Counter())
    print(f"  all: {tot.get('events', 0):,} events ({tot.get('events', 0) / years:.0f} a year over the WF stretch)")
    wfm = np.asarray((W.days >= WF0) & (W.days <= PRE_END))
    hole = np.flatnonzero(~np.isfinite(np.asarray(W.es.ret, float)) & wfm)
    print(f"  [E26] ES has no close-to-close return on {len(hole)} WF session(s)" + (f" ({', '.join(f'{W.days[t]:%Y-%m-%d}' for t in hole)})" if len(hole) else "") + ": every beta window (W's [E9], [E11]'s moved entries, M's [E13]) counts the 252 most recent "
          f"sessions on which ES has a return, reaching back past them; {tot.get('beta_reached_back', 0):,} events' windows reached back")
    ev = Lw.ev
    if ev.n:
        d = np.bincount(ev.e, minlength=W.T + 1) - np.bincount(ev.x + 1, minlength=W.T + 1)
        op = np.cumsum(d)[:W.T]
        wf = np.asarray((W.days >= WF0) & (W.days <= PRE_END))
        jy = jyear(W.days)
        print("  open W positions per session by July-June year (min / median / max over the WF sessions): " + "; ".join(f"{yl(y)} {int(op[wf & (jy == y)].min())} / {int(np.median(op[wf & (jy == y)]))} / {int(op[wf & (jy == y)].max())}"
                                                                                                              for y in YEARS if (wf & (jy == y)).any()))


# ------------------------------------------------------------------ the statistics, the judge, A2 over L, DD5, dollars a year, the beta credit rule
def stat_run(B, rows, run, lo=None, hi=None, series=None, years=None):
    """r15's cell statistics on one stretch (default WF) of a run's daily series (series: another daily series on the stock sessions with the run's position table; years: the July-June years of the breadth check, default the nine WF years) -> (stats, the series on #463's
    index, the positions held per row)"""
    lo, hi = (WF0 if lo is None else lo), (PRE_END if hi is None else hi)
    xB, cB = D15.to_B(run.x if series is None else series, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    return D15.cell_stats(B, xB, cB, lo, hi, run, years=YEARS if years is None else years), xB, cB


def per_year(net, years):
    """dollars a year beside every ROC (MANAGER #100): net / the stretch's years (the house yardstick's years)"""
    return float(net) / float(years) if years and np.isfinite(years) and years > 0 else float("nan")


def dd5_rec(B, x, lo=None, hi=None):
    """DD5 beside a ROC @ $30k (owner rule 2026-10-07, MANAGER #120; NETISS's dd5_rec): the mean depth of the 5 deepest drawdown episodes of the daily series x (#463's index) over [lo, hi] (default WF), the worst drawdown and the one-episode flag (worst > 1.3 x DD5)"""
    k = B.mask(WF0 if lo is None else lo, PRE_END if hi is None else hi)
    r = _dd5(pd.Series(np.asarray(x, float)[k], index=B.index[k]))
    return {"dd5": float(r["dd5_usd"]), "n": int(r["n"]), "max_dd": float(r["max_dd"]), "one_episode": bool(r["one_episode"])}


def dd5_txt(d):
    return f"DD5 ${d['dd5']:,.0f}" + (" - driven by one episode" if d["one_episode"] else "")


def a2_report(B, xB, ref, lo=None):
    """STAGE A2 (WF) - a REPORT, never a pass route: L (the S1-restated #463 + 0.264 x RES) + c x the cell against L, c by VOLATILITY on 2017-01-03 .. 2018-12-31 (25% of #463's daily std over those rows / the cell's: r17_resmom's A2 code through r18_divrun's a2_report),
    0.5c and 2c reported, the plain #463 + c x the cell a reported row; an incremental pass = ROC @ $30k AND Sortino both strictly above L's. Dollars a year (MANAGER #100) and DD5 (owner rule 2026-10-07) beside every ROC. lo after WF0 = [E25]'s sensitivity: a2_stretch"""
    if lo is not None and TS(lo) > WF0:
        return a2_stretch(B, xB, ref, lo)
    with patched(DV, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        a = DV.a2_report(B, xB, ref)
    yrs = float(ref.stats["years"])
    a["reference"]["usd_year"] = per_year(a["reference"]["net"], yrs)
    a["reference"]["dd5"] = dd5_rec(B, ref.raw)
    raw, xb = np.asarray(ref.raw, float), np.asarray(xB, float)
    c = a.get("c", float("nan"))
    if np.isfinite(c) and c > 0:
        a["usd_year"], a["dd5"] = per_year(a["net"], yrs), dd5_rec(B, raw + c * xb)
        for key, m in (("at_half_c", A2_REPORT[0]), ("at_double_c", A2_REPORT[1])):
            a[key]["usd_year"], a[key]["dd5"] = per_year(a[key]["net"], yrs), dd5_rec(B, raw + m * c * xb)
        pl = a["plain_463"]
        pl["usd_year"], pl["dd5"] = per_year(pl["net"], yrs), dd5_rec(B, np.asarray(B.raw, float) + c * xb)
    return a


def a2_window(lo):
    """[E25] CHOICE: the sensitivity's A2 window = the registered one clipped to start on its stretch's first day (2017-07-01 .. 2018-12-31): c is set on the stretch's own days, never on the days it leaves out"""
    return (max(A2_WIN[0], TS(lo)), A2_WIN[1])


def a2_stretch(B, xB, ref, lo):
    """[E25] A2 on the sensitivity stretch [lo, PRE_END]: c by the registered volatility rule on a2_window(lo); L + c x the cell (and at 0.5c / 2c) against L, both read on the stretch (ref = stretch_ref's: L's numbers on it), an incremental pass = ROC @ $30k AND Sortino
    both strictly above L's on the stretch; dollars a year and DD5 beside every ROC (no plain-#463 row: a report the full window carries)"""
    with patched(DV, A2_WIN=a2_window(lo), A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        plain = DV.plain_a2(B, xB)
    r, nan = ref.stats, float("nan")
    yrs = float(r["years"])
    raw, xb = np.asarray(ref.raw, float), np.asarray(xB, float)
    out = {k: plain[k] for k in ("window", "rows", "target", "std_book", "std_cell", "c")}
    out["reference"] = {"roc": float(r["roc"]), "sortino": float(r["sort"]), "net": float(r["net"]), "max_dd": float(r["max_dd"]), "weight_of_RES": DV.REF_W, "usd_year": per_year(r["net"], yrs), "dd5": dd5_rec(B, raw, lo)}
    c = plain["c"]
    if not (np.isfinite(c) and c > 0):
        out.update({"roc": nan, "sortino": nan, "net": nan, "max_dd": nan, "incremental_pass": False, "book_shadow_line": False, "at_half_c": None, "at_double_c": None, "error": plain.get("error", "no c: the cell has no spread over the window")})
        return out
    at = DV.ref_at(B, ref, xB, c, lo, PRE_END)
    ok = DV.incremental_pass(at, r)
    out.update({"roc": at["roc"], "sortino": at["sortino"], "net": at["net"], "max_dd": at["max_dd"], "roc_gain": at["roc"] - float(r["roc"]), "sortino_gain": at["sortino"] - float(r["sort"]), "incremental_pass": ok, "book_shadow_line": ok,
                "usd_year": per_year(at["net"], yrs), "dd5": dd5_rec(B, raw + c * xb, lo)})
    for key, m in (("at_half_c", A2_REPORT[0]), ("at_double_c", A2_REPORT[1])):
        a_ = DV.ref_at(B, ref, xB, m * c, lo, PRE_END)
        a_.update(usd_year=per_year(a_["net"], yrs), dd5=dd5_rec(B, raw + m * c * xb, lo))
        out[key] = a_
    return out


def plain_a2(B, xB):
    """the registered volatility rule for c (r18_divrun's plain_a2 = r17_resmom's A2 code) on 2017-01-03 .. 2018-12-31; Stage B recomputes the frozen c with it"""
    with patched(DV, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.plain_a2(B, xB)


def notional_series(W, cell, L):
    """one side's notional held on each stock session (T,): M = the mean of the two sides' dollars of the rebalance held ((L$ + S$) / 2 on rows f .. x), W = the long dollars ($4,000 x the events held, rows e .. x)"""
    s = np.zeros(W.T)
    if cell == "M":
        for rec in L.recs:
            if rec.traded:
                s[rec.f:rec.x + 1] += 0.5 * (rec.L_usd + rec.S_usd)
    else:
        ev = L.ev
        if ev.n:
            d = np.bincount(ev.e, minlength=W.T + 1) - np.bincount(ev.x + 1, minlength=W.T + 1)
            s = SPEC["w_slot"] * np.cumsum(d)[:W.T].astype(float)
    return s


def beta_credit(B, ref, W, rows, xB, side, lo=None):
    """A2's beta rule: the cell's realised beta to ES (its daily $ P&L on ES's daily return, r15's es_beta) on L's drawdown days ('R's days') and on every WF day, per $ of ONE SIDE's notional (CHOICE: the mean one-side notional held over the WF sessions with a
    position, notional_series); |beta| > 0.20 on either = the drawdown profile reported, never credited (a beta that cannot be computed refuses the credit). lo: the stretch's first day ([E25]: ref's stretch with it)"""
    k = B.mask(WF0 if lo is None else lo, PRE_END)
    sB = D15.to_B(side, rows, B.n)[k]
    den = float(sB[sB > 0].mean()) if (sB > 0).any() else float("nan")
    with np.errstate(all="ignore"):
        eb = D15.es_beta(B, ref.S, W, rows, xB)
    dd, al = eb["DD days"]["usd_per_1.00_es"] / den, eb["all WF days"]["usd_per_1.00_es"] / den
    ok = bool(np.isfinite(dd) and np.isfinite(al) and abs(dd) <= BETA_CAP and abs(al) <= BETA_CAP)
    return {"side_notional": den, "beta_L_dd_days": float(dd), "beta_all_days": float(al), "cap": BETA_CAP, "within_cap": ok, "es_beta_on_L_days": eb}


def judge_cell(cell, st, net10, nul, hedged_roc=None, n_years=9):
    """Stage A for one cell: (a) M >= 60 traded rebalances, W >= 500 events; (b) WF ROC @ $30k >= 15 and net > 0 at 5 AND at 10 bps a side; (c) [E12] above the null's 97.5th percentile - M: the random-name null's (the MAX over the 2 cells), W: the random-name null's AND
    [E11] the time-shift null's (W's own ROC); (d) positive in >= 6 of the 9 July-June WF years and net > 0 without 2020-02-15 .. 2020-04-30; (e) profitable without its best 1% of days AND without its best 1% of name-periods (M: name-months, W: events); [E13] M also
    needs M hedged with ES by its ex-ante beta gap at WF ROC @ $30k >= 15. (f), the hand audit, is never decided here. A NaN fails every comparison it enters. n_years: the stretch's July-June years (9; [E25]'s sensitivity: 8 - CHOICE: the bar stays >= 6)"""
    R = RULES
    q = f"p{R['pctl']:g}"
    chk = {}
    if cell == "M":
        chk[f"traded rebalances>={R['m_reb']}"] = st["n_units"] >= R["m_reb"]
    else:
        chk[f"events>={R['w_events']}"] = st["n_pos"] >= R["w_events"]
    chk[f"ROC>={R['roc']:g}"] = st["roc"] >= R["roc"]
    chk["net>0 at 5 bps"] = (st["net"] > 0) if R["net_pos"] else True
    chk["net>0 at 10 bps"] = (net10 > 0) if R["stress"] else True
    chk[f"ROC>random-name null {q}"] = (st["roc"] > nul["roc_max"][q]) if R["null"] else True
    if cell == "W":
        chk[f"ROC>time-shift null {q}"] = (st["roc"] > nul["time_shift"]["roc"][q]) if R["null"] else True
    chk[f"positive in >={R['years']} of {n_years} July-June years"] = st["years_pos"] >= R["years"]
    chk["net>0 without Feb 15 - Apr 30 2020"] = (st["net_ex2020"] > 0) if R["ex2020"] else True
    chk["profitable without its best 1% of days"] = (st["net_ex_best_days"] > 0) if R["exbest"] else True
    chk["profitable without its best 1% of " + ("name-months" if cell == "M" else "events")] = (st["net_ex_best_pos"] > 0) if R["exbest"] else True
    if cell == "M":
        chk[f"[E13] M hedged by its beta gap ROC>={R['roc']:g}"] = (hedged_roc >= R["roc"]) if R["m_hedged"] else True
    return {k: bool(v) for k, v in chk.items()}


def pick_candidate(cells, passing):
    """CHOICE (the prereg names no tie-break between two passing cells; A2 is only a report): the passing cell with the higher WF standalone ROC @ $30k goes to Stage B (ties: M first); the other is reported"""
    return max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: passing = the cells that clear (a) - (e) (+ [E13] for M); the candidate = pick_candidate(passing); (f), the hand audit, is never decided here - every passing cell awaits it and Stage B needs the lead's go-flag"""
    passing = [c for c in CELLS if cells[c].get("PASS")]
    return passing, pick_candidate(cells, passing)


def govern(cells_full, cells_sens):
    """[E25] the STRICTER of the two verdicts governs, pure: a cell passes only when it clears (a) - (e) (+ [E13]) on BOTH the full WF window and the sensitivity without 2016-17 (a FAIL in either fails); the candidate = pick_candidate among those (the higher full-window
    WF ROC, a tie to M) -> {pass_full, pass_sensitivity, pass_cells (governing), candidate, differ}"""
    pf, ps = stage_a_flow(cells_full)[0], stage_a_flow(cells_sens)[0]
    both = [c for c in CELLS if c in pf and c in ps]
    return {"pass_full": pf, "pass_sensitivity": ps, "pass_cells": both, "candidate": pick_candidate(cells_full, both), "differ": pf != ps}


def sens_years(lo):
    """the WF July-June years a stretch starting on lo holds whole (the full window: the nine 2016-17 .. 2024-25; [E25]'s sensitivity: the eight from 2017-18)"""
    y0 = int(jyear(pd.DatetimeIndex([TS(lo)]))[0])
    return tuple(y for y in YEARS if y >= y0)


def sens_bounds(W, lo):
    """[E25] CHOICE: the sensitivity keeps exactly the positions / events ENTERED on or after lo (none straddles the cut, so no day before it carries P&L): the exit bounds that select them (the legs are selected by exit) - M: the exit of the first built rank whose
    fill is on / after lo (exits rise with the ranks); W: the session 5 after the first session on / after lo (an event exits w_pre + w_post sessions after its entry) -> (M's lo, W's lo, the first session's row)"""
    ea = W.ea
    t0 = int(np.searchsorted(np.asarray(W.days), np.datetime64(TS(lo))))
    far = TS("2262-01-01")
    ks = [k for k in range(len(ea.r)) if ea.f[k] >= t0 and ea.x[k] >= 0]
    tw = t0 + SPEC["w_pre"] + SPEC["w_post"]
    return (W.days[ea.x[ks[0]]] if ks else far), (W.days[tw] if tw < W.T else far), t0


def stretch_ref(B, ref, lo):
    """[E25] #463 and L re-read on the sensitivity stretch [lo, PRE_END]: #463's r12_mdl.Stretch on it (the nulls' ROC, SEAT) and L with its Stretch (drawdown days, the R-day sum), its r11_risk numbers and drawdown structure on it (A2, the beta credit) -> (S12, ref)"""
    k = np.flatnonzero(B.mask(lo, PRE_END))
    S_ = M12.Stretch(ref.raw, B.index, None, lo, PRE_END)
    r2 = SimpleNamespace(**{**vars(ref), "S": S_, "stats": R11.stats(np.asarray(ref.raw, float)[k], B.index[k]), "structure": DV.ref_structure(S_), "rows": k})
    return M12.Stretch(np.asarray(B.raw, float), B.index, None, lo, PRE_END), r2


# ------------------------------------------------------------------ one reading of Stage A: the legs -> the cells -> the cost rows -> the nulls -> the checks -> A2
def evaluate(W, B, S12, ref, rows, mode, nreps, vcode=0, full=False, lo=None):
    """one reading of Stage A on the WF stretch. mode 'close' = the JUDGED reading [E16] (no in-hold event removes a name; a spin-off / stock-dividend ex-date inside the hold / window closes the position at the close before it; the nulls draw the same cut paths), 'keep' =
    the REPORTED removal reading (null-less). nreps > 0 draws the nulls (vcode picks the random streams: M [20261019, 0, vcode], W [20261019, 1, vcode], W's time shift [20261020, 1, vcode]) and judges (a) - (e); full = also the reports' rows (sides, borrow / survivorship
    stress, M's [E13] hedged twin, W's unhedged / hedge legs, the halves) -> (summary, objects). lo = the stretch's first day: None = WF0, the full WF window as registered; [E25]'s sensitivity passes 2017-07-01 with S12 / ref re-read on its stretch (stretch_ref):
    the legs keep the positions / events ENTERED on or after it (sens_bounds), and every statistic, the cost rows, DD5, A2 (a2_stretch), the beta credit and both nulls (the same seeds; [E11]'s moved windows may not start before it) read [lo, PRE_END]"""
    lo = WF0 if lo is None else TS(lo)
    hi = PRE_END
    if lo > WF0:
        lo_m, lo_w, t0 = sens_bounds(W, lo)
    else:
        lo_m, lo_w, t0 = lo, lo, 0
    yrs = sens_years(lo)
    legs = {"M": m_build(W, lo_m, hi, mode), "W": w_build(W, lo_w, hi, mode)}
    runf = {"M": lambda cfg, **kw: m_run(W, legs["M"], cfg, **kw), "W": lambda cfg, **kw: w_run(W, legs["W"], cfg, **kw)}
    runs, series, summ, side_x = {}, {}, {}, {}
    for cell in CELLS:
        base = runf[cell](D15.l1_cfg(), pos=True)
        st, xB, cB = stat_run(B, rows, base, lo, hi, years=yrs)
        runs[cell], series[cell] = base, (xB, cB)
        at = lambda cfg, cell=cell, **kw: stat_run(B, rows, runf[cell](cfg, **kw), lo, hi, years=yrs)[0]
        c = {"base": st, "n_years": len(yrs), "stretch": [f"{lo:%Y-%m-%d}", f"{hi:%Y-%m-%d}"], "usd_year": per_year(st["net"], st["years"]), "dd5": dd5_rec(B, xB, lo, hi),
             "cost_curve": {f"{b:g} bps": (st if b == COST_BPS else at(D15.l1_cfg(bps=b))) for b in COST_CURVE}, "seat": D15.seat_measure(S12, xB), "seat_ref": D15.seat_measure(ref.S, xB), "A2": a2_report(B, xB, ref, lo),
             "first_day": first_rank_day(W, legs[cell])}
        c["stress"] = {f"{b:g} bps": c["cost_curve"][f"{b:g} bps"] for b in STRESS_BPS}
        c["beta"] = beta_credit(B, ref, W, rows, xB, notional_series(W, cell, legs[cell]), lo)
        c["A2"]["credited"] = bool(c["beta"]["within_cap"])
        c["A2"]["incremental_credit"] = bool(c["A2"]["incremental_pass"] and c["beta"]["within_cap"])
        c["rday"] = float(xB[ref.S.rows][ref.S.dd].sum())                             # the R-day sum: CHOICE R's days = L's drawdown days on MDL r1's episode rule (the qualifying episodes, the day after the peak .. the trough)
        if cell == "M":
            hr = m_run(W, legs["M"], D15.l1_cfg(), hedged=True)
            sh = stat_run(B, rows, hr, lo, hi, years=yrs)[0]
            c["hedged"] = {"base": sh, "usd_year": per_year(sh["net"], sh["years"]), "unhedged_rebalances": hr.unhedged_rebalances}
        if full:
            c["sub"] = {lab: stat_run(B, rows, sub_run(W, legs[cell], base, a, b), a, b)[0] for lab, a, b in SUBPERIODS}
            if cell == "M":
                c["sides"] = {}
                for nm, sd in (("long side only", 1), ("short side only", -1)):
                    s_, sx, _ = stat_run(B, rows, m_run(W, legs["M"], D15.l1_cfg(), side=sd))
                    c["sides"][nm], side_x[sd] = s_, sx
                ex = {f"borrow {BORROW_STRESS[0]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[0])), f"borrow {BORROW_STRESS[1]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[1])),
                      "longs that stop printing valued at -100%": D15.l1_cfg(lose100=True), "shorts that stop printing valued at zero [R2]": {**D15.l1_cfg(), "short0": True}}
                c["extra"] = {nm: at(cfg) for nm, cfg in ex.items()}
            else:
                c["unhedged"] = stat_run(B, rows, w_run(W, legs["W"], D15.l1_cfg(), hedge=False))[0]
                c["hedge_leg"] = stat_run(B, rows, w_run(W, legs["W"], D15.l1_cfg(), stock=False))[0]
                c["extra"] = {"longs that stop printing valued at -100%": at(D15.l1_cfg(lose100=True))}
        summ[cell] = c
    nul = None
    if nreps:
        accm = m_null(W, legs["M"], nreps, np.random.default_rng([SEED, 0, vcode]))
        accw = w_null(W, legs["W"], nreps, np.random.default_rng([SEED, 1, vcode]))
        acct, left = w_shift_null(W, legs["W"], nreps, np.random.default_rng([SEED_SHIFT, 1, vcode]), t_min=t0)
        rn_roc, rn_rday = {}, {}
        for cell, acc in (("M", accm), ("W", accw)):
            rn_roc[cell], rn_rday[cell] = null_stats(S12, ref.S, acc, rows, B.n)
        ts_roc, ts_rday = null_stats(S12, ref.S, acct, rows, B.n)
        nul = null_summary(rn_roc, rn_rday, ts_roc, ts_rday, left)
        for cell in CELLS:
            c = summ[cell]
            c["checks"] = judge_cell(cell, c["base"], c["stress"]["10 bps"]["net"], nul, c["hedged"]["base"]["roc"] if cell == "M" else None, n_years=len(yrs))
            c["PASS"] = bool(all(c["checks"].values()))
            c["rday_null"] = {"random_name_p95": nul["rday_by_cell"][cell]["p95"], **({"time_shift_p95": nul["time_shift"]["rday"]["p95"]} if cell == "W" else {})}
    return {"variant": mode, "stretch": [f"{lo:%Y-%m-%d}", f"{hi:%Y-%m-%d}"], "cells": summ, "null": nul}, SimpleNamespace(legs=legs, runs=runs, series=series, side_x=side_x)


def first_rank_day(W, L):
    """[E15] the cell's first TRADED RANK (CHOICE: M = the rank session of its first traded rebalance; W = the rank session before its first event's entry) -> 'YYYY-MM-DD', None without one"""
    if L.kind == "M":
        r = next((rec.r for rec in L.recs if rec.traded), None)
    else:
        r = int(W.ea.r[L.ev.k].min()) if L.ev.n else None
    return None if r is None else f"{W.days[r]:%Y-%m-%d}"


def sub_run(W, L, run, lo, hi):
    """the same run with the position table cut to the positions that EXIT in [lo, hi] (a sub-period: positions by exit date, the daily series by session date)"""
    p = run.pos
    if L.kind == "M":
        dx = np.asarray(W.days)[[L.recs[int(i)].x for i in p.rec]] if len(p.rec) else np.zeros(0, "datetime64[ns]")
    else:
        dx = np.asarray(W.days)[L.ev.x] if L.ev.n else np.zeros(0, "datetime64[ns]")
    m = (dx >= np.datetime64(lo)) & (dx <= np.datetime64(hi))
    return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=int(m.sum()), n_units=(len({int(i) for i in p.rec[m]}) if L.kind == "M" else int(m.sum())), pos=SimpleNamespace(pnl=np.asarray(p.pnl, float)[m]))


# ------------------------------------------------------------------ the reports and the diagnostics (never a pass route)
def peak_days(W, ranks=None):
    """[E13] / [E14] the PEAK REPORTING WEEKS: the ISO weeks in which at least 10 universe names have an ACTUAL release (the calendar's reaction session - a report, never an input; CHOICE: a name counts when it is in the universe at the rank before its release's month) ->
    (T,) bool over the stock sessions (every session of such a week), the set of (iso year, week) keys"""
    ea = W.ea
    ranks = list(range(len(ea.r))) if ranks is None else ranks
    act = actual_rows(W)
    iso = W.days.isocalendar()
    wk = iso["year"].to_numpy().astype(np.int64) * 100 + iso["week"].to_numpy().astype(np.int64)
    n = Counter()
    for k in ranks:
        r, rn = int(ea.r[k]), int(ea.r_next[k])
        for j in ea.uni[k]:
            a = act.get(str(ea.cik[j]))
            if a is not None:
                for t in a[(a >= r + 1) & (a <= rn)]:
                    n[int(wk[t])] += 1
    keys = {w for w, v in n.items() if v >= SPEC["peak_names"]}
    return np.isin(wk, list(keys)), keys


def week_keys(dates):
    iso = pd.DatetimeIndex(dates).isocalendar()
    return iso["year"].to_numpy().astype(np.int64) * 100 + iso["week"].to_numpy().astype(np.int64)


def seat_e14(B, S12, ref, xs, peak_keys):
    """[E14] SEAT, printed before any correlation: per stretch (WF) each cell's P&L inside each of #463's and L's 5 DEEPEST drawdown episodes (R11.underwater on the stretch; CHOICE: the DD days from the day after the peak to the trough, r15's episodes_table convention), and the
    share of those episodes' ISO weeks that are peak reporting weeks against the share of all WF weeks. xs = {cell: daily P&L on #463's index}"""
    k = B.mask(WF0, PRE_END)
    allw = np.unique(week_keys(B.index[k]))
    base = float(np.isin(allw, list(peak_keys)).mean()) if len(allw) else float("nan")
    out = {"base_share_peak_weeks": base, "books": {}}
    for nm, Sx in (("#463", S12), ("L", ref.S)):
        rows_ = []
        for e in Sx.episodes[:5]:
            rr = Sx.rows[e["i0"]:e["it"] + 1]
            wks = np.unique(week_keys(B.index[rr]))
            rows_.append({"peak": e["peak"], "trough": e["trough"], "depth": float(e["depth"]), "dd_days": int(len(rr)), "weeks": int(len(wks)), "peak_weeks": int(np.isin(wks, list(peak_keys)).sum()),
                          "share_peak_weeks": float(np.isin(wks, list(peak_keys)).mean()) if len(wks) else float("nan"), "book_pnl": float(Sx.x[e["i0"]:e["it"] + 1].sum()), "cells": {c: float(np.asarray(xs[c], float)[rr].sum()) for c in xs}})
        out["books"][nm] = rows_
    return out


def print_seat(se):
    print(f"[E14] SEAT (WF; printed before any correlation): each cell's P&L inside the 5 DEEPEST drawdown episodes of #463 and of L (the DD days: the day after the peak .. the trough), and the share of each episode's ISO weeks that are PEAK REPORTING WEEKS (>= {SPEC['peak_names']} "
          f"universe names with an actual release) against {se['base_share_peak_weeks']:.0%} of all WF weeks:")
    for nm, rows_ in se["books"].items():
        for e in rows_:
            print(f"  {nm} {e['peak']} -> {e['trough']} (${e['depth']:,.0f}, {e['dd_days']} DD days, the book ${e['book_pnl']:,.0f}): " + ", ".join(f"{c} ${v:,.0f}" for c, v in e["cells"].items())
                  + f"; peak reporting weeks {e['peak_weeks']} of {e['weeks']} ({e['share_peak_weeks']:.0%})")


def tilt_e10(B, W, rows, xB, nq_ret, notional):
    """[E10] W'S GROWTH TILT (reported, never the verdict): W's daily $ P&L regressed (OLS, an intercept) on N_t x ES's return and N_t x (NQ's return - ES's), close to close, over the WF sessions on which W holds a position - N_t = W's long dollars held that session
    (CHOICE: the regressors are scaled by the dollars held, so both slopes are 'per $ long'); if |the NQ-minus-ES loading| > 0.20 per $ long, W's ROC @ $30k with that tilt removed (the daily P&L less the loading x N_t x (NQ - ES)) is printed beside the raw one,
    with the 2019-21 and 2022 rows apart (CHOICE: calendar years)"""
    k = B.mask(WF0, PRE_END)
    es, nq = D15.to_B(np.asarray(W.es.ret, float), rows, B.n), D15.to_B(np.asarray(nq_ret, float), rows, B.n)
    nB = D15.to_B(notional, rows, B.n)
    sel = k & (nB > 0) & np.isfinite(es) & np.isfinite(nq)
    out = {"days": int(sel.sum()), "cap": TILT_CAP}
    if sel.sum() < 10:
        out.update({"loading_nq_minus_es": float("nan"), "beta_es": float("nan"), "over_cap": False})
        return out
    X = np.column_stack([np.ones(sel.sum()), nB[sel] * es[sel], nB[sel] * (nq[sel] - es[sel])])
    b = np.linalg.lstsq(X, np.asarray(xB, float)[sel], rcond=None)[0]
    out.update({"beta_es": float(b[1]), "loading_nq_minus_es": float(b[2]), "over_cap": bool(abs(b[2]) > TILT_CAP)})
    adj = np.asarray(xB, float).copy()
    adj[sel] -= b[2] * nB[sel] * (nq[sel] - es[sel])
    rows_ = {}
    for lab, a, z in (("WF", WF0, PRE_END),) + TILT_ROWS:
        m = B.mask(a, z)
        s0, s1 = R11.stats(np.asarray(xB, float)[m], B.index[m]) or {}, R11.stats(adj[m], B.index[m]) or {}
        rows_[lab] = {"raw_net": s0.get("net", float("nan")), "raw_roc": s0.get("roc", float("nan")), "tilt_removed_net": s1.get("net", float("nan")), "tilt_removed_roc": s1.get("roc", float("nan"))}
    out["rows"] = rows_
    return out


def season_beta(B, W, rows, xB, peak, notional):
    """[E13] M's realised ES beta on REPORTING-SEASON days (the sessions of the peak reporting weeks) apart from the other days (Savor & Wilson's channel): the OLS slope of the cell's daily $ P&L on ES's daily return over each set of WF days with a position, per $ of
    one side's notional (notional_series' mean over the set)"""
    k = B.mask(WF0, PRE_END)
    es, pk, nB = D15.to_B(np.asarray(W.es.ret, float), rows, B.n), D15.to_B(np.asarray(peak, float), rows, B.n) > 0, D15.to_B(notional, rows, B.n)
    out = {}
    for lab, m in (("peak reporting weeks", pk), ("other days", ~pk)):
        sel = k & m & (nB > 0) & np.isfinite(es)
        if sel.sum() < 10 or not np.ptp(es[sel]) > 0:
            out[lab] = {"days": int(sel.sum()), "beta_per_usd": float("nan")}
            continue
        b = np.polyfit(es[sel], np.asarray(xB, float)[sel], 1)[0]
        out[lab] = {"days": int(sel.sum()), "usd_per_1.00_es": float(b), "beta_per_usd": float(b / nB[sel].mean())}
    return out


def live_stretch(B, ref, xB, c, first_day):
    """[E15] THE LIVE STRETCH: the WF book numbers - #463, L, L + c x the cell, the plain #463 + c x the cell - on the cell's live stretch (from its first traded rank, first_rank_day, printed) beside the full-WF numbers"""
    out = {"first_day": first_day}
    for lab, lo in (("live", TS(first_day) if first_day else WF0), ("full WF", WF0)):
        k = B.mask(lo, PRE_END)
        st = lambda x: R11.stats(np.asarray(x, float)[k], B.index[k]) or {}
        rows_ = {"#463": st(B.raw), "L": st(ref.raw)}
        if np.isfinite(c) and c > 0:
            rows_["L + c x cell"] = st(np.asarray(ref.raw, float) + c * np.asarray(xB, float))
            rows_["#463 + c x cell"] = st(np.asarray(B.raw, float) + c * np.asarray(xB, float))
        out[lab] = {nm: {"roc": s.get("roc", float("nan")), "sortino": s.get("sort", float("nan")), "net": s.get("net", float("nan")), "max_dd": s.get("max_dd", float("nan"))} for nm, s in rows_.items()}
    return out


def event_path(W, Lw):
    """the EVENT-TIME PATH of W's positions (reported, never traded): the hedged, cost-free mean abnormal return per session p + tau (tau = -10 .. +10; r - the event's beta x ES, r = the split-safe TOTAL daily return, r17_resmom's W.Rd), N per tau; and of the same
    names around their ACTUAL release (CHOICE: each event's nearest actual reaction session a of its CIK within 10 sessions of p - an event with none is counted apart - on a + tau). Returns bps"""
    ev = Lw.ev
    taus = np.arange(SPEC["path_lo"], SPEC["path_hi"] + 1)
    act = actual_rows(W)
    T = W.T

    def line(anchor, col, beta):
        if not len(anchor):
            return np.full(len(taus), np.nan), np.zeros(len(taus), np.int64)
        rr = anchor[:, None] + taus[None, :]
        rc = np.clip(rr, 0, T - 1)
        ok = (rr >= 0) & (rr <= T - 1)
        with np.errstate(invalid="ignore"):
            A = np.where(ok, np.asarray(W.Rd, float)[rc, col[:, None]] - beta[:, None] * np.asarray(W.es.ret, float)[rc], np.nan)
        n = np.isfinite(A).sum(axis=0)
        with np.errstate(invalid="ignore"):
            return np.where(n > 0, np.nansum(A, axis=0) / np.maximum(n, 1), np.nan) * 1e4, n
    mp, np_ = line(ev.p, ev.col, ev.beta)
    an, keep = [], []
    for i in range(ev.n):
        a = act.get(str(W.ea.cik[ev.col[i]]))
        if a is None or not len(a):
            continue
        j = int(a[np.argmin(np.abs(a - ev.p[i]))])
        if abs(j - int(ev.p[i])) <= SPEC["path_hi"]:
            an.append(j)
            keep.append(i)
    keep = np.asarray(keep, np.int64)
    ma, na = line(np.asarray(an, np.int64), ev.col[keep], ev.beta[keep]) if len(keep) else (np.full(len(taus), np.nan), np.zeros(len(taus), np.int64))
    return {"taus": taus.tolist(), "predicted": {"mean_bps": mp.tolist(), "n": np_.tolist(), "events": int(ev.n)}, "actual": {"mean_bps": ma.tolist(), "n": na.tolist(), "events": int(len(keep)), "no_actual_within_10": int(ev.n - len(keep))}}


def print_path(pth):
    t = pth["taus"]
    print(f"EVENT-TIME PATH of W's positions (the hedged, cost-free mean abnormal return per session, bps; reported, never traded) around the PREDICTED date p ({pth['predicted']['events']:,} events) and around the same names' ACTUAL release "
          f"({pth['actual']['events']:,} events with an actual release within 10 sessions of p; {pth['actual']['no_actual_within_10']:,} without):")
    print("  tau        " + " ".join(f"{int(v):>5d}" for v in t))
    for lab, key in (("p + tau   ", "predicted"), ("a + tau   ", "actual")):
        print(f"  {lab} " + " ".join(f"{v:>5.1f}" if np.isfinite(v) else "    ." for v in pth[key]["mean_bps"]))


def edrift_months(path=None):
    """EDRIFT r1's cells as its Stage A file holds them (the monthly nets reports.months.{V3, V5}: its daily series was never exported) -> ({cell: pd.Series by 'YYYY-MM'}, info); a missing / unreadable file -> (None, why)"""
    p = path or EDRIFT_JSON
    if not os.path.exists(p):
        return None, {"on_file": False, "text": f"EDRIFT r1's Stage A file is not on file ({p}): no correlation with its cells"}
    try:
        j = json.load(open(p))
        mo = j["reports"]["months"]
        out = {c: pd.Series({k_: float(v) for k_, v in mo[c].items()}) for c in EDRIFT_CELLS if c in mo}
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, {"on_file": True, "text": f"EDRIFT r1's Stage A file is unreadable ({type(e).__name__}): no correlation with its cells"}
    return out, {"on_file": True, "path": p, "sha256": M17.sha_raw(p)}


def correlations(B, ref, xs, legs_meta, edr):
    """the correlation with RES (daily, L's RES column on the WF rows), with EDRIFT r1's cells (CHOICE: monthly - its Stage A file keeps only the monthly nets) and with each #463 leg (r13_attn.corrs, daily). xs = {cell: daily P&L on #463's index}"""
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    out = {}
    for c, x in xs.items():
        a = np.asarray(x, float)[k]
        rs = np.asarray(ref.res, float)[k]
        with np.errstate(invalid="ignore", divide="ignore"):
            o = {"RES_daily": float(np.corrcoef(a, rs)[0, 1]) if np.ptp(a) > 0 and np.ptp(rs) > 0 else float("nan"), "legs": A13.corrs(B, x, legs_meta, WF0, PRE_END) if legs_meta else {}}
        if edr is not None:
            mon = pd.Series(a, index=B.index[k]).groupby(B.index[k].strftime("%Y-%m")).sum()
            for ec, s in edr.items():
                j = pd.concat([mon.rename("a"), s.rename("b")], axis=1, join="inner")
                o[f"EDRIFT_{ec}_monthly"] = float(j["a"].corr(j["b"])) if len(j) > 2 else float("nan")
                o[f"EDRIFT_{ec}_months"] = int(len(j))
        out[c] = o
    return out


def season_months(B, x):
    """the reporting-season months (January / April / July / October) apart from the others: the cell's net and its mean per month over the WF sessions of each group"""
    k = B.mask(WF0, PRE_END)
    ds, xs = B.index[k], np.asarray(x, float)[k]
    mon = pd.Series(xs, index=ds).groupby(ds.to_period("M")).sum()
    sm = mon.index.month.isin(SEASON_MONTHS)
    return {lab: {"months": int(m.sum()), "net": float(mon[m].sum()), "mean_per_month": float(mon[m].mean()) if m.any() else float("nan")} for lab, m in (("season (Jan / Apr / Jul / Oct)", sm), ("other months", ~sm))}


def top_rows(W, L, run, n=20, largest=True):
    """the n largest name-period gains (largest) or losses of a cell with their dates: M = name-months (symbol, side, fill / exit), W = events (symbol, entry / exit, p)"""
    p = run.pos
    if p is None or not len(p.pnl):
        return []
    o = np.argsort(-np.asarray(p.pnl, float) if largest else np.asarray(p.pnl, float), kind="stable")[:n]
    out = []
    for i in o:
        if L.kind == "M":
            rec = L.recs[int(p.rec[i])]
            out.append({"symbol": str(W.syms[int(p.col[i])]), "side": "long" if p.side[i] > 0 else "short", "fill": f"{W.days[rec.f]:%Y-%m-%d}", "exit": f"{W.days[rec.x]:%Y-%m-%d}", "pnl": float(p.pnl[i])})
        else:
            ev = L.ev
            out.append({"symbol": str(W.syms[int(ev.col[i])]), "entry": f"{W.days[ev.e[i]]:%Y-%m-%d}", "exit": f"{W.days[ev.x[i]]:%Y-%m-%d}", "p": f"{W.days[ev.p[i]]:%Y-%m-%d}", "pnl": float(p.pnl[i])})
    return out


def beta_gap_rows(W, Lm):
    """[E13] M's ex-ante beta gap at every traded rank (long minus short: the names' OLS ES betas over r-251 .. r, side-dollar weighted - equal names: the sides' means) and the book's dollar beta - printed before any P&L (betas, not P&L)"""
    out = []
    for rec in Lm.recs:
        if rec.traded:
            g, du = m_hedge_usd(rec)
            out.append({"rank": f"{W.days[rec.r]:%Y-%m-%d}", "nL": rec.nL, "nS": rec.nS, "L_usd": rec.L_usd, "S_usd": rec.S_usd, "beta_gap": g, "dollar_beta": du})
    return out


def print_beta_gap(rows_):
    g = np.array([r_["beta_gap"] for r_ in rows_], float)
    print(f"[E13] M's ex-ante BETA GAP (long minus short; the names' OLS ES betas over the 252 sessions to the rank close, side-dollar weighted) at every traded rank, before any P&L: {len(rows_)} ranks, mean {np.nanmean(g) if len(g) else float('nan'):+.3f}, "
          f"range {np.nanmin(g) if len(g) else float('nan'):+.3f} .. {np.nanmax(g) if len(g) else float('nan'):+.3f}; per rank (gap / the book's dollar beta = the [E13] hedge): " + "; ".join(f"{r_['rank']} {r_['beta_gap']:+.2f} / ${r_['dollar_beta']:,.0f}" for r_ in rows_))


def reports(W, B, S12, ref, rows, obj, summ, legs_meta, nq_ret, peak, peak_keys, edr):
    """everything the prereg's DIAGNOSTICS list (never a pass route), for the judged reading: [E14] SEAT, L's drawdown-episode table, the July-June rows (in summ), the halves (in summ), the long / short sides (M, in summ), W's event-time paths, the prediction accuracy by year
    (pre-P&L), the realised beta to ES, the correlations (RES, EDRIFT r1, #463's legs), the season months, the 20 largest name-period gains AND losses; [E10] W's tilt, [E13] M's season-day beta, [E15] the live stretch"""
    xs = {c: obj.series[c][0] for c in CELLS}
    rep = {"seat_e14": seat_e14(B, S12, ref, xs, peak_keys)}
    rep["episodes_L"] = {c: D15.episodes_table(ref.S, xs[c]) for c in CELLS}
    rep["beta_to_es"] = {c: D15.es_beta(B, S12, W, rows, xs[c]) for c in CELLS}
    rep["correlations"] = correlations(B, ref, xs, legs_meta, edr)
    rep["season_months"] = {c: season_months(B, xs[c]) for c in CELLS}
    rep["top20_gains"] = {c: top_rows(W, obj.legs[c], obj.runs[c], 20, True) for c in CELLS}
    rep["top20_losses"] = {c: top_rows(W, obj.legs[c], obj.runs[c], 20, False) for c in CELLS}
    rep["event_path"] = event_path(W, obj.legs["W"])
    rep["tilt_e10"] = tilt_e10(B, W, rows, xs["W"], nq_ret, notional_series(W, "W", obj.legs["W"]))
    rep["season_beta_e13"] = season_beta(B, W, rows, xs["M"], peak, notional_series(W, "M", obj.legs["M"]))
    rep["live_stretch_e15"] = {c: live_stretch(B, ref, xs[c], summ[c]["A2"].get("c", float("nan")), summ[c]["first_day"]) for c in CELLS}
    return rep


# ------------------------------------------------------------------ the hand audit (f): read, apply, status, the candidates' rows
AUDIT_FILE, CANDS_FILE, STAGE_A_FILE, STAGE_B_FILE = "eap_audit.csv", "eap_audit_candidates.csv", "eap_stageA.json", "eap_stageB.json"


def read_audit(path=None):
    """OUT\\eap_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that position from its cell AND the cell's nulls before anything is computed [(f)]. CHOICE: the key is the cell's own
    entry date - M: the FILL session (r17_resmom's key: the name-month at that rebalance, whatever its side), W: the ENTRY session (the event of that name entered that session) - exactly the 'date' of eap_audit_candidates.csv. Refuses a verdict / cell / date it cannot read
    (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, AUDIT_FILE)
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: {AUDIT_FILE} lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: {AUDIT_FILE} line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


def apply_audit(W, audit):
    """the audit's data_event rows on the World as removals: M rows on W.aud1 (fill session, name - m_one reads it), W rows on W.audw (entry session, name - w_build / w_pool read it). A data_event row that matches no session or no name of this data refuses -> counts"""
    W.aud1[:] = False
    W.audw[:] = False
    W.aud_hit.clear()
    if audit is None:
        return {"rows": 0, "keep": 0, "data_event": 0, "data_event_M": 0, "data_event_W": 0}
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    ev = (audit["verdict"] == "data_event").to_numpy()
    bad = np.flatnonzero(ev & ((di < 0) | (ci < 0)))
    if len(bad):
        refuse(f"refused: {AUDIT_FILE} data_event line(s) {[int(i) + 2 for i in bad][:10]} match no session or no name of this data (M: the FILL session, W: the ENTRY session; the symbol must be one the universe ever held) - fix the file (nothing computed, lockbox NOT read)")
    cm = (audit["cell"] == "M").to_numpy()
    for i in np.flatnonzero(ev):
        (W.aud1 if cm[i] else W.audw)[di[i], ci[i]] = True
    return {"rows": int(len(audit)), "keep": int((~ev).sum()), "data_event": int(ev.sum()), "data_event_M": int((ev & cm).sum()), "data_event_W": int((ev & ~cm).sum())}


def unused_audit_rows(W, audit):
    """data_event rows that removed nothing in the judged build (the name was not in that rebalance's / event's set): reported, so a wrong date cannot pass unnoticed"""
    if audit is None:
        return []
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    return [f"{audit['symbol'].iat[i]} {audit['date'].iat[i]:%Y-%m-%d} {audit['cell'].iat[i]}" for i in range(len(audit))
            if audit["verdict"].iat[i] == "data_event" and ((AUD if audit["cell"].iat[i] == "M" else AUD_W), int(di[i]), int(ci[i])) not in W.aud_hit]


def audit_status(cands, audit):
    """per cell: how many of the listed top-50 contributors appear in eap_audit.csv (symbol + date + cell); audit_complete = every listed one does. (f) itself is the lead's: the harness never decides it"""
    have = set() if audit is None else set(zip(audit["symbol"], audit["date"].dt.strftime("%Y-%m-%d"), audit["cell"]))
    out = {}
    for cell, rows_ in cands.items():
        n = sum((r_["symbol"], r_["date"], cell) in have for r_ in rows_)
        out[cell] = {"listed": len(rows_), "audited": int(n), "audit_complete": bool(len(rows_) > 0 and n == len(rows_))}
    return out


def candidate_rows(W, L, cell, run, status, n=AUDIT_N):
    """(f) the n largest single-name P&L contributors of a cell (CHOICE, r17_resmom's: the largest GAINS - a fake gain works for a pass) with what the hand audit needs - 'each one's predicted and actual dates, its fills and marks': symbol, CIK, date (M: the fill
    session, W: the entry session - the audit file's key), the rank, the exit, side, dollars, P&L (W: the stock leg and the hedge apart, the beta), the PREDICTED date(s) that made the position and the releases they came from (acceptance date, accession), the
    nearest ACTUAL release (reaction session) to each and the gap in sessions, the actual releases inside the hold, the fill (raw and split-safe open), the exit (raw open), the split-safe closes of the hold (the marks), [E16]'s close, the hygiene flags and the
    largest split-safe daily return in the hold, the asset status"""
    p = run.pos
    if p is None or not len(p.pnl):
        return []
    ea, rt = W.ea, W.ea.rt
    act = actual_rows(W)
    fmt = lambda t: f"{W.days[int(t)]:%Y-%m-%d}"
    out = []
    for rank, i in enumerate(np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n], 1):
        if L.kind == "M":
            rec = L.recs[int(p.rec[i])]
            col, f, x, k = int(p.col[i]), rec.f, rec.x, rec.k
            rels = [int(ri) for j, ri in ea.due_p[k] if j == col]
            q = int(np.flatnonzero(rec.pool == col)[0])
            cl, side, extra = int(rec.close[q]), ("long" if p.side[i] > 0 else "short"), {}
        else:
            ev = L.ev
            col, f, x, k = int(ev.col[i]), int(ev.e[i]), int(ev.x[i]), int(ev.k[i])
            rels, cl, side = [int(ev.rel[i])], int(ev.close[i]), "long"
            extra = {"stock_pnl": float(p.stock[i]), "hedge_pnl": float(p.hedge[i]), "beta": float(ev.beta[i])}
        a = act.get(str(ea.cik[col]), np.zeros(0, np.int64))
        preds = [int(rt.p_row[ri]) for ri in rels]
        near = [int(a[np.argmin(np.abs(a - pr))]) if len(a) else -1 for pr in preds]
        xe = cl if cl >= 0 else x
        dr = W.Rn[f + 1:xe + 1, col] if xe > f else np.zeros(0)
        jx = int(np.nanargmax(np.abs(dr))) if np.isfinite(dr).any() else -1
        fl = W.hyg(f, x, np.array([col]))[:, 0]
        out.append({"cell": cell, "rank": rank, "symbol": str(W.syms[col]), "cik": str(ea.cik[col]), "date": fmt(f), "rank_date": fmt(ea.r[k]), "exit": fmt(x), "side": side, "usd": float(p.usd[i]), "pnl": float(p.pnl[i]), **extra,
                    "predicted": ";".join(fmt(pr) for pr in preds), "predicted_from_release": ";".join(f"{dstr(rt.d[ri])} {rt.accession[ri]}" for ri in rels),
                    "actual_nearest": ";".join(fmt(t) if t >= 0 else "" for t in near), "actual_gap_sessions": ";".join(str(t - pr) if t >= 0 else "" for t, pr in zip(near, preds)),
                    "actual_in_hold": ";".join(fmt(t) for t in a[(a >= f) & (a <= x)]), "fill_open_raw": float(W.Od[f, col]), "fill_open_adj": float(W.Ao[f, col]), "exit_open_raw": float(W.Od[x, col]),
                    "marks_adj": ";".join(f"{v:.4f}" for v in W.Ac[f:x, col]), "closed_before_spin": fmt(cl) if cl >= 0 else "", "flags_in_hold": "+".join(h for h, v in zip(HYG, fl) if v),
                    "spin_or_stock_dividend_in_hold": bool(W.SPN[f + 1:x + 1, col].any()), "max_abs_daily_return_in_hold": float(dr[jx]) if jx >= 0 else float("nan"), "max_abs_daily_return_date": fmt(f + 1 + jx) if jx >= 0 else "",
                    "asset_status": status.get(str(W.syms[col]), "unknown")})
    return out


# ------------------------------------------------------------------ the printouts
def row(cell, c):
    s = c["base"]
    unit = "rebalances" if cell == "M" else "events"
    return (f"{cell} {unit} {s['n_units']:>5,} positions {s['n_pos']:>6,} net ${s['net']:>11,.0f} (${c['usd_year']:>9,.0f} a year) ROC@30k {s['roc']:>7.1f} / {dd5_txt(c['dd5'])} Sortino {s['sortino']:>6.2f} maxDD ${s['max_dd']:>9,.0f}; "
            f"positive in {s['years_pos']} of {c.get('n_years', 9)} July-June years")


def print_rday(res, rep, ref):
    """THE R-DAY SUM FIRST (the prereg's DIAGNOSTICS, before every other P&L line): each cell's P&L inside L's drawdown days against its null's p95, and L's drawdown-episode table with the cell's P&L inside each episode"""
    g = ref.structure
    print(f"THE R-DAY SUM FIRST - each cell's P&L inside L's drawdown days ({g['days']} DD days of L's {g['episodes']} qualifying episodes, MDL r1's rule) against its null's p95 (a REPORT):")
    for cell in CELLS:
        c = res["cells"][cell]
        nl = c.get("rday_null") or {}
        print(f"  {cell}: ${c['rday']:,.0f} against the random-name null's p95 ${nl.get('random_name_p95', float('nan')):,.0f}" + (f" and the time-shift null's p95 ${nl['time_shift_p95']:,.0f}" if "time_shift_p95" in nl else ""))
    print("  L's drawdown episodes (qualifying; the DD days: the day after the peak .. the trough) - the cell's P&L inside each: first DD day .. trough, depth, DD days, L's P&L | " + " | ".join(CELLS))
    for q, e in enumerate(rep["episodes_L"][CELLS[0]]):
        print(f"    {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days']} d, L {e['book_pnl']:+,.0f}) | " + " | ".join(f"{rep['episodes_L'][c][q]['cell_pnl']:+,.0f}" for c in CELLS))


def print_cells(res, audit_st=None):
    nul = res["null"]
    q = f"p{RULES['pctl']:g}"
    print(f"  null 1 - RANDOM NAMES ({nul['draws']} draws, seed {nul['seed']}; the statistic = the MAX over the 2 cells of WF ROC@30k): p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f} {q} {nul['roc_max'][q]:.1f}; each cell alone p50 / {q}: "
          + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c][q]:.1f}" for c in CELLS))
    ts = nul["time_shift"]
    print(f"  null 2 [E11] - W's TIME SHIFT ({ts['draws']} draws, seed {ts['seed']}; each event's window moved back {SPEC['shift_lo']} .. {SPEC['shift_hi']} sessions; W's own WF ROC@30k): p5 {ts['roc']['p5']:.1f} p50 {ts['roc']['p50']:.1f} p95 {ts['roc']['p95']:.1f} {q} {ts['roc'][q]:.1f}; "
          f"events sitting out a draw (their moved window unavailable): mean {ts['left_out_per_draw_mean']:.1f}, max {ts['left_out_per_draw_max']}")
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        print("  " + row(cell, c))
        print("        cost curve: " + ", ".join(f"{k} net ${v['net']:,.0f} ROC@30k {v['roc']:.1f}" for k, v in c["cost_curve"].items()) + "; by July-June year: " + " ".join(f"{yl(y)}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()))
        if cell == "M":
            h = c["hedged"]
            print(f"        [E13] M HEDGED with ES by its ex-ante dollar beta (re-set at each rank, 0.5 bps a side): net ${h['base']['net']:,.0f} (${h['usd_year']:,.0f} a year) ROC@30k {h['base']['roc']:.1f} Sortino {h['base']['sortino']:.2f} "
                  f"({h['unhedged_rebalances']} rebalance(s) without a defined hedge) - the bar: >= {RULES['roc']:g}")
        au = None if audit_st is None else audit_st[cell]
        print(f"        Stage A (a)-(e){' + [E13]' if cell == 'M' else ''} {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}" + ("" if au is None else f"; hand audit (f): {au['audited']}/{au['listed']} of the top-{AUDIT_N} listed in {AUDIT_FILE}"))


def print_keep(resK, cells, LkM, LkW):
    """[E16] the removal reading 'keep' beside the judged one, as a REPORT with its count, null-less"""
    cm = sum((Counter(c_) for c_ in LkM.cnt.values()), Counter())
    cw = sum((Counter(c_) for c_ in LkW.cnt.values()), Counter())
    print(f"  {LAB_K}, no null - it removed M {cm.get('post_calendar_split', 0):,} name-months for an announced split and {cm.get('post_spin', 0):,} for a spin-off / stock-dividend ex-date inside the hold; W {cw.get('post_calendar_split', 0):,} and "
          f"{cw.get('post_spin', 0):,} events inside the window:")
    for cell in CELLS:
        k = resK["cells"][cell]
        print(f"    {row(cell, k)} | the judged net ${cells[cell]['base']['net']:,.0f} against this reading's ${k['base']['net']:,.0f}")


def print_a2(cells):
    print("A2 (WF) - a REPORT, never a pass route: L + c x the cell against L (c by volatility: 25% of #463's daily std / the cell's over 2017-01-03 .. 2018-12-31); dollars a year and DD5 beside every ROC; the beta credit rule (|beta| <= 0.20 per $ of one side's notional on L's DD days AND all WF days)")
    for cell in CELLS:
        c = cells[cell]
        a2, b = c["A2"], c["beta"]
        print(f"  {cell} realised beta to ES per $ of one side's notional (${b['side_notional']:,.0f}, the mean held): L's DD days {b['beta_L_dd_days']:+.3f}, all WF days {b['beta_all_days']:+.3f} -> " + ("may be credited" if b["within_cap"] else "NOT CREDITED: the drawdown profile is reported, no incremental credit"))
        if a2.get("at_half_c"):
            rf, pl = a2["reference"], a2["plain_463"]
            print(f"     c x{a2['c']:.4g} (cell std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f}): L + c x cell ROC@30k {a2['roc']:.2f} / {dd5_txt(a2['dd5'])} (${a2['usd_year']:,.0f} a year) Sortino {a2['sortino']:.3f} against L's {rf['roc']:.2f} / {dd5_txt(rf['dd5'])} "
                  f"(${rf['usd_year']:,.0f} a year) / {rf['sortino']:.3f} -> " + ("INCREMENTAL PASS (both above, credited): MANAGER #70's route follows" if a2["incremental_credit"] else ("the numbers pass but the beta rule refuses the credit" if a2["incremental_pass"] else "no incremental pass"))
                  + f"; at 0.5c {a2['at_half_c']['roc']:.2f} / {dd5_txt(a2['at_half_c']['dd5'])} (${a2['at_half_c']['usd_year']:,.0f} a year) / {a2['at_half_c']['sortino']:.3f}, at 2c {a2['at_double_c']['roc']:.2f} / {dd5_txt(a2['at_double_c']['dd5'])} "
                  f"(${a2['at_double_c']['usd_year']:,.0f} a year) / {a2['at_double_c']['sortino']:.3f}; the plain #463 + c x cell (a reported row) {pl['roc']:.2f} / {dd5_txt(pl['dd5'])} (${pl['usd_year']:,.0f} a year) / {pl['sortino']:.3f}")
        else:
            print(f"     {a2.get('error', 'no c')} -> no incremental pass")


def print_sens(resS, gov):
    """[E25] the sensitivity without 2016-17, printed beside the full window's verdict: its nulls and cells (every check), A2 on its stretch, and the governing verdict (the stricter)"""
    lo, hi = resS["stretch"]
    print(f"[E25] SENSITIVITY - Stage A again with 2016-17 dropped: the positions / events entered and the days before {lo} left out; every check (a) - (e), both nulls (the same seeds), A2 and DD5 re-read on {lo} .. {hi}:")
    print_cells(resS)
    for cell in CELLS:
        a2 = resS["cells"][cell]["A2"]
        if a2.get("at_half_c"):
            rf = a2["reference"]
            print(f"  {cell} A2 on the stretch (a report; c x{a2['c']:.4g} on {a2['window'][0]} .. {a2['window'][1]}): L + c x cell {a2['roc']:.2f} / {dd5_txt(a2['dd5'])} (${a2['usd_year']:,.0f} a year) / {a2['sortino']:.3f} against L's {rf['roc']:.2f} / "
                  f"{dd5_txt(rf['dd5'])} (${rf['usd_year']:,.0f} a year) / {rf['sortino']:.3f} -> " + ("an incremental pass" if a2["incremental_pass"] else "no incremental pass"))
        else:
            print(f"  {cell} A2 on the stretch: {a2.get('error', 'no c')}")
    pv = lambda p: ", ".join(p) if p else "no cell"
    print(f"  [E25] VERDICTS: the full WF window passes {pv(gov['pass_full'])}; without 2016-17 {pv(gov['pass_sensitivity'])} -> " + (f"THEY DIFFER: the STRICTER governs - {pv(gov['pass_cells'])} passes" if gov["differ"] else f"the same: {pv(gov['pass_cells'])} passes"))


def print_live(rep):
    print("[E15] THE LIVE STRETCH - the WF book numbers from each cell's first traded rank (printed) beside the full-WF numbers (ROC@30k / Sortino / net / maxDD):")
    for cell in CELLS:
        ls = rep["live_stretch_e15"][cell]
        print(f"  {cell} (first traded rank {ls['first_day']}):")
        for lab in ("live", "full WF"):
            print(f"    {lab:<7}: " + "; ".join(f"{nm} {v['roc']:.2f} / {v['sortino']:.3f} / ${v['net']:,.0f} / ${v['max_dd']:,.0f}" for nm, v in ls[lab].items()))


def print_reports(rep, cells):
    """the DIAGNOSTICS (none a pass route), in the prereg's order after the R-day sum and SEAT: the halves, the sides (M), W's legs, the event-time paths, the realised beta to ES, [E10], [E13], the correlations, the season months, the 20 largest gains and losses"""
    print("DIAGNOSTICS - the judged reading, WF; none of this is a pass route")
    for cell in CELLS:
        c = cells[cell]
        print(f"  {cell} halves: " + "; ".join(f"{lab} net ${v['net']:,.0f} ROC@30k {v['roc']:.1f} ({v['n_pos']:,} positions exited)" for lab, v in c["sub"].items()))
        print(f"  {cell} stress rows: " + ", ".join(f"{k} ${v['net']:,.0f}" for k, v in c["extra"].items()))
    for nm, v in cells["M"]["sides"].items():
        print(f"  M {nm}: net ${v['net']:,.0f} ROC@30k {v['roc']:.1f} maxDD ${v['max_dd']:,.0f}; by July-June year " + " ".join(f"{yl(y)}:{x:+,.0f}" for y, x in v["by_year"].items()))
    w = cells["W"]
    print(f"  W the stock leg alone (unhedged): net ${w['unhedged']['net']:,.0f} ROC@30k {w['unhedged']['roc']:.1f}; the ES hedge leg alone: net ${w['hedge_leg']['net']:,.0f}")
    print_path(rep["event_path"])
    b = rep["beta_to_es"]
    print("  realised beta to ES ($ per 1% ES move; #463's DD days / DD weeks / all WF days): " + "; ".join(
        f"{c} {b[c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[c]['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    t = rep["tilt_e10"]
    print(f"[E10] W's GROWTH TILT (W's daily $ P&L on N_t x ES's return and N_t x (NQ - ES)'s, close to close, {t['days']} WF days with a position): the NQ-minus-ES loading {t['loading_nq_minus_es']:+.3f} per $ long (ES {t['beta_es']:+.3f}) - "
          + (f"OVER {TILT_CAP:.2f}: the tilt-removed ROC beside the raw one: " + "; ".join(f"{lab} raw {v['raw_roc']:.1f} (${v['raw_net']:,.0f}) / tilt removed {v['tilt_removed_roc']:.1f} (${v['tilt_removed_net']:,.0f})" for lab, v in t["rows"].items())
             if t.get("over_cap") else f"within {TILT_CAP:.2f}: " + "; ".join(f"{lab} raw {v['raw_roc']:.1f} / tilt removed {v['tilt_removed_roc']:.1f}" for lab, v in (t.get("rows") or {}).items())) + " (reported, never the verdict)")
    sb = rep["season_beta_e13"]
    print("[E13] M's realised ES beta per $ of one side's notional on the PEAK REPORTING WEEKS' sessions apart from the other days: " + "; ".join(f"{lab} {v['beta_per_usd']:+.3f} ({v['days']} days)" for lab, v in sb.items()))
    cr = rep["correlations"]
    for c in CELLS:
        print(f"  {c} correlation: RES daily {cr[c]['RES_daily']:+.3f}; " + "; ".join(f"{k} {v:+.3f}" for k, v in cr[c].items() if k.startswith("EDRIFT") and k.endswith("monthly")) + "; #463 and its legs " + ", ".join(f"{k} {v:+.3f}" for k, v in cr[c]["legs"].items()))
    for c in CELLS:
        print(f"  {c} season months: " + "; ".join(f"{lab} {v['months']} months net ${v['net']:,.0f} (${v['mean_per_month']:,.0f} a month)" for lab, v in rep["season_months"][c].items()))
    for c in CELLS:
        for lab, key in (("gains", "top20_gains"), ("losses", "top20_losses")):
            print(f"  {c} the 20 largest name-period {lab}: " + "; ".join(f"{r_['symbol']} {r_.get('fill', r_.get('entry'))} ${r_['pnl']:,.0f}" for r_ in rep[key][c]))


def print_m_counts(label, cnt):
    keys = ("rebalances", "traded", "thin", "empty", "universe", "due", "no_fill", "audit", "post_calendar_split", "post_spin", "pool", "kept_flagged", "kept_calendar_split", "closed_spin", "unresolved", "warmup")
    keys = [k for k in keys if any(k in c for c in cnt.values())]
    print(f"  M {label} by fill year (columns: " + " / ".join(keys) + "):")
    for y, c in sorted(cnt.items()):
        print(f"    {y}: " + " ".join(f"{c.get(k, 0):,}" for k in keys))


def years_of(W):
    """the WF stretch's years on the stock sessions (the house yardstick's: the first to the last WF session / 365.25)"""
    d = W.days[(W.days >= WF0) & (W.days <= PRE_END)]
    return float((d[-1] - d[0]).days / 365.25) if len(d) > 1 else float("nan")


def pre_pnl(W, cinfo, minfo, pinfo, mp, es_meta=None, nq_meta=None, nq_ret=None):
    """BEFORE ANY P&L (the prereg's list + [E3] / [E5] / [E6] / [E7] / [E13]'s beta gap / [E19]): counts only - the calendar per year / per name, the [E3] pairs, the names joined / not joined by reason, [E19]'s joined name-months per symbol, the universe per rank, DUE / NOT-DUE, [E1]'s dropped classes, W's events per year and
    the open positions per session, [E5] accuracy both ways (with the STOP), [E6] turnover and the break-even spread, [E7] the power line; with betas on the World (Stage A) also [E13]'s ex-ante beta gap per rank. Builds the legs WITHOUT unit paths (no price is costed,
    no P&L exists) -> the records"""
    ranks = wf_ranks(W)
    ea = W.ea
    print(f"BEFORE ANY P&L - THE CALENDAR, THE UNIVERSE, THE DUE LISTS, THE EVENTS (counts only; {len(ranks)} WF ranks from {W.days[ea.r[ranks[0]]]:%Y-%m-%d}, {ea.n_warm} earlier month-ends are warm-up: no full 252-session window)" if ranks else "BEFORE ANY P&L - no WF rank")
    print(f"[D2] the Nasdaq-100 members file {os.path.basename(minfo['path'])} (LF sha256 {minfo['sha256_lf'][:16]}...): {minfo['rows_read']:,} intervals read of {minfo['rows_on_file']:,}, {minfo['tickers']} tickers; the symbol -> CIK map (NETISS's pinned files, sha {mp.info['sha256']['map'][:8]} / {mp.info['sha256']['map_add'][:8]}): "
          f"{mp.info['rows']:,} symbols, {mp.info['usable_symbols']:,} usable ({mp.info['usable_ciks']:,} CIKs), by method {mp.info['by_method']}")
    if es_meta is not None:
        print(f"ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}; the 09:30 / 16:00 prints carried over holes: {W.es_carried}")
    if nq_meta is not None:
        print(f"[E10] NQ masters {nq_meta['raw']['filename']} (sha256 {nq_meta['raw'].get('sha256')}) / {nq_meta['adj']['filename']} (sha256 {nq_meta['adj'].get('sha256')}); an NQ close-to-close return on {int(np.isfinite(nq_ret).sum()):,} of {W.T:,} sessions")
    pairs = pairs_list(ea.rt)
    print_calendar(cinfo, W, pairs, ranks)
    mm = member_months(W, ranks)
    print_member_months(mm)
    pm = pred_months(W, ranks, pinfo)
    print_pred_months(pm, cinfo)
    ut = universe_table(W, ranks)
    print_universe(ut)
    LmJ, LmK = m_build(W, WF0, PRE_END, JUDGED, units=False), m_build(W, WF0, PRE_END, REPORT_MODE, units=False)
    LwJ, LwK = w_build(W, WF0, PRE_END, JUDGED, units=False), w_build(W, WF0, PRE_END, REPORT_MODE, units=False)
    print(f"M's rebalances: {len(LmJ.recs)} in WF ({sum(r_.traded for r_ in LmJ.recs)} traded: both sides >= {SPEC['min_side']} names; a side's dollars = min(${SPEC['side_usd']:,.0f}, ${SPEC['name_cap']:,.0f} x its count) [E8])")
    print_m_counts(LAB_J, LmJ.cnt)
    print_m_counts(LAB_K, LmK.cnt)
    yrs = years_of(W)
    print_events(W, LwJ, yrs)
    ck = sum((Counter(c_) for c_ in LwK.cnt.values()), Counter())
    print(f"  W {LAB_K}: {ck.get('events', 0):,} events ({ck.get('post_calendar_split', 0):,} removed for an announced split, {ck.get('post_spin', 0):,} for a spin-off / stock-dividend ex-date inside the window); the judged reading closes "
          f"{sum(c_.get('closed_spin', 0) for c_ in LwJ.cnt.values()):,} windows at the close before such an ex-date")
    acc = accuracy(W, ranks)
    print_accuracy(acc)
    tv = turnover(W, LmJ)
    print_turnover(tv)
    pw = power_line(W, LmJ, LwJ.ev.n, yrs)
    print_power(pw)
    rec = {"ranks": len(ranks), "warmup_month_ends": ea.n_warm, "calendar": cinfo, "pairs_e3": pairs, "member_months": mm, "e19_joined_name_months": pm, "universe": ut, "m_counts": {y: dict(c) for y, c in sorted(LmJ.cnt.items())},
           "m_counts_keep": {y: dict(c) for y, c in sorted(LmK.cnt.items())}, "w_counts": {y: dict(c) for y, c in sorted(LwJ.cnt.items())}, "w_counts_keep": {y: dict(c) for y, c in sorted(LwK.cnt.items())},
           "accuracy": acc, "turnover": {k: v for k, v in tv.items() if k != "rows"}, "turnover_rows": tv["rows"], "power": pw, "events_wf": int(LwJ.ev.n), "wf_years": yrs}
    if ea.beta is not None:
        bg = beta_gap_rows(W, LmJ)
        print_beta_gap(bg)
        rec["beta_gap_e13"] = bg
    return rec


# ------------------------------------------------------------------ the data a stage reads (every input cut at read)
def load_inputs(cut, enforce=True, counts_only=False):
    """every input of a stage, cut at `cut` (S.LB0: Stage A and the dryload; S.END: Stage B) and the World with W.ea: the wide corporate-actions calendar (r17_resmom), the earnings calendar + [E20]'s predecessors' releases (one table), the map, the members file, [E19]'s list (checked against
    the table and the map: pred_check), the SIPORB data, TBIS, ES (+ its 09:30 prints), NQ
    ([E10]; not in Stage B), the calendar's splits on the grid. enforce=False (the dryload): an unregistered wide calendar / earnings calendar is reported, not refused (the earnings calendar is then not read and nothing past the World is counted) -> namespace"""
    cal, winfo = M17.wide_load(cut, need=enforce, enforce=enforce)
    calf, cinfo = cal_load(cut, enforce=enforce)
    mp = load_map()
    mem, minfo = members_load(cut)
    pred, pinfo = pred_load(cut)
    if calf is not None:
        pinfo = pred_check(calf, pred, mp, pinfo)
    t0 = time.time()
    D = M17.load_data(cut)
    nfull = len(D.syms)
    tbis = D15.load_tbis(cut)
    es_frames, es_meta = D15.load_es(cut)
    nq_frames, nq_meta = load_nq(cut) if cut == S.LB0 else (None, None)
    W = M17.build_world(D, cut, es_frames, tbis, cal)
    D15.release(D)
    DV.cut_checks(W, cal, cut)
    M17.attach_calendar_splits(W, cal)
    es_open_prints(W, es_frames)
    nq_ret = nq_returns(W.days, nq_frames) if nq_frames is not None else None
    del es_frames, nq_frames
    if calf is not None:
        attach_eap(W, calf, mp, mem, pred, counts_only=counts_only)
    return SimpleNamespace(W=W, cal=cal, winfo=winfo, calf=calf, cinfo=cinfo, mp=mp, mem=mem, minfo=minfo, pred=pred, pinfo=pinfo, tbis=tbis, es_meta=es_meta, nq_meta=nq_meta, nq_ret=nq_ret, nfull=nfull, seconds=time.time() - t0)


# ------------------------------------------------------------------ dryload: counts only
def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: the pre-P&L block (the calendar, the joins, the universe, DUE / NOT-DUE, the events, [E5] accuracy with the STOP, [E6] turnover, [E7] the power line), the World's sessions / names / ES coverage. No price,
    return, beta or P&L is printed: no regression is run (counts_only), no unit path is built, the legs are built only to count what they hold"""
    prereg_ok()
    t0 = time.time()
    X = load_inputs(S.LB0, enforce=False, counts_only=True)
    W = X.W
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {X.nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in RESMOM's liquidity universe")
    if W.ca is not None:
        M17.print_wide(W.ca)
    else:
        print(f"wide corporate-actions calendar [R1]: not on file ({X.winfo.get('path')}) - Stage A refuses without it; this dryload counts without dividends / spin-offs")
    if X.calf is None:
        print(f"[D1] {X.cinfo.get('label', 'the earnings calendar')} is {'not on file' if not X.cinfo.get('present') else 'NOT the registered file (sha256 ' + str(X.cinfo.get('sha256')) + ')'} ({X.cinfo['path']}) - the calendar table is not read and nothing past the World "
              "can be counted; Stage A refuses")
    else:
        apply_audit(W, None)
        pre_pnl(W, X.cinfo, X.minfo, X.pinfo, X.mp, X.es_meta, X.nq_meta, X.nq_ret)
    e = W.es
    print(f"ES prints on the {W.T:,} stock sessions: 16:00 adj {int(np.isfinite(e.c16a).sum()):,}, 16:00 raw {int(np.isfinite(e.c16r).sum()):,}; ES return defined on {int(np.isfinite(e.ret).sum()):,} sessions")
    print(M17.es_report(W)[0])
    print(f"cache manifest sha256: {manifest_sha()}")
    pm = peak_mb()
    print(f"dryload took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))


# ------------------------------------------------------------------ Stage A
def stage_a():
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                          # CHOICE (r17's / r21's): once the lockbox has been read Stage A is frozen
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    M17.wide_load(S.LB0)                                                                      # the pinned files first (cheap): each refuses (nothing computed) when it is not on file / not the registered one
    calf0 = cal_load(S.LB0)[0]
    mp0 = load_map()
    members_load(S.LB0)
    pred_check(calf0, pred_load(S.LB0)[0], mp0)                                               # [E19] x [E20] x the map
    del calf0, mp0
    B, legs_meta = A13.load_463()                                                             # the book next: a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure - fix the input first (nothing computed)")
    ref = DV.ref_load(B, check_facts=CHECK_BOOK)                                              # [E17] the S1-restated L: refuses (nothing computed) unless the file is the pinned one and L reproduces 121.06 / 3.926 / $36,526 ...
    DV.print_reference(ref)
    rdd5 = dd5_rec(B, ref.raw)
    print(f"  [E17] L's DD5 (the 5 deepest WF drawdown episodes): ${rdd5['dd5']:,.0f} (registered ${REF_DD5:,.0f}); worst ${rdd5['max_dd']:,.0f}" + (" - driven by one episode" if rdd5["one_episode"] else ""))
    if CHECK_BOOK and not abs(rdd5["dd5"] - REF_DD5) <= 1.0:                                  # ... and DD5 $34,392 to the dollar
        refuse(f"Stage A refused: L's DD5 ${rdd5['dd5']:,.0f} is not the registered ${REF_DD5:,.0f} [E17] (nothing computed)")
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {D15.MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor - nothing computed")
    t0 = time.time()
    X = load_inputs(S.LB0)
    W = X.W
    audit = read_audit()
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, AUDIT_FILE))
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in RESMOM's liquidity universe; audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event)"), flush=True)
    es_txt, es_rec = M17.es_report(W)
    print(es_txt)
    M17.print_wide(W.ca)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stopped": False, "stageA": None, "candidate": None, "pending_hand_audit": None,
           "book_check": bk, "dd_structure": dd, "reference": DV.ref_record(ref), "reference_dd5": rdd5, "manifest_sha256": msha, "es_return": es_rec, "es_masters": X.es_meta, "nq_masters": X.nq_meta, "wide_calendar": W.ca,
           "earnings_calendar": X.cinfo, "map": {k: v for k, v in X.mp.info.items() if k != "sha256"}, "members": X.minfo, "predecessors_e4": X.pinfo, "audit": aud_n, "audit_sha256": asha, "judged_post_mode": JUDGED}
    pre = pre_pnl(W, X.cinfo, X.minfo, X.pinfo, X.mp, X.es_meta, X.nq_meta, X.nq_ret)                  # ---- BEFORE ANY P&L (the legs are counted, never costed)
    out["pre_pnl"] = pre
    acc = pre["accuracy"]
    out["e5_e25"] = e5_record(acc)
    if acc["halt"]:                                                                           # [E5] recall under 80% in a WF year the [E25] waiver does not name: the run STOPS here, before any P&L, and MANAGER rules
        out.update({"stopped": True, "stop_years": acc["halt_years"]})
        dump(out, STAGE_A_FILE)
        print(f"EAP Stage A: STOPPED BEFORE ANY P&L - [E5] recall is under {SPEC['recall_stop']:.0%} in the WF year(s) {', '.join(yl(y) for y in acc['halt_years'])}" + (f" (the [E25] waiver by {acc['waived_by']} covers only "
              f"{', '.join(yl(y) for y in acc['waived_years'])})" if acc["waived_years"] else "") + f"; no cell was costed; MANAGER rules ({STAGE_A_FILE} written, judged: false)")
        return out
    wv = e5_phrase(acc)
    if wv:
        print(f"[E25] {wv} - Stage A goes on (the waiver is recorded in {STAGE_A_FILE} and in the result line)")
    rows = A13.book_rows(B, W)
    t1 = time.time()
    resJ, objJ = evaluate(W, B, S12, ref, rows, JUDGED, NREP, 0, full=True)
    print(f"judged reading [E16] done ({time.time() - t1:.0f}s: the legs, the cells, the cost rows, {NREP} random-name draws per cell, {NREP} time-shift draws for W)", flush=True)
    t1 = time.time()
    S12s, refs = stretch_ref(B, ref, SENS_FROM)
    resS, objS = evaluate(W, B, S12s, refs, rows, JUDGED, NREP, 0, full=False, lo=SENS_FROM)          # [E25] the sensitivity: 2016-17 dropped, every check and both nulls (the same seeds) on the shorter stretch
    del objS
    print(f"[E25] the sensitivity without 2016-17 done ({time.time() - t1:.0f}s: the legs from {SENS_FROM:%Y-%m-%d}, the cells, {NREP} random-name draws per cell, {NREP} time-shift draws for W)", flush=True)
    unused = unused_audit_rows(W, audit)
    t1 = time.time()
    resK, objK = evaluate(W, B, S12, ref, rows, REPORT_MODE, 0, 1, full=False)                 # [E16] the removal reading, REPORTED beside the judged one with its count, without a null
    print(f"the removal reading done ({time.time() - t1:.0f}s)", flush=True)
    peak, peak_keys = peak_days(W, wf_ranks(W))
    edr, einfo = edrift_months()
    rep = reports(W, B, S12, ref, rows, objJ, resJ["cells"], legs_meta, X.nq_ret, peak, peak_keys, edr)
    rep["edrift_file"] = einfo
    rep["peak_weeks"] = sorted(int(k_) for k_ in peak_keys)
    cells = resJ["cells"]
    gov = govern(cells, resS["cells"])                                                        # [E25] the STRICTER of the two verdicts governs
    passing, cand = gov["pass_cells"], gov["candidate"]
    cands = {c: candidate_rows(W, objJ.legs[c], c, objJ.runs[c], D15.asset_status()) for c in CELLS}
    ast = audit_status(cands, audit)
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([r_ for c in CELLS for r_ in cands[c]]).to_csv(os.path.join(OUT, CANDS_FILE), index=False)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - {LAB_J}")
    print_rday(resJ, rep, ref)                                                                # the R-day sum FIRST
    print_cells(resJ, ast)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing: {unused[:5]}")
    print_sens(resS, gov)
    print_keep(resK, cells, objK.legs["M"], objK.legs["W"])
    print_a2(cells)
    print_seat(rep["seat_e14"])                                                               # [E14] before any correlation
    print_live(rep)
    print_reports(rep, cells)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell with their predicted / actual dates, fills and marks) -> {os.path.join(OUT, CANDS_FILE)}; the hand audit (f) is the lead's: a data event found = a row symbol, date, cell, data_event in {AUDIT_FILE} and stage_a again")
    out.update({"judged": True, "pending_hand_audit": passing, "stageA": {"cells": cells, "null": resJ["null"], "pass_cells": passing, "pass_cells_full_window": gov["pass_full"]},
                "sensitivity_e25": {"stretch": resS["stretch"], "cells": resS["cells"], "null": resS["null"], "pass_cells": gov["pass_sensitivity"]}, "governing_e25": gov,
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"], "a2_book_roc": cells[cand]["A2"]["roc"],
                               "a2_reference_roc": cells[cand]["A2"]["reference"]["roc"], "incremental_pass": cells[cand]["A2"]["incremental_pass"], "incremental_credit": cells[cand]["A2"]["incremental_credit"],
                               "beta_within_cap": cells[cand]["beta"]["within_cap"], "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "audit_status": ast, "audit_data_events_without_effect": unused,
                "removal_reading": {"cells": {c: {k: resK["cells"][c][k] for k in ("base", "usd_year", "dd5", "cost_curve")} for c in CELLS},
                                    "removed": {"M": {k: int(sum(c_.get(k, 0) for c_ in objK.legs["M"].cnt.values())) for k in ("post_calendar_split", "post_spin")},
                                                "W": {k: int(sum(c_.get(k, 0) for c_ in objK.legs["W"].cnt.values())) for k in ("post_calendar_split", "post_spin")}}},
                "counts_by_year": {"M": {y: dict(c) for y, c in sorted(objJ.legs["M"].cnt.items())}, "W": {y: dict(c) for y, c in sorted(objJ.legs["W"].cnt.items())}},
                "reports": rep})
    dump(out, STAGE_A_FILE)
    cs = resS["cells"]
    for c in passing:
        a2 = cells[c]["A2"]
        print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}; WF ROC@30k {cells[c]['base']['roc']:.1f} (${cells[c]['usd_year']:,.0f} a year, {dd5_txt(cells[c]['dd5'])}); without 2016-17 [E25] ROC@30k {cs[c]['base']['roc']:.1f} "
              f"(${cs[c]['usd_year']:,.0f} a year, {dd5_txt(cs[c]['dd5'])}); A2 (a report): L + c x cell {a2['roc']:.2f} / {a2['sortino']:.3f} against L's {a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f} -> "
              + ("an INCREMENTAL PASS, credited" if a2["incremental_credit"] else "no credited incremental pass"))
    pv = lambda p: ", ".join(p) if p else "no cell"
    gtxt = (f" - the full WF window alone passes {pv(gov['pass_full'])} and the [E25] sensitivity without 2016-17 {pv(gov['pass_sensitivity'])}: THE VERDICTS DIFFER, the STRICTER governs" if gov["differ"] else
            " on the full WF window and on the [E25] sensitivity without 2016-17 alike")
    wtxt = f" ({wv})" if wv else ""
    if passing:
        print(f"EAP Stage A: (a)-(e) pass for {passing}{gtxt}{wtxt}; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors (the harness never decides it); candidate {cand}. Stage B needs the lead's go-flag {GO_FLAG} on the stock families' one "
              "sealed-year day.")
    else:
        print("EAP Stage A: FAIL - no cell passes (" + "; ".join(f"{c}: " + (", ".join(k for k, v in cells[c]['checks'].items() if not v) or "passes the full window") + " | without 2016-17: " + (", ".join(k for k, v in cs[c]['checks'].items() if not v) or "passes")
                                                       for c in CELLS) + f"){gtxt}{wtxt} - EAP r1 is dead and the earnings family closes with it; no other windows, predictions or universes are tried; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def b_checks(cell, leg):
    """STAGE B's pass: the LEG's standalone veto and nothing else (RESMOM's: M >= 10 monthly rebalances; CHOICE W >= 100 events, DIVRUN's event-cell bar), net > 0, net > 0 without its top name-period. No book number enters it. A NaN fails every comparison"""
    n, lab = (RULES["b_m_reb"], "monthly rebalances") if cell == "M" else (RULES["b_w_events"], "events")
    return {f"leg {lab}>={n}": bool(leg["n_units"] >= n), "leg net>0": bool(leg["net"] > 0), "leg net>0 without its top name-period": bool(leg["net_ex_top_pos"] > 0)}


def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag eap_stageB_GO.flag is on file (written after the hand audit (f); its EXISTENCE is the sign-off, its text is stored with the read) and a Stage A candidate is on file. The sealed
    year is the LEG's standalone veto (b_checks). The book add (#463 + c x the cell at Stage A's frozen c) is computed, printed and stored as book_add_reported - NEVER part of the pass. Every refusal is before the read flag; the flag is written (exclusively) only after every
    load, every check and the whole result are in hand"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed {TAIL}")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, STAGE_A_FILE)
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    cand = sa.get("candidate")
    if not (isinstance(cand, dict) and sa.get("judged") is True and cand.get("cell") in ((sa.get("stageA") or {}).get("pass_cells") or [])):
        refuse("Stage B refused: no Stage A candidate (a cell that passes (a)-(e)) is on file - the lockbox stays sealed.")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / pinned file ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, AUDIT_FILE)):
        refuse(f"Stage B refused: {AUDIT_FILE} is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    go_text = open(go).read()[:500]
    B, legs_meta = A13.load_463()                                                             # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on - lockbox NOT read")
    X = load_inputs(S.END)
    W = X.W
    audit = read_audit()
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)
    runf = {"M": lambda L_, cfg, **kw: m_run(W, L_, cfg, **kw), "W": lambda L_, cfg, **kw: w_run(W, L_, cfg, **kw)}
    build = {"M": m_build, "W": w_build}
    Lw = build[cell](W, WF0, PRE_END, JUDGED)                                                 # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data
    run = runf[cell](Lw, D15.l1_cfg(), pos=True)
    xw = D15.to_B(run.x, rows, B.n)
    st, par = D15.cell_stats(B, xw, D15.to_B(run.cnt, rows, B.n), WF0, PRE_END, run), sa["parity"][cell]
    print(f"WF re-read on Stage B's data: {cell} positions {st['n_pos']:,} (Stage A {par['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${par['net']:,.0f})")
    if st["n_pos"] != par["n_pos"] or st["n_units"] != par["n_units"] or abs(st["net"] - par["net"]) > max(1.0, 1e-6 * abs(par["net"])):
        refuse(f"Stage B refused: the WF numbers of {cell} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    c2 = plain_a2(B, xw)["c"]
    print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed on Stage B's data")
    if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
        refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data (lockbox NOT read)")
    L = build[cell](W, LB0, LB1, JUDGED)                                                      # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
    run = runf[cell](L, D15.l1_cfg(), pos=True)
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    leg = D15.cell_stats(B, xB, cB, LB0, LB1, run)
    r = D15.book_at(B, xB, c, LB0, LB1)
    would = bool(r["roc"] >= RULES["b_roc"] and r["sortino"] >= RULES["b_sort"])
    chk = b_checks(cell, leg)
    ok = all(chk.values())                                                                    # the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "would_have_cleared": would,
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call)"}
    text = json.dumps({"cell": cell, "c": c, "go_flag": go_text, "book_check": bk, "es_masters": X.es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "earnings_calendar": X.cinfo,
                       "counts_by_year": {y: dict(v) for y, v in sorted(L.cnt.items())}, "top_positions": candidate_rows(W, L, cell, run, D15.asset_status(), 20), **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                       # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: positions {leg['n_pos']:,}, {'rebalances' if cell == 'M' else 'events'} {leg['n_units']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-period ${leg['top_pos']:,.0f}, net without it ${leg['net_ex_top_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would {'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("EAP Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) on the RUNBOARD; the book add above is a report - the forward record decides any book add (owner call)." if ok else
                                 "FAIL - the leg is vetoed by its sealed year: EAP r1 is dead and the earnings family closes; ledger + memory."))
    with open(flag, "x") as f:                                                                # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, STAGE_B_FILE), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made calendars and worlds, and plain-python recounts of every release, rank, universe, DUE flag, event, beta, path, null draw and count (independent of the vectorised code)
def close(a, b, tol=1e-9):
    return D15.close(a, b, tol)


def refused(fn, *frag):
    """fn() must refuse (SystemExit) with every fragment in its message -> the message"""
    try:
        with quiet():
            fn()
    except SystemExit as e:
        msg = str(e)
        assert all(f_ in msg for f_ in frag), (frag, msg)
        return msg
    raise AssertionError(f"{getattr(fn, '__name__', fn)} did not refuse ({frag})")


CAL_HDR = ("ticker", "ndx_tickers", "cik", "name", "form", "accepted_et", "reaction_session", "timing", "items", "accession")


def write_cal(path, rows, header=CAL_HDR):
    """a hand-made earnings calendar in TV's layout: rows = (ticker, ndx_tickers, cik, form, accepted 'YYYY-MM-DD HH:MM', reaction 'YYYY-MM-DD', timing, accession) -> the sha256 of its bytes"""
    lines = [",".join(header)]
    for t, nt, cik, form, acc, rs, timing, accn in rows:
        lines.append(",".join([t, nt, cik, f"{t} Inc", form, acc, rs, timing, "2.02", accn]))
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return M17.sha_raw(path)


def cal_rows_of(spec_rows):
    """(ticker, ndx_tickers, cik, acceptance Timestamp, timing 'amc' | 'bmo', form) -> the calendar's rows: the reaction session = the acceptance day for 'bmo' (07:00), the next business day for 'amc' (16:05); accession numbers in order"""
    out = []
    for q, (t, nt, cik, d, timing, form) in enumerate(spec_rows):
        d = TS(d)
        acc = d.replace(hour=7, minute=0) if timing == "bmo" else d.replace(hour=16, minute=5)
        rs = d if timing == "bmo" else d + pd.offsets.BDay(1)
        out.append((t, nt, cik, form, f"{acc:%Y-%m-%d %H:%M}", f"{rs:%Y-%m-%d}", timing, f"{cik}-{q:06d}"))
    return out


@contextlib.contextmanager
def calendar_file(rows, cut=None, pred_rows=None):
    """a hand-made calendar written to a temp file and registered for the block (CAL_CSV / CAL_SHA patched; with pred_rows a hand-made [E20] predecessors' file beside it, PRED_CAL patched - else PRED_CAL = None) -> (frame, info) as cal_load reads the table at `cut`
    (default S.LB0)"""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "earnings_calendar_ndx.csv")
        sha = write_cal(p, rows)
        pc = None
        if pred_rows is not None:
            pp = os.path.join(td, "earnings_calendar_predecessors.csv")
            pc = (pp, write_cal(pp, pred_rows))
        with patched(THIS, CAL_CSV=p, CAL_SHA=sha, PRED_CAL=pc):
            yield cal_load(S.LB0 if cut is None else cut)


def brute_rel(calf, days, pred=None):
    """plain python: per CIK the releases [P] reads (8-K/A rows out), in (acceptance stamp, accession) order, each with its next release's date (None for the last), its predicted row (the first session on / after d + 364 days, -1 past the data), its
    reaction session's row and pred ([E19]: a predecessor CIK's release accepted inside a pinned change's [first, last] 8-K dates, listed again under its successor - once, however many rows join it) -> {cik: [dict]}"""
    by = defaultdict(list)
    for t in calf.itertuples(index=False):
        if t.form != AMEND_FORM:
            by[str(t.cik)].append((TS(t.acc), str(t.accession), TS(t.d), TS(t.rs), False))
    if pred is not None:
        for p_ in pred.itertuples(index=False):
            have = {z[1] for z in by[str(p_.succ)]}
            for z in [z for z in by.get(str(p_.pred), []) if not z[4] and TS(p_.lo) <= z[2] <= TS(p_.hi)]:
                if z[1] not in have:
                    by[str(p_.succ)].append(z[:4] + (True,))
                    have.add(z[1])
    dl = list(pd.DatetimeIndex(days))
    out = {}
    for c, v in by.items():
        if not v:
            continue
        v.sort(key=lambda z: (z[0], z[1]))
        rows_ = []
        for q, (acc, accn, d, rs, pj) in enumerate(v):
            pr, rr = bisect.bisect_left(dl, d + pd.Timedelta(days=364)), bisect.bisect_left(dl, rs)
            rows_.append({"d": d, "nx": v[q + 1][2] if q + 1 < len(v) else None, "p_row": pr if pr < len(dl) else -1, "rs_row": rr if rr < len(dl) else -1, "accession": accn, "pred": pj})
        out[c] = rows_
    return out


def brute_counts_at(rels, R):
    """[E3] point in time at the rank date R, plain python: a release counts when it was accepted on or before R - 1 day and no later release of the CIK, itself accepted on or before R - 1, lies less than 50 days after it"""
    one = pd.Timedelta(days=1)
    return [(r_["d"] <= R - one) and not (r_["nx"] is not None and (r_["nx"] - r_["d"]).days < 50 and r_["nx"] <= R - one) for r_ in rels]


def brute_schedule(days, win):
    """the month-end ranks, plain python: every session that is the last of its calendar month and has a session after it; built = those with a full win-session window (r >= win - 1); the exit = the next rank's fill (-1 for the last); r_next = the next built rank's
    session (the data's last session for the last) -> [(r, f, x, r_next)] of the built ranks"""
    T = len(days)
    ends = [t for t in range(T - 1) if days[t].month != days[t + 1].month]
    out = []
    for i, r in enumerate(ends):
        if r >= win - 1:
            out.append((r, r + 1, ends[i + 1] + 1 if i + 1 < len(ends) else -1, ends[i + 1] if i + 1 < len(ends) else T - 1))
    return out


def brute_member(mem, m, sym, cik, ndx, wsyms):
    """the point-in-time membership of one World column on the 1st of month m, plain python over the members frame's rows: its own symbol on the list, or a listed ticker that is NOT a World symbol and is among the calendar's ndx_tickers of the column's CIK"""
    for t in mem.itertuples(index=False):
        if TS(t.lo) <= m and (pd.isna(t.hi) or TS(t.hi) > m):
            if t.ticker == sym or (t.ticker not in wsyms and cik and t.ticker in ndx.get(cik, ())):
                return True
    return False


def brute_dv(W, f, j, n=20):
    v = [W.Cl[t, j] * W.Vv[t, j] for t in range(f - n, f)] if f >= n else []
    return float(np.mean(v)) if len(v) == n and all(math.isfinite(z) for z in v) else float("nan")


def brute_env(W, calf, mp, mem, pred=None):
    """the plain-python inputs of every recount: the releases per CIK ([E19]'s joins included), the column -> CIK join, the CIK -> members-file tickers, the built ranks"""
    dfm = mp.df.set_index("symbol")
    cik_of = {}
    for j, s in enumerate(np.asarray(W.syms).astype(str)):
        cik_of[j] = str(dfm.loc[s, "cik"]) if s in dfm.index and bool(dfm.loc[s, "usable"]) else ""
    ndx = defaultdict(set)
    for c, ts in zip(calf["cik"], calf["tickers"]):
        ndx[str(c)].update(ts)
    return SimpleNamespace(rels=brute_rel(calf, W.days, pred), cik_of=cik_of, ndx=dict(ndx), mem=mem, wsyms=set(np.asarray(W.syms).astype(str)), ranks=brute_schedule(W.days, M17.SPEC["win"]))


def brute_universe(W, Z, r, f):
    """the universe at the rank r (fill f), plain python, every rule in its order -> (sorted columns, {column: first reason}, [E1]'s (dropped, kept) pairs)"""
    win, need = M17.SPEC["win"], M17.SPEC["min_n"]
    R = W.days[r]
    m = TS(f"{R:%Y-%m}-01")
    why, ok = {}, []
    for j in range(W.S):
        if not W.U[f, j]:
            continue
        nret = sum(1 for t in range(r - win + 1, r + 1) if t >= 0 and math.isfinite(M17.brute_ret(W, t, j)))
        npair = sum(1 for t in range(r - win + 1, r + 1) if t >= 0 and math.isfinite(M17.brute_ret(W, t, j)) and math.isfinite(W.es.ret[t]))
        c = Z.cik_of[j]
        rels = Z.rels.get(c, [])
        kk = brute_counts_at(rels, R)
        n_any = sum(kk)
        n400 = sum(1 for q, r_ in enumerate(rels) if kk[q] and r_["d"] >= R - pd.Timedelta(days=SPEC["look_days"]))
        if nret < need:
            why[j] = "short_history"
        elif npair < need:
            why[j] = "no_es_pairs"
        elif not brute_member(Z.mem, m, str(W.syms[j]), c, Z.ndx, Z.wsyms):
            why[j] = "not_member"
        elif not c:
            why[j] = "not_joined"
        elif n_any == 0:
            why[j] = "no_release"
        elif n400 < SPEC["min_rel"]:
            why[j] = "few_releases"
        else:
            ok.append(j)
    drops = []
    for c in sorted({Z.cik_of[j] for j in ok}):
        grp = [j for j in ok if Z.cik_of[j] == c]
        if len(grp) > 1:
            best = sorted(grp, key=lambda j: (-brute_dv(W, f, j) if math.isfinite(brute_dv(W, f, j)) else math.inf, str(W.syms[j])))[0]
            for j in grp:
                if j != best:
                    drops.append((j, best))
                    why[j] = "second_class"
    uni = sorted(j for j in ok if j not in {d_ for d_, _ in drops})
    return uni, why, drops


def brute_due(W, Z, r, rn, uni):
    """per universe name: (DUE, [release indices whose predicted row falls in r + 1 .. r_next and that count at the rank])"""
    R = W.days[r]
    out = {}
    for j in uni:
        rels = Z.rels[Z.cik_of[j]]
        kk = brute_counts_at(rels, R)
        hit = [q for q, r_ in enumerate(rels) if kk[q] and r_["p_row"] >= 0 and r + 1 <= r_["p_row"] <= rn]
        out[j] = (bool(hit), hit)
    return out


def brute_spin(W, a, b, j):
    """the first [E16] spin-off / stock-dividend ex-date row of name j in a .. b (the raw input W.Sp_in), -1 for none"""
    Sp = getattr(W, "Sp_in", None)
    if Sp is None:
        return -1
    return next((t for t in range(a, b + 1) if Sp[t, j]), -1)


def brute_csplit(W, a, b, j):
    return bool(getattr(W, "CSPL", None) is not None and any(W.CSPL[t, j] for t in range(a, b + 1)))


def brute_stock(W, f, x, j, sd, mode, **kw):
    """one position's daily P&L per $1 of entry: [E16] closed at the close before its first spin-off / stock-dividend ex-date in f+1 .. x (judged reading), else held to x (r17_resmom's plain-python paths)"""
    s = brute_spin(W, f + 1, x, j) if mode == "close" else -1
    if s >= 0:
        return M17.brute_close_path(W, f, x, j, sd, s, **kw)[0], s - 1
    return M17.brute_path(W, f, x, j, sd, False, **kw)[0], -1


def brute_m(W, Z, lo, hi, mode, cfgs=None):
    """cell M end to end in plain python: the built ranks whose exit lies in [lo, hi]; the universe; the pool (an open at the fill, no audit row; the removal reading: no announced split / spin-off ex-date in f+1 .. x); LONG the DUE names, SHORT the rest; the [E8] dollars; traded
    when both sides hold >= min_side; every pool name's path under each costing (cfgs: {label: brute keywords}) -> [dict per rank]"""
    cfgs = cfgs or {"base": {}}
    out = []
    for r, f, x, rn in Z.ranks:
        if x < 0 or not (lo <= W.days[x] <= hi):
            continue
        uni = brute_universe(W, Z, r, f)[0]
        due = brute_due(W, Z, r, rn, uni)
        pool, why = [], Counter()
        for j in uni:
            if not math.isfinite(W.Od[f, j] / W.F[f, j]):
                why["no_fill"] += 1
            elif W.aud1[f, j]:
                why["audit"] += 1
            elif mode == "keep" and brute_csplit(W, f + 1, x, j):
                why["post_calendar_split"] += 1
            elif mode == "keep" and brute_spin(W, f + 1, x, j) >= 0:
                why["post_spin"] += 1
            else:
                pool.append(j)
        L_ = [j for j in pool if due[j][0]]
        S_ = [j for j in pool if not due[j][0]]
        cap = lambda n: float(min(SPEC["side_usd"], SPEC["name_cap"] * n))
        b = {"r": r, "f": f, "x": x, "uni": uni, "pool": pool, "long": L_, "short": S_, "L_usd": cap(len(L_)), "S_usd": cap(len(S_)), "traded": len(L_) >= SPEC["min_side"] and len(S_) >= SPEC["min_side"], "why": why, "paths": {}}
        if b["traded"]:
            for lab, kw in cfgs.items():
                b["paths"][lab] = {j: brute_stock(W, f, x, j, 1 if j in L_ else -1, mode, kt=W.k[f:x + 1], **kw) for j in pool}
        out.append(b)
    return out


def brute_window(W, t_end, win=None):
    """[E26] plain python: the `win` most recent rows at or before t_end on which ES has a return, oldest first (None when there are fewer)"""
    win = SPEC["beta_win"] if win is None else win
    rows_ = [t for t in range(int(t_end), -1, -1) if math.isfinite(float(W.es.ret[t]))][:win]
    return rows_[::-1] if len(rows_) == win else None


def brute_beta(W, e, j, t_end=None, need=None):
    """[E9] / [E26] plain python: the OLS slope (numpy least squares, an intercept) of the name's split-safe total return on ES's over the win most recent sessions at or before t_end (default e - 1: before the entry) ON WHICH ES HAS A RETURN, at least `need` (default all win)
    of the name's own returns among them -> (beta or NaN, 'ok' | 'no_beta')"""
    need = SPEC["beta_need"] if need is None else need
    t_end = e - 1 if t_end is None else t_end
    rows_ = brute_window(W, t_end) if t_end >= 0 else None
    if rows_ is None:
        return float("nan"), "no_beta"
    pr = [(M17.brute_ret(W, t, j), float(W.es.ret[t])) for t in rows_]
    pr = [(y, z) for y, z in pr if math.isfinite(y)]
    if len(pr) < need:
        return float("nan"), "no_beta"
    X = np.column_stack([np.ones(len(pr)), np.asarray([z for _, z in pr])])
    return float(np.linalg.lstsq(X, np.asarray([y for y, _ in pr]), rcond=None)[0][1]), "ok"


def brute_hedge(W, e, x, beta, c=-1, bps=HEDGE_BPS):
    """the ES hedge per $1 of stock entry notional, plain python: short beta at the 09:30 print of e (counted on the unadjusted print), marked at each 16:00 print of e .. x-1, bought back at the 09:30 print of x - or, [E16], lifted at the 16:00 print of the close row c;
    0.5 bps of the notional at the entry and of the value at the exit"""
    lvl = W.eso_r[e]
    q = [W.eso_a[e]] + [W.esc_a[t] for t in range(e, x)] + [W.eso_a[x]]
    last = (c - e) if c >= 0 else (x - e)
    out = [0.0] * (x - e + 1)
    for h in range(last + 1):
        out[h] = -beta * (q[h + 1] - q[h]) / lvl
    out[0] -= bps * 1e-4 * abs(beta)
    out[last] -= bps * 1e-4 * abs(beta) * (W.esc_r[c] if c >= 0 else W.eso_r[x]) / lvl
    return out


def brute_w(W, Z, lo, hi, mode, cfgs=None):
    """cell W end to end in plain python: every counted release of every universe name whose entry e = p - 3 falls in its rank's r + 1 .. r_next, exit x = p + 2 in [lo, hi]; the reasons in order (no open at e, [E9] / [E26] no beta, audit, the removal reading's split /
    spin-off); the beta by least squares; the stock leg under each costing and the hedge -> (events sorted by (e, column), counts by entry year, unresolved by entry year)"""
    cfgs = cfgs or {"base": {}}
    ev, cnt = [], defaultdict(Counter)
    for r, f, x0, rn in Z.ranks:
        R = W.days[r]
        uni = brute_universe(W, Z, r, f)[0]
        for j in uni:
            rels = Z.rels[Z.cik_of[j]]
            kk = brute_counts_at(rels, R)
            for q, r_ in enumerate(rels):
                p = r_["p_row"]
                if not kk[q] or p < 0 or not (r + 1 <= p - SPEC["w_pre"] <= rn):
                    continue
                e, x = p - SPEC["w_pre"], p + SPEC["w_post"]
                y = int(W.days[e].year)
                if x > W.T - 1:
                    cnt[y]["unresolved"] += 1
                    continue
                if not (lo <= W.days[x] <= hi):
                    continue
                cnt[y]["candidates"] += 1
                b, st = brute_beta(W, e, j)
                if not math.isfinite(W.Od[e, j] / W.F[e, j]):
                    cnt[y]["no_entry_open"] += 1
                elif st != "ok":
                    cnt[y]["no_beta"] += 1
                elif W.audw[e, j]:
                    cnt[y]["audit"] += 1
                elif mode == "keep" and brute_csplit(W, e + 1, x, j):
                    cnt[y]["post_calendar_split"] += 1
                elif mode == "keep" and brute_spin(W, e + 1, x, j) >= 0:
                    cnt[y]["post_spin"] += 1
                else:
                    cnt[y]["events"] += 1
                    cnt[y]["beta_reached_back"] += int(brute_window(W, e - 1)[0] < e - SPEC["beta_win"])
                    paths = {lab: brute_stock(W, e, x, j, 1, mode, **kw) for lab, kw in cfgs.items()}
                    c = paths[next(iter(paths))][1]
                    ev.append({"e": e, "x": x, "p": p, "col": j, "beta": b, "close": c, "stock": {lab: v[0] for lab, v in paths.items()}, "hedge": brute_hedge(W, e, x, b, c)})
    ev.sort(key=lambda z: (z["e"], z["col"]))
    return ev, cnt


def add_path(acc, row0, path, scale=1.0):
    for h, v in enumerate(path):
        acc[row0 + h] += scale * v


# ------------------------------------------------------------------ the toy world of the selftest (hand-made: 300 sessions x 20 names, 60-session windows, every case planted by hand)
TOY_WIN = {"win": 60, "min_n": 55, "beta_win": 60, "beta_need": 60, "m_beta_need": 55, "min_side": 3, "side_usd": 60000.0, "name_cap": 10000.0}      # the selftest's shrunk windows and sides (the real ones: 252 / 230 / 252 / 252 / 230, 8, $200,000, $10,000)
TOY_SYMS = [f"N{j:02d}" for j in range(20)]


TOY_PRED_CIK = f"{9000:010d}"                                            # [E19] N00's predecessor CIK: N00 filed under it until TOY_CHANGE (its releases in the [E20] predecessors' file)
TOY_CHANGE = TS("2024-03-01")
TOY_PRED_EXPECTED, TOY_PRED_HOLES = {"N00": TOY_PRED_CIK}, ("N09", "N15")      # the toy list's change and its two rows that are NOT changes (N09: an empty predecessor; N15: a predecessor equal to its successor)


def toy_cik(j):
    return f"{1000 + (10 if j == 11 else j):010d}"                       # [E1] N11 is the second share class of N10: one CIK


def toy_pred_map_text():
    """the toy [E19] list in TV's columns: N00 <- TOY_PRED_CIK (8-Ks 2022-12-01 .. 2024-02-29), N09 and N15 NOT CIK changes"""
    return ",".join(PRED_COLS) + "\n" + "\n".join([f"N00,{TOY_PRED_CIK},N00 Holdings Ltd,{toy_cik(0)},2022-12-01,2024-02-29,toy://N00,toy: re-domiciled 2024-03",
                                                   f"N09,,,{toy_cik(9)},,,,NOT A CIK CHANGE - toy: a foreign filer (6-K)",
                                                   f"N15,{toy_cik(15)},,{toy_cik(15)},,,,NOT A CIK CHANGE - toy: same CIK; a late first release"]) + "\n"


@contextlib.contextmanager
def pred_list_file(text, expected=None, holes=None, cut=None):
    """a hand-made [E19] list written to a temp file and pinned for the block (PRED_LIST / PRED_EXPECTED / PRED_HOLES patched; default the toy's) -> pred_load at `cut` (default S.LB0)"""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "edgar_predecessor_map.csv")
        with open(p, "w", newline="\n") as f:
            f.write(text)
        with patched(THIS, PRED_LIST=(p, M17.sha_raw(p)), PRED_EXPECTED=dict(TOY_PRED_EXPECTED if expected is None else expected), PRED_HOLES=tuple(TOY_PRED_HOLES if holes is None else holes)):
            yield pred_load(S.LB0 if cut is None else cut)


def toy_split(spec_rows):
    """the toy calendar's rows -> (the calendar's rows, the [E20] predecessors' rows): N00's releases accepted before TOY_CHANGE carry its predecessor's CIK and sit in the predecessors' file (MRVL's case)"""
    main_, prev = [], []
    for t, nt, cik, d, tm, form in spec_rows:
        if t == "N00" and TS(d) < TOY_CHANGE:
            prev.append((t, t, TOY_PRED_CIK, d, tm, form))
        else:
            main_.append((t, nt, cik, d, tm, form))
    return main_, prev


def toy_releases(shift_from=None, shift_days=35):
    """the toy calendar's releases: per CIK a 91-day cycle (13 weeks: the same weekday every quarter, so d + 364 is exactly the date four releases on) starting on a Monday 2023-01-02 + 7 x (j mod 13) days, through 2025-02-14; odd j release after the close (16:05, reacting
    the next session), even j before the open (07:00, reacting that session). Planted: N05 a pre-announcement 21 days before its first 2023 release ([E3]: the later counts); N06 an 8-K/A 30 days after each 2023 release ([E2]); N07's 2024 releases two weeks late (the
    prediction misses: [E5]); N09 no release at all (no_release); N15 releases from 2023-11 only (few_releases until four are known); N11 shares N10's CIK (no rows of its own); shift_from = every release on / after that date moved shift_days later (the
    STOP calendar of [E5]) -> [(ticker, ndx_tickers, cik, date, timing, form)]"""
    out = []
    for j in range(20):
        if j in (9, 11):
            continue
        t, cik = TOY_SYMS[j], toy_cik(j)
        nt = {10: "N10;N11", 17: "OLD17;N17"}.get(j, t)
        tm = "amc" if j % 2 else "bmo"
        d = TS("2023-01-02") + pd.Timedelta(days=7 * (j % 13))
        first = True
        while d <= TS("2025-02-14"):
            dd = d
            if j == 7 and d.year == 2024:
                dd = d + pd.Timedelta(days=14)
            if shift_from is not None and dd >= TS(shift_from):
                dd = dd + pd.Timedelta(days=shift_days)
            if not (j == 15 and d < TS("2023-11-01")):
                out.append((t, nt, cik, dd, tm, "8-K"))
                if j == 5 and first:
                    out.append((t, nt, cik, dd - pd.Timedelta(days=21), "bmo", "8-K"))
                    first = False
                if j == 6 and d.year == 2023:
                    out.append((t, nt, cik, dd + pd.Timedelta(days=30), "amc", AMEND_FORM))
            d = d + pd.Timedelta(days=91)
    out.sort(key=lambda z: (z[2], z[3]))
    return out


def toy_map():
    """the toy map (NETISS's shape, as load_map returns it): every symbol current_ticker with its CIK but N14 (absent: not_in_map) and N19 (unmapped: no CIK)"""
    rows_ = [(s, toy_cik(j), "current_ticker") for j, s in enumerate(TOY_SYMS) if j not in (14, 19)] + [("N19", "", "unmapped")]
    df = pd.DataFrame(rows_, columns=["symbol", "cik", "method"]).assign(source="base")
    df["usable"] = (df["cik"] != "") & df["method"].isin(ALLOWED_METHODS + ADD_METHODS)
    return SimpleNamespace(df=df, info={"sha256": {"map": "toy", "map_add": "toy"}, "rows": len(df), "usable_symbols": int(df["usable"].sum()), "usable_ciks": int(df.loc[df["usable"], "cik"].nunique()), "by_method": dict(Counter(df["method"]))})


def toy_members():
    """the toy members list: every symbol from 2016 but N16 (from 2024-07-01) and N17, listed as OLD17 until 2024-07-01 (a renamed member: OLD17 is not a World symbol and N17's CIK names it)"""
    rows_ = [(s, TS("2016-01-01"), pd.NaT) for j, s in enumerate(TOY_SYMS) if j not in (16, 17)]
    rows_ += [("N16", TS("2024-07-01"), pd.NaT), ("OLD17", TS("2016-01-01"), TS("2024-07-01")), ("N17", TS("2024-07-01"), pd.NaT)]
    return pd.DataFrame(rows_, columns=["ticker", "lo", "hi"])


def toy_world(seed=3, T=300):
    """300 sessions (Mon 2024-01-01 on) x 20 names: split-safe prices that load on an ES path (c16 prints 4000 x the compounded return; the roll-corrected print 50 points above; the 09:30 print the prior close x a small gap) with a hole in the ES master on row 270
    (no print: no return there and on 271; the prints carry). Planted: N12 a registered 2-for-1 split on row 120 (the factor moves, the split-safe path does not); N18 first trades on row 30 (short history); N08 no close on row 200 (two returns lost: [E9] no beta for
    60 sessions); N01 no open on row 132, the entry of its July window (no entry); N02 a cash dividend every 63 sessions; ES's k_t > 1.5 on some sessions (the borrow stress) -> (World with W.Dr_in / W.Sp_in, the ES pieces)"""
    rng = np.random.default_rng(seed)
    Sn = len(TOY_SYMS)
    m = rng.normal(0.0003, 0.009, T)
    m[0] = 0.0
    c16r = 4000.0 * np.cumprod(1.0 + m)
    c16a = c16r + 50.0
    c16r[270], c16a[270] = np.nan, np.nan
    es_ret = np.full(T, np.nan)
    es_ret[1:] = (c16a[1:] - c16a[:-1]) / c16r[:-1]
    beta = rng.uniform(0.5, 1.5, Sn)
    ret = beta * m[:, None] + rng.normal(0.0002, 0.012, (T, Sn))
    ret[0] = 0.0
    Cl = 30.0 * (1.0 + 0.05 * np.arange(Sn)) * np.cumprod(1.0 + ret, axis=0)
    Od = np.vstack([Cl[:1], Cl[:-1]]) * (1.0 + rng.normal(0.0, 0.003, (T, Sn)))
    Vv = rng.uniform(2e6, 4e6, (T, Sn))
    Vv[:150, 10] *= 3.0                                                                    # [E1] N10 is the more liquid class until row 150, N11 after
    Vv[150:, 11] *= 3.0
    F, chg = np.ones((T, Sn)), np.zeros((T, Sn), bool)
    F[:120, 12] = 2.0
    Cl[:, 12] *= F[:, 12]
    Od[:, 12] *= F[:, 12]
    chg[120, 12] = True
    for a in (Od, Cl, Vv, F):
        a[:30, 18] = np.nan
    Cl[200, 8] = np.nan
    Od[132, 1] = np.nan                                                                    # N01: no open on the entry session of its July 2024 window (no_entry_open)
    Dr = np.zeros((T, Sn))
    Dr[np.arange(T) % 63 == 40, 2] = 0.3
    k = np.clip(rng.lognormal(0.0, 0.5, T), 0.5, 2.0)
    W = M17.mk_world(Cl, es_ret, F=F, chg=chg, Od=Od, k=k, Vv=Vv, Dr=Dr, Sp=np.zeros((T, Sn), bool))
    W.syms = np.array(TOY_SYMS)
    W.es.c16a, W.es.c16r = c16a, c16r
    eo = np.r_[c16r[0], np.where(np.isfinite(c16r[:-1]), c16r[:-1], np.nan)] * (1.0 + rng.normal(0.0, 0.002, T))
    eo[271] = np.nan                                                                       # no 09:30 print the session after the hole either
    seq_a = np.empty(2 * T)
    seq_a[0::2], seq_a[1::2] = eo + 50.0, c16a
    seq_r = np.empty(2 * T)
    seq_r[0::2], seq_r[1::2] = eo, c16r
    fa, fr = pd.Series(seq_a).ffill().to_numpy(), pd.Series(seq_r).ffill().to_numpy()
    W.eso_a, W.esc_a, W.eso_r, W.esc_r = fa[0::2], fa[1::2], fr[0::2], fr[1::2]
    return W


def toy_setup(spins=True, calendar=None, members=None):
    """the toy world + its calendar and [E20] predecessors' file (N00's releases before 2024-03 under its predecessor's CIK; read as one table through cal_load from temp files) + map + members + the toy [E19] list (N00 joined; N09 / N15 not CIK changes: no join),
    the spin-offs planted where they bite once the events are known (N04: a spin-off ex-date ON the predicted date of its first W event - inside the window; N03: a stock dividend inside an M hold), N13 a calendar split inside an M hold (the removal reading's case), the
    audit rows (N02 at the third rank's fill: M; N01's first W event: W), everything attached (W.ea.pred = the list; W.toy_pinfo = its info after pred_check) -> (W, calf, mp, mem, Z)"""
    W = toy_world()
    main_, prev = toy_split(calendar if calendar is not None else toy_releases())
    with calendar_file(cal_rows_of(main_), pred_rows=cal_rows_of(prev)) as (calf, cinfo):
        pass
    mp, mem = toy_map(), (toy_members() if members is None else members)
    with pred_list_file(toy_pred_map_text()) as (pred, pinfo):
        W.toy_pinfo = pred_check(calf, pred, mp, pinfo)
    M17.attach_calendar_splits(W, None)
    attach_eap(W, calf, mp, mem, pred)
    if spins:
        c = W.ea.cand
        j4 = [i for i in range(c.n) if c.col[i] == 4 and c.x[i] >= 0 and c.e[i] > 100]
        Sp = np.array(W.Sp_in, bool, copy=True)
        Sp[c.p[j4[0]], 4] = True                                                            # inside N04's window e .. x (e < p <= x)
        rk = W.ea
        k3 = next(k for k in range(len(rk.r)) if 3 in rk.uni[k] and rk.x[k] > 0 and rk.f[k] > 90)
        Sp[rk.f[k3] + 5, 3] = True                                                          # inside an M hold of N03 (f < t <= x)
        M17.with_dividends(W, W.Dr_in, Sp)
        k13 = next(k for k in range(len(rk.r)) if 13 in rk.uni[k] and rk.x[k] > 0 and rk.f[k] > 120)
        split = pd.DataFrame({"symbol": ["N13"], "ex": [W.days[rk.f[k13] + 4]], "type": ["forward_split"]})
        M17.attach_calendar_splits(W, SimpleNamespace(split=split))
        attach_eap(W, calf, mp, mem, pred)
    Z = brute_env(W, calf, mp, mem, pred)
    return W, calf, mp, mem, Z


# ------------------------------------------------------------------ the selftest groups
def t_constants():
    assert SPEC["pred_days"] == 364 and SPEC["look_days"] == 400 and SPEC["min_rel"] == 4 and SPEC["pair_days"] == 50 and (SPEC["side_usd"], SPEC["name_cap"], SPEC["min_side"]) == (200000.0, 10000.0, 8)
    assert (SPEC["w_slot"], SPEC["w_pre"], SPEC["w_post"]) == (4000.0, 3, 2) and (SPEC["beta_win"], SPEC["beta_need"], SPEC["m_beta_need"]) == (252, 252, 230) and (SPEC["shift_lo"], SPEC["shift_hi"]) == (27, 36)
    assert SPEC["near"] == (3, 7) and SPEC["recall_stop"] == 0.80 and SPEC["peak_names"] == 10 and SPEC["dv_n"] == 20 and M17.SPEC["win"] == 252 and M17.SPEC["min_n"] == 230
    assert (NREP, SEED, SEED_SHIFT) == (500, 20261019, 20261020) and CELLS == ("M", "W") and RULES["pctl"] == 97.5 and (RULES["m_reb"], RULES["w_events"], RULES["roc"], RULES["years"]) == (60, 500, 15.0, 6)
    assert (RULES["b_m_reb"], RULES["b_w_events"]) == (10, 100) and COST_BPS == 5.0 and STRESS_BPS == (10.0, 20.0) and COST_CURVE == (0.0, 5.0, 10.0, 20.0) and HEDGE_BPS == 0.5 and BETA_CAP == TILT_CAP == 0.20
    assert A2_WIN == (TS("2017-01-03"), TS("2018-12-31")) and A2_TARGET == 0.25 and A2_REPORT == (0.5, 2.0) and REF_DD5 == 34392.0 and JUDGED == "close" and REPORT_MODE == "keep" and AMEND_FORM == "8-K/A"
    assert DV.REF_SHA == "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18" and DV.REF_FACTS == {"roc": 121.06, "sortino": 3.926, "max_dd": 36526.0} and DV.REF_CSV_PINNED.endswith("resmom_cells_daily_wf_close.csv")
    assert CAL_SHA == "8f4f9f4bc61dc671a6f169f37f72c334fa3aecafff87a06af5ab250bcc85d4db" and MAP_SHA["map"].startswith("19adc9ba") and MAP_SHA["map_add"].startswith("6bf8dfab")
    assert os.path.basename(PRED_LIST_PINNED[0]) == "edgar_predecessor_map.csv" and PRED_LIST_PINNED[1] == "87620b86be78d46db10c3b68df3e5f6d03101595c5bc0923bbb6805cce6a3c00", "[E19] the list pinned"
    assert os.path.basename(PRED_CAL_PINNED[0]) == "earnings_calendar_predecessors.csv" and PRED_CAL_PINNED[1] == "5a9c4142966c11067f990615473c2c36ba598376d0276b483194388f9215ba1a", "[E20] the predecessors' releases pinned"
    assert PRED_EXPECTED == {"AVGO": "0001649338", "FOX": "0001308161", "FOXA": "0001308161", "MRVL": "0001058057", "CEG": "0001168165"} and PRED_HOLES == ("DISH", "NXPI", "SIRI", "TEAM") and NOT_CHANGE == "NOT A CIK CHANGE"
    assert PRED_COLS == ("symbol", "predecessor_cik", "predecessor_name", "successor_cik", "first_8k_date", "last_8k_date", "edgar_source_url", "note") and PRED_LIST is None and PRED_CAL is None, "the selftest reads no real file: its groups pin their own"
    assert PREREG_SHA == "df4f77495f2d77fa98dacbb3723fe5c1f6cf19b7725692de0d6bbeebbe532c57" and (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30"))
    assert E5_WAIVER == {"by": "MANAGER #141", "years": ("2016-17",), "addendum": "[E25]"} and SENS_FROM == TS("2017-07-01") and "no_beta_es_hole" not in W_REASONS, "[E25] the waiver and the sensitivity; [E26] no ES-hole reason"
    with quiet():
        pok = prereg_ok()
    assert pok["verified"] and pok["committed"] == "match", pok
    with patched(THIS, PREREG_SHA="0" * 64):
        refused(prereg_ok, "DIFFERS")
    with patched(D15, committed_state=lambda: "untracked"):
        refused(prereg_ok, "is not committed")
    with patched(D15, committed_state=lambda: "unknown"):
        refused(prereg_ok, "cannot be read")
    assert jyear(pd.DatetimeIndex(["2017-06-30", "2017-07-03"])).tolist() == [2016, 2017] and dstr(day_i(TS("2019-01-08"))) == "2019-01-08"


def t_files():
    """the pinned files' loaders: the earnings calendar (sha gate, columns, [E2], the cut at read on both dates, the ET stamps read as they stand), the map (sha gates, usable rows, the overlap / duplicate / bad-additions refusals), the members file ([E19] / [E20]: t_predecessors)"""
    rows_ = cal_rows_of([("AAA", "AAA", "123", TS("2024-01-08"), "amc", "8-K"), ("AAA", "AAA", "123", TS("2024-01-10"), "amc", AMEND_FORM), ("BBB", "BBB;BB2", "456", TS("2025-06-27"), "amc", "8-K"),
                         ("BBB", "BBB;BB2", "456", TS("2025-06-30"), "bmo", "8-K"), ("CCC", "CCC", "789", TS("2024-03-05"), "bmo", "8-K")])
    with calendar_file(rows_) as (fr, info):
        assert len(fr) == 3 and info["rows_on_file"] == 5 and info["dropped_accepted_on_or_after_the_cut"] == 1 and info["dropped_reaction_on_or_after_the_cut"] == 1 and info["amendments_dropped_e2"] == 1, info
        assert fr["cik"].tolist() == ["0000000123", "0000000123", "0000000789"] and fr["amend"].tolist() == [False, True, False] and fr["d"].tolist() == [TS("2024-01-08"), TS("2024-01-10"), TS("2024-03-05")]
        assert fr["acc"].iloc[0] == TS("2024-01-08 16:05") and fr["rs"].iloc[0] == TS("2024-01-09") and fr["rs"].iloc[2] == TS("2024-03-05") and info["releases_by_year"] == {2024: 2} and fr["tickers"].iloc[0] == ["AAA"]
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "cal.csv")
        sha = write_cal(p, rows_)
        with patched(THIS, CAL_CSV=p, CAL_SHA="0" * 64):
            refused(lambda: cal_load(S.LB0), "is not the registered one")
            assert cal_load(S.LB0, enforce=False)[0] is None
        with patched(THIS, CAL_CSV=os.path.join(td, "absent.csv"), CAL_SHA=sha):
            refused(lambda: cal_load(S.LB0), "is not on file")
        p2 = os.path.join(td, "cal2.csv")
        sha2 = write_cal(p2, rows_, header=tuple(h if h != "reaction_session" else "reaction" for h in CAL_HDR))
        with patched(THIS, CAL_CSV=p2, CAL_SHA=sha2):
            refused(lambda: cal_load(S.LB0), "lacks the column")
        mpf, adf = os.path.join(td, "map.csv"), os.path.join(td, "add.csv")
        open(mpf, "w", newline="\n").write("symbol,cik,method,name\nAAA,123,current_ticker,A\nBBB,,name_ambiguous,B\nCCC,789,name_exact,C\nDDD,555,non_common,D\n")
        open(adf, "w", newline="\n").write("symbol,cik,method,name\nBBB,456,reviewed_same_firm,B\n")
        files = {"map": mpf, "map_add": adf}
        shas = {k: M17.sha_raw(v) for k, v in files.items()}
        with patched(THIS, MAP_FILES=files, MAP_SHA=shas):
            mp = load_map()
            u = dict(zip(mp.df["symbol"], mp.df["usable"]))
            assert u == {"AAA": True, "CCC": True, "DDD": False, "BBB": True} and dict(zip(mp.df["symbol"], mp.df["cik"]))["BBB"] == "0000000456" and mp.info["usable_ciks"] == 3, (u, mp.info)
            ciks, codes = join_codes(np.array(["AAA", "DDD", "ZZZ", "BBB"]), mp)
            assert ciks.tolist() == ["0000000123", "", "", "0000000456"] and codes.tolist() == ["joined", "map_non_common", "not_in_map", "joined"]
        with patched(THIS, MAP_FILES=files, MAP_SHA={**shas, "map": "0" * 64}):
            refused(load_map, "is not the registered")
        open(adf, "a", newline="\n").write("AAA,123,reviewed_same_firm,A\n")
        with patched(THIS, MAP_FILES=files, MAP_SHA={k: M17.sha_raw(v) for k, v in files.items()}):
            refused(load_map, "usable row in BOTH")
        open(adf, "w", newline="\n").write("symbol,cik,method,name\nBBB,456,current_ticker,B\n")
        with patched(THIS, MAP_FILES=files, MAP_SHA={k: M17.sha_raw(v) for k, v in files.items()}):
            refused(load_map, "without a CIK or with a method outside")
        mf = os.path.join(td, "members.csv")
        open(mf, "w", newline="\n").write("ticker,from,to\nAAA,2016-01-01,\nBBB,2016-01-01,2020-03-01\nCCC,2020-03-01,\nLATE,2025-07-01,\n")
        mem, minfo = members_load(S.LB0, mf)
        assert minfo["rows_read"] == 3 and members_on(mem, "2020-02-01") == {"AAA", "BBB"} and members_on(mem, "2020-03-01") == {"AAA", "CCC"}, minfo
        refused(lambda: members_load(S.LB0, os.path.join(td, "absent.csv")), "not on file")


def t_pairs():
    """[E3] MANAGER's named cases at their real dates (2019): ILMN 01-08 / 01-29, REGN 01-07 / 02-06, ISRG 01-09 / 01-24 (the JPM-week preliminary results), DXCM 01-07 / 02-21 (45 days); a pair exactly 50 days apart and one 52 days apart are NOT pairs; two releases
    on one day: the later-accepted counts; an 8-K/A out [E2]; [P]'s 364-day rule and the next-session move; the point-in-time rule at ranks between the two releases; the vectorised table against the plain-python one"""
    spec_rows = []
    for t, cik, a, b in (("ILMN", "1110803", "2019-01-08", "2019-01-29"), ("REGN", "872589", "2019-01-07", "2019-02-06"), ("ISRG", "1035267", "2019-01-09", "2019-01-24"), ("DXCM", "1093557", "2019-01-07", "2019-02-21"),
                         ("FIFT", "500", "2019-01-07", "2019-02-26"), ("FTWO", "501", "2019-01-07", "2019-02-28")):
        spec_rows += [(t, t, cik, TS(a), "bmo", "8-K"), (t, t, cik, TS(b), "amc", "8-K"), (t, t, cik, TS(b) + pd.Timedelta(days=91), "amc", "8-K")]
    spec_rows += [("SAME", "SAME", "600", TS("2019-04-03"), "bmo", "8-K"), ("SAME", "SAME", "600", TS("2019-04-03"), "amc", "8-K"), ("SAME", "SAME", "600", TS("2019-04-05"), "amc", AMEND_FORM)]
    days = pd.bdate_range("2018-06-01", "2020-12-31")
    with calendar_file(cal_rows_of(spec_rows)) as (calf, info):
        rt = release_table(calf, days)
        Bz = brute_rel(calf, days)
    assert rt.n == len(calf) - 1 and info["amendments_dropped_e2"] == 1
    for c, rels in Bz.items():
        a, b = rt.span[c]
        assert [dstr(v) for v in rt.d[a:b]] == [f"{r_['d']:%Y-%m-%d}" for r_ in rels] and rt.p_row[a:b].tolist() == [r_["p_row"] for r_ in rels] and rt.rs_row[a:b].tolist() == [r_["rs_row"] for r_ in rels], c
        assert [dstr(v) if v < BIG else None for v in rt.nx[a:b]] == [None if r_["nx"] is None else f"{r_['nx']:%Y-%m-%d}" for r_ in rels], c
        for R in pd.date_range("2019-01-05", "2019-12-31", freq="5D"):
            assert kept_at(rt, a, b, int(day_i(R))).tolist() == brute_counts_at(rels, R), (c, R)
    pl = {(p_["ticker"], p_["earlier"], p_["later"]): p_["gap_days"] for p_ in pairs_list(rt)}
    assert pl == {("ILMN", "2019-01-08", "2019-01-29"): 21, ("REGN", "2019-01-07", "2019-02-06"): 30, ("ISRG", "2019-01-09", "2019-01-24"): 15, ("DXCM", "2019-01-07", "2019-02-21"): 45, ("SAME", "2019-04-03", "2019-04-03"): 0}, pl
    a, b = rt.span["0001110803"]
    R = int(day_i(TS("2019-12-31")))
    assert kept_at(rt, a, b, R).tolist() == [False, True, True], "ILMN: once both are known only the later (the real release) counts"
    assert kept_at(rt, a, b, int(day_i(TS("2019-01-20")))).tolist() == [True, False, False], "ILMN at a rank between the two: the pre-announcement counts - its real release is not known yet"
    assert dstr(rt.p_day[a + 1]) == "2020-01-28" and days[rt.p_row[a + 1]] == TS("2020-01-28") and dstr(rt.p_day[a]) == "2020-01-07"
    a, b = rt.span["0000000500"]
    assert kept_at(rt, a, b, R).tolist() == [True, True, True], "exactly 50 days apart is not a pair (the rule is 'less than 50')"
    a, b = rt.span["0000000600"]
    assert kept_at(rt, a, b, R).tolist() == [False, True] and rt.accession[a] < rt.accession[a + 1], "two releases on one day: the later-accepted counts"
    sat = cal_rows_of([("WKD", "WKD", "700", TS("2019-03-02"), "bmo", "8-K")])                        # a Saturday release: p = 2020-02-29 (a Saturday) moves to Monday 2020-03-02
    with calendar_file(sat) as (calf2, _i):
        rt2 = release_table(calf2, days)
    assert dstr(rt2.p_day[0]) == "2020-02-29" and days[rt2.p_row[0]] == TS("2020-03-02")


def t_predecessors():
    """[E19] / [E20]: the pinned list in TV's columns (the rows told apart from their content - a real CIK change, an empty predecessor, a predecessor equal to its successor; the addendum's changes asserted; the cut: a last date clipped, a first date dropped), every refusal
    (another sha, absent, a column missing, a symbol twice, a row that contradicts itself, changes / holes other than the addendum's); the predecessors' releases read as ONE table with the calendar (per-file counts, the cut; another sha / absent / a column missing refuse and
    the dryload reports; the same accession in both files refuses, and twice in one); the list x the table x the map (pred_check: a successor that is not the map's CIK, a stray predecessors' row, a predecessors' file without a list, the counts per change); the join (the
    window inclusive at both ends, a release two rows join added once - FOX / FOXA -, the predecessor's own rows kept, a row that is not a change joins nothing) against the plain-python table; the toy world: N00 in the universe from the first rank only through the join,
    [E19]'s joined name-months against a plain count (with / without the join / the member-month reading), N09 / N15 holes with their reasons"""
    txt = toy_pred_map_text()
    with pred_list_file(txt) as (fr, pi):
        assert fr["symbol"].tolist() == ["N00"] and fr["pred"].tolist() == [TOY_PRED_CIK] and fr["succ"].tolist() == [toy_cik(0)] and fr["lo"].tolist() == [TS("2022-12-01")] and fr["hi"].tolist() == [TS("2024-02-29")], fr
        assert pi["pinned"] and [h["symbol"] for h in pi["holes"]] == ["N09", "N15"] and pi["clipped_at_the_cut"] == 0 and pi["joins"][0]["source"] == "toy://N00" and "1 real CIK changes" in pi["text"], pi
    with pred_list_file(txt.replace("2024-02-29", "2026-08-06")) as (fr, pi):
        assert fr["hi"].tolist() == [S.LB0 - pd.Timedelta(days=1)] and pi["clipped_at_the_cut"] == 1 and pi["joins"][0]["clipped_at_the_cut"] and pi["joins"][0]["last_8k_date_read"] == "2025-06-29", "CEG's case: a last date past the cut is clipped"
    with pred_list_file(txt.replace("2022-12-01", "2025-07-01").replace("2024-02-29", "2025-08-01")) as (fr, pi):
        assert len(fr) == 0 and pi["dropped_first_on_or_after_the_cut"] == 1
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "edgar_predecessor_map.csv")
        with open(p, "w", newline="\n") as f:
            f.write(txt)
        with patched(THIS, PRED_LIST=(p, "0" * 64)):
            refused(lambda: pred_load(S.LB0), "is not the pinned one")
        with patched(THIS, PRED_LIST=(os.path.join(td, "absent.csv"), M17.sha_raw(p))):
            refused(lambda: pred_load(S.LB0), "is not on file")
    with patched(THIS, PRED_LIST=None):
        fr, pi = pred_load(S.LB0)
        assert fr is None and not pi["pinned"] and "NOT pinned" in pi["text"]

    def bad(text, frag, **kw):
        def fn():
            with pred_list_file(text, **kw):
                pass
        return refused(fn, frag)
    bad(txt.replace("edgar_source_url,note", "edgar_source_url,remark"), "lacks the column")
    bad(txt + f"N09,,,{toy_cik(9)},,,,NOT A CIK CHANGE - twice\n", "more than once")
    bad(txt.replace("toy: re-domiciled 2024-03", "NOT A CIK CHANGE - toy"), "does not say what they are")
    bad(txt.replace("NOT A CIK CHANGE - toy: a foreign filer (6-K)", "toy: a foreign filer"), "does not say what they are")
    bad(txt.replace("2022-12-01", "2022-13-01"), "does not say what they are")
    bad(txt.replace("2022-12-01", "2024-12-01"), "does not say what they are")
    bad(txt.replace("toy://N00", ""), "does not say what they are")
    bad(txt.replace(toy_cik(9), ""), "does not say what they are")
    bad(txt, "are not the addendum's", expected={"N00": TOY_PRED_CIK, "N01": f"{9001:010d}"})
    bad(txt, "are not the addendum's", expected={"N00": f"{9999:010d}"})
    bad(txt, "are not the addendum's", holes=("N09",))
    # [E20] the predecessors' releases: ONE table with the calendar
    main_rows = cal_rows_of([("AAA", "AAA", "123", TS("2024-01-08"), "amc", "8-K"), ("BBB", "BBB", "456", TS("2024-02-08"), "bmo", "8-K")])
    prev_rows = cal_rows_of([("AAA", "AAA", "900", TS("2023-10-09"), "amc", "8-K"), ("AAA", "AAA", "900", TS("2025-07-07"), "amc", "8-K")])
    with calendar_file(main_rows, pred_rows=prev_rows) as (fr, info):
        fl = info["files"]
        assert len(fr) == 3 and info["rows_on_file"] == 4 and fl["calendar"]["rows_read"] == 2 and fl["predecessors"]["rows_on_file"] == 2 and fl["predecessors"]["rows_read"] == 1 and info["dropped_accepted_on_or_after_the_cut"] == 1, info
        assert fr["src"].tolist().count("predecessors") == 1 and fr.loc[fr["src"] == "predecessors", "cik"].tolist() == ["0000000900"] and info["releases_by_year"] == {2023: 1, 2024: 2}
    with calendar_file(main_rows) as (fr, info):
        assert len(fr) == 2 and list(info["files"]) == ["calendar"] and set(fr["src"]) == {"calendar"}

    def bad_cal(rows_, prows, *frag):
        def fn():
            with calendar_file(rows_, pred_rows=prows):
                pass
        return refused(fn, *frag)
    bad_cal(main_rows, [prev_rows[0][:7] + (main_rows[0][7],)], "in both the calendar and the [E20] predecessors' releases")
    bad_cal(main_rows + [main_rows[1][:4] + ("2024-05-08 07:00", "2024-05-08") + main_rows[1][6:]], prev_rows, "listed twice in one file")
    with tempfile.TemporaryDirectory() as td:
        p0, p1, p2 = (os.path.join(td, n_) for n_ in ("cal.csv", "pred.csv", "pred2.csv"))
        s0, s1 = write_cal(p0, main_rows), write_cal(p1, prev_rows)
        s2 = write_cal(p2, prev_rows, header=tuple(h if h != "accession" else "acc_no" for h in CAL_HDR))
        with patched(THIS, CAL_CSV=p0, CAL_SHA=s0, PRED_CAL=(p1, "0" * 64)):
            refused(lambda: cal_load(S.LB0), "the [E20] predecessors' releases", "is not the registered one")
            fr_, i_ = cal_load(S.LB0, enforce=False)
            assert fr_ is None and i_["label"] == CAL_LABEL["predecessors"] and i_["matches"] is False, "the dryload reports another file and reads no table"
        with patched(THIS, CAL_CSV=p0, CAL_SHA=s0, PRED_CAL=(os.path.join(td, "absent.csv"), s1)):
            refused(lambda: cal_load(S.LB0), "the [E20] predecessors' releases is not on file")
        with patched(THIS, CAL_CSV=p0, CAL_SHA=s0, PRED_CAL=(p2, s2)):
            refused(lambda: cal_load(S.LB0), "the [E20] predecessors' releases lacks the column")
    # the join: NEWA / NEWB (two classes, one successor 700) <- 800 whose releases are in the calendar itself (FOX / FOXA's case), OTHR <- 900 whose releases are in the predecessors' file (MRVL's), HOLE not a change (same CIK)
    plist = ",".join(PRED_COLS) + "\n" + "\n".join(["NEWA,800,Old X,700,2018-10-01,2019-01-07,src://800,x", "NEWB,800,Old X,700,2018-10-01,2019-01-07,src://800,x", "OTHR,900,Old O,750,2017-01-01,2018-12-31,src://900,o",
                                                    "HOLE,760,,760,,,,NOT A CIK CHANGE - a same-CIK hole"]) + "\n"
    exp = {"NEWA": "0000000800", "NEWB": "0000000800", "OTHR": "0000000900"}
    m_spec = [("NEWA", "NEWA;NEWB", "700", TS("2019-04-08"), "bmo", "8-K"), ("NEWA", "NEWA;NEWB", "700", TS("2019-07-08"), "bmo", "8-K"), ("OTHR", "OTHR", "750", TS("2019-03-04"), "amc", "8-K"),
              ("HOLE", "HOLE", "760", TS("2019-02-04"), "amc", "8-K"), ("HOLE", "HOLE", "760", TS("2019-05-06"), "amc", "8-K")]
    m_spec += [("OLDX", "OLDX;OLDY", "800", TS(d_), "amc", "8-K") for d_ in ("2018-09-28", "2018-10-01", "2019-01-07", "2019-02-28")]     # a day before the window, its first day, its last day, after it
    m_spec += [("OLDX", "OLDX;OLDY", "800", TS("2018-10-03"), "amc", AMEND_FORM)]
    p_spec = [("OTHR", "OTHR", "900", TS(d_), "amc", "8-K") for d_ in ("2018-03-05", "2018-06-04", "2018-09-04", "2018-12-03")]
    mp2 = SimpleNamespace(df=pd.DataFrame({"symbol": ["NEWA", "NEWB", "OTHR", "HOLE"], "cik": ["0000000700", "0000000700", "0000000750", "0000000760"], "method": ["current_ticker"] * 4, "usable": [True] * 4}))
    days = pd.bdate_range("2018-01-02", "2020-12-31")
    with calendar_file(cal_rows_of(m_spec), pred_rows=cal_rows_of(p_spec)) as (calf, info):
        with pred_list_file(plist, expected=exp, holes=("HOLE",)) as (pred, pinfo):
            pi2 = pred_check(calf, pred, mp2, pinfo)
            refused(lambda: pred_check(calf, pred.assign(succ="0000000750"), mp2, pinfo), "not the symbol's usable CIK")
            refused(lambda: pred_check(calf.assign(cik=np.where(calf["src"] == "predecessors", "0000000800", calf["cik"])), pred, mp2, pinfo), "not a pinned [E19] predecessor's releases")
            refused(lambda: pred_check(calf.assign(tickers=pd.Series([["OTHR", "X"] if s_ == "predecessors" else t_ for s_, t_ in zip(calf["src"], calf["tickers"])], index=calf.index, dtype=object)), pred, mp2, pinfo), "not a pinned [E19] predecessor's releases")
            refused(lambda: pred_check(calf, None, mp2, pinfo), "no [E19] predecessor-CIK list is pinned")
        rt = release_table(calf, days, pred)
        Bz = brute_rel(calf, days, pred)
    j_ = {j["symbol"]: j for j in pi2["joins"]}
    assert (j_["NEWA"]["releases_joined"], j_["NEWA"]["from_calendar"], j_["NEWA"]["from_predecessors_file"], j_["NEWA"]["outside_the_window"], j_["NEWA"]["first"], j_["NEWA"]["last"]) == (2, 2, 0, 2, "2018-10-01", "2019-01-07"), j_["NEWA"]
    assert (j_["OTHR"]["releases_joined"], j_["OTHR"]["from_predecessors_file"], j_["OTHR"]["from_calendar"]) == (4, 4, 0) and j_["NEWB"]["releases_joined"] == 2, j_
    a, b = rt.span["0000000700"]
    assert [dstr(v) for v in rt.d[a:b]] == ["2018-10-01", "2019-01-07", "2019-04-08", "2019-07-08"] and rt.pred[a:b].tolist() == [True, True, False, False], "the window is inclusive at both ends; NEWA and NEWB join 800's releases ONCE"
    a, b = rt.span["0000000800"]
    assert b - a == 4 and not rt.pred[a:b].any(), "the predecessor's own rows stay under its own CIK"
    a, b = rt.span["0000000750"]
    assert rt.pred[a:b].tolist() == [True] * 4 + [False] and rt.n_pred_rows == 6
    a, b = rt.span["0000000760"]
    assert b - a == 2 and not rt.pred[a:b].any(), "a row that is not a CIK change joins nothing"
    assert set(Bz) == set(rt.span), (sorted(Bz), sorted(rt.span))
    for c, rels in Bz.items():
        a, b = rt.span[c]
        assert [dstr(v) for v in rt.d[a:b]] == [f"{r_['d']:%Y-%m-%d}" for r_ in rels] and rt.pred[a:b].tolist() == [r_["pred"] for r_ in rels] and rt.accession[a:b].tolist() == [r_["accession"] for r_ in rels], c
        assert rt.p_row[a:b].tolist() == [r_["p_row"] for r_ in rels] and [dstr(v) if v < BIG else None for v in rt.nx[a:b]] == [None if r_["nx"] is None else f"{r_['nx']:%Y-%m-%d}" for r_ in rels], c
    # the toy world: N00 (re-domiciled 2024-03; its earlier releases in the predecessors' file) is in the universe from the first rank only through the join; N09 / N15 join nothing
    with spec(**TOY_WIN):
        W, calf, mp, mem, Z = toy_setup(spins=False)
        ea = W.ea
        ks = list(range(len(ea.r)))
        assert ea.rt.n_pred_rows == sum(1 for r_ in Z.rels[toy_cik(0)] if r_["pred"]) == 5 and all(0 in ea.uni[k] for k in ks), "N00 joined: in the universe at every rank"
        pm = pred_months(W, ks, W.toy_pinfo)
        attach_eap(W, calf, mp, mem, None)
        k0 = ks[0]
        q0 = int(np.flatnonzero(W.ea.base[k0] == 0)[0])
        assert 0 not in W.ea.uni[k0] and UNI_REASONS[int(W.ea.first[k0][q0])] == "no_release", "without the join N00 has no release of its own before 2024-03"
        attach_eap(W, calf, mp, mem, ea.pred)
        rels = Z.rels[toy_cik(0)]
        want = {"joined_months": [], "fail_with": [], "fail_without": [], "fail_month_reading": []}
        lo_, hi_ = TS("2022-12-01"), TS("2024-02-29")
        own = [r_ for r_ in rels if not r_["pred"]]
        own = [{**r_, "nx": own[q + 1]["d"] if q + 1 < len(own) else None} for q, r_ in enumerate(own)]
        for k, (r, f, x, rn) in enumerate(Z.ranks):
            R = W.days[r]
            mon_ = f"{R:%Y-%m}"
            look = R - pd.Timedelta(days=SPEC["look_days"])
            kk, ko = brute_counts_at(rels, R), brute_counts_at(own, R)
            if any(kk[q] and r_["pred"] and r_["d"] >= look for q, r_ in enumerate(rels)):
                want["joined_months"].append(mon_)
            w_ok = sum(kk) > 0 and sum(1 for q, r_ in enumerate(rels) if kk[q] and r_["d"] >= look) >= SPEC["min_rel"]
            o_ok = sum(ko) > 0 and sum(1 for q, r_ in enumerate(own) if ko[q] and r_["d"] >= look) >= SPEC["min_rel"]
            for key, ok_ in (("fail_with", w_ok), ("fail_without", o_ok), ("fail_month_reading", w_ok if lo_ <= TS(f"{mon_}-01") <= hi_ else o_ok)):
                if not ok_:
                    want[key].append(mon_)
        got = pm["joins"][0]
        assert {k_: got[k_] for k_ in want} == want and got["member_months"] == got["in_universe"] == len(ks) and got["joined_in_universe"] == len(got["joined_months"]) > 0, (got, want)
        assert want["fail_with"] == [] and len(want["fail_without"]) >= 6 and want["fail_month_reading"] == want["fail_without"], want
        h_ = {h["symbol"]: h for h in pm["holes"]}
        assert set(h_["N09"]["out"]) == {"no_release"} and h_["N09"]["in_universe"] == 0 and "few_releases" in h_["N15"]["out"] and toy_cik(9) not in ea.rt.span and not ea.rt.pred[slice(*ea.rt.span[toy_cik(15)])].any(), h_
        with quiet():
            print_pred_months(pm, {"files": {"predecessors": {"path": "x.csv", "sha256": "0" * 64, "rows_on_file": 5, "rows_read": 5}}})
    return rt.n_pred_rows


def toy_counts(L, keys):
    tot = sum((Counter(c) for c in L.cnt.values()), Counter())
    return {k: int(tot.get(k, 0)) for k in keys}


def t_pipeline():
    """the toy world end to end against the plain-python recounts: every rank's universe (with its first reasons and [E1]'s drops, the alias member, the late member, the short history, the unmapped / unjoined / release-less / few-release names), the DUE flags, M's pools,
    sides and [E8] dollars, every pool name's path under four costings (base, 10 bps, the borrow stress, -100% for a stopped long) in the judged reading (N03's stock dividend inside an M hold CLOSES its position at the close before) and in the removal reading
    (N13's announced split and N03's ex-date remove them), W's events, reasons ([E9] with the ES hole apart, N08's lost close, N01's missing opens, the audit) and betas, every event's stock path and hedge (N04's spin-off inside its window closes both legs at the
    close before), the daily series of both cells; [E1]'s tie goes to the lower symbol -> the number of paths compared"""
    with spec(**TOY_WIN):
        W, calf, mp, mem, Z = toy_setup()
        ea = W.ea
        T = W.T
        ranks = [(r, f, x, rn) for r, f, x, rn in Z.ranks]
        assert ea.r.tolist() == [r for r, f, x, rn in ranks] and ea.x.tolist() == [x for r, f, x, rn in ranks] and ea.r_next.tolist() == [rn for r, f, x, rn in ranks], "the schedule"
        whys = Counter()
        for k, (r, f, x, rn) in enumerate(ranks):
            uni, why, drops = brute_universe(W, Z, r, f)
            assert ea.uni[k].tolist() == uni, (W.days[r], ea.uni[k].tolist(), uni)
            assert sorted(ea.drops[k]) == sorted(drops), (W.days[r], ea.drops[k], drops)
            base = np.flatnonzero(W.U[f])
            got = {int(j): (UNI_REASONS[int(q)] if q >= 0 else None) for j, q in zip(base, ea.first[k])}
            assert {j: v for j, v in got.items() if v} == why, (W.days[r], got, why)
            due = brute_due(W, Z, r, rn, uni)
            assert ea.due[k].tolist() == [due[j][0] for j in uni], (W.days[r], "DUE")
            whys.update(why.values())
        assert {"short_history", "not_member", "not_joined", "no_release", "few_releases", "second_class"} <= set(whys), whys
        j10, j11, j16, j17 = 10, 11, 16, 17
        k_early = next(k for k in range(len(ranks)) if W.days[ranks[k][0]] < TS("2024-06-01"))
        k_late = next(k for k in range(len(ranks)) if W.days[ranks[k][0]] > TS("2024-09-01"))
        assert j10 in ea.uni[k_early] and j11 not in ea.uni[k_early] and j11 in ea.uni[k_late] and j10 not in ea.uni[k_late], "[E1] the more liquid class stays, and the class that stays switches with the volume"
        assert j17 in ea.uni[k_early] and j16 not in ea.uni[k_early] and j16 in ea.uni[k_late], "the renamed member (OLD17) counts through its CIK's ndx_tickers; N16 only from 2024-07"
        lo, hi = TS("2024-01-01"), TS("2025-12-31")
        cfgs = {"base": (D15.l1_cfg(), {}), "10 bps": (D15.l1_cfg(bps=10.0), {"bps": 10.0}), "borrow stress": (D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[1])), {"borrow": (BORROW, BORROW_STRESS[1])}),
                "lose100": (D15.l1_cfg(lose100=True), {"lose100": True})}
        # the audit rows: an M name at the third rank's fill, a W event of N01
        W.aud1[ea.f[2], 2] = True
        c0 = ea.cand
        i1 = next(i for i in range(c0.n) if c0.col[i] == 1 and c0.x[i] >= 0 and c0.e[i] > 70 and np.isfinite(W.Ao[c0.e[i], 1]))
        W.audw[c0.e[i1], 1] = True
        n_paths = 0
        for mode in (JUDGED, REPORT_MODE):
            Bz = brute_m(W, Z, lo, hi, mode, {k_: v[1] for k_, v in cfgs.items()})
            L = m_build(W, lo, hi, mode)
            assert len(L.recs) == len(Bz) >= 8, (len(L.recs), len(Bz))
            for rec, b in zip(L.recs, Bz):
                assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]) and rec.pool.tolist() == b["pool"] and rec.pool[rec.iL].tolist() == b["long"] and rec.pool[rec.iS].tolist() == b["short"], (mode, W.days[rec.r])
                assert rec.traded == b["traded"] and close(rec.L_usd, b["L_usd"]) and close(rec.S_usd, b["S_usd"]), (mode, W.days[rec.r])
            assert sum(r_.traded for r_ in L.recs) >= 6 and any(r_.traded and r_.L_usd < SPEC["side_usd"] for r_ in L.recs) and any(r_.traded and r_.S_usd == SPEC["side_usd"] for r_ in L.recs), "[E8] a capped side and an uncapped one"
            with spec(min_side=6):
                L6 = m_build(W, lo, hi, mode, units=False)
            assert any(not r_.traded for r_ in L6.recs) and all(r_.traded == (r_.nL >= 6 and r_.nS >= 6) for r_ in L6.recs), "a month with fewer than min_side names on a side trades nothing"
            for lab, (cfg, _kw) in cfgs.items():
                run = m_run(W, L, cfg, pos=True)
                want = np.zeros(T)
                for rec, b in zip(L.recs, Bz):
                    if not b["traded"]:
                        continue
                    for j in b["pool"]:
                        sd = 1 if j in b["long"] else -1
                        usd = b["L_usd"] / len(b["long"]) if sd > 0 else b["S_usd"] / len(b["short"])
                        path, cl = b["paths"][lab][j]
                        add_path(want, b["f"], path, usd)
                        q = int(np.flatnonzero(rec.pool == j)[0])
                        assert rec.close[q] == cl, (mode, j, rec.close[q], cl)
                        n_paths += 1
                assert np.allclose(run.x, want, atol=1e-7, rtol=0), (mode, lab, float(np.abs(run.x - want).max()))
            if mode == JUDGED:
                assert any((rec.close >= 0).any() for rec in L.recs), "N03's stock dividend inside an M hold closes the position at the close before it [E16]"
                assert toy_counts(L, ("kept_calendar_split", "closed_spin"))["kept_calendar_split"] >= 1
            else:
                assert toy_counts(L, ("post_calendar_split", "post_spin")) == {"post_calendar_split": sum(b["why"]["post_calendar_split"] for b in Bz), "post_spin": sum(b["why"]["post_spin"] for b in Bz)} and sum(b["why"]["post_calendar_split"] for b in Bz) >= 1
            assert sum(b["why"]["audit"] for b in Bz) == toy_counts(L, ("audit",))["audit"] == 1 and sum(b["why"]["no_fill"] for b in Bz) == toy_counts(L, ("no_fill",))["no_fill"]
            # W
            evs, bcnt = brute_w(W, Z, lo, hi, mode, {k_: v[1] for k_, v in cfgs.items() if k_ != "borrow stress"})
            Lw = w_build(W, lo, hi, mode)
            ev = Lw.ev
            assert ev.n == len(evs) >= 15, (ev.n, len(evs))
            assert ev.e.tolist() == [z["e"] for z in evs] and ev.col.tolist() == [z["col"] for z in evs] and ev.p.tolist() == [z["p"] for z in evs] and ev.x.tolist() == [z["x"] for z in evs] and ev.close.tolist() == [z["close"] for z in evs]
            assert np.allclose(ev.beta, [z["beta"] for z in evs], atol=1e-9, rtol=0), "[E9] the betas against least squares"
            for y in set(bcnt) | set(Lw.cnt):
                for key in ("candidates", "unresolved", "no_entry_open", "no_beta", "audit", "post_calendar_split", "post_spin", "events", "beta_reached_back"):
                    assert Lw.cnt[y].get(key, 0) == bcnt[y].get(key, 0), (mode, y, key, Lw.cnt[y].get(key, 0), bcnt[y].get(key, 0))
            tot = sum((Counter(c) for c in bcnt.values()), Counter())
            assert tot["beta_reached_back"] >= 1 and tot["no_beta"] >= 1 and tot["no_entry_open"] >= 1 and tot["audit"] == 1, tot
            for lab, (cfg, _kw) in cfgs.items():
                if lab == "borrow stress":
                    continue
                run = w_run(W, Lw, cfg, pos=True)
                want = np.zeros(T)
                for i, z in enumerate(evs):
                    tot_ = [SPEC["w_slot"] * (a_ + b_) for a_, b_ in zip(z["stock"][lab], z["hedge"])]
                    add_path(want, z["e"], tot_)
                    assert abs(run.pos.pnl[i] - sum(tot_)) < 1e-7, (mode, lab, i)
                    n_paths += 1
                assert np.allclose(run.x, want, atol=1e-7, rtol=0), (mode, lab, float(np.abs(run.x - want).max()))
            if mode == JUDGED:
                assert 4 in ev.col[ev.close >= 0].tolist(), "N04's spin-off inside its window closes the event (stock and hedge) at the close before it"
            else:
                assert tot["post_spin"] >= 1
        # [E1] a tie in dollar volume goes to the lower symbol
        W.Cl[:, 11], W.Vv[:, 11], W.Od[:, 11] = W.Cl[:, 10], W.Vv[:, 10], W.Od[:, 10]
        attach_eap(W, calf, mp, mem, W.ea.pred)
        assert all(not (11 in u and 10 not in u) for u in W.ea.uni) and any(10 in u for u in W.ea.uni) and all(11 not in u for u in W.ea.uni), "[E1] a dollar-volume tie: the lower symbol stays"
    return n_paths


def t_nulls():
    """both nulls replayed in plain python with the same seeds: M's random names (the DUE side drawn from the rank's pool, the rest short, the same sizes / costs / [E16] cut paths), W's random names (one independent draw per event from the pool: an open, a beta, no audit row - the
    drawn name's own beta and close), [E11] W's time shift (each event's window moved back 27 .. 36 sessions, its own name, the hedge rule re-applied at the moved entry, an unavailable move = the event sits out that draw, counted); the shift range itself"""
    with spec(**TOY_WIN):
        W, calf, mp, mem, Z = toy_setup()
        lo, hi = TS("2024-01-01"), TS("2025-12-31")
        T, nr = W.T, 5
        Lm, Lw = m_build(W, lo, hi), w_build(W, lo, hi)
        acc = m_null(W, Lm, nr, np.random.default_rng([SEED, 0, 9]))
        rng = np.random.default_rng([SEED, 0, 9])
        want = np.zeros((nr, T))
        for rec in Lm.recs:
            if not rec.traded:
                continue
            n = len(rec.pool)
            o = np.argsort(rng.random((nr, n)), axis=1)[:, :rec.nL]
            for i in range(nr):
                lg = set(o[i].tolist())
                for q in range(n):
                    j = int(rec.pool[q])
                    sd = 1 if q in lg else -1
                    usd = rec.L_usd / rec.nL if sd > 0 else rec.S_usd / rec.nS
                    add_path(want[i], rec.f, brute_stock(W, rec.f, rec.x, j, sd, JUDGED, kt=W.k[rec.f:rec.x + 1])[0], usd)
        assert np.allclose(acc, want, atol=1e-7, rtol=0), float(np.abs(acc - want).max())
        accw = w_null(W, Lw, nr, np.random.default_rng([SEED, 1, 9]))
        rng = np.random.default_rng([SEED, 1, 9])
        want = np.zeros((nr, T))
        npool = 0
        for g in Lw.groups:
            k = int(g.k)
            bp = [int(j) for j in W.ea.uni[k] if math.isfinite(W.Od[g.e, j] / W.F[g.e, j]) and brute_beta(W, g.e, j)[1] == "ok" and not W.audw[g.e, j]]
            assert g.pool.tolist() == bp, (W.days[g.e], g.pool.tolist(), bp)
            picks = rng.integers(0, len(g.pool), (len(g.ev), nr))
            for qi in range(len(g.ev)):
                for i in range(nr):
                    j = int(g.pool[picks[qi, i]])
                    b = brute_beta(W, g.e, j)[0]
                    sp, cl = brute_stock(W, g.e, g.x, j, 1, JUDGED)
                    add_path(want[i], g.e, [SPEC["w_slot"] * (a_ + b_) for a_, b_ in zip(sp, brute_hedge(W, g.e, g.x, b, cl))])
            npool += len(g.pool)
        assert np.allclose(accw, want, atol=1e-7, rtol=0), float(np.abs(accw - want).max())
        acct, left = w_shift_null(W, Lw, 7, np.random.default_rng([SEED_SHIFT, 1, 9]), block=3)
        rng = np.random.default_rng([SEED_SHIFT, 1, 9])
        want, wl = np.zeros((7, T)), np.zeros(7, np.int64)
        ev = Lw.ev
        seen = set()
        for b0 in range(0, 7, 3):
            D = min(3, 7 - b0)
            s = rng.integers(SPEC["shift_lo"], SPEC["shift_hi"] + 1, (ev.n, D))
            seen.update(s.ravel().tolist())
            for i in range(D):
                for q in range(ev.n):
                    e2, j = int(ev.e[q] - s[q, i]), int(ev.col[q])
                    x2 = e2 + SPEC["w_pre"] + SPEC["w_post"]
                    b, st = brute_beta(W, e2, j) if e2 >= 0 else (float("nan"), "no_beta")
                    if e2 < 0 or not math.isfinite(W.Od[e2, j] / W.F[e2, j]) or st != "ok":
                        wl[b0 + i] += 1
                        continue
                    sp, cl = brute_stock(W, e2, x2, j, 1, JUDGED)
                    add_path(want[b0 + i], e2, [SPEC["w_slot"] * (a_ + b_) for a_, b_ in zip(sp, brute_hedge(W, e2, x2, b, cl))])
        assert np.allclose(acct, want, atol=1e-7, rtol=0) and left.tolist() == wl.tolist() and wl.max() > 0, (float(np.abs(acct - want).max()), left.tolist(), wl.tolist())
        assert seen <= set(range(27, 37))
    big = np.random.default_rng(1).integers(SPEC["shift_lo"], SPEC["shift_hi"] + 1, 20000)
    assert set(big.tolist()) == set(range(27, 37)), "[E11] 27 .. 36 inclusive, uniform"
    return npool


def t_accuracy():
    """[E5] both ways against a plain-python count on the toy world (N07's two-week-late year lowers both), and the STOP: a calendar whose releases from 2024-02 on are five weeks late sends recall under 80% and stops the run before any P&L; [E6] turnover and the break-even
    spread against a plain-python count; [E7] the power line's arithmetic"""
    with spec(**TOY_WIN):
        W, calf, mp, mem, Z = toy_setup(spins=False)
        acc = accuracy(W)
        want_p, want_r, cut = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0]), 0
        actual = {}
        for c, rels in Z.rels.items():
            actual[c] = sorted({r_["rs_row"] for r_ in rels if r_["rs_row"] >= 0 and not (r_["nx"] is not None and (r_["nx"] - r_["d"]).days < 50)})
        for (r, f, x, rn) in Z.ranks:
            if x < 0 or not (WF0 <= W.days[x] <= PRE_END):
                continue
            uni = brute_universe(W, Z, r, f)[0]
            due = brute_due(W, Z, r, rn, uni)
            for j in uni:
                a = actual.get(Z.cik_of[j], [])
                for q in due[j][1]:
                    p = Z.rels[Z.cik_of[j]][q]["p_row"]
                    if p > W.T - 1 - 7:
                        cut += 1
                        continue
                    dmin = min((abs(t - p) for t in a), default=10 ** 6)
                    v = want_p[int(jyear(W.days[[p]])[0])]
                    v[0] += 1
                    v[1] += dmin <= 3
                    v[2] += dmin <= 7
                for t in a:
                    if r + 1 <= t <= rn:
                        v = want_r[int(jyear(W.days[[t]])[0])]
                        v[0] += 1
                        v[1] += due[j][0]
        for y, v in acc["by_year"].items():
            assert v["predicted"] == want_p[y][0] and (v["predicted"] == 0 or (close(v["within_3"], want_p[y][1] / want_p[y][0]) and close(v["within_7"], want_p[y][2] / want_p[y][0]))), (y, v, want_p[y])
            assert v["actual"] == want_r[y][0] and v["recalled"] == want_r[y][1], (y, v, want_r[y])
        assert acc["left_out_near_the_data_end"] == cut and not acc["stop"] and 0.5 < acc["total"]["within_3"] < 1.0 and acc["total"]["recall"] > 0.8, acc["total"]
        tv = turnover(W, m_build(W, TS("2024-01-01"), TS("2025-12-31"), units=False))
        prev, n_tr = None, 0
        for r_ in tv["rows"]:
            if r_["transition"]:
                n_tr += 1
                assert 0.0 <= r_["turnover_long"] <= 1.0 and 0.0 <= r_["turnover_short"] <= 1.0
        L0 = m_build(W, TS("2024-01-01"), TS("2025-12-31"), units=False)
        prev = None
        q = 0
        for rec in L0.recs:
            if not rec.traded:
                prev = None
                continue
            cur = {"L": {int(j): rec.L_usd / rec.nL for j in rec.pool[rec.iL]}, "S": {int(j): rec.S_usd / rec.nS for j in rec.pool[rec.iS]}}
            row_ = tv["rows"][q]
            cost5 = 5e-4 * 2 * (rec.L_usd + rec.S_usd) + BORROW * rec.S_usd * (rec.x - rec.f) / 252.0
            assert close(row_["breakeven_5"], cost5 / (0.5 * (rec.L_usd + rec.S_usd))), row_
            if prev is not None:
                for sd, usd, pusd in (("L", rec.L_usd, prev["L$"]), ("S", rec.S_usd, prev["S$"])):
                    names = set(cur[sd]) | set(prev[sd])
                    tw = 0.5 * sum(abs(cur[sd].get(n_, 0.0) / usd - prev[sd].get(n_, 0.0) / pusd) for n_ in names)
                    assert close(row_["turnover_long" if sd == "L" else "turnover_short"], tw), (sd, row_)
            prev = {**cur, "L$": rec.L_usd, "S$": rec.S_usd}
            q += 1
        assert q == tv["traded_rebalances"] and n_tr == tv["transitions"] >= 4
        pw = power_line(W, L0, 400, 2.0)
        m_ = pw["M"]
        recs = [r_ for r_ in L0.recs if r_.traded]
        side = float(np.mean([0.5 * (r_.L_usd + r_.S_usd) for r_ in recs]))
        c5 = sum(5e-4 * 2 * (r_.L_usd + r_.S_usd) + BORROW * r_.S_usd * (r_.x - r_.f) / 252.0 for r_ in recs) / 2.0
        assert close(m_["need"]["dd15000_5bps"], (7500.0 + c5) / (len(recs) / 2.0) / side) and m_["need"]["dd30000_10bps"] > m_["need"]["dd15000_5bps"]
        w_ = pw["W"]
        assert 0.0 < w_["net_need"] < 0.2 and close(w_["gross_need"]["5bps"] - w_["net_need"], 2 * 5e-4 + 2 * HEDGE_BPS * 1e-4)
        # the STOP: from 2024-02 on every release is five weeks late
        W2, calf2, mp2, mem2, Z2 = toy_setup(spins=False, calendar=toy_releases(shift_from="2024-02-01"))
        acc2 = accuracy(W2)
        assert acc2["stop"] and 2023 in acc2["stop_years"] and all(acc2["by_year"][y]["recall"] < 0.8 for y in acc2["stop_years"]), acc2["by_year"]
        with quiet():
            print_accuracy(acc2)
        # [E25] the waiver: the stop still FIRES; Stage A goes on only when the recorded waiver names every failing year - any other failing year still stops
        sy = acc2["stop_years"]
        assert acc2["halt"] and acc2["halt_years"] == sy and acc2["waived_years"] == [] and e5_phrase(acc2) == "", "the registered waiver (2016-17) covers none of the toy's years"
        with patched(THIS, E5_WAIVER={"by": "TEST #1", "years": tuple(yl(y) for y in sy), "addendum": "[E25]"}):
            a3 = accuracy(W2)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                print_accuracy(a3)
            rec = e5_record(a3)
            assert a3["stop"] and not a3["halt"] and a3["waived_years"] == sy and a3["waived_by"] == "TEST #1" and "FIRED at" in e5_phrase(a3) and "WAIVED by TEST #1" in e5_phrase(a3), a3
            assert "[E5] STOP: FIRED" in buf.getvalue() and "the run goes on" in buf.getvalue() and rec["fired"] and not rec["halted"] and rec["waived_by"] == "TEST #1" and set(rec["failing_years"]) == {yl(y) for y in sy}
        with patched(THIS, E5_WAIVER={"by": "TEST #2", "years": (yl(sy[0]), "2099-00"), "addendum": "[E25]"}):
            a4 = accuracy(W2)
            assert a4["stop"] and a4["waived_years"] == sy[:1] and a4["halt_years"] == sy[1:] and a4["halt"] == bool(sy[1:]), a4
        with patched(THIS, E5_WAIVER={"by": "TEST #3", "years": ("2099-00",), "addendum": "[E25]"}):
            assert accuracy(W2)["halt"], "a waiver for another year waives nothing"
        assert e5_waive([2016]) == ([2016], []) and e5_waive([2016, 2019]) == ([2016], [2019]) and e5_waive([2024]) == ([], [2024]) and e5_waive([]) == ([], []), "the registered waiver: 2016-17 alone"
    return acc["total"]


def t_es_window():
    """[E26] the beta window = the 252 (toy: 60) most recent sessions before the entry ON WHICH ES HAS A RETURN: across the toy ES master's hole (no return on rows 270 / 271) it reaches back two sessions and still counts 60, the beta against least squares on exactly
    those rows; a window without the hole does not reach back; a stock missing its own return on one of the window's sessions still has no beta (planted); M's [E13] betas (the window to the rank close, >= 55 of the name's returns) and the shift null's moved entries read the
    same windows; the dryload's counts-only path counts the same no_beta / beta_reached_back as the full one"""
    with spec(**TOY_WIN):
        W, calf, mp, mem, Z = toy_setup(spins=False)
        assert np.flatnonzero(~np.isfinite(np.asarray(W.es.ret, float))).tolist() == [0, 270, 271], "the toy ES master: no return on row 0 and on the hole's two sessions"
        j = 3
        b, n, reach = w_beta(W, [290], [j])
        rows_ = brute_window(W, 289)
        assert len(rows_) == 60 and rows_[0] == 228 and 270 not in rows_ and 271 not in rows_ and n[0] == 60 and reach[0], (rows_[:3], n, reach)
        X = np.column_stack([np.ones(60), np.asarray(W.es.ret, float)[rows_]])
        assert close(b[0], float(np.linalg.lstsq(X, np.asarray(W.Rd, float)[rows_, j], rcond=None)[0][1]), 1e-9) and close(b[0], brute_beta(W, 290, j)[0], 1e-9), "the reached-back window against least squares"
        b2, n2, r2 = w_beta(W, [250], [j])
        assert brute_window(W, 249)[0] == 190 and n2[0] == 60 and not r2[0] and close(b2[0], brute_beta(W, 250, j)[0], 1e-9), "no hole in the window: rows e-60 .. e-1, no reach-back"
        b61, b60 = w_beta(W, [61], [j]), w_beta(W, [60], [j])
        assert b61[1][0] == 60 and np.isfinite(b61[0][0]) and b60[1][0] == 0 and not np.isfinite(b60[0][0]), "row 0 has no ES return: the first full window is rows 1 .. 60 (an entry on row 61)"
        r = 280
        bm = m_betas(W, r, np.array([j, 8]))
        assert close(bm[0], brute_beta(W, 0, j, t_end=r, need=SPEC["m_beta_need"])[0], 1e-9) and brute_window(W, r)[0] == 219, "M's [E13] betas: the 60 ES-defined sessions to the rank close"
        Lw = w_build(W, TS("2024-01-01"), TS("2025-12-31"), units=False)
        tot = sum((Counter(c) for c in Lw.cnt.values()), Counter())
        attach_eap(W, calf, mp, mem, W.ea.pred, counts_only=True)
        Lc = w_build(W, TS("2024-01-01"), TS("2025-12-31"), units=False)
        totc = sum((Counter(c) for c in Lc.cnt.values()), Counter())
        assert all(tot.get(k, 0) == totc.get(k, 0) for k in ("candidates", "no_entry_open", "no_beta", "events", "beta_reached_back")) and tot["beta_reached_back"] >= 1, (tot, totc)
        Rd = np.array(W.Rd, float, copy=True)
        W.Rd[265, j] = np.nan                                                                   # planted: the stock has no return on row 265, inside the reached-back window of an entry at 290
        attach_eap(W, calf, mp, mem, W.ea.pred)
        b3, n3, r3 = w_beta(W, [290], [j])
        assert n3[0] == 59 and r3[0] and not np.isfinite(b3[0]), "a stock missing its own return on a session of a reached-back window still fails [E26]"
        b8, n8, _ = w_beta(W, [230], [8])
        assert n8[0] == 58 and not np.isfinite(b8[0]) and brute_beta(W, 230, 8)[1] == "no_beta", "N08's lost close on row 200 (no return on 200 / 201): no beta, as the plain count says"
        assert np.isfinite(m_betas(W, 280, np.array([j]))[0]), "M's count is >= 55 of 60: one missing return keeps M's beta"
        W.Rd[:] = Rd
        attach_eap(W, calf, mp, mem, W.ea.pred)
    return int(tot["beta_reached_back"])


def t_sensitivity():
    """[E25] the sensitivity without 2016-17: the governing verdict is the STRICTER (a FAIL in either fails; both pass -> the candidate passes both, by the full window's ROC); the stretch's years (8) and the judge's breadth label; the legs keep exactly the positions / events
    ENTERED on / after the stretch's first day (against the full window's legs), nothing before it carries P&L - the cells, both random-name nulls (the same seeds) and the time-shift null (a moved window may not start before it: it sits out, counted); A2 on the stretch
    (c on the clipped window 2017-07-01 .. 2018-12-31, L + c x the cell against L on the stretch, DD5) against a plain computation"""
    P_ = lambda ok, roc: {"PASS": ok, "base": {"roc": roc}}
    g = govern({"M": P_(True, 30.0), "W": P_(True, 40.0)}, {"M": P_(True, 20.0), "W": P_(True, 25.0)})
    assert g == {"pass_full": ["M", "W"], "pass_sensitivity": ["M", "W"], "pass_cells": ["M", "W"], "candidate": "W", "differ": False}, g
    g = govern({"M": P_(True, 30.0), "W": P_(True, 40.0)}, {"M": P_(True, 20.0), "W": P_(False, 5.0)})
    assert g["pass_cells"] == ["M"] and g["candidate"] == "M" and g["differ"], "the sensitivity fails W: the stricter verdict keeps M alone, though W has the higher full-window ROC"
    g = govern({"M": P_(False, 10.0), "W": P_(False, 3.0)}, {"M": P_(True, 20.0), "W": P_(False, 5.0)})
    assert g["pass_cells"] == [] and g["candidate"] is None and g["differ"], "a sensitivity pass never rescues a full-window FAIL"
    g = govern({"M": P_(True, 30.0), "W": P_(False, 3.0)}, {"M": P_(False, 10.0), "W": P_(False, 5.0)})
    assert g["pass_cells"] == [] and g["candidate"] is None and g["pass_full"] == ["M"] and g["differ"]
    assert sens_years(SENS_FROM) == tuple(range(2017, 2025)) and sens_years(WF0) == YEARS and sens_years(None or WF0) == YEARS and a2_window(SENS_FROM) == (TS("2017-07-01"), TS("2018-12-31")) and a2_window(WF0) == A2_WIN
    st = {"n_units": 100, "n_pos": 900, "roc": 40.0, "net": 1e5, "years_pos": 6, "net_ex2020": 5e4, "net_ex_best_days": 3e4, "net_ex_best_pos": 2e4}
    nul = {"roc_max": {"p97.5": 20.0}, "time_shift": {"roc": {"p97.5": 25.0}}}
    assert judge_cell("W", st, 5e4, nul, n_years=8)["positive in >=6 of 8 July-June years"] and not judge_cell("W", {**st, "years_pos": 5}, 5e4, nul, n_years=8)["positive in >=6 of 8 July-June years"]
    with spec(**TOY_WIN):
        W, calf, mp, mem, Z = toy_setup(spins=False)
        lo2, hi = TS("2024-07-01"), TS("2025-12-31")
        lo_m, lo_w, t0 = sens_bounds(W, lo2)
        assert W.days[t0] == TS("2024-07-01") and W.days[t0 - 1] < lo2
        Lm_f, Lm_s = m_build(W, WF0, hi), m_build(W, lo_m, hi)
        assert [(r_.r, r_.f, r_.x) for r_ in Lm_s.recs] == [(r_.r, r_.f, r_.x) for r_ in Lm_f.recs if r_.f >= t0] and 0 < len(Lm_s.recs) < len(Lm_f.recs), "M: exactly the rebalances filled on / after the cut"
        Lw_f, Lw_s = w_build(W, WF0, hi), w_build(W, lo_w, hi)
        keep = Lw_f.ev.e >= t0
        assert Lw_s.ev.e.tolist() == Lw_f.ev.e[keep].tolist() and Lw_s.ev.col.tolist() == Lw_f.ev.col[keep].tolist() and 0 < Lw_s.ev.n < Lw_f.ev.n, "W: exactly the events entered on / after the cut"
        xm, xw = m_run(W, Lm_s, D15.l1_cfg()).x, w_run(W, Lw_s, D15.l1_cfg()).x
        assert not xm[:t0].any() and not xw[:t0].any() and xm[t0:].any() and xw[t0:].any(), "no P&L before the stretch"
        am = m_null(W, Lm_s, 4, np.random.default_rng([SEED, 0, 0]))
        aw = w_null(W, Lw_s, 4, np.random.default_rng([SEED, 1, 0]))
        a0, l0 = w_shift_null(W, Lw_s, 6, np.random.default_rng([SEED_SHIFT, 1, 0]))
        a1, l1 = w_shift_null(W, Lw_s, 6, np.random.default_rng([SEED_SHIFT, 1, 0]), t_min=t0)
        assert not am[:, :t0].any() and not aw[:, :t0].any() and not a1[:, :t0].any() and a0[:, :t0].any(), "the nulls on the stretch: nothing before it (the shift null's moved windows may not start before it)"
        assert (l1 >= l0).all() and (l1 > l0).any(), "a moved window that would start before the stretch sits out that draw, counted"
    days = pd.bdate_range("2016-07-01", "2019-06-28")
    rng = np.random.default_rng(11)
    B = ToyB(days, rng.normal(50.0, 300.0, len(days)))
    xB = np.where(np.asarray(days >= SENS_FROM), rng.normal(5.0, 100.0, len(days)), 0.0)
    raw_L = np.asarray(B.raw) + 0.264 * rng.normal(10.0, 200.0, len(days))
    ref = SimpleNamespace(raw=raw_L, S=None, stats=R11.stats(raw_L, B.index))
    S12s, refs = stretch_ref(B, ref, SENS_FROM)
    a = a2_report(B, xB, refs, SENS_FROM)
    k = B.mask(TS("2017-07-01"), TS("2018-12-31"))
    c = 0.25 * np.std(np.asarray(B.raw)[k], ddof=1) / np.std(xB[k], ddof=1)
    k2 = B.mask(SENS_FROM, PRE_END)
    s = R11.stats((raw_L + c * xB)[k2], B.index[k2])
    r2 = R11.stats(raw_L[k2], B.index[k2])
    assert close(a["c"], c, 1e-12) and a["window"] == ["2017-07-01", "2018-12-31"] and close(a["roc"], s["roc"], 1e-9) and close(a["sortino"], s["sort"], 1e-9) and close(a["reference"]["roc"], r2["roc"], 1e-9), a
    assert a["incremental_pass"] == bool(s["roc"] > r2["roc"] and s["sort"] > r2["sort"]) and close(a["dd5"]["dd5"], dd5_rec(B, raw_L + c * xB, SENS_FROM)["dd5"]) and close(a["at_double_c"]["c"], 2 * c, 1e-12)
    assert S12s.dates[0] >= SENS_FROM and refs.S.dates[0] >= SENS_FROM and refs.S.dates[-1] == days[-1]
    return int(Lw_s.ev.n)


def t_judge():
    """Stage A's checks, each broken alone (every other one passing): (a) the count, (b) the ROC and the two nets, (c) above the random-name null's p97.5 (and W: the time-shift null's), (d) the years and the 2020 window, (e) the best days / name-periods, [E13] M's hedged
    ROC; the candidate pick; Stage B's leg veto, each check alone"""
    st = {"n_units": 100, "n_pos": 900, "roc": 40.0, "net": 1e5, "years_pos": 7, "net_ex2020": 5e4, "net_ex_best_days": 3e4, "net_ex_best_pos": 2e4}
    nul = {"roc_max": {"p97.5": 20.0}, "time_shift": {"roc": {"p97.5": 25.0}}}
    q = f"p{RULES['pctl']:g}"
    for cell in CELLS:
        hr = 30.0 if cell == "M" else None
        base = judge_cell(cell, st, 5e4, nul, hr)
        assert all(base.values()) and len(base) == 10, (cell, base)
        breaks = [({"n_units": 59, "n_pos": 499}, 5e4, nul, hr, f"traded rebalances>={RULES['m_reb']}" if cell == "M" else f"events>={RULES['w_events']}"),
                  ({"roc": 14.9}, 5e4, {"roc_max": {"p97.5": 10.0}, "time_shift": {"roc": {"p97.5": 10.0}}}, hr, f"ROC>={RULES['roc']:g}"),
                  ({"net": -1.0}, 5e4, nul, hr, "net>0 at 5 bps"), ({}, -1.0, nul, hr, "net>0 at 10 bps"),
                  ({}, 5e4, {"roc_max": {"p97.5": 40.0}, "time_shift": {"roc": {"p97.5": 25.0}}}, hr, f"ROC>random-name null {q}"),
                  ({"years_pos": 5}, 5e4, nul, hr, f"positive in >={RULES['years']} of 9 July-June years"), ({"net_ex2020": 0.0}, 5e4, nul, hr, "net>0 without Feb 15 - Apr 30 2020"),
                  ({"net_ex_best_days": -1.0}, 5e4, nul, hr, "profitable without its best 1% of days"), ({"net_ex_best_pos": -1.0}, 5e4, nul, hr, "profitable without its best 1% of " + ("name-months" if cell == "M" else "events"))]
        breaks += [({}, 5e4, nul, 14.9, f"[E13] M hedged by its beta gap ROC>={RULES['roc']:g}")] if cell == "M" else [({}, 5e4, {"roc_max": {"p97.5": 20.0}, "time_shift": {"roc": {"p97.5": 40.0}}}, hr, f"ROC>time-shift null {q}")]
        for upd, n10, nu, h, want in breaks:
            bad = [k for k, v in judge_cell(cell, {**st, **upd}, n10, nu, h).items() if not v]
            assert bad == [want], (cell, upd, bad, want)
        assert not judge_cell(cell, {**st, "roc": float("nan")}, 5e4, nul, hr)[f"ROC>={RULES['roc']:g}"], "a NaN fails"
    cells = {"M": {"base": {"roc": 30.0}, "PASS": True}, "W": {"base": {"roc": 30.0}, "PASS": True}}
    assert stage_a_flow(cells) == (["M", "W"], "M") and stage_a_flow({**cells, "M": {"base": {"roc": 20.0}, "PASS": True}})[1] == "W" and stage_a_flow({c: {**v, "PASS": False} for c, v in cells.items()}) == ([], None)
    leg = {"n_units": 12, "net": 10.0, "net_ex_top_pos": 1.0}
    assert all(b_checks("M", leg).values()) and not b_checks("M", {**leg, "n_units": 9})["leg monthly rebalances>=10"] and not all(b_checks("W", leg).values()) and all(b_checks("W", {**leg, "n_units": 100}).values())
    assert not b_checks("M", {**leg, "net": float("nan")})["leg net>0"] and not b_checks("M", {**leg, "net_ex_top_pos": 0.0})["leg net>0 without its top name-period"]


class ToyB:
    """a stand-in for #463's index on the toy sessions (the reports read only index / n / mask / raw)"""
    def __init__(self, days, raw):
        self.index, self.n, self.raw = pd.DatetimeIndex(days), len(days), np.asarray(raw, float)

    def mask(self, lo, hi):
        return np.asarray((self.index >= lo) & (self.index <= hi))


def t_reports():
    """the reports on hand-made series: [E10]'s loading recovered from a planted tilt and the tilt-removed ROC, [E13]'s peak weeks against a plain count and the season-day beta, [E14] SEAT's episode sums and week shares, [E15]'s live stretch, the event-time path against a
    plain average, the notional series, es_open_prints' carries"""
    with spec(**TOY_WIN, peak_names=2):
        W, calf, mp, mem, Z = toy_setup(spins=False)
        T = W.T
        rows = np.arange(T)
        rng = np.random.default_rng(5)
        Lw = w_build(W, TS("2024-01-01"), TS("2025-12-31"))
        N = notional_series(W, "W", Lw)
        want = np.zeros(T)
        for e, x in zip(Lw.ev.e, Lw.ev.x):
            want[e:x + 1] += SPEC["w_slot"]
        assert np.array_equal(N, want)
        es = np.nan_to_num(np.asarray(W.es.ret, float))
        nq = es + rng.normal(0.0, 0.004, T)
        x = N * (0.5 * es + 0.3 * (nq - es)) + rng.normal(0.0, 1.0, T) * (N > 0)
        B = ToyB(W.days, rng.normal(10.0, 300.0, T))
        t = tilt_e10(B, W, rows, x, nq, N)
        assert abs(t["loading_nq_minus_es"] - 0.3) < 0.02 and abs(t["beta_es"] - 0.5) < 0.02 and t["over_cap"], t
        adj = x.copy()
        sel = (N > 0) & np.isfinite(np.asarray(W.es.ret, float))
        adj[sel] -= t["loading_nq_minus_es"] * N[sel] * (nq[sel] - es[sel])
        s1 = R11.stats(adj, B.index)
        assert close(t["rows"]["WF"]["tilt_removed_roc"], s1["roc"]) and close(t["rows"]["WF"]["raw_roc"], R11.stats(x, B.index)["roc"])
        peak, keys = peak_days(W)
        act = actual_rows(W)
        cnt = Counter()
        iso = W.days.isocalendar()
        wk = (iso["year"] * 100 + iso["week"]).to_numpy()
        for k in range(len(W.ea.r)):
            for j in W.ea.uni[k]:
                for t_ in act.get(str(W.ea.cik[j]), []):
                    if W.ea.r[k] + 1 <= t_ <= W.ea.r_next[k]:
                        cnt[int(wk[t_])] += 1
        assert keys == {w for w, v in cnt.items() if v >= 2} and len(keys) >= 3 and np.array_equal(peak, np.isin(wk, list(keys))), (keys, cnt)
        sb = season_beta(B, W, rows, x, peak, N)
        sel = (N > 0) & peak & np.isfinite(np.asarray(W.es.ret, float))
        assert close(sb["peak reporting weeks"]["usd_per_1.00_es"], np.polyfit(es[sel], x[sel], 1)[0], 1e-6)
        S12 = M12.Stretch(B.raw, B.index, None, WF0, PRE_END)
        ref = SimpleNamespace(S=M12.Stretch(B.raw + 0.5 * x, B.index, None, WF0, PRE_END), raw=B.raw + 0.5 * x)
        se = seat_e14(B, S12, ref, {"W": x}, keys)
        e0 = S12.episodes[0]
        assert close(se["books"]["#463"][0]["cells"]["W"], x[S12.rows[e0["i0"]:e0["it"] + 1]].sum()) and close(se["books"]["#463"][0]["book_pnl"], B.raw[e0["i0"]:e0["it"] + 1].sum())
        assert len(se["books"]["#463"]) == min(5, len(S12.episodes)) and 0.0 <= se["base_share_peak_weeks"] <= 1.0
        ls = live_stretch(B, ref, x, 0.5, f"{W.days[100]:%Y-%m-%d}")
        k_ = B.mask(W.days[100], PRE_END)
        assert close(ls["live"]["L"]["roc"], R11.stats(ref.raw[k_], B.index[k_])["roc"]) and close(ls["live"]["L + c x cell"]["net"], (ref.raw + 0.5 * x)[k_].sum())
        pth = event_path(W, Lw)
        tau0 = pth["taus"].index(0)
        vals = [W.Rd[p, j] - b * W.es.ret[p] for p, j, b in zip(Lw.ev.p, Lw.ev.col, Lw.ev.beta) if np.isfinite(W.Rd[p, j] - b * W.es.ret[p])]
        assert close(pth["predicted"]["mean_bps"][tau0], 1e4 * np.mean(vals), 1e-9) and pth["predicted"]["n"][tau0] == len(vals)
    # es_open_prints on a hand-made pair of 5-minute masters: a missing 09:30 bar falls back to the first bar before 10:00, a day without bars carries the last print
    days = pd.bdate_range("2024-03-04", periods=4)
    idx, o, c = [], [], []
    for q, d in enumerate(days):
        if q == 2:
            continue                                                                             # no bar at all on the third session
        for s_ in range(78):
            if q == 1 and s_ == 0:
                continue                                                                         # no 09:30 bar on the second
            idx.append(d + pd.Timedelta(minutes=570 + 5 * s_))
            o.append(100.0 + q + 0.01 * s_)
            c.append(100.0 + q + 0.01 * s_ + 0.005)
    fr = pd.DataFrame({"open": o, "close": c}, index=pd.DatetimeIndex(idx).tz_localize("US/Eastern"))
    Wd = SimpleNamespace(days=days, T=4, es=SimpleNamespace(c16a=np.array([1.0, 2.0, np.nan, 4.0]), c16r=np.array([1.0, 2.0, np.nan, 4.0])))
    es_open_prints(Wd, {"adj": fr, "raw": fr})
    assert np.allclose(Wd.eso_a, [100.0, 101.01, 2.0, 103.0]) and np.allclose(Wd.esc_a, [1.0, 2.0, 2.0, 4.0]) and Wd.es_carried["open_prints_carried_adj"] == 1 and Wd.es_carried["close_prints_carried_adj"] == 1, (Wd.eso_a, Wd.esc_a, Wd.es_carried)


def t_audit_and_stage_b():
    """the audit file (read: the refusals; apply: M rows by fill session on aud1, W rows by entry session on audw; a data_event matching nothing refuses), and Stage B's refusals before any read (no go-flag, no candidate, a stale stamp)"""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, AUDIT_FILE)
        open(p, "w", newline="\n").write("symbol,date,cell,verdict,note\nN01,2024-03-04,M,keep,x\nN02,2024-03-05,W,data_event,y\n")
        a = read_audit(p)
        W = M17.mk_world(np.full((60, 3), 50.0), np.zeros(60))
        W.audw = np.zeros((W.T, W.S), bool)
        n = apply_audit(W, a)
        assert n == {"rows": 2, "keep": 1, "data_event": 1, "data_event_M": 0, "data_event_W": 1} and W.audw[W.days.get_loc(TS("2024-03-05")), 2] and not W.aud1.any()
        open(p, "w", newline="\n").write("symbol,date,cell,verdict,note\nN01,2024-03-04,X,keep,x\n")
        refused(lambda: read_audit(p), "a cell outside")
        open(p, "w", newline="\n").write("symbol,date,cell,verdict,note\nZZZ,2024-03-04,M,data_event,x\n")
        refused(lambda: apply_audit(W, read_audit(p)), "match no session or no name")
        with patched(THIS, OUT=td):
            refused(stage_b, "go-flag")
            open(os.path.join(td, GO_FLAG), "w").write("go")
            refused(stage_b, "no Stage A candidate")
            json.dump({"judged": True, "candidate": {"cell": "M", "c": 0.5}, "stageA": {"pass_cells": ["M"]}, "prereg_sha256_lf": PREREG_SHA}, open(os.path.join(td, STAGE_A_FILE), "w"))
            refused(stage_b, "different harness version")
            open(os.path.join(td, READ_FLAG), "w").write("read")
            refused(stage_b, "already read once")
            refused(stage_a, "Stage A is frozen")


# ------------------------------------------------------------------ smoke: offline end to end on SYNTHETIC worlds (every number means nothing)
SMOKE_NAMES = [f"S{k:02d}" for k in range(1, 35)] + ["LOWP", "LOWV", "LOWA", "SPL", "RVS", "DLST"] + [f"D{k:02d}" for k in range(1, 41)]      # r18_divrun's synthetic market (r5_siporb's fake Alpaca + 40 payers)
SMOKE_PREMIUM = 0.015            # the planted announcement premium: +1.5% on the actual reaction session and on the session before it, every release of every name (the PLANTED world only)
SMOKE_DUAL = ("D04", "D11")      # [E1] D11 reads D04's CIK: two classes of one firm
SMOKE_NOT_MEMBER = ("S30", "S31", "S32", "S33", "S34", "LOWP", "LOWV", "LOWA")
SMOKE_SPIN_W = ("S15", 2022)     # a spin-off ex-date planted ON the predicted date of S15's first release of that year (inside its W window: [E16] closes it)
SMOKE_PRED = {"S20": {"pred": f"{290020:010d}", "lo": "2014-01-01", "hi": "2019-03-31", "change": "2019-04-01", "old": "S20", "file": "predecessors", "name": "S20 Old Ltd"},       # [E19] MRVL's case: the predecessor's releases in the [E20] predecessors' file
              "S21": {"pred": f"{290021:010d}", "lo": "2014-01-01", "hi": "2026-08-06", "change": "2018-07-01", "old": "OLD21", "file": "calendar", "name": "OLD21 Corp"}}            # FOX's case: in the calendar itself under the old ticker; CEG's: a last 8-K date past the cut
SMOKE_PRED_HOLES = ("S02", "S12")                                         # [E19] rows that are NOT CIK changes: S02 (the foreign filer: no predecessor), S12 (the hole: its own CIK as predecessor)


def smoke_refusal(root):
    """r17_resmom's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, the other families' OUTs, the #463 records) + this harness's OUT"""
    why = M17.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds EAP OUT"
    except ValueError:
        pass
    return None


def smoke_cik(name):
    k = SMOKE_NAMES.index(SMOKE_DUAL[0] if name == SMOKE_DUAL[1] else name)
    return f"{200000 + k:010d}"


def smoke_releases(stop=False, seed=71):
    """the synthetic 8-K item 2.02 calendar: per name a 91-day cycle (13 weeks) from a Monday in January 2014 + 7 x (its index mod 13) days through 2026-06-30, now and then a week early or late (the prediction misses by a week: [E5]'s precision); odd names release after the
    close (16:05), even names before the open (07:00). Planted: S02 a foreign filer (no release), S03 not in the map, S04 an ambiguous map row, D11 D04's second class (no rows of its own: [E1]), S10 a pre-announcement 20 days before its first release of each year ([E3]), S11
    an 8-K/A two days after each release ([E2]), S12 a hole 2019-06 .. 2020-06 and S13 a first release in 2018-03 (few_releases), S27 listed as OLD27 before 2020-07 (its CIK names both), S20 / S21 filed under a predecessor CIK before their change dates ([E19]:
    SMOKE_PRED - S21's under its old ticker OLD21). stop=True: every 2020 release five weeks late (recall falls under 80%: the STOP of [E5]) -> [(ticker, ndx_tickers, cik, date, timing, form)]"""
    rng = np.random.default_rng(seed)
    out = []
    for k, nm in enumerate(SMOKE_NAMES):
        if nm in ("S02", SMOKE_DUAL[1]):
            continue
        cik = smoke_cik(nm)
        nt = {"S27": "OLD27;S27", SMOKE_DUAL[0]: f"{SMOKE_DUAL[0]};{SMOKE_DUAL[1]}"}.get(nm, nm)
        tm = "amc" if k % 2 else "bmo"
        d = TS("2014-01-06") + pd.Timedelta(days=7 * (k % 13))
        seen_year = set()
        while d <= TS("2026-06-30"):
            dd = d + pd.Timedelta(days=int(rng.choice([-7, 0, 7], p=[0.05, 0.9, 0.05])))
            if stop and dd.year == 2020:
                dd = dd + pd.Timedelta(days=35)
            skip = (nm == "S12" and TS("2019-06-01") <= dd <= TS("2020-06-30")) or (nm == "S13" and dd < TS("2018-03-01"))
            if not skip:
                sp_ = SMOKE_PRED.get(nm)
                if sp_ and dd < TS(sp_["change"]):
                    out.append((sp_["old"], sp_["old"], sp_["pred"], dd, tm, "8-K"))
                else:
                    out.append((nm, nt, cik, dd, tm, "8-K"))
                if nm == "S10" and dd.year not in seen_year:
                    out.append((nm, nt, cik, dd - pd.Timedelta(days=20), "bmo", "8-K"))
                    seen_year.add(dd.year)
                if nm == "S11":
                    out.append((nm, nt, cik, dd + pd.Timedelta(days=2), "amc", AMEND_FORM))
            d = d + pd.Timedelta(days=91)
    out.sort(key=lambda z: (z[2], z[3]))
    return out


def smoke_drift(days, rel_rows):
    """the planted premium: + SMOKE_PREMIUM on every actual reaction session and on the session before it, for every name of the release's CIK (D04's releases for D11 too; a [E19] predecessor's for its successor) -> (D, N)"""
    dl = pd.DatetimeIndex(days)
    out = np.zeros((len(days), len(SMOKE_NAMES)))
    cols = defaultdict(list)
    for k, nm in enumerate(SMOKE_NAMES):
        cols[smoke_cik(nm)].append(k)
        if nm in SMOKE_PRED:
            cols[SMOKE_PRED[nm]["pred"]].append(k)
    for _t, _nt, cik, form, _acc, rs, _tm, _accn in rel_rows:
        if form == AMEND_FORM:
            continue
        t = dl.searchsorted(TS(rs))
        if 1 <= t < len(dl):
            for k in cols[cik]:
                out[t - 1:t + 1, k] += SMOKE_PREMIUM
    return out


class EapFake(DV.DivFake):
    """r18_divrun's synthetic daily market (80 names through r5_siporb's fake Alpaca transport: close-to-close log return = beta x the fake ES master's return + noise, the calendar's dividends taken off the open of the ex-date, S.Fake's plants: SPL's 2-for-1 on 2024-03-15, S18's
    missed x4 on 04-22, S23's +60% gap on 05-14, DLST's last bar on 05-31, S33 / S34's late starts, LOWP / LOWV / LOWA below the filters, RVS's reverse split), built by DivFake itself with no dividend run-up; `drift` (D, N) then compounds into every name's path: a session's
    drift moves its close and every later price by exp(drift) (the open of that session is untouched: the drift is earned open to close) - the planted announcement premium (None = the null world: the same random numbers, no premium)"""
    def __init__(self, days, mkt, div, drift=None):
        super().__init__(days, mkt, div, plant=0.0)
        if drift is not None:
            C = np.cumsum(np.asarray(drift, float), axis=0).T                                     # (N, D)
            Cp = np.concatenate([np.zeros((C.shape[0], 1)), C[:, :-1]], axis=1)
            o, h, lo, c = (self.daily[:, :, q] for q in range(4))
            o2, c2 = o * np.exp(Cp), c * np.exp(C)
            self.daily[:, :, 0], self.daily[:, :, 3] = o2, c2
            self.daily[:, :, 1] = np.fmax(h * np.exp(C), np.fmax(o2, c2))
            self.daily[:, :, 2] = np.fmin(lo * np.exp(Cp), np.fmin(o2, c2))


def install_futures(esf, nqf):
    """the house's futures registry answered by the fake masters: ES (r15_ddw.ESFake) and NQ (r13_attn.NQFake), raw and roll-corrected, leaky (load_master_arrays ignores date_to: only the loaders' own cut stands between Stage A and the later bars)"""
    data, srcs = A13.data_mod(), (A13.SRC_RAW, A13.SRC_ADJ)

    def find(instrument, timeframe, session=None, source=None):
        assert instrument in ("ES", "NQ") and (timeframe, session) == ("5m", "rth") and source in srcs, (instrument, timeframe, session, source)
        return {"id": (33 if instrument == "ES" else 37) + (0 if source == A13.SRC_RAW else 30), "instrument": instrument, "timeframe": timeframe, "session": session, "source": source, "filename": f"SMOKE_{instrument}"}

    def arrays(master, date_from=None, date_to=None):
        w = esf if master["instrument"] == "ES" else nqf
        idx, o, c = w.tab["raw" if master["source"] == A13.SRC_RAW else "adj"]
        keep = np.ones(len(idx), bool)
        if date_from:
            keep &= np.asarray(idx >= TS(date_from, tz="US/Eastern"))
        if date_to and not w.leaky:
            keep &= np.asarray(idx < TS(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
        return {"index": idx[keep], "open": o[keep], "close": c[keep], "meta": master}
    data.find_master, data.load_master_arrays = find, arrays


def smoke_files(root, days):
    """the synthetic pinned files: the earnings calendar (planted / stop twins) and its [E20] predecessors' file (S20's releases before its change), the symbol -> CIK map + its reviewed additions, the [E19] list (S20, S21 real changes; S02, S12 not), the members file,
    an EDRIFT r1 stub -> namespace of paths and shas"""
    d = os.path.join(root, "edgar")
    os.makedirs(d)
    in_pf = lambda r_: r_[2] in {v["pred"] for v in SMOKE_PRED.values() if v["file"] == "predecessors"}
    all_p = smoke_releases()
    rows_p, rows_s, rows_pf = cal_rows_of([r_ for r_ in all_p if not in_pf(r_)]), cal_rows_of([r_ for r_ in smoke_releases(stop=True) if not in_pf(r_)]), cal_rows_of([r_ for r_ in all_p if in_pf(r_)])
    cal_p, cal_s, cal_pf = os.path.join(d, "earnings_calendar_ndx.csv"), os.path.join(d, "earnings_calendar_ndx_stop.csv"), os.path.join(d, "earnings_calendar_predecessors.csv")
    sha_p, sha_s, sha_pf = write_cal(cal_p, rows_p), write_cal(cal_s, rows_s), write_cal(cal_pf, rows_pf)
    pl = [",".join(PRED_COLS)] + [f"{nm},{v['pred']},{v['name']},{smoke_cik(nm)},{v['lo']},{v['hi']},smoke://{nm},smoke: the CIK changed {v['change']}" for nm, v in SMOKE_PRED.items()]
    pl += [f"S02,,,{smoke_cik('S02')},,,,NOT A CIK CHANGE - smoke: a foreign filer (6-K)", f"S12,{smoke_cik('S12')},,{smoke_cik('S12')},,,,NOT A CIK CHANGE - smoke: same CIK; a hole 2019-06 .. 2020-06"]
    pmf = os.path.join(d, "edgar_predecessor_map.csv")
    with open(pmf, "w", newline="\n") as f:
        f.write("\n".join(pl) + "\n")
    base = [f"{nm},{'' if nm in ('S04', 'D39') else smoke_cik(nm)},{'name_ambiguous' if nm == 'S04' else 'unmapped' if nm == 'D39' else 'current_ticker'},{nm} Inc" for nm in SMOKE_NAMES if nm != "S03"]
    mp, ma = os.path.join(d, "symbol_cik_map.csv"), os.path.join(d, "symbol_cik_map_additions.csv")
    open(mp, "w", newline="\n").write("symbol,cik,method,name\n" + "\n".join(base) + "\n")
    open(ma, "w", newline="\n").write(f"symbol,cik,method,name\nD39,{smoke_cik('D39')},reviewed_same_firm,D39 Inc\n")
    mem = []
    for nm in SMOKE_NAMES:
        if nm in SMOKE_NOT_MEMBER:
            continue
        if nm == "S27":
            mem += ["OLD27,2015-01-01,2020-07-01", "S27,2020-07-01,"]
        elif nm == "S28":
            mem.append("S28,2015-01-01,2021-01-01")
        elif nm == "S29":
            mem.append("S29,2019-01-01,")
        else:
            mem.append(f"{nm},2015-01-01,")
    mf = os.path.join(root, "data", "ndx_members.csv")
    os.makedirs(os.path.dirname(mf))
    open(mf, "w", newline="\n").write("ticker,from,to\n" + "\n".join(mem) + "\n")
    ej = os.path.join(root, "edrift", "edrift_stageA.json")
    os.makedirs(os.path.dirname(ej))
    rng = np.random.default_rng(83)
    months = [f"{p_}" for p_ in pd.period_range("2016-07", "2025-06", freq="M")]
    json.dump({"reports": {"months": {c: {m_: float(rng.normal(0, 500)) for m_ in months} for c in EDRIFT_CELLS}}}, open(ej, "w"))
    return SimpleNamespace(cal=cal_p, cal_sha=sha_p, cal_stop=cal_s, cal_stop_sha=sha_s, rows=rows_p, pred_cal=cal_pf, pred_cal_sha=sha_pf, pred_rows=rows_pf, pred_map=pmf, pred_map_sha=M17.sha_raw(pmf), map={"map": mp, "map_add": ma},
                           map_sha={"map": M17.sha_raw(mp), "map_add": M17.sha_raw(ma)}, members=mf, edrift=ej)


@contextlib.contextmanager
def smoke_env(root, nrep=100, build=("plant", "null")):
    """everything the smoke patches, restored on exit: OUT and every module's output folder into `root`, CHECK_BOOK off, NREP = nrep, the wide calendar's pinned sha = the synthetic file's, the earnings calendar + [E20] predecessors' file / map / [E19] list (and its
    expected changes / holes) / members / EDRIFT files = the synthetic ones (paths and
    shas), r5_siporb's transport = EapFake (one cache per world), the futures registry = the fake ES and NQ masters, the TBIS file, a fake #463, a stub of the S1-restated L line as the registered one. Builds the worlds in `build` ('plant' = the announcement premium,
    'null' = none, the same random numbers) through r5_siporb's own pulls -> namespace"""
    root = os.path.abspath(root)
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    data = A13.data_mod()
    keep = dict(S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get), fut=(data.find_master, data.load_master_arrays), tb=(D15.TBIS_CSV, A13.TBIS_QA), wide=M17.WIDE_CA_SHA, ref=(DV.REF_CSV, DV.REF_SHA))
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
            days = pd.bdate_range("2015-11-02", "2025-09-30")
            t0 = time.time()
            esf, mkt = DV.smoke_market(days)
            nqf = A13.NQFake(days.union(pd.bdate_range("2015-05-01", "2015-10-30")))
            div, spin, split, _q = DV.smoke_calendar(days)
            fx = smoke_files(root, days)
            sw = [r_ for r_ in fx.rows if r_[0] == SMOKE_SPIN_W[0] and r_[3] == "8-K" and r_[4][:4] == str(SMOKE_SPIN_W[1])][0]
            p_spin = TS(sw[4][:10]) + pd.Timedelta(days=364)
            p_spin = days[days.searchsorted(p_spin)]
            ca_rows = DV.smoke_ca_text(div, spin, split) + [f"spin_off,{SMOKE_SPIN_W[0]},,{SMOKE_SPIN_W[0]}.W,{p_spin:%Y-%m-%d},{p_spin:%Y-%m-%d},,,,0.1,1,,"]
            drift = smoke_drift(days, fx.rows + fx.pred_rows)
            env = SimpleNamespace(root=root, days=days, esf=esf, nqf=nqf, mkt=mkt, fk={}, cache={}, wide_files={}, files=fx, p_spin=p_spin, ca_rows=ca_rows)
            for world in build:
                fk = EapFake(days, mkt, div, drift=drift if world == "plant" else None)
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
            install_futures(esf, nqf)
            A13.smoke_book()
            b0, _legs0 = A13.load_463()
            k0 = np.flatnonzero(b0.mask(WF0, PRE_END))
            env.ref_res = np.random.default_rng(31).normal(6.0, 320.0, len(k0))
            env.ref_csv = os.path.join(root, "resmom", "resmom_cells_daily_wf_close.csv")
            env.ref_sha = DV.write_ref_csv(env.ref_csv, b0, env.ref_res)
            DV.REF_CSV, DV.REF_SHA = env.ref_csv, env.ref_sha
            with open(os.path.join(S.OUT, "siporb_cache_manifest.json"), "w") as f:
                json.dump({"manifest_sha256": D15.MANIFEST_PREFIX + "0" * 56, "files": 0}, f)
            with open(tbis_path, "w") as f:
                f.write("symbol,day,price_ratio,vol_ratio,split_like\nS18,2024-04-22,4.0,0.25,True\nSPL,2024-03-15,0.5,2.1,True\nS05,2024-02-13,0.5,1.0,False\nZZZZ,2024-02-14,0.5,2.0,True\nS07,2025-07-01,0.5,2.0,True\n")
            es.enter_context(patched(THIS, CAL_CSV=fx.cal, CAL_SHA=fx.cal_sha, MAP_FILES=dict(fx.map), MAP_SHA=dict(fx.map_sha), MEMBERS_CSV=fx.members, EDRIFT_JSON=fx.edrift, PRED_LIST=(fx.pred_map, fx.pred_map_sha),
                                     PRED_CAL=(fx.pred_cal, fx.pred_cal_sha), PRED_EXPECTED={nm: v["pred"] for nm, v in SMOKE_PRED.items()}, PRED_HOLES=SMOKE_PRED_HOLES))

            def switch(world):
                S.CACHE, S._http_get = env.cache[world], env.fk[world].handle
                env.wide_csv, env.wide_manifest = env.wide_files[world]
            env.switch = switch
            if build:
                switch(build[0])
            yield env
        finally:
            S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get = keep["S"]
            data.find_master, data.load_master_arrays = keep["fut"]
            D15.TBIS_CSV, A13.TBIS_QA = keep["tb"]
            M17.WIDE_CA_SHA = keep["wide"]
            DV.REF_CSV, DV.REF_SHA = keep["ref"]


def smoke_world(env, world):
    """the World a stage reads, built through the REAL loaders with the calls stage_a makes (every input cut at 2025-06-30 at read time), the raw dividend / spin-off inputs placed again by plain python for the recounts (W.Dr_in / W.Sp_in) -> namespace (load_inputs')"""
    env.switch(world)
    with quiet():
        X = load_inputs(S.LB0)
    csv_path = M17.wide_paths()["csv"]
    X.W.Dr_in = M17.brute_div_matrix(csv_path, X.W.days, X.W.syms, S.LB0)
    X.W.Sp_in = M17.brute_spin_matrix(csv_path, X.W.days, X.W.syms, S.LB0)
    apply_audit(X.W, None)
    return X


ALLOWED_DOLLAR_LINES = ("M's rebalances:", "  M: ", "  W: ", "[E6]", "  by year (one-way turnover", "  the break-even monthly gross spread", "[E7] THE POWER LINE")


def dryload_text_checks(txt):
    """the dryload's printout is COUNTS: no P&L, ROC@30k, Sortino, drawdown or beta; a dollar figure only on the lines that state the registered sizes and [E6] / [E7]'s computed costs and needs (no return is read for them); no date on / after the cut but the line that names
    the cut; the count lines it promises"""
    for l_ in txt.splitlines():
        assert not re.search(r"ROC@30k|Sortino|maxDD|\bbeta [+-]\d|BETA GAP|realised beta", l_), ("the dryload printed an outcome", l_)
        if l_.startswith(ALLOWED_DOLLAR_LINES):                                              # the registered sizes, [E6]'s costs and [E7]'s needs at the draft's ASSUMED drawdowns: no return is read for them
            continue
        assert not re.search(r"net [$]|drawdown [$]|[$]\s*-?\d", l_), ("a dollar figure outside the size / cost lines", l_)
    dates = [d for l_ in txt.splitlines() if "cut to dates <" not in l_ for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l_)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    for frag in ("BEFORE ANY P&L", "[D1] TV's EDGAR earnings calendar", "releases per year", "releases per name", "[E3] the pairs of releases", "names joined / not joined by reason", "[E19] THE JOINED NAME-MONTHS PER SYMBOL", "[E20] the predecessors' releases",
                 "NOT CIK changes - they join nothing", "predecessor-CIK releases joined to their successors", "[E26] ES has no close-to-close return on", "events' windows reached back", "the universe per rank", "DUE", "W's events per year", "open W positions per session",
                 "[E5] ACCURACY OF [P], BOTH WAYS", "[E5] STOP:", "[E6] M's TURNOVER", "[E7] THE POWER LINE", "[E10] NQ masters", "ES return (", "cache manifest sha256", "prereg check:", LAB_J, LAB_K):
        assert frag in txt, frag


def smoke(*a):
    """python r24_eap.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). Order: the selftest; the planted world through the real loaders against the plain-python recounts over a stretch
    (the universe of every rank, every DUE flag, M's pools / sides / dollars and every path, W's events / betas / paths, both readings); the dryload (counts only); Stage A's refusal paths; Stage A on the STOP calendar (it must stop before any P&L), on the NULL world (it must
    FAIL) and on the PLANTED world (the premium must be found: (a)-(e) pass, (f) awaits the hand audit; the pre-P&L block prints before any P&L, the R-day sum first); the hand audit (keep / data_event); Stage B's refusal paths; with the argument stage_b the one read too"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "eap_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()
    t_start = time.time()
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    with smoke_env(root) as env:
        sa_path, go, rd = os.path.join(OUT, STAGE_A_FILE), os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
        print(f"synthetic market: {len(SMOKE_NAMES)} names x {len(env.days):,} business days ({env.days[0]:%Y-%m-%d} .. {env.days[-1]:%Y-%m-%d}), a quarterly 8-K 2.02 calendar ({len(env.files.rows):,} rows), the PLANTED world earns +{SMOKE_PREMIUM:.1%} on every reaction "
              f"session and the one before it, the NULL world does not; both through r5_siporb's own pulls ({env.build_seconds:.0f}s)")
        # ---- 1. the planted world through the REAL loaders against the plain-python recounts
        X = smoke_world(env, "plant")
        W = X.W
        assert W.days.max() < S.LB0 and X.cinfo["dropped_accepted_on_or_after_the_cut"] > 0 and X.cinfo["amendments_dropped_e2"] > 30, X.cinfo
        Z = brute_env(W, X.calf, X.mp, X.mem, X.pred)
        ea = W.ea
        lo_, hi_ = TS("2023-10-01"), TS("2024-12-31")
        t0 = time.time()
        ks = [k for k in range(len(ea.r)) if lo_ <= W.days[ea.r[k]] <= hi_]
        ks_j = [k for k in range(len(ea.r)) if TS("2018-06-01") <= W.days[ea.r[k]] <= TS("2019-06-30")]                        # [E19]: the ranks around S21's (2018-07) and S20's (2019-04) CIK changes
        for k in ks_j + ks:
            r, f = int(ea.r[k]), int(ea.f[k])
            uni, why_, drops = brute_universe(W, Z, r, f)
            assert ea.uni[k].tolist() == uni and sorted(ea.drops[k]) == sorted(drops), (W.days[r], ea.uni[k].tolist(), uni)
            due = brute_due(W, Z, r, int(ea.r_next[k]), uni)
            assert ea.due[k].tolist() == [due[j][0] for j in uni]
        ix = list(W.syms)
        j4, j11 = ix.index(SMOKE_DUAL[0]), ix.index(SMOKE_DUAL[1])
        assert all(not ({j4, j11} <= set(ea.uni[k].tolist())) for k in range(len(ea.r))) and any(j4 in ea.uni[k] or j11 in ea.uni[k] for k in range(len(ea.r))), "[E1] one class per CIK"
        assert ix.index("S27") in ea.uni[ks[0]] and ix.index("S02") not in ea.uni[ks[0]] and ix.index("S03") not in ea.uni[ks[0]], "the renamed member joins through its CIK; the foreign filer and the unmapped name never"
        assert all(ix.index("S20") in ea.uni[k] and ix.index("S21") in ea.uni[k] for k in ks_j) and ea.rt.n_pred_rows > 30, "[E19] the joined names stay in the universe across their CIK changes"
        Bm = brute_m(W, Z, lo_, hi_, JUDGED)
        Lm = m_build(W, lo_, hi_, JUDGED)
        n_p = 0
        run = m_run(W, Lm, D15.l1_cfg())
        want = np.zeros(W.T)
        for rec, b in zip(Lm.recs, Bm):
            assert rec.pool.tolist() == b["pool"] and rec.pool[rec.iL].tolist() == b["long"] and rec.traded == b["traded"] and close(rec.L_usd, b["L_usd"]) and close(rec.S_usd, b["S_usd"])
            if b["traded"]:
                for j in b["pool"]:
                    sd = 1 if j in b["long"] else -1
                    add_path(want, b["f"], b["paths"]["base"][j][0], (b["L_usd"] / len(b["long"])) if sd > 0 else (b["S_usd"] / len(b["short"])))
                    n_p += 1
        assert len(Lm.recs) == len(Bm) >= 12 and np.allclose(run.x, want, atol=1e-6, rtol=0), float(np.abs(run.x - want).max())
        evs, bcnt = brute_w(W, Z, lo_, hi_, JUDGED)
        Lw = w_build(W, lo_, hi_, JUDGED)
        assert Lw.ev.n == len(evs) >= 100 and Lw.ev.e.tolist() == [z["e"] for z in evs] and Lw.ev.col.tolist() == [z["col"] for z in evs] and np.allclose(Lw.ev.beta, [z["beta"] for z in evs], atol=1e-9, rtol=0)
        runw = w_run(W, Lw, D15.l1_cfg())
        want = np.zeros(W.T)
        for z in evs:
            add_path(want, z["e"], [SPEC["w_slot"] * (a_ + b_) for a_, b_ in zip(z["stock"]["base"], z["hedge"])])
        assert np.allclose(runw.x, want, atol=1e-6, rtol=0), float(np.abs(runw.x - want).max())
        tot = sum((Counter(c) for c in bcnt.values()), Counter())
        assert tot["beta_reached_back"] > 0 and all(Lw.cnt[y].get(k_, 0) == bcnt[y].get(k_, 0) for y in bcnt for k_ in ("candidates", "no_beta", "events", "beta_reached_back")), "[E26]: the beta windows reach back past the fake ES master's hole of 2024-03-05"
        Lfull = w_build(W, WF0, PRE_END, JUDGED, units=False)
        assert TS(env.p_spin) in set(W.days[Lfull.ev.p[Lfull.ev.close >= 0]]), "the spin-off planted on S15's predicted date closes that window [E16]"
        print(f"  {len(Bm)} rebalances and {len(evs)} events ({lo_:%Y-%m-%d} .. {hi_:%Y-%m-%d}) against the recount ({time.time() - t0:.0f}s): every universe, DUE flag, pool, side, [E8] dollars, {n_p:,} M paths, every event's beta and stock + hedge path, both daily series; "
              f"[E19] / [E20]: {ea.rt.n_pred_rows} predecessor releases joined, the universe and DUE flags of the {len(ks_j)} ranks around the CIK changes against the recount too")
        # ---- 2. the dryload: COUNTS only
        before = sorted(os.listdir(OUT))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dryload()
        td = buf.getvalue()
        assert sorted(os.listdir(OUT)) == before, "the dryload writes nothing"
        dryload_text_checks(td)
        print("dryload ok on the synthetic world: counts only (no P&L, ROC, Sortino, drawdown or beta; dollars only on the size / cost lines), no lockbox date, nothing written")
        # ---- 3. Stage A's refusal paths: nothing computed, nothing written
        env.switch("plant")

        def must(*frag, fn=stage_a, **kw):
            with quiet(), patched(THIS, **kw):
                msg = refused(fn, *frag)
            assert not os.path.exists(sa_path) and not os.path.exists(rd), "a refusal writes no stage file and burns nothing"
            return msg
        must("DIFFERS", PREREG_SHA="0" * 64)
        must("is not the registered one", CAL_SHA="0" * 64)
        must("is not on file", CAL_CSV=os.path.join(root, "edgar", "absent.csv"))
        must("is not the registered", MAP_SHA={**MAP_SHA, "map": "0" * 64})
        must("is not on file", MEMBERS_CSV=os.path.join(root, "data", "absent.csv"))
        must("is not the pinned one", PRED_LIST=(env.files.pred_map, "0" * 64))
        must("the [E20] predecessors' releases", "is not the registered one", PRED_CAL=(env.files.pred_cal, "0" * 64))
        must("are not the addendum's", PRED_EXPECTED={"S20": SMOKE_PRED["S20"]["pred"]})
        with patched(M17, WIDE_CA_SHA="0" * 64):
            must("is not the registered wide calendar")
        must("do not reproduce", CHECK_BOOK=True)
        with patched(DV, REF_SHA="0" * 64):
            must("RESMOM line file")
        print("Stage A refuses (and writes nothing) on: a changed pre-registration, the earnings calendar (another sha / absent), the map (another sha), the members file (absent), [E19]'s list (another sha / changes other than the addendum's), [E20]'s predecessors' "
              "releases (another sha), an unregistered wide calendar, a #463 that does not reproduce, an L line that is not the registered one")

        def run_stage_a(world, **kw):
            env.switch(world)
            b_ = io.StringIO()
            with contextlib.redirect_stdout(b_), patched(THIS, **kw):
                o_ = stage_a()
            return o_, b_.getvalue()
        # ---- 4. the STOP calendar: [E5] recall under 80% in a WF year stops the run before any P&L
        out_s, txt_s = run_stage_a("null", CAL_CSV=env.files.cal_stop, CAL_SHA=env.files.cal_stop_sha)
        assert out_s["stopped"] is True and out_s["judged"] is False and out_s["stageA"] is None and {2019, 2020} & set(out_s["stop_years"]), (out_s.get("stop_years"), out_s["pre_pnl"]["accuracy"]["by_year"])
        assert "STOPPED BEFORE ANY P&L" in txt_s and not re.search(r"ROC@30k|Sortino|net [$]", txt_s[txt_s.index("BEFORE ANY P&L - THE CALENDAR"):]) and "THE R-DAY SUM FIRST" not in txt_s, "no cell is costed after the STOP"
        os.remove(sa_path)
        print(f"Stage A on the STOP calendar (every 2020 release five weeks late): STOPPED before any P&L, recall under 80% in {[yl(y) for y in out_s['stop_years']]} - years the [E25] waiver ({E5_WAIVER['years']}) does not name")
        wv = {"by": "SMOKE #1", "years": tuple(yl(y) for y in out_s["stop_years"]), "addendum": "[E25]"}
        out_w, txt_w = run_stage_a("null", CAL_CSV=env.files.cal_stop, CAL_SHA=env.files.cal_stop_sha, E5_WAIVER=wv)
        assert out_w["stopped"] is False and out_w["judged"] is True and out_w["e5_e25"]["fired"] and not out_w["e5_e25"]["halted"] and out_w["e5_e25"]["waived_by"] == "SMOKE #1", out_w["e5_e25"]
        last = [l_ for l_ in txt_w.splitlines() if l_.startswith("EAP Stage A:")]
        assert len(last) == 1 and "FIRED at" in last[0] and "WAIVED by SMOKE #1 [E25]" in last[0] and "[E5] STOP: FIRED" in txt_w, last
        os.remove(sa_path)
        print("Stage A on the STOP calendar with a recorded waiver naming those years [E25]: the stop FIRES, is waived, Stage A goes on and its result line states the waiver")
        # ---- 5. the NULL world must FAIL
        t0 = time.time()
        out_n, txt_n = run_stage_a("null")
        cells_n = out_n["stageA"]["cells"]
        assert out_n["judged"] is True and out_n["stageA"]["pass_cells"] == [] and out_n["candidate"] is None and out_n["stageA"]["null"]["draws"] == NREP == 100, {c: (v["base"]["roc"], [k for k, x in v["checks"].items() if not x]) for c, v in cells_n.items()}
        assert "EAP Stage A: FAIL - no cell passes" in txt_n and all(d < "2025-06-30" for d in dates_of(txt_n))
        assert out_n["sensitivity_e25"]["pass_cells"] == [] and out_n["governing_e25"]["pass_cells"] == [] and out_n["sensitivity_e25"]["null"]["draws"] == NREP, out_n["governing_e25"]
        os.remove(sa_path)
        print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - WF ROC@30k " + ", ".join(f"{c} {cells_n[c]['base']['roc']:.1f}" for c in CELLS) + f"; random-name null p97.5 {out_n['stageA']['null']['roc_max']['p97.5']:.1f}")
        # ---- 6. the PLANTED world: the premium must be found
        t0 = time.time()
        out, txt = run_stage_a("plant")
        cells = out["stageA"]["cells"]
        passing, cand = stage_a_flow(cells)
        assert out["judged"] is True and set(passing) == set(CELLS) and out["candidate"]["cell"] == cand and out["pending_hand_audit"] == passing, {c: (cells[c]["base"]["roc"], [k for k, v in cells[c]["checks"].items() if not v]) for c in CELLS}
        assert "(f) AWAITS THE HAND AUDIT" in txt and all(d < "2025-06-30" for d in dates_of(txt)) and {k: out.get(k) for k in stamp()} == stamp() and out["prereg_sha256_lf"] == PREREG_SHA
        order = ("BEFORE ANY P&L - THE CALENDAR", "[D1] TV's EDGAR earnings calendar", "names joined / not joined by reason", "[E19] THE JOINED NAME-MONTHS PER SYMBOL", "the universe per rank", "W's events per year", "[E5] ACCURACY OF [P]", "[E6] M's TURNOVER", "[E7] THE POWER LINE", "[E13] M's ex-ante BETA GAP",
                 "judged reading [E16] done", "[E25] the sensitivity without 2016-17 done", "THE R-DAY SUM FIRST", "null 1 - RANDOM NAMES", "[E25] SENSITIVITY", "[E25] VERDICTS", "A2 (WF)", "[E14] SEAT", "[E15] THE LIVE STRETCH", "DIAGNOSTICS",
                 "[E10] W's GROWTH TILT", "correlation: RES daily")
        seq = [txt.index(s_) for s_ in order]
        assert seq == sorted(seq), ("the printout is out of the prereg's order", [o_ for o_, s_ in zip(order, seq)])
        pre = txt[seq[0]:txt.index("judged reading [E16] done")]
        assert not re.search(r"ROC@30k|Sortino|net [$]|maxDD", pre), "a P&L figure before the cells"
        for c in CELLS:
            ck = cells[c]
            assert all(ck["checks"].values()) and ck["base"]["roc"] > ck["cost_curve"]["20 bps"]["roc"] and ck["cost_curve"]["0 bps"]["net"] > ck["base"]["net"] > ck["cost_curve"]["10 bps"]["net"], c
            assert abs(ck["usd_year"] - ck["base"]["net"] / ck["base"]["years"]) < 1e-6 and np.isfinite(ck["dd5"]["dd5"]) and ck["A2"]["c"] > 0 and "rday_null" in ck, c
        assert cells["M"]["hedged"]["base"]["roc"] >= RULES["roc"] and set(cells["W"]["checks"]) >= {f"ROC>time-shift null p{RULES['pctl']:g}"}
        rep = out["reports"]
        assert len(rep["seat_e14"]["books"]["#463"]) == 5 and rep["event_path"]["predicted"]["mean_bps"][rep["event_path"]["taus"].index(0)] > 50 and np.isfinite(rep["tilt_e10"]["loading_nq_minus_es"]) and rep["correlations"]["M"]["EDRIFT_V3_months"] > 50
        assert out["pre_pnl"]["accuracy"]["total"]["recall"] > 0.8 and len(out["pre_pnl"]["pairs_e3"]) >= 8 and all(p_["ticker"] == "S10" for p_ in out["pre_pnl"]["pairs_e3"]) and out["pre_pnl"]["calendar"]["amendments_dropped_e2"] > 30
        assert out["removal_reading"]["removed"]["W"]["post_spin"] >= 1 and sum(v.get("closed_spin", 0) for v in out["counts_by_year"]["W"].values()) >= 1
        cs_ = out["sensitivity_e25"]["cells"]
        assert out["sensitivity_e25"]["pass_cells"] == passing and out["governing_e25"]["pass_cells"] == passing and not out["governing_e25"]["differ"] and out["sensitivity_e25"]["stretch"][0] == "2017-07-01", out["governing_e25"]
        assert all(0 < cs_[c]["base"]["n_pos"] < cells[c]["base"]["n_pos"] and cs_[c]["n_years"] == 8 and len(cs_[c]["base"]["by_year"]) == 8 and cs_[c]["A2"]["window"][0] == "2017-07-01" for c in CELLS), {c: cs_[c]["base"]["n_pos"] for c in CELLS}
        e19 = out["pre_pnl"]["e19_joined_name_months"]
        jn, hl = {j["symbol"]: j for j in e19["joins"]}, {h["symbol"]: h for h in e19["holes"]}
        assert jn["S20"]["from_predecessors_file"] > 15 and jn["S20"]["from_calendar"] == 0 and jn["S21"]["from_calendar"] > 10 and jn["S21"]["clipped_at_the_cut"] and out["predecessors_e4"]["clipped_at_the_cut"] == 1, jn
        assert jn["S20"]["fail_with"] == [] and len(jn["S20"]["fail_without"]) >= 6 and len(jn["S20"]["joined_months"]) > 6 and jn["S21"]["fail_with"] == [] and len(jn["S21"]["fail_without"]) >= 6, jn
        assert "no_release" in hl["S02"]["out"] and hl["S02"]["in_universe"] == 0 and "few_releases" in hl["S12"]["out"], hl
        cd = pd.read_csv(os.path.join(OUT, CANDS_FILE))
        assert set(cd["cell"]) == set(CELLS) and cd.groupby("cell").size().max() == AUDIT_N and {"predicted", "actual_nearest", "fill_open_raw", "marks_adj", "exit_open_raw", "closed_before_spin"} <= set(cd.columns) and cd["exit"].max() < "2025-06-30"
        print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the premium is found - " + ", ".join(f"{c} ROC@30k {cells[c]['base']['roc']:.0f} (${cells[c]['usd_year']:,.0f} a year, {cells[c]['base']['n_pos']:,} positions)" for c in CELLS)
              + f"; M hedged [E13] {cells['M']['hedged']['base']['roc']:.0f}; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit; the event-time path at p: {rep['event_path']['predicted']['mean_bps'][10]:.0f} bps")
        # ---- 7. the hand audit: every candidate 'keep' -> the same numbers; a data_event on the candidate's largest gain -> out of the cell and its nulls
        ap = os.path.join(OUT, AUDIT_FILE)
        cd[["symbol", "date", "cell"]].assign(verdict="keep", note="smoke: nothing found").to_csv(ap, index=False)
        out2, _t2 = run_stage_a("plant")
        assert out2["audit"]["keep"] == len(cd) and all(v["audit_complete"] for v in out2["audit_status"].values()) and all(out2["stageA"]["cells"][c]["base"]["net"] == cells[c]["base"]["net"] for c in CELLS), "a keep changes no number"
        au = pd.read_csv(ap)
        for c in CELLS:
            top = cd[cd["cell"] == c].iloc[0]
            au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]) & (au["cell"] == c), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        out3, _t3 = run_stage_a("plant")
        assert out3["audit"]["data_event"] == 2 and out3["audit_data_events_without_effect"] == [] and all(out3["stageA"]["cells"][c]["base"]["net"] != cells[c]["base"]["net"] for c in CELLS), "the audited positions are out"
        assert out3["stageA"]["cells"]["W"]["base"]["n_pos"] == cells["W"]["base"]["n_pos"] - 1 and out3["stageA"]["null"]["roc_max"]["p97.5"] != out2["stageA"]["null"]["roc_max"]["p97.5"], "the event is out of W and of both nulls"
        print(f"hand audit: {len(cd)} rows 'keep' -> the same numbers; a data_event on each cell's largest gain -> out of the cell and its nulls (W {cells['W']['base']['n_pos']:,} -> {out3['stageA']['cells']['W']['base']['n_pos']:,} events)")
        cand, c_frozen = out3["candidate"]["cell"], out3["candidate"]["c"]
        # ---- 8. Stage B's refusal paths
        env.switch("plant")

        def must_b(frag, **kw):
            with quiet(), patched(THIS, **kw):
                msg = refused(stage_b, frag)
            assert not os.path.exists(rd), "a refused Stage B must not burn the lockbox"
            return msg
        must_b("go-flag")
        with open(go, "w") as f:
            f.write("smoke: the lead's go-flag")
        js0 = open(sa_path).read()
        for k in stamp():
            j = json.loads(js0)
            j[k] = "0" * 64
            open(sa_path, "w").write(json.dumps(j))
            must_b("different harness version")
        for edit in (lambda j: j.update(judged=False), lambda j: j.update(candidate=None), lambda j: j["stageA"].update(pass_cells=[])):
            j = json.loads(js0)
            edit(j)
            open(sa_path, "w").write(json.dumps(j))
            must_b("no Stage A candidate")
        for badc in (0.0, -1.0, None):
            j = json.loads(js0)
            j["candidate"]["c"] = badc
            open(sa_path, "w").write(json.dumps(j))
            must_b("positive number")
        open(sa_path, "w").write(js0)
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2017-01-03,M,keep,a changed audit file\n")
        must_b("not the file Stage A ran with")
        open(ap, "w").write(au0)
        must_b("do not reproduce its LB numbers", CHECK_BOOK=True)
        j = json.loads(js0)
        j["parity"][cand]["net"] += 1e6
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data")
        j = json.loads(js0)
        j["candidate"]["c"] *= 1.0001
        open(sa_path, "w").write(json.dumps(j))
        must_b("volatility-set size c")
        open(sa_path, "w").write(js0)
        print("Stage B refused before the flag in every case above (the flag was never written)")
        if with_b:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = stage_b()
            txt_b = buf.getvalue()
            print(txt_b.rstrip())
            sb = json.load(open(os.path.join(OUT, STAGE_B_FILE)))
            assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c_frozen and set(sb["checks"]) == set(b_checks(cand, sb["leg"])) and "never a pass" in sb["book_add_reported"]["note"]
            refused(stage_b, "already read")
            refused(stage_a, "Stage A is frozen")
            print("Stage B read once (the flag after the load and the checks), refused a second read; Stage A is frozen")
        else:
            os.remove(go)
        try:
            main(["bogus"])
        except SystemExit:
            pass
        pm = peak_mb()
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline" + ("" if with_b else " (Stage B's read: `smoke DIR stage_b`)"))


# ------------------------------------------------------------------ the commands
TESTS = ("t_constants", "t_files", "t_pairs", "t_predecessors", "t_pipeline", "t_nulls", "t_accuracy", "t_es_window", "t_sensitivity", "t_judge", "t_reports", "t_audit_and_stage_b")


def selftest():
    """hand-made calendars and worlds, no data, no network (no real pinned file is read: [E19]'s list and [E20]'s file are off unless a group pins its own): each group prints one line"""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=os.path.join(td, "out"), PRED_LIST=None, PRED_CAL=None), patched(DV, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf_close.csv")):
        for name in TESTS:
            t1 = time.time()
            res = globals()[name]()
            print(f"  {name} ok ({time.time() - t1:.1f}s)" + (f": {res}" if isinstance(res, int) else ""), flush=True)
    print(f"selftest ok: {len(TESTS)} groups ({', '.join(t[2:] for t in TESTS)}) in {time.time() - t0:.0f}s")


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r24_eap.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b   (dryload: counts only; stage_a: the lead's, after review; stage_b only on the stock families' one sealed-year day with the lead's eap_stageB_GO.flag on file)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
