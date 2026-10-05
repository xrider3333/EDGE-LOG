# XGAP r1 - the FIRM-SPECIFIC overnight gap of Nasdaq-100 members, faded inside the cash session, dollar-neutral: each session long the 10 most negative and short the 10 most positive
# RELATIVE gaps (the raw gap minus the session universe's median), filled at the open of the 09:35 bar, out at the official close (Berkman, Koch, Tuttle & Zhang 2012; Chan 2003).
# Pre-registered: tools/rocfrontier/PREREG_XGAP_R1.txt (canonical LF sha256 7e29938e...f81f: the draft, MANAGER's six edits [X1]-[X6], MANAGER #48 [B48], and PRE-DATA ADDENDUM 1 of 2026-10-05 - TV's X1-X6 cited
# here as [TV X1]..[TV X6], NOISE's H1-H4 as [NOISE H1]..[NOISE H4], MANAGER #56 (A2 is a report, not a gate), #57 and #58 (the calendar's two files pinned by sha256) - all written before any number of this family exists). Every rule, threshold, window and
# cost below is that file; where it is silent the choice is marked CHOICE; the bracket tags cite its edits.
#   python r16_xgap.py capull [--probe] [--force]   [X1] the ONE corporate-actions pull (cash dividends, splits, name changes ...) for every ndx_members.csv ticker; MANAGER runs it through its key wrapper:
#                                                   python C:\EdgeLog\manager\_scripts\with_alpaca_keys.py r16_xgap.py capull   (--probe = ONE request, structure only, nothing saved)
#   python r16_xgap.py capull --names FILE --tag TAG [--probe] [--force]   WIDE mode for the other lanes (RESMOM, XSML): the symbols come from FILE (one a line) instead of ndx_members.csv and the pull lands in
#                                                   corporate_actions_TAG_raw.jsonl / corporate_actions_TAG.csv / corporate_actions_TAG_manifest.json beside the NDX files, which it never touches (the overwrite
#                                                   refusal and --force are per tag; the manifest records the names file's sha256); stage_a / stage_b never read a tagged calendar
#   python r16_xgap.py selftest    hand-made worlds: every rule, the calendar parser on a canned response, the identity check and the symbol map, the share-class rule, the statistics (the twin veto, both readings), the X2 drop rates, the c rule, DO / rho_dd, the Stage B refusals
#   python r16_xgap.py smoke DIR   offline end-to-end on a SYNTHETIC world (r5_siporb's fake Alpaca, a mocked capull transport, a fake NQBRD member cache, a fake ES master, a fake #463 book); DIR's name must contain 'smoke'
#   python r16_xgap.py dryload     outcome-free counts of the real caches (sessions, members, identity-check agreement, eligible names, exclusions by reason, the no-data line, share-class and X2 rates, twin coverage); no price, gap or P&L is printed; pre-lockbox only
#   python r16_xgap.py stage_a     WF Stage A (every bar, the beta-twin veto, a second reading when X2 triggers) + the A2 REPORT + the reports -> xgap_stageA.json, PRE-LOCKBOX ONLY (every input is cut to dates < 2025-06-30 when it is read); refuses without the calendar
#   python r16_xgap.py stage_b     Stage B [B48] (lockbox, once, on the one sealed-year day): the LEG's standalone veto; refuses unless Stage A passed (both readings, the twin veto) with the hand audit complete - A2 is a report, not a gate [MANAGER #56] - and DDW r1's sibling decision is on file
# Reads (never writes) the SIPORB daily cache through r5_siporb (Data, read_long, missed_split_flags), the NQBRD member cache C:\EdgeLog\alpaca_cache\nqbrd\open_bars.csv, tools/data/ndx_members.csv, TBIS's split-QA
# list, the ES 5m RTH masters through augur_engine.data (like r13_attn loads NQ) and the #463 book through r11_risk. The only network use is `capull`, through r5_siporb._get (the shared account pace; the keys come from
# r5_siporb.keys() and never reach a print, a log or a file). Results go to OUT (outside git); the calendar goes to C:\EdgeLog\alpaca_cache\xgap. Nothing here commits, pushes or writes anywhere else.
import contextlib, csv, hashlib, io, itertools, json, math, os, re, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r5_siporb as S        # Data (the split rule, the gap scan), read_long, missed_split_flags, _get / keys (the shared pace), Fake (the smoke's Alpaca), EARLY_CLOSE_DATES - imported, never copied
import r11_risk as R11       # the #463 book (records -> Book), stats, underwater, the windows and the reference numbers - imported, never copied
import r12_mdl as MDL        # Stretch / realised: DO and rho_dd exactly as MDL r1; vmeas = r11_risk.stats row by row (the null's statistic)
import r13_attn as A         # the sibling: refuse, assert_cut, book_rows, load_463, nw_t, ceil_pct, breadth, corrs, nq_prints / hedge_prints (the ES prints), the fake NQ master of its smoke

TS = pd.Timestamp
OUT = os.environ.get("EDGELOG_XGAP_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\xgap_r1")        # results, outside git
PREREG = os.path.join(HERE, "PREREG_XGAP_R1.txt")
PREREG_SHA = "7e29938e069271efcc9dadffe0da9cb8e4c83378a8696b4bac0a33ce336cf81f"                  # canonical (LF) sha256 of the pre-registration with its PRE-DATA ADDENDUM 1 and MANAGER #58 (the draft's own was 06811c06...)
CAL_RAW_SHA = "eac8ccef7d6c22315b2fe5cc770534aa48eab988dc04c0903892f253c7c61f8d"                 # [MANAGER #58] the calendar pull the prereg pins: corporate_actions_raw.jsonl's sha256 ...
CAL_CSV_SHA = "d7acffbe5de0c5eccf3e13625c55d30ab4a173b9ce7952f576d1f0ac659b81b2"                 # ... and corporate_actions.csv's: Stage A and B refuse any other file (a re-pull is a new photograph and a new addendum)
WF0, PRE_END, LB0, LB1 = R11.WF0, R11.PRE_END, R11.LB0, R11.LB1    # WF = sessions [2016-07-01, 2025-06-29], LB = [2025-06-30, 2026-06-30] INCLUSIVE; cuts: S.LB0 (Stage A) / S.END (Stage B)
CUT_A, CUT_B = S.LB0, S.END                                       # every input is cut to dates < CUT at read time: Stage A 2025-06-30, Stage B 2026-07-01
BOOK_WF, BOOK_LB, TOL = R11.P2_REF["unified"]["WF"], R11.P2_REF["unified"]["LB"], R11.P2_TOL    # #463's unified-convention ROC@30k / Sortino (93.81 / 3.816, 155.54 / 4.150) and the match tolerance
BOOK_DD = 44849.0                                                 # #463's deepest WF drawdown (MDL r1: 2020-03-02 -> 2020-03-27), reproduced to the dollar before anything is judged
NPOS, SLOT, CAP = 10, 5000.0, 0.08                               # names a side; $ a name (fractional shares); CAP8: |g| <= 8%
COST = {"base": (10.0, 5.0), "stress": (20.0, 10.0)}             # bps of notional (entry at the 09:35 open, exit value at the official close)
CELLS = ("ALL", "CAP8")
NREP, SEED = 500, 20261005
FLAG_WIN = 6                                                      # a flag from t-5 through t = 6 session rows
BETA_WIN = 60                                                     # [X3] the OLS beta window: the previous 60 sessions, all present
ID_ABS, ID_REL = 0.01, 0.0010                                     # [TV X1] the identity check: |the cache's raw 09:30 open - SIPORB's raw official open| <= max(1 cent, 0.10% of the official open)
ID_EPS = 1e-9                                                     # CHOICE: float noise only - a difference of exactly one cent / exactly 0.10% is inside (prices are cents; 100.01 - 100.00 is 0.010000000000005 in floats)
MAP_YEAR_MAX = 0.02                                               # a year with more than 2% of member-days dropped by the IDENTITY check is named; the no-data drops are the survivorship line ([NOISE H3])
X2_RATIO = 1.5                                                    # [TV X2] the top / bottom-10 names' identity-drop rate over the rest's: above it, Stage A is computed a second time with those slots left empty
GAP_MAX = 0.50                                                    # a raw gap beyond +-50% with no split-factor change
C_TARGET, C_ROWS = 0.25, (TS("2016-07-01"), TS("2018-06-29"))   # [X2] c: the cell's daily P&L std over these rows = 25% of #463's
YEARS = A.YEARS                                                   # the nine July-June WF years 2016-17 .. 2024-25
HALVES = ((TS("2016-07-01"), TS("2020-12-31")), (TS("2021-01-01"), PRE_END))
RULES = {"sessions": 1800, "roc": 15.0, "pf": 1.10, "t": 2.0, "nw_lags": 5, "null": True, "mirror": True, "stress": True, "exbest": True, "best_days": 5, "best_pct": 1, "years": 6, "halves": True, "x2020": True,
         "audit": True, "a2_roc": 1.05 * BOOK_WF[0], "a2_sort": BOOK_WF[1], "a2_dd": 1.10 * BOOK_DD, "b_namedays": 50, "b_sessions": 30,
         "null_pct": 97.5, "twin": True, "twin_half": 0.5, "x2": True, "x2_ratio": X2_RATIO}   # CHOICE: A2's bar is 1.05 x 93.81 as a formula (98.5005), not its rounding 98.5. [TV X3] check (c) reads the null's 97.5th percentile; [TV X4] the twin veto; [TV X2] the second reading
SHARE_CLASS = (("GOOG", "GOOGL"), ("FOX", "FOXA"), ("NWS", "NWSA"), ("LBTYA", "LBTYB", "LBTYK"), ("DISCA", "DISCB", "DISCK"), ("LILA", "LILAK"), ("BATRA", "BATRK"), ("LBRDA", "LBRDK"), ("VIAC", "VIACA"))   # [TV X1] the addendum's explicit list
CLASS_LETTERS = "ABCKL"   # CHOICE: the trailing letters the share-class detector reads as a class (GOOGL; FOXA / NWSA / TFCFA; LBTYK / DISCK / LMCK ...); every other shared-root pair is printed, not enforced
EARN_CSV = os.path.join(S.REPO, "tools", "data", "megacap_earnings.csv")        # [TV X6] / [MANAGER #57] EARN r1's ticker, accepted_et, items: mega caps only - the ex-earnings reading is a REPORT
SIBLINGS = {"cells_tried": 4, "text": "sibling cells tried: 4 (DDW r1 L2-F, L2-S - dead at Stage A; XGAP ALL, CAP8)"}       # [TV X3]
CHECK_BOOK = True       # refuse to judge if the #463 records do not reproduce its numbers; a real run always checks (only smoke() may switch it)
FLAG_FILE = "xgap_stageB_READ.flag"
MEMBERS_CSV = os.path.join(S.REPO, "tools", "data", "ndx_members.csv")
TBIS_QA = os.environ.get("EDGELOG_TBIS_SPLIT_QA", r"C:\EdgeLog\_research_cache\split_qa\siporb_split_flags_voltest.csv")
DDW_STAGE_A = os.path.join(os.path.dirname(OUT), "ddw_r1", "ddw_stageA.json")          # the sibling's verdict file (MANAGER: Stage B reads it)
ES_D0 = "2016-06-01"    # CHOICE: the ES masters are loaded from 2016-06-01 (a month before WF: the first session's prior 16:00 print), cut at the stage's cut
SRC_RAW, SRC_ADJ = A.SRC_RAW, A.SRC_ADJ                          # the same two registry sources r13_attn reads for NQ

# the corporate-actions endpoint [X1]
CA_URL = "https://data.alpaca.markets/v1/corporate-actions"
CA_TYPES = ("cash_dividend", "forward_split", "reverse_split", "unit_split", "stock_dividend", "name_change", "spin_off")    # the ONE place the accepted type names live: if the server rejects one, `capull --probe` shows its message - edit this tuple
CA_START, CA_END = "2016-06-01", "2026-06-30"
CA_BATCH, CA_LIMIT, CA_MAXBAD = 50, 1000, 50                      # CHOICE: 50 symbols a request (a URL of ~350 characters), the endpoint's page limit, and the stop on rejected symbols (S.fetch_safe's idiom)
CA_PROBE = ("AAPL,NVDA,TSLA,FB,META", "2019-01-01", "2024-12-31")
CA_KEYS = {"cash_dividends": "cash_dividend", "forward_splits": "forward_split", "reverse_splits": "reverse_split", "unit_splits": "unit_split", "stock_dividends": "stock_dividend",
           "name_changes": "name_change", "spin_offs": "spin_off"}                                                # response key -> type name; any other key is kept raw as its own type
CA_COLS = ("type", "symbol", "old_symbol", "new_symbol", "ex_date", "process_date", "record_date", "payable_date", "rate", "new_rate", "old_rate", "cash", "special")
CA_USED = {"symbol", "source_symbol", "old_symbol", "new_symbol", "ex_date", "effective_date", "process_date", "record_date", "payable_date", "rate", "new_rate", "old_rate", "source_rate", "cash",
           "cash_rate", "special"}                                  # the record fields the flat CSV carries (the raw pages keep everything else: cusip, foreign, alternate_symbol ...)
DIV_TYPES, SPLIT_TYPES = ("cash_dividend", "stock_dividend", "spin_off"), ("forward_split", "reverse_split", "unit_split")
# CHOICE: the 'ex-dividend' exclusion covers cash dividends (the prereg's word) AND stock dividends and spin-offs - the same mechanical drop on the ex-date; reported apart by type
_SECRETS = ()           # (key, secret) of this process once capull has them: scrub() removes them from anything about to be printed or stored


def refuse(msg):
    A.refuse(msg)


def scrub(text):
    """a key never reaches a print, a log or a file: the key / secret values this process holds are replaced in any text (a server message, an exception) before it is shown"""
    t = str(text)
    for v in _SECRETS:
        if v and len(v) >= 6:
            t = t.replace(v, "<key>")
    return t


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def prereg_ok():
    """the frozen spec this file implements must still be the committed one (a changed spec = a new file, r2): a missing or changed file refuses Stage A and B"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_XGAP_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_XGAP_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_XGAP_R1.txt sha256 matches the registered one")
    return True


def stamp():
    """the version a stage ran with: this file's LF sha256 + the shared half-day list, like SIPORB's stamp (Stage B refuses on any change). CHOICE: also r5_siporb.py, r11_risk.py, r12_mdl.py and r13_attn.py -
    Data, the book loader, the statistics, Stretch / realised and the imported helpers decide the numbers, so a change to any of them after Stage A must send it through Stage A again"""
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "siporb_sha256": R11.sha_lf(S.__file__), "r11_sha256": R11.sha_lf(R11.__file__), "r12_sha256": R11.sha_lf(MDL.__file__),
            "attn_sha256": R11.sha_lf(A.__file__), "early_close": sorted(S.EARLY_CLOSE_DATES)}


def dump(obj, name):
    """strict JSON (non-finite -> null, MDL r1's cleaner) into OUT"""
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(MDL._clean(obj), f, indent=1, default=R11.js)


def read_json(path):
    with open(path) as f:
        return json.load(f)


def num(x, default=float("nan")):
    """None (a strict-JSON null) back to NaN"""
    return default if x is None else float(x)


# ------------------------------------------------------------------ the corporate-actions calendar [X1]: capull, the parser, the loader
def ca_paths(tag=None):
    """the calendar's files in the shared cache folder: the NDX pull's (no tag) - the only one stage_a / stage_b read - or a WIDE pull's corporate_actions_TAG_raw.jsonl / corporate_actions_TAG.csv /
    corporate_actions_TAG_manifest.json (a tag is letters, digits and underscores; no tagged name can equal an untagged one)"""
    d = os.path.join(S.CACHE, "xgap")
    if tag is None:
        return {"dir": d, "raw": os.path.join(d, "corporate_actions_raw.jsonl"), "csv": os.path.join(d, "corporate_actions.csv"), "manifest": os.path.join(d, "corporate_actions_manifest.json")}
    return {"dir": d, "raw": os.path.join(d, f"corporate_actions_{tag}_raw.jsonl"), "csv": os.path.join(d, f"corporate_actions_{tag}.csv"), "manifest": os.path.join(d, f"corporate_actions_{tag}_manifest.json")}


def read_members(path=None):
    """tools/data/ndx_members.csv: ticker, from, to (month starts, 'to' exclusive, '' = open) - the tickers as the list printed them at the time (FB until 2022-07-01, then META)"""
    return pd.read_csv(path or MEMBERS_CSV, dtype=str, keep_default_na=False)


def members_tickers(path=None):
    return sorted(read_members(path)["ticker"].unique())


def ca_parse(js):
    """one decoded page -> ([(type, record)], info). Tolerant: the documented shape is {"corporate_actions": {"cash_dividends": [...], "forward_splits": [...], ...}, "next_page_token": ...}; a key
    this file does not know is kept raw as its own type (info['unknown_types']), a top-level key other than those two is listed (info['unknown_top_keys']), a flat list of records with a 'type' is grouped by it"""
    recs, info = [], {"unknown_top_keys": [], "unknown_types": Counter()}
    if not isinstance(js, dict):
        info["unknown_top_keys"].append(f"<{type(js).__name__}>")
        return recs, info
    info["unknown_top_keys"] = [k for k in js if k not in ("corporate_actions", "next_page_token")]
    ca = js.get("corporate_actions")
    if isinstance(ca, dict):
        for key, lst in ca.items():
            typ = CA_KEYS.get(key)
            if typ is None:
                info["unknown_types"][key] += len(lst) if isinstance(lst, list) else 1
                typ = key
            recs += [(typ, r) for r in lst if isinstance(r, dict)] if isinstance(lst, list) else []
    elif isinstance(ca, list):
        for r in ca:
            if isinstance(r, dict):
                typ = str(r.get("ca_type") or r.get("type") or "unknown")
                typ = CA_KEYS.get(typ, typ)
                if typ not in CA_KEYS.values():
                    info["unknown_types"][typ] += 1
                recs.append((typ, r))
    return recs, info


def ca_flatten(typ, r):
    """one record -> (flat row of CA_COLS, the field names this flattening does not carry). Missing fields are None. CHOICE: a spin-off's source_symbol fills `symbol` and its source_rate `old_rate`; a unit split's
    effective_date fills `ex_date`; the date a name change took effect is its process_date (it has no ex-date)"""
    def g(*ks):
        return next((r[k] for k in ks if r.get(k) not in (None, "")), None)
    row = {"type": typ, "symbol": g("symbol", "source_symbol"), "old_symbol": g("old_symbol"), "new_symbol": g("new_symbol"), "ex_date": g("ex_date", "effective_date"),
           "process_date": g("process_date"), "record_date": g("record_date"), "payable_date": g("payable_date"), "rate": g("rate"), "new_rate": g("new_rate"), "old_rate": g("old_rate", "source_rate"),
           "cash": g("cash", "cash_rate"), "special": r.get("special")}
    return row, sorted(set(r) - CA_USED)


def ca_year(row):
    d = row.get("ex_date") or row.get("process_date") or ""
    return str(d)[:4] if re.match(r"^\d{4}", str(d)) else "n/a"


class CaPull:
    """the sink of one pull: every raw page is written as ONE JSON line to the .part file as it arrives, the records are parsed and kept; nothing is renamed until the pull is complete. CHOICE: a raw line is
    {"i": page number, "round": 1|2, "params": the request without its page token (never a key - keys travel in headers inside r5_siporb._get), "page": the response body}; r5_siporb._get hands back the DECODED
    JSON, not the wire bytes, so `page` is that JSON re-encoded compactly (values unchanged) - the sha256 in the manifest is of this file, not of the vendor's bytes"""
    def __init__(self, part, maxbad=CA_MAXBAD, every=0):
        os.makedirs(os.path.dirname(part), exist_ok=True)
        self.f = open(part, "w", encoding="utf-8", newline="\n")
        self.pages, self.requests, self.recs = 0, 0, []
        self.unknown_top, self.unknown_types, self.unflat, self.bad = Counter(), Counter(), Counter(), []
        self.maxbad, self.every, self.t0 = maxbad, every, time.time()      # the stop on rejected symbols; a progress line (counts only) every `every` pages when > 0 (the wide pull)

    def __call__(self, js, params, label):
        self.f.write(json.dumps({"i": self.pages, "round": label, "params": params, "page": js}, separators=(",", ":"), default=str) + "\n")
        self.pages += 1
        if self.every and self.pages % self.every == 0:
            print(f"  ... {self.requests:,} requests, {self.pages:,} pages, {len(self.recs):,} records ({time.time() - self.t0:.0f}s)", flush=True)
        recs, info = ca_parse(js)
        self.recs += recs
        self.unknown_top.update(info["unknown_top_keys"])
        self.unknown_types.update(info["unknown_types"])
        for typ, r in recs:
            self.unflat.update(ca_flatten(typ, r)[1])

    def close(self):
        self.f.close()


def ca_fetch(symbols, key, secret, sink, label, start=CA_START, end=CA_END):
    """every page for `symbols` in batches of CA_BATCH, through r5_siporb._get (the shared pace, 429 / 5xx retries). A 400 that names a symbol is bisected down to the offender (logged in sink.bad,
    skipped, at most CA_MAXBAD) - the endpoint may reject a name it never knew (YHOO, PCLN ...); a 400 that names anything else (a type) stops the pull"""
    syms = list(symbols)
    for b in range(0, len(syms), CA_BATCH):
        ca_fetch_safe(syms[b:b + CA_BATCH], key, secret, sink, label, start, end)


def ca_fetch_safe(chunk, key, secret, sink, label, start, end):
    try:
        token = None
        while True:
            p = {"symbols": ",".join(chunk), "types": ",".join(CA_TYPES), "start": start, "end": end, "limit": CA_LIMIT}
            if token:
                p["page_token"] = token
            js = S._get(CA_URL, p, key, secret)
            sink.requests += 1
            sink(js, {k: v for k, v in p.items() if k != "page_token"}, label)
            token = js.get("next_page_token") if isinstance(js, dict) else None
            if not token:
                return
    except S.BadRequest as e:
        if "symbol" not in str(e).lower():
            raise
        if len(chunk) > 1:
            h = len(chunk) // 2
            ca_fetch_safe(chunk[:h], key, secret, sink, label, start, end)
            ca_fetch_safe(chunk[h:], key, secret, sink, label, start, end)
            return
        sink.bad.append(chunk[0])
        if len(sink.bad) > sink.maxbad:
            raise RuntimeError(f"more than {sink.maxbad} symbols rejected in one pull - check the endpoint and the symbol list")


def ca_new_names(recs, asked):
    """the names a name_change record reveals (old or new) that this pull has not asked for yet - the one extra round"""
    new = set()
    for typ, r in recs:
        if typ == "name_change":
            new |= {str(r.get(k)) for k in ("old_symbol", "new_symbol") if r.get(k)}
    return sorted(new - set(asked))


def ca_rows(recs):
    """records -> the flat rows, exact duplicates dropped (a record repeated by the endpoint), sorted for a reproducible file; -> (rows, duplicates dropped)"""
    seen, rows, dup = set(), [], 0
    for typ, r in recs:
        k = json.dumps([typ, r], sort_keys=True, default=str)
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        rows.append(ca_flatten(typ, r)[0])
    key = lambda w: tuple("" if w[c] is None else str(w[c]) for c in ("type", "symbol", "old_symbol", "new_symbol", "ex_date", "process_date", "record_date", "payable_date", "rate", "new_rate", "old_rate", "cash", "special"))
    return sorted(rows, key=key), dup


def ca_write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CA_COLS)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in CA_COLS])


def ca_probe(key, secret):
    """ONE request (AAPL, NVDA, TSLA, FB, META over 2019-2024): prints the HTTP status, the top-level keys, the record counts per type and the field NAMES of the first record of each type - no value of any
    record, nothing saved. A refusal prints the server's message (scrubbed): a type name it rejects is then edited in CA_TYPES"""
    syms, d0, d1 = CA_PROBE
    p = {"symbols": syms, "types": ",".join(CA_TYPES), "start": d0, "end": d1, "limit": CA_LIMIT}
    print(f"probe: ONE request to the corporate-actions endpoint, symbols {syms}, {d0} .. {d1}, types {','.join(CA_TYPES)} (nothing is saved; no value is printed)", flush=True)
    try:
        js = S._get(CA_URL, p, key, secret)
    except S.BadRequest as e:
        print(f"HTTP status: 400/422 - the request was refused: {scrub(e)}")
        print("  if the message names a type, edit CA_TYPES (the one constant listing the accepted type names) and probe again", flush=True)
        return None
    except (RuntimeError, SystemExit) as e:
        print(f"HTTP status: not 200 - {scrub(e)}", flush=True)
        return None
    recs, info = ca_parse(js)
    print("HTTP status: 200")
    print("top-level keys: " + (", ".join(sorted(map(str, js))) if isinstance(js, dict) else f"<{type(js).__name__}>"))
    ca = js.get("corporate_actions") if isinstance(js, dict) else None
    print("corporate_actions keys: " + (", ".join(sorted(map(str, ca))) if isinstance(ca, dict) else f"<{type(ca).__name__}>"))
    by, first = Counter(t for t, _ in recs), {}
    for t, r in recs:
        first.setdefault(t, sorted(r))
    print("record counts per type: " + (", ".join(f"{t} {n}" for t, n in sorted(by.items())) or "none"))
    for t in sorted(first):
        print(f"  {t}: first record's fields: {', '.join(first[t])}")
    print("next_page_token present: " + ("yes (page 1 only was read)" if isinstance(js, dict) and js.get("next_page_token") else "no"))
    miss = [t for t in CA_KEYS.values() if t not in by]
    print("types asked with no record in this probe: " + (", ".join(miss) or "none"))
    unk = []
    if info["unknown_types"]:
        unk.append("response keys this parser does not know (kept raw as their own type): " + ", ".join(f"{k} ({n})" for k, n in info["unknown_types"].items()))
    if info["unknown_top_keys"]:
        unk.append("top-level keys it does not know: " + ", ".join(info["unknown_top_keys"]))
    fl = Counter()
    for t, r in recs:
        fl.update(ca_flatten(t, r)[1])
    if fl:
        unk.append("record fields the flat CSV does not carry (the raw pages keep them): " + ", ".join(sorted(fl)))
    print("not recognised: " + ("; ".join(unk) if unk else "nothing"), flush=True)
    return js


NAME_RE = re.compile(r"[A-Za-z0-9.\-]{1,12}")


def read_names(path):
    """the WIDE pull's symbol list: one symbol per line (CRLF or LF, a BOM, blank lines and # comments skipped, lower case folded to upper, a repeated symbol dropped, the file's order kept) -> (symbols, info with the
    file's sha256, counts, first / last). A line that is not one symbol (a comma, a space, more than 12 characters of letters, digits, '.' and '-'), a missing file or one with no symbol refuses"""
    if not os.path.isfile(path):
        refuse(f"capull refused: the names file {path} is not on file (nothing pulled)")
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        refuse(f"capull refused: {os.path.basename(path)} is not UTF-8 text (nothing pulled)")
    syms, seen, info = [], set(), {"blank_or_comment_lines": 0, "duplicates_dropped": 0, "lowercase_folded": 0}
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            info["blank_or_comment_lines"] += 1
            continue
        if not NAME_RE.fullmatch(s):
            refuse(f"capull refused: {os.path.basename(path)} line {n}: {s[:24]!r} is not one symbol - one a line, letters, digits, '.' and '-', at most 12 characters (nothing pulled)")
        u = s.upper()
        info["lowercase_folded"] += u != s
        if u in seen:
            info["duplicates_dropped"] += 1
            continue
        seen.add(u)
        syms.append(u)
    if not syms:
        refuse(f"capull refused: {os.path.basename(path)} holds no symbol (nothing pulled)")
    info.update({"path": os.path.abspath(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "symbols": len(syms), "first": syms[0], "last": syms[-1]})
    return syms, info


def print_names_report(path, info, tag):
    print(f"names file {os.path.basename(path)} (tag {tag}): {info['symbols']:,} symbols (first {info['first']}, last {info['last']}), sha256 {info['sha256']}; {info['blank_or_comment_lines']} blank or comment lines skipped, "
          f"{info['duplicates_dropped']} repeated symbols dropped, {info['lowercase_folded']} lower-case symbols folded; round 1 = {-(-info['symbols'] // CA_BATCH):,} requests at least ({CA_BATCH} symbols a request, more for pages)", flush=True)


def capull_args(args):
    """capull's command line -> (probe, force, names_path | None, tag | None). `--names FILE --tag TAG` (both or neither; `--names=FILE` works too) is the WIDE mode; anything else is refused (nothing is pulled)"""
    a, probe, force, val, i = list(args), False, False, {}, 0
    while i < len(a):
        x = a[i]
        if x in ("--probe", "--force"):
            probe, force = probe or x == "--probe", force or x == "--force"
        elif x in ("--names", "--tag") or x.startswith(("--names=", "--tag=")):
            k, eq, v = x.partition("=")
            if not eq:
                i += 1
                v = a[i] if i < len(a) else ""
            if not v or v.startswith("--") or k in val:
                refuse(f"capull refused: {k} takes exactly one value, given once (usage: capull [--probe] [--force] [--names FILE --tag TAG])")
            val[k] = v
        else:
            refuse(f"capull refused: unknown argument {x!r} (usage: capull [--probe] [--force] [--names FILE --tag TAG])")
        i += 1
    names, tag = val.get("--names"), val.get("--tag")
    if (names is None) != (tag is None):
        refuse("capull refused: --names FILE and --tag TAG go together - a wide pull writes corporate_actions_TAG_* files and never touches the NDX pull's (usage: capull [--probe] [--force] [--names FILE --tag TAG])")
    if tag is not None and not re.fullmatch(r"[A-Za-z0-9_]{1,40}", tag):
        refuse(f"capull refused: the tag {tag!r} must be 1 to 40 letters, digits or underscores")
    return probe, force, names, tag


def capull(*args):
    """[X1] the ONE pull: round 1 = every ticker of ndx_members.csv, round 2 = every NEW name a name_change record reveals; the raw pages (one JSON line each, .part then an atomic rename), the flat CSV and the
    manifest (sha256 of both files, row counts by type and year, request count, start / end, created) land in C:\\EdgeLog\\alpaca_cache\\xgap. A complete pull on file is never overwritten without --force
    (then the old files are kept as *.prev-<stamp>); the keys come from r5_siporb.keys() and are never shown.
    WIDE mode for the other lanes: `--names FILE --tag TAG` reads one symbol per line from FILE instead of ndx_members.csv and writes corporate_actions_TAG_raw.jsonl / corporate_actions_TAG.csv /
    corporate_actions_TAG_manifest.json in the same folder - the untagged NDX files are never touched, the overwrite refusal and --force are per tag, round 2 for name changes works the same, and the manifest also
    records the names file's sha256. CHOICE: the stop on rejected symbols scales with the list (CA_MAXBAD, or 2% of the names when that is more) and a progress line, counts only, is printed every 20 pages"""
    global _SECRETS
    probe, force, names_path, tag = capull_args(args)
    wide = tag is not None
    P = ca_paths(tag)
    if wide:
        tickers, ninfo = read_names(names_path)                # a bad names file stops here, before a key is touched
        N = ca_paths()
        assert not {P[k] for k in ("raw", "csv", "manifest")} & {N[k] for k in ("raw", "csv", "manifest")}, "a wide pull never writes the NDX pull's files"
    if not probe and os.path.exists(P["manifest"]) and not force:
        refuse(f"capull refused: a complete corporate-actions pull is already on file{f' for tag {tag!r}' if wide else ''} ({P['manifest']}) - a re-pull is a different photograph of the vendor (Alpaca re-adjusts history "
               "between pulls); --force replaces it (the old files are kept as *.prev-<stamp>)")
    key, secret = S.keys()
    _SECRETS = (key, secret)
    if probe:
        if wide:
            print_names_report(names_path, ninfo, tag)
        ca_probe(key, secret)
        return
    if not wide:
        tickers = members_tickers()
    src = f"{len(tickers)} symbols of {os.path.basename(names_path)} (tag {tag})" if wide else f"{len(tickers)} tickers of ndx_members.csv"
    print(f"capull: {src}, {CA_START} .. {CA_END}, types {','.join(CA_TYPES)}, {CA_BATCH} symbols a request (the shared account pace; nothing printed but counts)", flush=True)
    if wide:
        print_names_report(names_path, ninfo, tag)
    os.makedirs(P["dir"], exist_ok=True)
    sink = CaPull(P["raw"] + ".part", maxbad=max(CA_MAXBAD, -(-len(tickers) // 50)) if wide else CA_MAXBAD, every=20 if wide else 0)
    t0 = time.time()
    try:
        ca_fetch(tickers, key, secret, sink, 1)
        n1 = sink.requests
        new = ca_new_names(sink.recs, tickers)
        print(f"  round 1: {n1} requests, {sink.pages} pages, {len(sink.recs):,} records; {len(new)} new names revealed by name_change records" + (f": {', '.join(new)}" if new and len(new) <= 40 else ""), flush=True)
        if new:
            ca_fetch(new, key, secret, sink, 2)
        sink.close()
    except BaseException as e:
        sink.close()
        refuse(f"capull FAILED after {sink.requests} requests: {type(e).__name__}: {scrub(e)} - nothing was renamed into place ({P['raw']}.part is the partial raw file; run again)")
    rows, dup = ca_rows(sink.recs)
    ca_write_csv(rows, P["csv"] + ".part")
    ys, bytype = defaultdict(Counter), Counter()
    for r in rows:
        ys[r["type"]][ca_year(r)] += 1
        bytype[r["type"]] += 1
    stampt = pd.Timestamp.now().strftime("%Y%m%dT%H%M%S")
    for k in ("raw", "csv", "manifest"):                       # --force: the old pull stays beside the new one
        if force and os.path.exists(P[k]):
            os.replace(P[k], P[k] + ".prev-" + stampt)
    os.replace(P["raw"] + ".part", P["raw"])
    os.replace(P["csv"] + ".part", P["csv"])
    kr, kc = os.path.basename(P["raw"]), os.path.basename(P["csv"])
    man = {"created": pd.Timestamp.now().isoformat(timespec="seconds"), "endpoint": CA_URL, "types": list(CA_TYPES), "start": CA_START, "end": CA_END, "limit": CA_LIMIT, "batch": CA_BATCH,
           "requests": sink.requests, "pages": sink.pages, "tickers_round1": len(tickers), "names_round2": len(new), "records": len(sink.recs), "duplicates_dropped": dup, "rows": len(rows),
           "rows_by_type": dict(bytype), "rows_by_type_year": {t: dict(sorted(c.items())) for t, c in sorted(ys.items())},
           "unknown_types": dict(sink.unknown_types), "unknown_top_keys": dict(sink.unknown_top), "fields_not_flattened": dict(sink.unflat), "rejected_symbols": sink.bad,
           "sha256": {kr: sha_file(P["raw"]), kc: sha_file(P["csv"])}, "harness": os.path.basename(__file__)}
    if wide:
        man.update({"mode": "wide", "tag": tag, "names_file": ninfo, "max_rejected_symbols": sink.maxbad})
    with open(P["manifest"] + ".part", "w") as f:
        json.dump(man, f, indent=1)
    os.replace(P["manifest"] + ".part", P["manifest"])        # the manifest lands last: its presence = a complete pull
    print(f"capull done ({time.time() - t0:.0f}s): {sink.requests} requests, {sink.pages} pages, {len(sink.recs):,} records -> {len(rows):,} rows ({dup} exact duplicates dropped); rows by type: "
          + ", ".join(f"{t} {n:,}" for t, n in sorted(bytype.items())))
    if sink.bad:
        print(f"  symbols the endpoint rejected (no records): {', '.join(sink.bad)}")
    if sink.unknown_types or sink.unknown_top:
        print("  NOT RECOGNISED (kept raw in the .jsonl): " + "; ".join([f"response key {k} x{n}" for k, n in sink.unknown_types.items()] + [f"top-level key {k} x{n}" for k, n in sink.unknown_top.items()]))
    if sink.unflat:
        print("  record fields not carried by the flat CSV (kept in the .jsonl): " + ", ".join(sorted(sink.unflat)))
    print(f"  sha256 raw {man['sha256'][kr][:16]}...  csv {man['sha256'][kc][:16]}...  manifest {P['manifest']}" + (f"  names file {ninfo['sha256'][:16]}..." if wide else ""))
    return man


def load_calendar(cut=None, need=True, tag=None):
    """the pulled calendar -> (DataFrame, info). Refuses (nothing computed) when corporate_actions.csv or its manifest is missing or the csv's sha256 differs from the manifest's; the raw jsonl is checked
    too when it is on file (CHOICE: missing = a warning, differing = a refusal). [MANAGER #58] The NDX calendar (no tag) is also PINNED: with need=True (stage_a, stage_b) both files must hash to exactly
    CAL_CSV_SHA / CAL_RAW_SHA - beside the manifest check - or the run refuses; need=False (dryload) only reports it (info['pinned']). A WIDE pull's calendar (tag) gets the manifest check alone: the pins are the
    NDX pull's. Cut at READ time: a dated action (ex-date) on/after `cut` is dropped and asserted gone. CHOICE: name_change rows of ANY date
    are kept - they are the identity table that maps a historical ticker to SIPORB's today's name (a company renamed after the cut still has its 2016-25 bars under the new name); they carry no price
    information. need=False (dryload) -> (None, {'present': False, ...}) when the files are missing"""
    P = ca_paths(tag)
    kr, kc = os.path.basename(P["raw"]), os.path.basename(P["csv"])
    if not (os.path.exists(P["csv"]) and os.path.exists(P["manifest"])):
        if not need:
            return None, {"present": False}
        refuse(f"refused: the corporate-actions calendar is not on file ({P['csv']} / {os.path.basename(P['manifest'])}) - MANAGER runs `capull{f' --names FILE --tag {tag}' if tag else ''}` first (nothing computed, lockbox NOT read)")
    man = read_json(P["manifest"])
    got = sha_file(P["csv"])
    if got != (man.get("sha256") or {}).get(kc):
        refuse(f"refused: {kc} does not match the sha256 in its manifest - the calendar changed after the pull (nothing computed, lockbox NOT read)")
    raw_sha, warn = None, []
    if os.path.exists(P["raw"]):
        raw_sha = sha_file(P["raw"])
        if raw_sha != (man.get("sha256") or {}).get(kr):
            refuse(f"refused: {kr} does not match the sha256 in its manifest (nothing computed, lockbox NOT read)")
    else:
        warn.append("the raw jsonl is not on file")
    pinned = None
    if tag is None:
        pinned = {"csv": got == CAL_CSV_SHA, "raw": raw_sha == CAL_RAW_SHA}
        if need and not (pinned["csv"] and pinned["raw"]):
            refuse("refused: the calendar on file is not the one the pre-registration pins ([MANAGER #58]; a re-pull is a new photograph and a new addendum): "
                   f"{kc} sha256 {got[:12]}... " + ("is the pinned file" if pinned["csv"] else f"DIFFERS from the pinned {CAL_CSV_SHA[:12]}...") + f"; {kr} " +
                   ("is the pinned file" if pinned["raw"] else (f"sha256 {raw_sha[:12]}... DIFFERS from the pinned {CAL_RAW_SHA[:12]}..." if raw_sha else f"is NOT ON FILE (pinned {CAL_RAW_SHA[:12]}...)")) + " (nothing computed, lockbox NOT read)")
    df = pd.read_csv(P["csv"], dtype=str, keep_default_na=False)
    for c in CA_COLS:
        if c not in df.columns:
            refuse(f"refused: {kc} has no column {c} (nothing computed, lockbox NOT read)")
    df["ex"] = pd.to_datetime(df["ex_date"].mask(df["ex_date"] == ""), errors="coerce")
    df["proc"] = pd.to_datetime(df["process_date"].mask(df["process_date"] == ""), errors="coerce")
    nc = df["type"] == "name_change"
    df["ev"] = np.where(nc, df["proc"], df["ex"])                              # the date a row acts on: a name change its process date, everything else its ex-date (no ex-date = unusable, counted)
    df["ev"] = pd.to_datetime(df["ev"])
    n0, nodate = len(df), int((df["ev"].isna() & ~nc).sum())
    if cut is not None:
        df = df[nc | (df["ev"] < TS(cut))].copy()
        A.assert_cut("calendar", df.loc[df["type"] != "name_change", "ev"].dropna(), cut)
    info = {"present": True, "csv_sha256": got, "manifest_sha256": sha_file(P["manifest"]), "raw_sha256": raw_sha, "created": man.get("created"), "rows_on_file": n0, "rows_read": len(df),
            "rows_without_ex_date": nodate, "rows_by_type": {k: int(v) for k, v in df["type"].value_counts().items()}, "warnings": warn, "pinned": pinned, "tag": tag}
    return df.reset_index(drop=True), info


# ------------------------------------------------------------------ the inputs: membership, the NQBRD member cache, TBIS's flags, SIPORB's daily arrays (all cut when they are read)
def nq_cache_path():
    return os.path.join(S.CACHE, "nqbrd", "open_bars.csv")


def member_mask(days, tick, mem):
    """(T, X) bool: ticker x is a point-in-time member on session t - from <= the first of t's month < to (the prereg's 'from <= t < to': both are month starts, so the two readings agree)"""
    ms = np.asarray(days.strftime("%Y-%m-01"))
    out = np.zeros((len(days), len(tick)), bool)
    ix = pd.Index(tick)
    for tk, f, e in zip(mem["ticker"], mem["from"], mem["to"]):
        out[:, ix.get_loc(tk)] |= (ms >= f) & ((e == "") | (ms < e))
    return out


def read_cache(cut, path=None):
    """NQBRD's member cache (symbol, t, o, c, day; t = the bar START in UTC, RAW prices, symbols as of each month start): the 09:30 and 09:35 ET bars only -> DataFrame(symbol, day, hm, o) with hm = the minute of the
    US/Eastern day (570 / 575). Cut to day < `cut` AT READ TIME, chunk by chunk: a later row is never kept (asserted). CHOICE: a duplicated (symbol, day, bar) keeps the last row and is counted"""
    p = path or nq_cache_path()
    if not os.path.exists(p):
        refuse(f"refused: the NQBRD member cache is not on file ({p}) (nothing computed)")
    cut_s, parts, n_rows, n_bad_day = f"{TS(cut):%Y-%m-%d}", [], 0, 0
    for ch in pd.read_csv(p, usecols=["symbol", "t", "o", "day"], dtype={"symbol": str, "t": str, "day": str}, chunksize=500_000):
        n_rows += len(ch)
        ch = ch[(ch["day"] < cut_s) & ch["t"].str.slice(11, 16).isin(("13:30", "14:30", "13:35", "14:35"))]      # only the two bars (UTC 13:xx in EDT, 14:xx in EST) are converted
        if not len(ch):
            continue
        et = pd.to_datetime(ch["t"], utc=True).dt.tz_convert("US/Eastern")
        hm = (et.dt.hour * 60 + et.dt.minute).to_numpy()
        eday = et.dt.strftime("%Y-%m-%d")
        n_bad_day += int((eday.to_numpy() != ch["day"].to_numpy()).sum())
        k = np.isin(hm, (570, 575)) & (eday.to_numpy() < cut_s)
        parts.append(pd.DataFrame({"symbol": ch["symbol"].to_numpy()[k], "day": pd.to_datetime(eday.to_numpy()[k]), "hm": hm[k], "o": ch["o"].to_numpy(float)[k]}))
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"symbol": [], "day": pd.to_datetime([]), "hm": [], "o": []})
    n0 = len(df)
    df = df.drop_duplicates(["symbol", "day", "hm"], keep="last").reset_index(drop=True)
    A.assert_cut("member cache", df["day"], cut)
    df.attrs.update({"rows_read": n_rows, "dup_dropped": n0 - len(df), "et_day_differs_from_day": n_bad_day})
    return df


def cache_arrays(df, days, tick):
    """the two bars on the session x ticker grid -> (o930, o935, info); NaN = no bar"""
    T, X = len(days), len(tick)
    d = days.get_indexer(pd.DatetimeIndex(df["day"]))
    x = pd.Index(tick).get_indexer(df["symbol"])
    ok = (d >= 0) & (x >= 0)
    out = []
    for hm in (570, 575):
        a = np.full((T, X), np.nan)
        m = ok & (df["hm"].to_numpy() == hm)
        a[d[m], x[m]] = df["o"].to_numpy(float)[m]
        out.append(a)
    return out[0], out[1], {"bars": int(len(df)), "bars_off_grid": int((~ok).sum()), "sessions_with_bars": int(np.isfinite(out[0]).any(axis=1).sum()), **{k: int(v) for k, v in df.attrs.items()}}


def read_tbis(cut, path=None):
    """TBIS's split-QA list (symbol, day, price_ratio, vol_ratio, split_like): all listed rows, cut to day < cut at read time. The registered 'TBIS volume-confirmed flag' = the rows with split_like True (CHOICE: the
    DDW r1 / ATTN phrase 'volume-confirmed' is that column; the other rows are price-only candidates that failed the volume test and are shown in the audit table, not used). A missing file is a refusal"""
    p = path or TBIS_QA
    if not os.path.exists(p):
        refuse(f"refused: TBIS's split-QA list is missing ({p}) - the registered universe needs its volume-confirmed flags (nothing computed)")
    q = pd.read_csv(p, dtype={"symbol": str, "day": str})
    q["day"] = pd.to_datetime(q["day"])
    q["split_like"] = q["split_like"].astype(str).str.lower().isin(("true", "1"))
    q = q[q["day"] < TS(cut)].reset_index(drop=True)
    A.assert_cut("TBIS list", q["day"], cut)
    return q


def load_data(cut):
    """r5_siporb.Data cut at `cut`, no 09:30 file read (XGAP's 09:30 / 09:35 bars come from the NQBRD cache): sessions, symbols, the raw open, the registered split rule and the gap scan"""
    D = S.Data(cut, open5=False)
    A.assert_cut("sessions", D.days, cut)
    return D


# ------------------------------------------------------------------ the symbol map and the calendar's identity table
def chain_next(cal):
    """old -> new of the name_change rows (a later process date wins a conflict); {} without a calendar"""
    nxt = {}
    if cal is None or not len(cal):
        return nxt
    nc = cal[(cal["type"] == "name_change") & (cal["old_symbol"] != "") & (cal["new_symbol"] != "")].sort_values("proc", kind="stable")
    for o, n in zip(nc["old_symbol"], nc["new_symbol"]):
        if o != n:
            nxt[o] = n
    return nxt


def forward_chain(sym, nxt):
    """the ticker, then its calendar successors (FB -> META): the candidate symbols of SIPORB's today's-names daily file, same ticker first; a cycle stops the chain"""
    out, cur = [sym], sym
    while cur in nxt and nxt[cur] not in out:
        cur = nxt[cur]
        out.append(cur)
    return out


def alias_components(cal):
    """symbol -> the set of symbols joined to it by name changes (either direction): the names a calendar action may be filed under for one company"""
    par = {}

    def find(a):
        par.setdefault(a, a)
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    if cal is not None and len(cal):
        nc = cal[(cal["type"] == "name_change") & (cal["old_symbol"] != "") & (cal["new_symbol"] != "")]
        for o, n in zip(nc["old_symbol"], nc["new_symbol"]):
            par[find(o)] = find(n)
    groups = defaultdict(set)
    for s in list(par):
        groups[find(s)].add(s)
    return {s: frozenset(g) for g in groups.values() for s in g}


def _cal_mask(cal, tick, days, comp, types):
    """(T, X) bool: a calendar action of one of `types` acts on that ticker's session. An action is filed under symbols (symbol / old_symbol / new_symbol) and attaches to every ticker whose alias set holds one;
    a date that is not a session reads the next session; a date before the first session is ignored; none without a calendar"""
    T, X = len(days), len(tick)
    out = np.zeros((T, X), bool)
    if cal is None or not len(cal):
        return out
    sym2x = defaultdict(list)
    for x, tk in enumerate(tick):
        for s in comp.get(str(tk), (str(tk),)):
            sym2x[s].append(x)
    ev = cal[cal["type"].isin(types) & cal["ev"].notna() & (cal["ev"] >= days[0])]
    rows = days.searchsorted(pd.DatetimeIndex(ev["ev"]), side="left")
    for r, s0, s1, s2 in zip(rows, ev["symbol"], ev["old_symbol"], ev["new_symbol"]):
        if r >= T:
            continue
        for s in (s0, s1, s2):
            for x in sym2x.get(s, ()) if s else ():
                out[r, x] = True
    return out


def cal_flags(cal, tick, days, comp):
    """(T, X) bool on the ticker axis from the calendar: exdiv = an ex-dividend date (cash dividend, stock dividend or spin-off - CHOICE, see DIV_TYPES) is this session, split = a split ex-date (forward,
    reverse, unit) is this session. An action is filed under symbols (symbol / old_symbol / new_symbol) and attaches to every ticker whose alias set holds one; a date that is not a session reads the next
    session; a date before the first session is ignored; none without a calendar"""
    return _cal_mask(cal, tick, days, comp, DIV_TYPES), _cal_mask(cal, tick, days, comp, SPLIT_TYPES)


def exdiv_by_type(cal, tick, days, comp):
    """{type: (T, X) bool}: the ex-dividend flags apart by type (cash_dividend, stock_dividend, spin_off) - their union is cal_flags' exdiv (the exclusion reported apart by type)"""
    return {t: _cal_mask(cal, tick, days, comp, (t,)) for t in DIV_TYPES}


def identity_ok(a, b):
    """[TV X1] the identity check, price against price: |a - b| <= max(1 cent, 0.10% of b) - a = the member cache's raw 09:30 open, b = SIPORB's raw official open (ID_EPS: float noise only)"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(a) & np.isfinite(b) & (np.abs(a - b) <= np.maximum(ID_ABS, ID_REL * b) + ID_EPS)


def choose_map(o930, od_k, cand_k):
    """the symbol map, per ticker x and session t: the first candidate symbol (same ticker first, then the calendar's old -> new chain; a share-class member has its own ticker only) whose raw official open passes the
    IDENTITY check against the member cache's raw 09:30 open [TV X1]: |09:30 open - official open| <= max(1 cent, 0.10% of the official open)
    -> (ksel (T, X): the candidate's column in od_k, -1 = none passes; nodata (T, X): no candidate has an official open that session - a name Alpaca never kept, or a missing bar)"""
    T, X = o930.shape
    ksel, nodata = np.full((T, X), -1, np.int64), np.ones((T, X), bool)
    for x in range(X):
        for kk in cand_k[x]:
            od = od_k[:, kk]
            have = np.isfinite(od) & (od > 0)
            nodata[:, x] &= ~have
            ok = have & identity_ok(o930[:, x], od) & (ksel[:, x] < 0)
            ksel[ok, x] = kk
    return ksel, nodata


def fallback_map(od_k, cand_k, ksel):
    """[TV X2] the symbol each name-day WOULD map to if the identity check were waived: the chosen one where it passed, else the first candidate (the same ticker first) that has an official open that session;
    -1 = none has one (no data). Its prices give the dropped names' g"""
    kw = ksel.copy()
    for x, cs in enumerate(cand_k):
        for kk in cs:
            od = od_k[:, kk]
            m = (kw[:, x] < 0) & np.isfinite(od) & (od > 0)
            kw[m, x] = kk
    return kw


def share_class_groups(tickers):
    """[TV X1] -> (groups, report): the member tickers that are classes of one company and so map ONLY to their own ticker in both pulls (no name-change chain may carry them across classes). groups = sorted tuples of
    connected tickers: every name of the addendum's explicit list that is on file (even one whose partner is not) plus the pairs the DETECTOR finds among the member tickers - one is the other plus a trailing class
    letter (GOOG / GOOGL, FOX / FOXA, TFCF / TFCFA), or the two differ only in a last letter that is a class letter in both (LBTYA / LBTYK, LMCA / LMCK). CHOICE: CLASS_LETTERS = A B C K L; every other pair of tickers that
    shares a root (ADI / ADP, INTC / INTU ...) is listed in the report as `not_taken` and printed, never enforced"""
    t = sorted({str(x) for x in tickers})
    ts = set(t)
    explicit = {s for fam in SHARE_CLASS for s in fam if s in ts}
    taken = {tuple(sorted(p)) for fam in SHARE_CLASS for p in itertools.combinations([s for s in fam if s in ts], 2)}
    exp_pairs, loose = set(taken), set()
    for a, b in itertools.combinations(t, 2):
        lo, hi = (a, b) if len(a) <= len(b) else (b, a)
        plus = len(hi) == len(lo) + 1 and hi.startswith(lo) and len(lo) >= 2
        same = len(a) == len(b) >= 3 and a[:-1] == b[:-1]
        if (plus and hi[-1] in CLASS_LETTERS) or (same and len(a) >= 4 and a[-1] in CLASS_LETTERS and b[-1] in CLASS_LETTERS):
            taken.add((a, b))
        elif plus or same:
            loose.add((a, b))
    par = {s: s for s in explicit | {x for p in taken for x in p}}

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in taken:
        par[find(a)] = find(b)
    grp = defaultdict(list)
    for s in par:
        grp[find(s)].append(s)
    groups = sorted(tuple(sorted(g)) for g in grp.values())
    report = {"explicit_pairs_on_file": sorted(exp_pairs), "explicit_names_on_file": sorted(explicit), "explicit_families_with_no_member": [list(f) for f in SHARE_CLASS if not any(s in ts for s in f)],
              "detected_beyond_the_list": sorted(taken - exp_pairs), "shared_root_not_taken": sorted(loose), "groups": [list(g) for g in groups], "class_letters": CLASS_LETTERS}
    return groups, report


def restrict_candidates(tick, full, pairmem):
    """[TV X1] the candidate symbols per ticker from the calendar chain `full` (each starts with the ticker itself): a share-class member keeps its OWN ticker only (no name-change chain may carry it across classes, nor
    along a rename), and nobody keeps a class member's symbol as a chain successor. -> (cand, the (ticker, symbol) chain edges refused)"""
    cand = [[str(tk)] if str(tk) in pairmem else [s for s in c if s == str(tk) or s not in pairmem] for tk, c in zip(tick, full)]
    return cand, sorted({(str(tk), s) for tk, c, f in zip(tick, cand, full) for s in f if s not in c})


def payer_flags(cal, tick, days, comp):
    """[TV X5] (T, X) bool: a cash dividend with an ex-date in the trailing 365 days (ex-date e, session t: e < t <= e + 365 days), attached to tickers like the ex-dividend flags (alias sets; a share-class member by its own
    ticker only). The calendar starts 2016-06-01, so the lookback is complete only from 2017-06-02 on. None without a calendar"""
    T, X = len(days), len(tick)
    out = np.zeros((T, X), bool)
    if cal is None or not len(cal):
        return out
    sym2x = defaultdict(list)
    for x, tk in enumerate(tick):
        for s in comp.get(str(tk), (str(tk),)):
            sym2x[s].append(x)
    cd = cal[(cal["type"] == "cash_dividend") & cal["ev"].notna()]
    for e, s0, s1, s2 in zip(cd["ev"], cd["symbol"], cd["old_symbol"], cd["new_symbol"]):
        xs = {x for s in (s0, s1, s2) if s for x in sym2x.get(s, ())}
        r0, r1 = int(days.searchsorted(e, side="right")), int(days.searchsorted(e + pd.Timedelta(days=365), side="right"))
        if r0 < r1:
            for x in xs:
                out[r0:r1, x] = True
    return out


def roll_any(a, w=FLAG_WIN, lag=0):
    """(T, ...) bool: True where any row in [t-w+1-lag, t-lag] is True (r5_siporb's rolling-max idiom); lag 1 with w 5 = the sessions t-5 .. t-1"""
    r = pd.DataFrame(np.asarray(a, np.float32)).rolling(w, min_periods=1).max().to_numpy() > 0
    if lag:
        r = np.vstack([np.zeros((lag,) + r.shape[1:], bool), r[:-lag]])
    return r


def prev(a):
    """each row's previous session (NaN / False on the first)"""
    a = np.asarray(a)
    fill = np.nan if a.dtype.kind == "f" else False
    return np.concatenate([np.full((1,) + a.shape[1:], fill, a.dtype), a[:-1]])


def gather(a_k, ksel):
    """(T, K) on the SIPORB-symbol axis -> (T, X) on the ticker axis through each name's chosen symbol (NaN / False where none was chosen)"""
    T, X = ksel.shape
    m = ksel >= 0
    out = np.full((T, X), np.nan if a_k.dtype.kind == "f" else False, a_k.dtype)
    ti = np.broadcast_to(np.arange(T)[:, None], (T, X))
    out[m] = a_k[ti[m], ksel[m]]
    return out


def long_to_k(days, df, csyms, field):
    """a long daily frame (symbol category, date, o / c ...) -> (T, K) on the session x candidate-symbol axes"""
    cat = pd.Index(csyms).get_indexer(df["symbol"].cat.categories.astype(str))
    codes = df["symbol"].cat.codes.to_numpy()
    kp = np.where(codes >= 0, cat[np.maximum(codes, 0)], -1)
    d = days.get_indexer(pd.DatetimeIndex(df["date"]))
    ok = (kp >= 0) & (d >= 0)
    a = np.full((len(days), len(csyms)), np.nan)
    a[d[ok], kp[ok]] = df[field].to_numpy(float)[ok]
    return a


# ------------------------------------------------------------------ the world on the session x ticker grid
def betas(ret, member, win=BETA_WIN, min_names=10):
    """[X3] beta_i,t = the OLS slope of the name's split-safe daily returns on the universe's median daily return over the previous `win` sessions (t-win .. t-1), all `win` present, else NaN.
    The median runs over the members of that session with a return (CHOICE: at least `min_names` of them). -> (beta (T, X), mkt (T,))"""
    T, X = ret.shape
    mkt = np.full(T, np.nan)
    for t in range(T):
        v = ret[t, member[t] & np.isfinite(ret[t])]
        if len(v) >= min_names:
            mkt[t] = np.median(v)
    ok = np.isfinite(ret) & np.isfinite(mkt)[:, None]
    y, x = np.where(ok, ret, 0.0), np.where(ok, mkt[:, None], 0.0)

    def rs(a):
        return pd.DataFrame(a).rolling(win, min_periods=win).sum().shift(1).to_numpy()
    n, sx, sy, sxy, sxx = rs(ok.astype(float)), rs(x), rs(y), rs(x * y), rs(x * x)
    den, nu = n * sxx - sx * sx, n * sxy - sx * sy
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((n == win) & (den > 1e-18), nu / den, np.nan), mkt


def split_safe_gap(od, cl_prev, f, f_prev):
    """the raw gap = the official open / the prior official close - 1, SPLIT-SAFE: the open is put on the prior session's share basis (x F_t-1 / F_t, SIPORB's raw / split-adjusted open factor - r13_attn's exit-value
    idiom), so a 2-for-1 split between the two prints reads the true +2%, not -49%; NaN where any input is missing"""
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(od, float) * np.asarray(f_prev, float) / np.asarray(f, float) / np.asarray(cl_prev, float) - 1.0


# ONE RAW PRICE BASIS A NAME-DAY, MISSING PIECES, THE NULL'S POOL [NOISE H2, H3, H4] - confirmed here, enforced below:
#   ENTRY  = the member cache's RAW 09:35 bar open (o935, the vendor's own unadjusted basis);   EXIT = SIPORB's RAW official close of session t (Cl, the daily_raw bar; on a half-day session that bar IS the session's
#   early official close, so a half-day exits at that session's official close);   IDENTITY check = the cache's RAW 09:30 bar open against SIPORB's RAW official open of t (choose_map) - entry, identity check and exit
#   all sit on day t's raw basis, and the signal g is SIPORB's official open / prior official close put on one split basis (split_safe_gap).
#   A name-day with an entry but NO official close on t (or none on t-1) is dropped from the cell AND the null (universe code no_prior: why_conds); a member-day with no SIPORB bar at all after the rename chain is
#   map_nodata - the SURVIVORSHIP line, printed by year on its own and NOT counted in the 2% rule, which counts the identity-check drops (map_open) only. Every exclusion shrinks the universe U, and the null draws
#   from that same pool, so each new exclusion leaves the null's pool as well [H4].
def assemble(P, removed=None):
    """everything one stage reads -> the world on the session x ticker grid (every array (T, X); the SIPORB side is read per candidate symbol (K) and gathered through the day's chosen symbol).
    P = (D: r5_siporb.Data, cut, cal | None, tbis, cache, members). `removed` = {(symbol, date)} the hand audit found to be data events: they leave the universe (cells AND null).
    The world W is the REGISTERED reading (the identity check enforced). W.waived is the same world with the identity check waived [TV X2] (a name-day that failed it is read through its fallback symbol, so its g
    comes from SIPORB's official prices); W.idfail marks the name-days the check dropped. [TV X1] a share-class member maps to its own ticker only: W.pairs / W.pair_info / W.refused say what that refused"""
    D, cut, cal, mem = P.D, P.cut, P.cal, P.members
    days, T = D.days, len(D.days)
    tick = np.array(sorted(mem["ticker"].unique()), dtype=object)
    X = len(tick)
    member = member_mask(days, tick, mem)
    o930, o935, cinfo = cache_arrays(P.cache, days, tick)
    nxt, comp = chain_next(cal), alias_components(cal)
    groups, pinfo = share_class_groups([str(t) for t in tick])
    pairmem = {s for g in groups for s in g}
    full = [forward_chain(str(tk), nxt) for tk in tick]                                 # what the calendar chain alone would offer
    cand, refused_edges = restrict_candidates(tick, full, pairmem)                      # [TV X1]: a class member maps ONLY to its own ticker; nobody maps onto a class member's symbol
    comp = {**comp, **{s: frozenset({s}) for s in pairmem}}                             # a class member's calendar actions are its own ticker's: no alias set joins two classes
    sidx = pd.Index(D.syms)
    csyms = sorted({s for c in full for s in c if s in sidx})                           # the SIPORB symbols any ticker can map to that exist in the data
    kpos = {s: j for j, s in enumerate(csyms)}
    cand_k = [[kpos[s] for s in c if s in kpos] for c in cand]
    full_k = [[kpos[s] for s in c if s in kpos] for c in full]
    kcols = sidx.get_indexer(csyms)
    Od_k, chg_k, ms_k = D.Od[:, kcols], D.chg[:, kcols], D.msplit[:, kcols]
    raw, spl = S.read_long("raw", cut), S.read_long("split", cut)                       # read_long cuts at read time; asserted again here
    A.assert_cut("daily_raw", raw["date"], cut)
    A.assert_cut("daily_split", spl["date"], cut)
    Cl_k, Os_k, Cs_k = long_to_k(days, raw, csyms, "c"), long_to_k(days, spl, csyms, "o"), long_to_k(days, spl, csyms, "c")
    del raw, spl
    with np.errstate(invalid="ignore", divide="ignore"):
        F_k = Od_k / Os_k                                                               # SIPORB's split factor: raw / split-adjusted OPEN
        Clp_k = prev(Cl_k)
        R_k = Od_k / Clp_k
    tb_k = np.zeros((T, len(csyms)), bool)
    tb = P.tbis[P.tbis["split_like"]]
    i, j = days.get_indexer(pd.DatetimeIndex(tb["day"])), pd.Index(csyms).get_indexer(tb["symbol"].astype(str))
    ok = (i >= 0) & (j >= 0)
    tb_k[i[ok], j[ok]] = True                                                           # the volume-confirmed TBIS symbol-days
    with np.errstate(invalid="ignore"):
        g50_k = np.isfinite(R_k) & (np.abs(R_k - 1.0) > GAP_MAX) & ~chg_k               # a raw gap beyond +-50% with no split-factor change
    ksel, nodata = choose_map(o930, Od_k, cand_k)
    own_k = [[kpos[str(tk)]] if str(tk) in kpos else [] for tk in tick]
    ksel_own, nodata_own = choose_map(o930, Od_k, own_k)                                # the same-ticker map alone: the name-change chain's recovery (dryload) is the difference
    ksel_full, _ = choose_map(o930, Od_k, full_k)
    ksel_w = fallback_map(Od_k, cand_k, ksel)
    exdiv, cal_ev = cal_flags(cal, tick, days, comp)
    exdiv_t = exdiv_by_type(cal, tick, days, comp)
    payer = payer_flags(cal, tick, days, comp)
    cal6 = roll_any(cal_ev)
    rk = {"reg": roll_any(chg_k), "gap": roll_any(ms_k), "tb": roll_any(tb_k), "tbp": roll_any(tb_k, FLAG_WIN - 1, lag=1), "g50": roll_any(g50_k)}
    # [TV X4] THE TWIN'S BETA INPUTS DO NOT DEPEND ON THE IDENTITY CHECK. The prereg's beta is the OLS slope of the name's split-safe daily close-to-close returns (SIPORB's daily_split bars) on the universe's median
    # return over the previous 60 sessions, ALL PRESENT - a statement about SIPORB's bars, not about the 09:30 open matching. Read through the REGISTERED symbol choice an identity-dropped name-day would have no
    # return, and with the registered 0.10% tolerance dropping several percent of member-days a year a full 60-session window would almost never exist (the twin would trade on a tenth of the sessions and the veto
    # would test an artifact), so the returns are read through the symbol chosen WITHOUT the check (the chosen one where it passed, else the first candidate with an official open): one beta array for both readings.
    # CHOICE (counted by dryload: the share of eligible name-days with a beta, the sessions the twin trades)
    Gw = lambda a: gather(a, ksel_w)
    with np.errstate(invalid="ignore", divide="ignore"):
        ret_w = Gw(Cs_k) / Gw(prev(Cs_k)) - 1.0                                         # split-adjusted close-to-close return (the daily_split bars)
    ret_w = np.where(Gw(chg_k) | Gw(ms_k) | Gw(tb_k) | Gw(g50_k) | cal_ev, np.nan, ret_w)    # CHOICE: a return on a day any split rule fired is dropped from the beta windows (an unadjusted split would be a -50% 'return')
    beta_w, mkt_w = betas(ret_w, member)

    def world(ks):
        G = lambda a: gather(a, ks)
        Wd = SimpleNamespace(days=days, tick=tick, member=member, o930=o930, o935=o935, ksel=ks, nodata=nodata, csyms=csyms, cand=cand, cand_k=cand_k, cut=cut,
                             Od=G(Od_k), Cl=G(Cl_k), Cl_prev=G(Clp_k), F=G(F_k), F_prev=G(prev(F_k)), exdiv=exdiv, cal_ev=cal_ev, cal6=cal6, payer=payer,
                             reg_ev=G(chg_k), gap_ev=G(ms_k), tbis_ev=G(tb_k), g50_ev=G(g50_k),
                             reg6=G(rk["reg"]), gap6=G(rk["gap"]), tbis6=G(rk["tb"]), tbis6_prior=G(rk["tbp"]), g506=G(rk["g50"]),
                             audit=np.zeros((T, X), bool), cache_info=cinfo, has_calendar=cal is not None)
        Wd.gap = split_safe_gap(Wd.Od, Wd.Cl_prev, Wd.F, Wd.F_prev)                    # the signal: SPLIT-SAFE raw gap (SIPORB's official prices; H2: one price basis a name-day)
        Wd.ret, Wd.beta, Wd.mkt = ret_w, beta_w, mkt_w                                  # the twin's inputs: the same in both readings (see the CHOICE above)
        return Wd
    W = world(ksel)
    W.waived = world(ksel_w)
    W.comp = comp                                                                       # the alias sets the calendar flags used (share-class members: their own ticker only)
    W.ksel_own, W.nodata_own, W.exdiv_type = ksel_own, nodata_own, exdiv_t                # the same-ticker map alone; the ex-dividend flags apart by type (reports only)
    W.idfail = (ksel < 0) & (ksel_w >= 0)                                               # the identity check dropped it (a SIPORB bar exists, no candidate passes)
    W.pairs, W.pair_members = groups, pairmem
    rm = (ksel < 0) & (ksel_full >= 0) & member                                         # a calendar-chain symbol would have passed where the share-class member's own ticker did not: REFUSED
    ref = Counter()
    for t_, x_ in zip(*np.nonzero(rm)):
        ref[(str(tick[x_]), csyms[ksel_full[t_, x_]], int(days[t_].year))] += 1
    W.refused = ref
    W.pair_info = {**pinfo, "chain_edges_refused": [list(e) for e in refused_edges],
                   "refused_cross_class_name_days": [{"ticker": a, "symbol": b, "year": y, "name_days": n} for (a, b, y), n in sorted(ref.items())]}
    for sym, d in (removed or ()):
        r = days.get_indexer([TS(d)])[0]
        if r >= 0:
            for x in range(X):
                if sym == tick[x] or sym in cand[x]:
                    W.audit[r, x] = True
                    W.waived.audit[r, x] = True
    return W


def sym_of(W, t, x):
    """the SIPORB symbol a name-day was mapped to ('' = none)"""
    k = W.ksel[t, x]
    return W.csyms[k] if k >= 0 else ""


# ------------------------------------------------------------------ the universe (prereg UNIVERSE) and its hygiene counts
WHY = ("ok", "no_bar", "map_nodata", "map_open", "no_prior", "no_factor", "ex_div", "split_cal", "split_reg", "split_gap", "split_tbis", "gap50", "audit")


def why_conds(W, tbis=None):
    """the exclusion rules in the order of WHY[1:] as (T, X) bool arrays (each True where the rule alone would drop the member-day)"""
    fin = np.isfinite
    with np.errstate(invalid="ignore"):
        return [~(fin(W.o930) & fin(W.o935) & (W.o930 > 0) & (W.o935 > 0)),                                       # no 09:30 or no 09:35 bar on t
                W.nodata,                                                                                         # no SIPORB daily bar on t under any candidate symbol (a name Alpaca never kept)
                (W.ksel < 0) & ~W.nodata,                                                                         # identity check [TV X1]: a daily bar exists but the 09:30 open is not within max(1 cent, 0.10%) of the official open
                ~(fin(W.Od) & fin(W.Cl) & fin(W.Cl_prev) & (W.Od > 0) & (W.Cl > 0) & (W.Cl_prev > 0)),            # no daily bar on t-1 (the prior close) or no official close on t
                ~(fin(W.F) & fin(W.F_prev)),                                                                      # no split factor: the gap cannot be made split-safe
                W.exdiv,                                                                                          # ex-dividend (calendar) on t
                W.cal6, W.reg6, W.gap6, W.tbis6_prior if tbis is None else tbis, W.g506,                          # a split in the calendar / registered / gap scan / raw gap beyond +-50%, t-5 .. t (known by the open); TBIS's volume-confirmed flag t-5 .. t-1 only [NOISE H1]
                W.audit]                                                                                          # the hand audit's data events


def why_codes(W, tbis=None):
    """the FIRST failing rule per member-day (index into WHY; 0 = in the universe, -1 = not a member that session)"""
    conds = why_conds(W, tbis)
    why = np.zeros(W.member.shape, np.int8)
    for code in range(len(conds), 0, -1):
        why[conds[code - 1]] = code
    why[~W.member] = -1
    return why


def universe(W):
    """-> SimpleNamespace(why, elig): elig = member and no rule fires; every exclusion counted by reason and year in hygiene()"""
    why = why_codes(W)
    return SimpleNamespace(why=why, elig=why == 0)


def by_year(days, a):
    yr = days.year.to_numpy()
    return {int(y): int(a[yr == y].sum()) for y in sorted(set(yr))}


def chain_recovery(W, bars_ok, mem, days):
    """what the calendar's name-change chain adds to the symbol map, by year, COUNTS ONLY, over the member-days that have both cache bars: no SIPORB bar under the same-ticker map alone, after the chain, the member-days
    the chain recovers from 'no data' (a chain symbol has an official open) and how many of those then pass the identity check, and the member-days it RESCUES from an identity drop (the ticker's own bar fails
    the check, a chain symbol passes) - plus the tickers involved (and the tickers still without a bar after the chain: the survivorship)"""
    m = mem & bars_ok
    own, aft = W.nodata_own & m, W.nodata & m
    rec = own & ~W.nodata
    rec_ok = rec & (W.ksel >= 0)
    resc = m & ~W.nodata_own & (W.ksel_own < 0) & (W.ksel >= 0)
    yr = days.year.to_numpy()
    out = {"by_year": {}}
    for y in sorted(set(yr)):
        s = yr == y
        n = int(mem[s].sum())
        if n:
            out["by_year"][int(y)] = {"member_days": n, "no_data_same_ticker": int(own[s].sum()), "no_data_after_chain": int(aft[s].sum()), "recovered": int(rec[s].sum()),
                                      "recovered_identity_ok": int(rec_ok[s].sum()), "rescued_from_identity_drop": int(resc[s].sum())}
    tk = lambda a: {str(W.tick[x]): int(a[:, x].sum()) for x in np.flatnonzero(a.any(axis=0))}
    out["tickers_recovered"], out["tickers_rescued"], out["tickers_no_data_after_chain"] = tk(rec), tk(resc), tk(aft)
    return out


def hygiene(W, U):
    """counts only: member-days, universe size, the first-failing-rule partition and the any-rule counts of every exclusion by year, the symbol map's IDENTITY-drop rate (a year over 2% is named - [NOISE H3]: the
    identity-check drops only) and, as their own line, the no-data drops by year (a member-day with no Alpaca bar at all after the rename chain: the survivorship the draft lists), the TBIS flag under both windows
    ([NOISE H1]: registered t-5 .. t-1; the old t-5 .. t beside it, with the name-days only a flag dated t itself removes), and the calendar-vs-price-rule disagreements by year"""
    days, yr = W.days, W.days.year.to_numpy()
    live = np.isfinite(W.o930).any(axis=1)                                              # sessions the member cache has any bar on (the others are not member-days of this study)
    mem = W.member & live[:, None]
    why = U.why
    out = {"sessions_by_year": {int(y): int(((yr == y) & live).sum()) for y in sorted(set(yr))}, "member_days_by_year": by_year(days, mem),
           "eligible_by_year": by_year(days, U.elig & live[:, None])}
    first = {}
    for code, name in enumerate(WHY[1:], 1):
        first[name] = by_year(days, (why == code) & live[:, None])
    out["excluded_first_rule_by_year"] = first
    anyc = {}
    for name, c in zip(WHY[1:], why_conds(W)):
        anyc[name] = by_year(days, c & mem)
    out["excluded_any_rule_by_year"] = anyc
    mp = {}
    chk = np.isfinite(W.o930) & ~W.nodata & W.member                                    # member-days a check can be made on: a 09:30 bar and a SIPORB bar
    for y in sorted(set(yr)):
        s = (yr == y) & live
        n = int(mem[s].sum())
        ident = int(((why == 3) & mem)[s].sum())
        nod = int(((why == 2) & mem)[s].sum())
        nchk = int(chk[s].sum())
        mp[int(y)] = {"member_days": n, "identity_drops": ident, "share": ident / n if n else float("nan"), "no_data": nod, "no_data_share": nod / n if n else float("nan"),
                      "checked": nchk, "agreement_rate": float((chk & (W.ksel >= 0))[s].sum()) / nchk if nchk else float("nan")}
    out["symbol_map_by_year"] = mp
    out["map_years_over_2pct"] = [y for y, v in mp.items() if v["member_days"] and v["share"] > MAP_YEAR_MAX]       # [NOISE H3] the identity-check drops only; the no-data drops are the survivorship line
    if hasattr(W, "nodata_own"):
        out["chain_recovery"] = chain_recovery(W, ~why_conds(W)[0], mem, days)                                        # the calendar's name-change chain: what it recovers from no-data and rescues from identity drops
    if hasattr(W, "exdiv_type"):
        out["ex_div_by_type"] = {t: by_year(days, m_ & mem) for t, m_ in W.exdiv_type.items()}                       # the ex-dividend flag fired, by type (any other rule aside)
    wt = why_codes(W, W.tbis6)                                                          # the old window, t-5 .. t, beside the registered t-5 .. t-1
    out["tbis"] = {"registered_t5_to_t1_removals": by_year(days, (why == 10) & live[:, None]), "through_t_removals": by_year(days, (wt == 10) & live[:, None]),
                   "removed_only_by_a_flag_dated_t": by_year(days, (wt == 10) & (why == 0) & live[:, None]),
                   "note": "[NOISE H1] the registered window is t-5 .. t-1 (the volume ratio needs a full session); the through-t version is the draft's, counted beside it; first-failing-rule removals"}
    pr = W.reg_ev | W.gap_ev | W.tbis_ev | W.g50_ev                                     # a price rule fired on that name-day
    cal_n, price_n = _near(W.cal_ev), _near(pr)
    ce, pe = W.cal_ev & mem, pr & mem
    out["calendar_vs_price"] = {"calendar_split_events": by_year(days, ce), "calendar_only": by_year(days, ce & ~price_n), "price_rule_events": by_year(days, pe), "price_only": by_year(days, pe & ~cal_n),
                                "note": "an event is a name-day; 'only' = no event of the other kind on the same name within one session either side"}
    out["share_class"] = W.pair_info if hasattr(W, "pair_info") else None
    return out


def _near(a):
    """(T, X) bool: an event on the row itself or one session either side"""
    a = np.asarray(a, bool)
    r = a.copy()
    r[1:] |= a[:-1]
    r[:-1] |= a[1:]
    return r


# ------------------------------------------------------------------ the baskets, the costs, the null
def name_pnl(side, o, c, bps, slot=SLOT):
    """P&L of a $5,000 position per name-day: fractional shares slot / o bought at the OPEN of the 09:35 bar (o), sold (or covered) at the official close c; costs = bps of the entry notional (slot) and of the exit
    value (shares x c) - base 10 / 5 bps, stress 20 / 10. side +1 = long, -1 = short; no compounding"""
    eb, xb = bps
    vx = slot * np.asarray(c, float) / np.asarray(o, float)
    return side * (vx - slot) - eb * 1e-4 * slot - xb * 1e-4 * vx


def cents_pnl(side, o, c, slot=SLOT):
    """SIPORB's cents-per-share costs (S.COMM + S.SLIP a share a side, both sides) on the same fractional shares - the third reported row, never judged"""
    sh = slot / np.asarray(o, float)
    return side * (sh * np.asarray(c, float) - slot) - sh * 2.0 * (S.COMM + S.SLIP)


def draw_picks(rng, n, k, nreps):
    """nreps random assignments of 2k DISTINCT names out of n: (nreps, 2k) positions, the first k the longs, the last k the shorts. The 2k smallest of n i.i.d. uniform keys are a uniform 2k-subset and,
    sorted by key, a uniform ordering of it - so every long set of k and every short set of k is equally likely"""
    if not 0 < 2 * k <= n:
        raise ValueError(f"cannot draw {2 * k} of {n}")
    keys = rng.random((nreps, n))
    sel = np.argpartition(keys, 2 * k - 1, axis=1)[:, :2 * k]
    return np.take_along_axis(sel, np.argsort(np.take_along_axis(keys, sel, 1), axis=1), 1)


def run_cells(W, U, rows, nb, i0, nreps=0, seed=SEED, k=NPOS, twin=True, untrade=None):
    """every session from row i0: the relative gap g = split-safe raw gap - the median raw gap of the session's universe; per cell the pool (ALL: the universe; CAP8: |g| <= 8%), the k most negative g long and the k
    most positive short (ties: g, then ticker order), the MIRROR (the opposite baskets), the beta-adjusted twin [X3] (g_b = raw gap - beta x the median, names with a full 60-session beta only) and, with nreps > 0,
    the family-aware random-pick null: each draw, each session, each cell = k longs + k shorts uniform without replacement from that cell's pool (the same costs). A pool under 2k names = no trade (CHOICE:
    both sides always full, so a basket needs 2k distinct names). `untrade` (T, X) bool [TV X2]: a name that is in the pool but cannot be traded (the identity check dropped it) - a position it would take is left EMPTY:
    its side trades fewer names, no cost, nothing takes its place (the 11th name does not step in); the null's draws leave the same slots empty. Every exclusion that shrinks U shrinks the null's pool the same way
    [NOISE H4]: the null draws from the same pool as the cell.
    -> SimpleNamespace(nd {(variant, cell): name-day arrays i, x, side, g, gap, o, c}, acc {cell: (nreps, nb) base-cost P&L by #463 row})"""
    T, X = U.elig.shape
    rng = np.random.default_rng(seed)
    rec = {(v, c): {"i": [], "x": [], "side": [], "g": []} for v in ("P", "M", "T") for c in CELLS}
    acc = {c: np.zeros((nreps, nb)) for c in CELLS} if nreps else None

    def add(v, c, i, longs, shorts, g):
        if untrade is not None:
            longs, shorts = longs[~untrade[i, longs]], shorts[~untrade[i, shorts]]
        r = rec[(v, c)]
        r["i"].append(np.full(len(longs) + len(shorts), i))
        r["x"].append(np.concatenate([longs, shorts]))
        r["side"].append(np.concatenate([np.ones(len(longs)), -np.ones(len(shorts))]))
        r["g"].append(g[np.concatenate([longs, shorts])])

    def basket(pool, g):
        o = pool[np.lexsort((pool, g[pool]))]
        return o[:k], o[-k:]
    for i in range(i0, T):
        e = np.flatnonzero(U.elig[i])
        if len(e) < 2 * k:
            continue
        gap = W.gap[i]
        med = float(np.median(gap[e]))
        g = gap - med
        if nreps:
            lp, sp = name_pnl(1.0, W.o935[i], W.Cl[i], COST["base"]), name_pnl(-1.0, W.o935[i], W.Cl[i], COST["base"])
            if untrade is not None:
                lp, sp = np.where(untrade[i], 0.0, lp), np.where(untrade[i], 0.0, sp)
        for c in CELLS:
            pool = e if c == "ALL" else e[np.abs(g[e]) <= CAP + 1e-12]
            if len(pool) < 2 * k:
                continue
            lo, sh = basket(pool, g)
            add("P", c, i, lo, sh, g)
            add("M", c, i, sh, lo, g)
            if nreps:
                sel = pool[draw_picks(rng, len(pool), k, nreps)]
                acc[c][:, rows[i]] += lp[sel[:, :k]].sum(axis=1) + sp[sel[:, k:]].sum(axis=1)
        if twin:
            et = e[np.isfinite(W.beta[i, e])]
            if len(et) >= 2 * k:
                gb = gap - W.beta[i] * med
                for c in CELLS:
                    pool = et if c == "ALL" else et[np.abs(gb[et]) <= CAP + 1e-12]
                    if len(pool) >= 2 * k:
                        lo, sh = basket(pool, gb)
                        add("T", c, i, lo, sh, gb)
    nd = {}
    for key, r in rec.items():
        a = {n: (np.concatenate(v) if v else np.zeros(0)) for n, v in r.items()}
        a["i"], a["x"] = a["i"].astype(np.int64), a["x"].astype(np.int64)
        a["gap"], a["o"], a["c"] = W.gap[a["i"], a["x"]], W.o935[a["i"], a["x"]], W.Cl[a["i"], a["x"]]
        nd[key] = a
    return SimpleNamespace(nd=nd, acc=acc)


# ------------------------------------------------------------------ the statistics
def day_series(nd, p, rows, nb):
    """name-day P&L -> (daily P&L on the #463 index, name-days booked per row); a session's P&L is stamped on its own session (the exit is that day's close)"""
    r = rows[nd["i"]]
    return np.bincount(r, weights=p, minlength=nb), np.bincount(r, minlength=nb)


def cell_stats(B, nd, p, rows, lo, hi, years=YEARS):
    """one basket on [lo, hi] (inclusive, on the #463 index). ROC @ $30k / Sortino / max drawdown / years: r11_risk.stats on the daily series (zeros on the days without a basket; peak from 0). PF, the
    Newey-West t (5 lags), the best-5-days removal and the July-June breadth: on the TRADED sessions' series (CHOICE: the sessions with a basket, r13_attn's 'nights'); the best 1% of NAME-DAYS: ceil(1% x
    name-days) single positions removed; the two halves and the Feb 15 - Apr 30 2020 removal on the daily rows. -> dict"""
    x, cnt = day_series(nd, p, rows, B.n)
    k = B.mask(lo, hi)
    xs, ds, cs = x[k], B.index[k], cnt[k]
    st = R11.stats(xs, ds) or {}
    tr = xs[cs > 0]
    gw, gl = float(tr[tr > 0].sum()), float(-tr[tr < 0].sum())
    pn = np.asarray(p)[k[rows[nd["i"]]]]
    m = A.ceil_pct(len(pn), RULES["best_pct"])
    nets, npos = A.breadth(xs, ds, years)
    nan = float("nan")
    x20 = ~((ds >= R11.X20[0]) & (ds <= R11.X20[1]))
    return {"name_days": int(cs.sum()), "sessions": int(len(tr)), "net": float(xs.sum()), "years": st.get("years", nan), "max_dd": st.get("max_dd", nan), "roc": st.get("roc", nan),
            "sortino": st.get("sort", nan), "pf": (gw / gl if gl > 0 else float("inf")) if gw > 0 or gl > 0 else nan, "t": A.nw_t(tr) if len(tr) else nan,
            "net_ex_best_days": float(tr.sum()) - float(np.sort(tr)[::-1][:RULES["best_days"]].sum()) if len(tr) else nan,
            "net_ex_best_pct": float(pn.sum()) - float(np.sort(pn)[::-1][:m].sum()) if len(pn) else nan, "best_pct_n": int(m),
            "top_nameday": float(pn.max()) if len(pn) else nan, "net_ex_top_nameday": float(pn.sum()) - float(pn.max()) if len(pn) else nan,
            "years_pos": int(npos), "by_year": nets, "halves": [float(x[B.mask(a, b) & k].sum()) for a, b in HALVES], "net_ex_2020": float(xs[x20].sum())}


def null_stat(acc, B, lo=WF0, hi=PRE_END):
    """the family statistic of every draw: the MAX over the cells of the WF ROC @ $30k of that draw's daily series (MDL's vmeas = r11_risk.stats row by row); NaN where no cell has a drawdown"""
    k = B.mask(lo, hi)
    yrs = (B.index[k][-1] - B.index[k][0]).days / 365.25
    rocs = np.vstack([MDL.vmeas(acc[c][:, k], yrs)["roc"] for c in CELLS])
    return np.fmax.reduce(rocs, axis=0), rocs


def a2_eval(B, x, lo=WF0, hi=PRE_END):
    """[X2] STAGE A2 - a REPORT, not a gate [MANAGER #56]: c is set by VOLATILITY, never picked on returns - the cell's daily P&L std over the first two WF years (2016-07-01 .. 2018-06-29, every #463 index row of them) =
    25% of #463's over the same rows; the book #463 + c x cell on the WF rows against ROC @ $30k >= 98.5005 with Sortino >= 3.816 and a max drawdown <= 1.10 x $44,849 (`book_shadow_line` = all three: it decides only
    whether a forward BOOK shadow line is also opened); 0.5c and 2c are reported. -> dict"""
    kc = B.mask(*C_ROWS)
    sb, sc = float(np.std(B.raw[kc], ddof=1)), float(np.std(x[kc], ddof=1))
    c = C_TARGET * sb / sc if sc > 0 else float("nan")
    k = B.mask(lo, hi)
    out = {"c": c, "std_book": sb, "std_cell": sc, "c_rows": int(kc.sum()), "by_mult": {}}
    for m in (0.5, 1.0, 2.0):
        s = R11.stats((B.raw + m * c * x)[k], B.index[k]) if np.isfinite(c) else None
        out["by_mult"][f"{m:g}"] = {"c": m * c, "roc": s["roc"] if s else float("nan"), "sortino": s["sort"] if s else float("nan"), "net": s["net"] if s else float("nan"),
                                   "max_dd": s["max_dd"] if s else float("nan")}
    b = out["by_mult"]["1"]
    out["checks"] = {f"book ROC@30k>={RULES['a2_roc']:.4f}": bool(b["roc"] >= RULES["a2_roc"]), f"book Sortino>={RULES['a2_sort']:g}": bool(b["sortino"] >= RULES["a2_sort"]),
                     f"book max drawdown<=${RULES['a2_dd']:,.0f}": bool(b["max_dd"] <= RULES["a2_dd"])}
    out["book_roc"], out["book_sortino"], out["book_max_dd"] = b["roc"], b["sortino"], b["max_dd"]
    out["book_shadow_line"] = bool(np.isfinite(c) and all(out["checks"].values()))
    return out


def judge_a(e, p_null, audit_ok):
    """STAGE A (a)-(h) for one cell on one reading, plus the BETA-ADJUSTED TWIN VETO [TV X4]; e = evaluate()'s dict for the cell (base, stress, mirror, twin, twin_stress); p_null = the null's percentile that (c) reads
    (the 97.5th, [TV X3]); NaN never passes. The costs: every check reads the base costs except (e) and the twin's stress check ([COSTS clarified])"""
    R, c = RULES, e["base"]["stats"]
    mirror_roc, stress_net = e["mirror"]["stats"]["roc"], e["stress"]["stats"]["net"]
    tw, tws = e["twin"]["stats"], e["twin_stress"]["stats"]
    return {f"(a) traded sessions>={R['sessions']}": c["sessions"] >= R["sessions"], f"(b) ROC@30k>={R['roc']:g}": c["roc"] >= R["roc"], f"(b) PF>={R['pf']:g}": c["pf"] >= R["pf"],
            f"(b) NW t>={R['t']:g}": c["t"] >= R["t"], f"(c) ROC>null p{R['null_pct']:g}": (c["roc"] > p_null) if R["null"] else True, "(d) beats its mirror": (c["roc"] > mirror_roc) if R["mirror"] else True,
            "(e) net>0 at the stress costs": (stress_net > 0) if R["stress"] else True,
            "(f) profitable without its best 5 days": (c["net_ex_best_days"] > 0) if R["exbest"] else True,
            "(f) profitable without its best 1% of name-days": (c["net_ex_best_pct"] > 0) if R["exbest"] else True, f"(g) positive in >={R['years']} of 9 years": c["years_pos"] >= R["years"],
            "(g) both halves positive": all(h > 0 for h in c["halves"]) if R["halves"] else True, "(g) net>0 without Feb 15 - Apr 30 2020": (c["net_ex_2020"] > 0) if R["x2020"] else True,
            "twin net>0 base": (tw["net"] > 0) if R["twin"] else True, "twin net>0 stress": (tws["net"] > 0) if R["twin"] else True,
            "twin ROC >= half the primary's": (tw["roc"] >= R["twin_half"] * c["roc"]) if R["twin"] else True,
            "(h) hand audit complete": bool(audit_ok) if R["audit"] else True}


def core_ok(chk):
    """every check but (h), the hand audit: the cell's Stage A bars as the data decide them"""
    return all(v for k, v in chk.items() if not k.startswith("(h)"))


def verdict_of(chk, chk2, audit_ok):
    """[TV X2] a cell passes Stage A only if BOTH readings pass (chk2 None = the second reading was not triggered); the hand audit is the last word -> (the data's verdict, PASS | PENDING_AUDIT | FAIL)"""
    core = core_ok(chk) and (chk2 is None or core_ok(chk2))
    return core, ("PASS" if core and audit_ok else ("PENDING_AUDIT" if core else "FAIL"))


def pick_cell(cells):
    """the Stage B candidate [MANAGER #56]: of the cells that PASSED Stage A (every bar, both readings, the twin veto, the hand audit complete) the one with the higher WF ROC @ $30k - the leg's own number, not the
    book's (a tie: ALL, the first in CELLS) -> name or None"""
    ok = [c for c in CELLS if cells[c]["stageA"]["PASS"]]
    return max(ok, key=lambda c: (cells[c]["stageA"]["stats"]["roc"], -CELLS.index(c))) if ok else None


# ------------------------------------------------------------------ the hand audit [(h)]
def audit_rows(W, B, rows, nd, p, lo, hi, cell, cal, tbis, n=30, reading="registered"):
    """the n largest single-name P&L contributors of one cell on [lo, hi] (base costs), largest first, with what a hand audit needs: symbols, date, side, $, g, the raw gap, the prices, the split factor
    on t and t-1, the calendar actions filed under the name within 10 days, TBIS's rows within 7 days, and how the symbol map resolved (same ticker or chain, the 09:30 / official open ratio); `reading` says
    which reading's baskets it came from ([TV X2]: registered | slots-left-empty)"""
    k = B.mask(lo, hi)[rows[nd["i"]]]
    idx = np.flatnonzero(k)
    top = idx[np.argsort(-np.asarray(p)[idx], kind="stable")][:n]
    comp = alias_components(cal)
    out = []
    for r, j in enumerate(top, 1):
        i, x = int(nd["i"][j]), int(nd["x"][j])
        tk, sy, d = str(W.tick[x]), sym_of(W, i, x), W.days[i]
        al = set(comp.get(tk, (tk,))) | ({sy} if sy else set())
        near = []
        if cal is not None and len(cal):
            m = cal["ev"].notna() & ((cal["ev"] - d).abs() <= pd.Timedelta(days=10)) & (cal["symbol"].isin(al) | cal["old_symbol"].isin(al) | cal["new_symbol"].isin(al))
            near = [f"{a.type} {a.ev:%Y-%m-%d} rate={a.rate or '-'} {a.old_rate or '-'}->{a.new_rate or '-'}" for a in cal[m].itertuples()]
        tn = []
        if tbis is not None and len(tbis):
            m = tbis["symbol"].isin(al) & ((tbis["day"] - d).abs() <= pd.Timedelta(days=7))
            tn = [f"{a.day:%Y-%m-%d} split_like={a.split_like} price_ratio={a.price_ratio} vol_ratio={a.vol_ratio}" for a in tbis[m].itertuples()]
        out.append({"cell": cell, "reading": reading, "rank": r, "symbol": tk, "siporb_symbol": sy, "date": f"{d:%Y-%m-%d}", "side": "long" if nd["side"][j] > 0 else "short", "pnl": float(p[j]), "g": float(nd["g"][j]),
                    "raw_gap": float(nd["gap"][j]), "fill_0935": float(nd["o"][j]), "official_open": float(W.Od[i, x]), "prior_close": float(W.Cl_prev[i, x]), "close": float(nd["c"][j]),
                    "factor_t": float(W.F[i, x]), "factor_t_1": float(W.F_prev[i, x]), "map": "same ticker" if sy == tk else ("chain" if sy else "none"),
                    "open_0930_over_official": float(W.o930[i, x] / W.Od[i, x]) if np.isfinite(W.Od[i, x]) else float("nan"), "calendar_near": " | ".join(near), "tbis_near": " | ".join(tn)})
    return out


def merge_candidates(c1, c2):
    """[TV X2] when the second reading is computed, ITS 30 largest name-day gains need a verdict too (the names that step in or drop out change the winners): per cell the registered reading's rows, then the second
    reading's rows that are not already among them; a name-day in both readings is marked 'both' -> {cell: rows}"""
    out = {}
    for cell in CELLS:
        rows = [dict(r) for r in c1.get(cell, ())]
        at = {(r["symbol"], r["date"]): r for r in rows}
        for r in c2.get(cell, ()):
            k = (r["symbol"], r["date"])
            if k in at:
                at[k]["reading"] = "both"
            else:
                rows.append(dict(r))
        out[cell] = rows
    return out


AUDIT_COLS = ("cell", "reading", "rank", "symbol", "siporb_symbol", "date", "side", "pnl", "g", "raw_gap", "fill_0935", "official_open", "prior_close", "close", "factor_t", "factor_t_1", "map",
              "open_0930_over_official", "calendar_near", "tbis_near")


def write_candidates(rows_by_cell, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(AUDIT_COLS)
        for cell in CELLS:
            for r in rows_by_cell.get(cell, ()):
                w.writerow([r[c] for c in AUDIT_COLS])


def read_audit(path, cut=None):
    """OUT\\xgap_audit.csv (symbol, date, cell, verdict keep | data_event, note) -> (rows, removed {(symbol, date)}); optional: no file = no rows. A bad verdict / cell / date, a date on/after the cut or two
    different verdicts for one (symbol, date, cell) is a refusal. A data_event removes that name-day from the universe - cells AND null (CHOICE: whichever cell it was listed under, a bad print is bad for both)"""
    if not os.path.exists(path):
        return [], set()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in ("symbol", "date", "cell", "verdict"):
        if c not in df.columns:
            refuse(f"refused: {os.path.basename(path)} has no column {c} (nothing computed)")
    rows, seen = [], {}
    for r in df.itertuples():
        v, cell = r.verdict.strip().lower(), r.cell.strip().upper()
        d = pd.to_datetime(r.date, errors="coerce")
        if v not in ("keep", "data_event") or cell not in CELLS or pd.isna(d) or not r.symbol.strip():
            refuse(f"refused: {os.path.basename(path)} line {r.Index + 2}: needs symbol, a date, cell ALL | CAP8 and verdict keep | data_event (got {r.symbol!r} {r.date!r} {r.cell!r} {r.verdict!r}) (nothing computed)")
        key = (r.symbol.strip(), d, cell)
        if key in seen and seen[key] != v:
            refuse(f"refused: {os.path.basename(path)} gives two verdicts for {key[0]} {d:%Y-%m-%d} {cell} (nothing computed)")
        seen[key] = v
        rows.append({"symbol": key[0], "date": d, "cell": cell, "verdict": v, "note": getattr(r, "note", "")})
    if cut is not None and rows:
        A.assert_cut("audit file", pd.DatetimeIndex([r["date"] for r in rows]), cut)
    return rows, {(r["symbol"], r["date"]) for r in rows if r["verdict"] == "data_event"}


def audit_status(cands, rows):
    """per cell: the audit is complete when every one of the cell's candidates (matched by its ticker or its SIPORB symbol, and the date) has a verdict row for THAT cell -> ({cell: bool}, {cell: [missing]})"""
    have = {(r["symbol"], r["date"].strftime("%Y-%m-%d"), r["cell"]) for r in rows}
    ok, miss = {}, {}
    for cell in CELLS:
        m = [f"{c['symbol']} {c['date']}" for c in cands.get(cell, ()) if (c["symbol"], c["date"], cell) not in have and (c["siporb_symbol"], c["date"], cell) not in have]
        ok[cell], miss[cell] = bool(cands.get(cell)) and not m, m
    return ok, miss


# ------------------------------------------------------------------ ES (the beta report) - r13_attn's NQ loader with ES in place of NQ
def load_es(t_end):
    """the ES 5m RTH masters (roll-corrected for price changes, unadjusted for levels) -> ({'raw': df, 'adj': df} of open / close on the tz-aware bar-START index, their registry rows), cut to bars BEFORE t_end
    and asserted so; the same registry calls as r13_attn.load_nq (it hard-codes NQ, so this mirrors it)"""
    data = A.data_mod()
    cut = TS(t_end).tz_localize("US/Eastern")
    d1 = str((TS(t_end) - pd.Timedelta(days=1)).date())
    out, meta = {}, {}
    for tag, src in (("raw", SRC_RAW), ("adj", SRC_ADJ)):
        m = data.find_master("ES", "5m", "rth", src)
        if m is None or m.get("source") != src:
            raise RuntimeError(f"no {src} ES 5m RTH master in the registry")
        a = data.load_master_arrays(m, ES_D0, d1)
        ix = pd.DatetimeIndex(a["index"])
        keep = np.asarray(ix < cut)
        df = pd.DataFrame({kk: np.asarray(a[kk], float)[keep] for kk in ("open", "close")}, index=ix[keep])
        if not len(df):
            raise RuntimeError(f"the {src} ES master has no bar before the cut")
        A.assert_cut(f"ES {src}", df.index, cut)
        out[tag], meta[tag] = df, {kk: m.get(kk) for kk in ("id", "source", "filename")}
    return out, meta


def es_returns(days, es):
    """the ES daily returns on the session grid: cc = (the roll-corrected 16:00 print's change from the previous session) / the previous session's UNADJUSTED 16:00 print (the prereg's daily return);
    oc = (16:00 minus the 09:30 open, roll-corrected) / the previous unadjusted 16:00 print (CHOICE: the part of the day the basket is exposed to). NaN where a print is missing"""
    pr = A.hedge_prints(es).reindex(days)
    c_adj, o_adj, c_raw = (pr[k].to_numpy(float) for k in ("c_adj", "o_adj", "c_raw"))
    cc, oc = np.full(len(days), np.nan), np.full(len(days), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        cc[1:] = (c_adj[1:] - c_adj[:-1]) / c_raw[:-1]
        oc[1:] = (c_adj[1:] - o_adj[1:]) / c_raw[:-1]
    return cc, oc


def ols(y, x):
    """OLS slope of y on x (+ the correlation and n) over the rows where both are finite; NaN under 3 rows or no spread in x"""
    y, x = np.asarray(y, float), np.asarray(x, float)
    ok = np.isfinite(y) & np.isfinite(x)
    n = int(ok.sum())
    nan = float("nan")
    if n < 3 or not np.ptp(x[ok]) > 0:
        return {"n": n, "slope": nan, "per_1pct": nan, "corr": nan}
    xm, ym = x[ok] - x[ok].mean(), y[ok] - y[ok].mean()
    b = float(xm @ ym / (xm @ xm))
    r = float(np.corrcoef(x[ok], y[ok])[0, 1]) if np.ptp(y[ok]) > 0 else nan
    return {"n": n, "slope": b, "per_1pct": b / 100.0, "corr": r}


def es_beta(B, x, rows, cc, oc, lo=WF0, hi=PRE_END):
    """the realised beta of a cell's daily P&L ($) to ES (OLS on the ES daily return; $ per +1% ES): #463's drawdown weeks FIRST (the ISO weeks with >= 3 days in a qualifying drawdown, MDL r1), its
    qualifying drawdown days, then every WF row; both ES definitions (es_returns)"""
    St = MDL.Stretch(np.asarray(B.raw, float), B.index, None, lo, hi)
    es_row = {"cc": np.full(B.n, np.nan), "oc": np.full(B.n, np.nan)}
    es_row["cc"][rows], es_row["oc"][rows] = cc, oc
    sets = {"dd_weeks": St.rows[St.wk_rows], "dd_days": St.rows[St.dd], "all_wf_rows": St.rows}
    return {sname: {kind: ols(x[r], es_row[kind][r]) for kind in ("cc", "oc")} for sname, r in sets.items()}


def map_point(B, x, c, lo=WF0, hi=PRE_END):
    """the cell's place on the MDL r1 map: standalone ROC @ $30k, rho_dd and DO against #463's own drawdown weeks (r12_mdl.Stretch / realised, exactly as MDL r1; the unit-size leg, c = 1), and the bins"""
    St = MDL.Stretch(np.asarray(B.raw, float), B.index, None, lo, hi)
    r = St.rows
    alone = MDL.pstats(np.asarray(x)[r], St.dates)
    rho, do = MDL.realised(np.asarray(x)[r][None, :], St)
    return {"roc": alone["roc"], "net_per_year": alone["net_per_year"], "max_dd": alone["max_dd"], "rho_dd": float(rho[0]), "do": float(do[0]), "do_at_c": float(do[0]) * c,
            "dd_days": int(St.n_dd_days), "dd_weeks": int(St.n_dd_weeks),
            "roc_bin": MDL.ROC_LABELS[int(MDL.roc_bin(alone["roc"]))] if np.isfinite(alone["roc"]) else None,
            "rho_bin": MDL.RHO_LABELS[int(MDL.rho_bin(rho[0]))] if np.isfinite(rho[0]) else None}


def by_side(nd, p, k_in):
    out = {}
    for s, nm in ((1.0, "long"), (-1.0, "short")):
        m = k_in & (nd["side"] == s)
        n = int(m.sum())
        out[nm] = {"n": n, "net": float(p[m].sum()), "mean_bps": float(1e4 * np.mean(p[m] / SLOT)) if n else float("nan"), "share_pos": float(np.mean(p[m] > 0)) if n else float("nan")}
    return out


def bucket_masks(ag):
    """P&L by |g| bucket (the prereg's 0-2, 2-4, 4-8, > 8%): [0, 2%), [2%, 4%), [4%, 8%], (8%, inf) - CAP8's edge (|g| <= 8%) closes the third bucket"""
    ag = np.asarray(ag, float)
    return {"0-2%": ag < 0.02, "2-4%": (ag >= 0.02) & (ag < 0.04), "4-8%": (ag >= 0.04) & (ag <= CAP + 1e-12), ">8%": ag > CAP + 1e-12}


def by_bucket(nd, p, k_in):
    out = {}
    for nm, bm in bucket_masks(np.abs(nd["g"])).items():
        m = k_in & bm
        n = int(m.sum())
        out[nm] = {"n": n, "net": float(p[m].sum()), "mean_bps": float(1e4 * np.mean(p[m] / SLOT)) if n else float("nan")}
    return out


def top_gains(W, nd, p, k_in, n=20):
    idx = np.flatnonzero(k_in)
    top = idx[np.argsort(-np.asarray(p)[idx], kind="stable")][:n]
    return [{"date": f"{W.days[int(nd['i'][j])]:%Y-%m-%d}", "symbol": str(W.tick[int(nd['x'][j])]), "side": "long" if nd["side"][j] > 0 else "short", "pnl": float(p[j]), "g": float(nd["g"][j])} for j in top]


# ------------------------------------------------------------------ [TV X2] the identity drops against the signal, [TV X5] dividend payers, [TV X6] the ex-earnings reading
def _rate(a):
    return a[1] / a[0] if a[0] else float("nan")


def _ratio(tail, rest):
    """the tail's drop rate over the rest's: infinite when the rest never drops and the tail does, NaN when neither can be read"""
    rt, rr = _rate(tail), _rate(rest)
    if not (math.isfinite(rt) and math.isfinite(rr)):
        return float("nan")
    return (rt / rr) if rr > 0 else (float("inf") if rt > 0 else float("nan"))


def x2_rates(W, Uw, i0, hi=PRE_END, k=NPOS):
    """[TV X2] the identity drops against the signal, on the sessions from row i0 through `hi` - counts and rates only. The population is the WOULD-BE members: every name-day that passes every rule but the identity
    check (Uw.elig, the waived world); each is `dropped` when the check dropped it (W.idfail). g = the split-safe raw gap from SIPORB's official prices minus the median over that population (the dropped names
    included; the prereg's 'g from SIPORB's official prices'). Buckets: |g| 0-2 / 2-4 / 4-8 / > 8% by side (g < 0 a long candidate, else a short one). The tails: the drop rate of the names that would rank among the
    k most negative or the k most positive g - in the ALL pool (every would-be member) and in the CAP8 pool (|g| <= 8%) - against the rest of that pool. triggered: a ratio above RULES['x2_ratio'] (1.5) in EITHER pool
    (CHOICE: the more careful reading of 'the names that would rank among the 10 most negative or 10 most positive g'; the ALL pool's ratio alone is stored too)"""
    Wd, idf = W.waived, W.idfail
    last = int(W.days.searchsorted(hi, side="right"))
    bk = {b: {"long": [0, 0], "short": [0, 0]} for b in ("0-2%", "2-4%", "4-8%", ">8%")}
    tl = {c: {"tail": [0, 0], "rest": [0, 0]} for c in CELLS}
    ns = nn = nd = 0
    for i in range(i0, last):
        e = np.flatnonzero(Uw.elig[i])
        if not len(e):
            continue
        ns += 1
        gap = Wd.gap[i]
        g = gap - float(np.median(gap[e]))
        dr = idf[i]
        ge, de = g[e], dr[e]
        lg = ge < 0
        for b, m in bucket_masks(np.abs(ge)).items():
            for side, sm in (("long", lg), ("short", ~lg)):
                sel = m & sm
                bk[b][side][0] += int(sel.sum())
                bk[b][side][1] += int(de[sel].sum())
        nn += len(e)
        nd += int(de.sum())
        for c in CELLS:
            pool = e if c == "ALL" else e[np.abs(g[e]) <= CAP + 1e-12]
            if len(pool) < 2 * k:
                continue
            o = pool[np.lexsort((pool, g[pool]))]
            dt, dp = int(dr[np.concatenate([o[:k], o[-k:]])].sum()), int(dr[pool].sum())
            tl[c]["tail"][0] += 2 * k
            tl[c]["tail"][1] += dt
            tl[c]["rest"][0] += len(pool) - 2 * k
            tl[c]["rest"][1] += dp - dt
    fmt = lambda a: {"n": int(a[0]), "dropped": int(a[1]), "rate": _rate(a)}
    tails = {c: {"tail": fmt(v["tail"]), "rest": fmt(v["rest"]), "ratio": _ratio(v["tail"], v["rest"])} for c, v in tl.items()}
    thr = RULES["x2_ratio"]
    return {"sessions": ns, "would_be_name_days": nn, "identity_dropped": nd, "rate": nd / nn if nn else float("nan"),
            "by_bucket_side": {b: {s: fmt(a) for s, a in v.items()} for b, v in bk.items()}, "tails": tails, "threshold": thr,
            "ratio_all_pool": tails["ALL"]["ratio"], "triggered": bool(RULES["x2"] and any(t["ratio"] > thr for t in tails.values()))}


def payer_shares(W, U, R, B, rows, lo, hi):
    """[TV X5] the share of dividend payers (a cash dividend per the calendar in the trailing 365 days) among each cell's long and short name-days on [lo, hi], beside the universe's own share and the same from
    2017-06-02 on (the first session whose whole 365-day lookback lies inside the calendar, which starts 2016-06-01). {} without a calendar"""
    if not W.has_calendar:
        return {}
    wf, late = B.mask(lo, hi), W.days >= TS("2017-06-02")
    sh = lambda pay, m: {"n": int(m.sum()), "payers": int(pay[m].sum()), "share": float(pay[m].mean()) if m.any() else float("nan")}
    out = {}
    for cell in CELLS:
        nd = R.nd[("P", cell)]
        k, pay = wf[rows[nd["i"]]], W.payer[nd["i"], nd["x"]]
        lt = late[nd["i"]]
        out[cell] = {"long": sh(pay, k & (nd["side"] > 0)), "short": sh(pay, k & (nd["side"] < 0)), "long_full_lookback": sh(pay, k & lt & (nd["side"] > 0)), "short_full_lookback": sh(pay, k & lt & (nd["side"] < 0))}
    sess = (W.days >= lo) & (W.days <= hi)
    el = U.elig & sess[:, None]
    out["universe"] = {"member_days_eligible": int(el.sum()), "payer_share": float(W.payer[el].mean()) if el.any() else float("nan"),
                       "payer_share_full_lookback": float(W.payer[el & late[:, None]].mean()) if (el & late[:, None]).any() else float("nan")}
    return out


def read_earnings(cut, path=None):
    """[TV X6] tools/data/megacap_earnings.csv (ticker, accepted_et 'YYYY-MM-DD HH:MM' US/Eastern, items) -> DataFrame(ticker, acc, items) of the events accepted BEFORE `cut` (cut at read and asserted), or None when
    the file is not there (a report: its absence is printed, never a refusal)"""
    p = path or EARN_CSV
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    for c in ("ticker", "accepted_et"):
        if c not in df.columns:
            refuse(f"refused: {os.path.basename(p)} has no column {c} (nothing computed)")
    df["acc"] = pd.to_datetime(df["accepted_et"], errors="coerce")
    df = df[df["acc"].notna() & (df["acc"].dt.normalize() < TS(cut))].reset_index(drop=True)
    A.assert_cut("earnings file", df["acc"].dt.normalize(), cut)
    return df[["ticker", "acc"] + (["items"] if "items" in df.columns else [])]


def earn_mask(ev, days, tick, comp):
    """[TV X6] (T, X) bool of the removed name-days: an event accepted AFTER 16:00 ET on day d removes session d+1 (the next session); one accepted before 09:30 removes that same session; CHOICE: one accepted during
    the session (09:30 .. 16:00) removes session d too (the hold covers the release); a day that is not a session reads the next session. An event attaches to every ticker whose alias set holds its ticker (FB / META).
    -> (mask, the tickers it covers (T-independent bool over X))"""
    T, X = len(days), len(tick)
    mask, covered = np.zeros((T, X), bool), np.zeros(X, bool)
    sym2x = defaultdict(list)
    for x, tk in enumerate(tick):
        for s in comp.get(str(tk), (str(tk),)):
            sym2x[s].append(x)
    for t, a in zip(ev["ticker"], ev["acc"]):
        xs = sym2x.get(t, ())
        if not xs:
            continue
        d, hm = a.normalize(), a.hour * 60 + a.minute
        r = int(days.searchsorted(d, side="right" if hm > 960 else "left"))
        for x in xs:
            covered[x] = True
            if r < T:
                mask[r, x] = True
    return mask, covered


# ------------------------------------------------------------------ the stages: inputs, evaluation, Stage A, the sibling rule, Stage B
def prepare(cut, cal, cinfo):
    """every input of one run, each cut to dates < cut when it is read (the calendar `cal` was read first: it refuses the whole run when it is missing) -> SimpleNamespace(D, cut, cal, cinfo, tbis, cache, members)"""
    tb = read_tbis(cut)
    mem = read_members()
    cache = read_cache(cut)
    return SimpleNamespace(D=load_data(cut), cut=cut, cal=cal, cinfo=cinfo, tbis=tb, cache=cache, members=mem)


def siporb_manifest():
    """SIPORB's cache manifest (alpaca_r1\\siporb_cache_manifest.json): its own manifest_sha256 (380b05f2... on 2026-10-05), the daily files' recorded sha256 and whether their sizes still match - recorded with every result"""
    p = os.path.join(S.OUT, "siporb_cache_manifest.json")
    if not os.path.exists(p):
        return {"present": False}
    m = read_json(p)
    kf = m.get("key_files") or {}
    out = {"present": True, "manifest_sha256": m.get("manifest_sha256"), "built": m.get("built")}
    for n in ("daily_raw.parquet", "daily_split.parquet"):
        f = os.path.join(S.CACHE, "siporb", n)
        out[n] = {"sha256": (kf.get(n) or {}).get("sha256"), "size_matches_manifest": bool(os.path.exists(f) and os.path.getsize(f) == (kf.get(n) or {}).get("bytes"))}
    return out


def input_shas(cinfo):
    """the photographs a stage read, recorded with its result and compared by Stage B (a changed input is a different vendor photograph: never mixed)"""
    return {"calendar_csv_sha256": cinfo["csv_sha256"], "calendar_manifest_sha256": cinfo["manifest_sha256"], "calendar_raw_sha256": cinfo.get("raw_sha256"),
            "nqbrd_cache_sha256": sha_file(nq_cache_path()), "tbis_sha256": sha_file(TBIS_QA), "members_sha256": sha_file(MEMBERS_CSV), "siporb_cache": siporb_manifest()}


def book_check_x(B, lo, hi, ref, dd=None):
    """#463 must reproduce its published ROC / Sortino on [lo, hi] (r13_attn.book_check) and, for WF, its deepest drawdown to the dollar ($44,849)"""
    bk = A.book_check(B, lo, hi, ref)
    if dd is not None:
        mdd = float(R11.unified(B, B.raw, lo, hi)["dd"])
        bk.update({"max_dd": mdd, "max_dd_ref": dd})
        bk["ok"] = bool(bk["ok"] and abs(mdd - dd) < 1.0)
    return bk


def evaluate(R, B, rows, lo, hi):
    """every cell's numbers on [lo, hi]: the primary basket at the base costs (stats, name-day P&L p, daily series x), at the stress costs and at SIPORB's cents-per-share costs, the mirror at the base costs, and the
    beta-adjusted twin at the base AND at the stress costs [TV X4]"""
    E = {}
    for cell in CELLS:
        e = {}
        for key, v in (("base", "P"), ("stress", "P"), ("cents", "P"), ("mirror", "M"), ("twin", "T"), ("twin_stress", "T")):
            nd = R.nd[(v, cell)]
            p = name_pnl(nd["side"], nd["o"], nd["c"], COST["stress"] if key.endswith("stress") else COST["base"]) if key != "cents" else cents_pnl(nd["side"], nd["o"], nd["c"])
            e[key] = {"stats": cell_stats(B, nd, p, rows, lo, hi), "p": p}
        e["x"] = day_series(R.nd[("P", cell)], e["base"]["p"], rows, B.n)[0]
        E[cell] = e
    return E


def fmt_row(name, s):
    return (f"{name:<22} name-days {s['name_days']:>6,} sessions {s['sessions']:>5,} net ${s['net']:>11,.0f} ROC@30k {s['roc']:>8.1f} PF {s['pf']:>5.2f} t {s['t']:>5.2f} Sortino {s['sortino']:>6.2f} "
            f"max DD ${s['max_dd']:>9,.0f} years+ {s['years_pos']}")


def ddw_series(B, lo, hi):
    """CHOICE: DDW r1's L2 daily P&L series, when the sibling lane has written them next to its verdict file as <something L2 something>.csv with date, pnl columns -> {name: series on the #463 index}; none = {}"""
    d = os.path.dirname(DDW_STAGE_A)
    out = {}
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith(".csv") and "l2" in fn.lower():
                try:
                    df = pd.read_csv(os.path.join(d, fn))
                    s = pd.Series(df["pnl"].to_numpy(float), index=pd.to_datetime(df["date"])).groupby(level=0).sum()
                    out[fn[:-4]] = s.reindex(B.index).fillna(0.0).to_numpy(float)
                except Exception:
                    continue
    return out


def reports(W, U, R, E, B, rows, legs, lo, hi, esr=None, with_corr=True, hy=None, mps=None, extra=None):
    """the REPORTED paragraph, never a pass route (the twin is a veto now, [TV X4], and is also stored here): the realised beta to ES, the MDL map point, the correlations (#463's legs, DDW r1's L2 when it has written
    series), the long and short sides apart, P&L by |g| bucket, the 20 largest name-day gains, SIPORB's cents row, the mirror, the stress row, the beta-adjusted twin and its verdict on the primary, the hygiene counts;
    `extra` = the X2 identity-drop rates, the dividend-payer shares, the ex-earnings reading, the sibling line"""
    rep = {"hygiene": hy if hy is not None else hygiene(W, U), "es_beta": esr, "cells": {}}
    ddw = ddw_series(B, lo, hi) if with_corr else {}
    for cell in CELLS:
        e, nd = E[cell], R.nd[("P", cell)]
        k_in = B.mask(lo, hi)[rows[nd["i"]]]
        s = e["base"]["stats"]
        c = {"sides": by_side(nd, e["base"]["p"], k_in), "buckets": by_bucket(nd, e["base"]["p"], k_in), "top_gains": top_gains(W, nd, e["base"]["p"], k_in), "stress": e["stress"]["stats"],
             "cents": e["cents"]["stats"], "mirror": e["mirror"]["stats"], "twin": e["twin"]["stats"], "twin_stress": e["twin_stress"]["stats"]}
        tw = e["twin"]["stats"]
        c["twin_contradicts_primary"] = bool((not tw["net"] > 0) or (tw["roc"] < RULES["twin_half"] * s["roc"])) if np.isfinite(s["roc"]) and s["roc"] > 0 else None
        if with_corr and lo == WF0:
            c["map_point"] = mps[cell] if mps else map_point(B, e["x"], 1.0)
            c["corr_daily"] = A.corrs(B, e["x"], legs, lo, hi)
            if ddw:
                with np.errstate(invalid="ignore"):
                    c["corr_ddw_l2"] = {n: float(np.corrcoef(e["x"][B.mask(lo, hi)], y[B.mask(lo, hi)])[0, 1]) for n, y in ddw.items()}
        rep["cells"][cell] = c
    rep.update(extra or {})
    return rep


def print_cell(cell, E, chk, verdict, E2=None, chk2=None):
    e = E[cell]
    print(f"  {cell}: " + fmt_row("primary (10+5 bps)", e["base"]["stats"]).strip())
    for key, lab in (("mirror", "mirror"), ("stress", "stress 20+10 bps"), ("cents", "SIPORB cents (report)"), ("twin", "beta twin (base)"), ("twin_stress", "beta twin (stress)")):
        s = e[key]["stats"]
        print(f"        {lab:<22} name-days {s['name_days']:>6,} net ${s['net']:>11,.0f} ROC@30k {s['roc']:>8.1f}")
    print("        checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()))
    if E2 is not None:
        print("        slots-left-empty reading [TV X2]: " + fmt_row("primary", E2[cell]["base"]["stats"]).strip())
        print("          checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk2.items()))
    print(f"        -> {verdict}")


def print_hygiene(H, with_calendar=True):
    """the exclusions by reason (first failing rule) and year, the eligible count and the member-days, the no-data (survivorship) line, the TBIS flag under both windows - from hygiene(): counts only (the
    calendar-vs-price comparison only when a calendar is on file)"""
    print("exclusions by reason (first failing rule; member-days) by year:")
    ys = sorted(H["member_days_by_year"])
    print("  reason".ljust(14) + "".join(f"{y:>9}" for y in ys))
    for name in WHY[1:]:
        row = H["excluded_first_rule_by_year"][name]
        print("  " + name.ljust(12) + "".join(f"{row.get(y, 0):>9,}" for y in ys))
    print("  eligible".ljust(14) + "".join(f"{H['eligible_by_year'].get(y, 0):>9,}" for y in ys))
    print("  member-days".ljust(14) + "".join(f"{H['member_days_by_year'].get(y, 0):>9,}" for y in ys))
    mp = H["symbol_map_by_year"]
    print("no-data (survivorship) drops by year [NOISE H3] - member-days with no SIPORB bar at all after the rename chain (mostly delisted or acquired names); NOT counted in the 2% rule: "
          + ", ".join(f"{y}: {v['no_data']:,} ({v['no_data_share']:.1%})" for y, v in mp.items() if v["member_days"]))
    cv = H["calendar_vs_price"]
    if with_calendar:
        if H.get("chain_recovery"):
            print_chain_recovery(H["chain_recovery"])
        print_exdiv(H)
        print("calendar vs price rules (name-days): calendar split events " + str(cv["calendar_split_events"]) + "; of them with no price rule within a session: " + str(cv["calendar_only"]))
        print("  price-rule events " + str(cv["price_rule_events"]) + "; of them with no calendar split within a session: " + str(cv["price_only"]))
    tb = H["tbis"]
    print("TBIS volume-confirmed flag [NOISE H1] - removals by year under the registered window t-5 .. t-1: " + str(tb["registered_t5_to_t1_removals"]) + "; under the draft's t-5 .. t: " + str(tb["through_t_removals"])
          + "; removed only by a flag dated t itself: " + str(tb["removed_only_by_a_flag_dated_t"]))


def print_chain_recovery(cr):
    """the calendar's name-change chain in the symbol map: member-days with no SIPORB bar under the same-ticker map alone -> after the chain, what it recovers and rescues - counts and shares only"""
    print("symbol map through the name-change chain [X1] - member-days with no SIPORB bar, the same ticker alone -> after the calendar's chain; the chain recovers a member-day when a chain symbol has an official open; "
          "rescued = the ticker's own bar fails the identity check and a chain symbol passes:")
    for y, v in cr["by_year"].items():
        n = v["member_days"]
        print(f"  {y}: {v['no_data_same_ticker']:,} ({v['no_data_same_ticker'] / n:.1%}) -> {v['no_data_after_chain']:,} ({v['no_data_after_chain'] / n:.1%}); recovered {v['recovered']:,} "
              f"({v['recovered'] / n:.2%} of member-days), {v['recovered_identity_ok']:,} of them pass the identity check; rescued from an identity drop {v['rescued_from_identity_drop']:,}")
    for key, what in (("tickers_recovered", "member-days recovered from no-data by the chain"), ("tickers_rescued", "member-days rescued from an identity drop by the chain"),
                      ("tickers_no_data_after_chain", "member-days still without a SIPORB bar after the chain (the survivorship; all years)")):
        t = cr[key]
        print(f"  tickers with {what}: " + (", ".join(f"{k} {n:,}" for k, n in sorted(t.items(), key=lambda kv: (-kv[1], kv[0]))[:15]) + (f" (and {len(t) - 15} more)" if len(t) > 15 else "") if t else "none"))


def print_exdiv(H):
    """the ex-dividend exclusion [X1] by year: dropped on this rule first, the ex-date flag fired whatever else dropped the name-day (with its share of the member-days), and the flag by type - counts only"""
    ys = sorted(H["member_days_by_year"])
    f, a, md = H["excluded_first_rule_by_year"]["ex_div"], H["excluded_any_rule_by_year"]["ex_div"], H["member_days_by_year"]
    print("ex-dividend exclusions [X1] (member-days) by year - dropped on this rule first: " + ", ".join(f"{y}: {f.get(y, 0):,}" for y in ys)
          + "; the ex-date flag fired, whatever else dropped the name-day: " + ", ".join(f"{y}: {a.get(y, 0):,} ({a.get(y, 0) / md[y]:.1%})" for y in ys if md.get(y)))
    bt = H.get("ex_div_by_type")
    if bt:
        print("  the ex-date flag fired, by type: " + "; ".join(f"{t} " + ", ".join(f"{y}: {v.get(y, 0):,}" for y in ys) + f" (total {sum(v.values()):,})" for t, v in bt.items()))


def print_share_class(info):
    """[TV X1] the share-class members (own ticker only), the detector's finds, the refused cross-class mappings - counts only"""
    if not info:
        return
    print("share-class members [TV X1] - each maps to its OWN ticker in both pulls, never across classes: " + (", ".join("/".join(g) for g in info["groups"]) or "none"))
    print(f"  the addendum's list: {len(info['explicit_names_on_file'])} names on file; families with no member on file: " + (", ".join("/".join(f) for f in info["explicit_families_with_no_member"]) or "none")
          + "; pairs the detector added beyond the list: " + (", ".join("/".join(p) for p in info["detected_beyond_the_list"]) or "none")
          + f"; other shared-root pairs found and NOT taken (the last letter is not a class letter in {info['class_letters']}): " + (", ".join("/".join(p) for p in info["shared_root_not_taken"]) or "none"))
    rf = info["refused_cross_class_name_days"]
    tot = sum(r["name_days"] for r in rf)
    print(f"  refused cross-class mappings: {tot:,} name-days where a calendar-chain symbol would have passed the identity check but the member maps to its own ticker only"
          + (" - " + "; ".join(f"{r['ticker']} -> {r['symbol']} {r['year']}: {r['name_days']:,}" for r in rf[:12]) if rf else "") + f"; name-change edges not followed for class members: {len(info['chain_edges_refused'])}"
          + (" (" + ", ".join(f"{a} -> {b}" for a, b in info["chain_edges_refused"][:12]) + ")" if info["chain_edges_refused"] else ""))


def print_x2(x2):
    """[TV X2] the identity drops against the signal - rates and counts only"""
    print(f"[TV X2] identity drops against the signal ({x2['sessions']:,} WF sessions; {x2['identity_dropped']:,} of {x2['would_be_name_days']:,} would-be member-days dropped = {x2['rate']:.2%}); "
          "would-be = every rule but the identity check passes, g from SIPORB's official prices:")
    print("  by |g| bucket and side - dropped / would-be (rate):")
    for b, v in x2["by_bucket_side"].items():
        print(f"    {b:>5}: long {v['long']['dropped']:>5,} / {v['long']['n']:>8,} ({v['long']['rate']:.2%})   short {v['short']['dropped']:>5,} / {v['short']['n']:>8,} ({v['short']['rate']:.2%})")
    for c in CELLS:
        t = x2["tails"][c]
        r = t["ratio"]
        rt = "inf" if r == float("inf") else ("n/a" if not math.isfinite(r) else f"{r:.2f}")
        print(f"  the names that would rank among the {NPOS} most negative or {NPOS} most positive g, {c} pool: dropped {t['tail']['dropped']:,} of {t['tail']['n']:,} ({t['tail']['rate']:.2%}) vs the rest "
              f"{t['rest']['dropped']:,} of {t['rest']['n']:,} ({t['rest']['rate']:.2%}) -> ratio {rt} (threshold {x2['threshold']:g})")
    print("  " + ("TRIGGERED - Stage A is computed a second time with each dropped top / bottom-10 name's slot left EMPTY (its side trades fewer names, the same dollars a name), cells and null alike; a cell passes only if both readings pass"
                  if x2["triggered"] else ("not triggered (no ratio above the threshold)" if RULES["x2"] else "switched off") + ": the registered reading alone"))


def null_summary(R, B):
    """the random-pick null of one reading: the max over the cells of each draw's WF ROC @ $30k - its median, 95th and 97.5th percentiles; check (c) reads the 97.5th [TV X3] (Bonferroni for the two families that
    tested the gap-reversal hypothesis), the 95th stays beside it -> (dict, the finite draws)"""
    maxroc, rocs = null_stat(R.acc, B)
    fin = maxroc[np.isfinite(maxroc)]
    pct = lambda q: float(np.percentile(fin, q)) if len(fin) else float("nan")
    return ({"draws": NREP, "seed": SEED, "finite": int(len(fin)), "p50": pct(50), "p95": pct(95), "p97_5": pct(97.5), "pct_used": RULES["null_pct"], "p_used": pct(RULES["null_pct"]),
             "mean": float(fin.mean()) if len(fin) else float("nan"), "statistic": "max over the 2 cells of WF ROC @ $30k",
             "cells_p95": {c: float(np.nanpercentile(rocs[j], 95)) if np.isfinite(rocs[j]).any() else float("nan") for j, c in enumerate(CELLS)}}, fin)


def earn_reading(W, U, B, rows, i0, ev):
    """[TV X6] the ex-earnings reading - REPORT ONLY, never judged ([MANAGER #57]: the file covers mega caps only, so CAP8 stays the judged cell): the sessions an EARN r1 release removes (earn_mask) leave the universe, both
    cells run again at the base costs, coverage printed. No null: nothing here is a pass route (a null would lose the same pool, [NOISE H4])"""
    mask, covered = earn_mask(ev, W.days, W.tick, W.comp)
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    mem = W.member & wf[:, None]
    Ue = SimpleNamespace(why=U.why, elig=U.elig & ~mask)
    Re = run_cells(W, Ue, rows, B.n, i0, 0, twin=False)
    cells = {}
    for cell in CELLS:
        nd = Re.nd[("P", cell)]
        cells[cell] = cell_stats(B, nd, name_pnl(nd["side"], nd["o"], nd["c"], COST["base"]), rows, WF0, PRE_END)
    n_mem = int(mem.sum())
    cov = {"events_before_the_cut": int(len(ev)), "tickers_in_file": sorted(set(ev["ticker"])), "member_tickers_covered": sorted(str(t) for t in W.tick[covered]), "first_event": f"{ev['acc'].min():%Y-%m-%d}" if len(ev) else None,
           "last_event": f"{ev['acc'].max():%Y-%m-%d}" if len(ev) else None, "wf_member_days": n_mem, "wf_member_days_covered": int((mem & covered[None, :]).sum()),
           "share_of_member_days_covered": float((mem & covered[None, :]).sum()) / n_mem if n_mem else float("nan"), "wf_eligible_name_days_removed": int((U.elig & mask & wf[:, None]).sum())}
    return {"coverage": cov, "cells": cells, "note": "REPORT ONLY, never judged: a release accepted after 16:00 ET on day d removes session d+1, one before 09:30 removes that session, one during the session removes it too (CHOICE)"}


def stage_a():
    if os.path.exists(os.path.join(OUT, FLAG_FILE)):                                       # CHOICE: once the lockbox has been read Stage A is frozen (a re-run could change the verdict after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({FLAG_FILE})")
    pok = prereg_ok()
    cal, cinfo = load_calendar(CUT_A)                                                      # [X1]: refuses (nothing computed) without the calendar, or when its sha256 differs from its manifest
    print(f"calendar: {cinfo['rows_read']:,} rows read (by type: " + ", ".join(f"{k} {v:,}" for k, v in sorted(cinfo['rows_by_type'].items())) + f"), csv sha256 {cinfo['csv_sha256'][:12]}..., raw sha256 "
          f"{(cinfo.get('raw_sha256') or '')[:12]}... - both are the files the prereg pins [MANAGER #58]")
    B, legs = A.load_463()                                                                 # the book first: cheap, and a book that does not reproduce stops everything
    bk = book_check_x(B, WF0, PRE_END, BOOK_WF, BOOK_DD)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]} / ${BOOK_DD:,.0f}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f} deepest drawdown ${bk['max_dd']:,.0f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage A refused: the #463 records do not reproduce its WF numbers - fix the input first (nothing computed)")
    audit_path = os.path.join(OUT, "xgap_audit.csv")
    arows, removed = read_audit(audit_path, CUT_A)
    t0 = time.time()
    P = prepare(CUT_A, cal, cinfo)                                                         # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    inputs = input_shas(cinfo)
    W = assemble(P, removed)
    U, Uw = universe(W), universe(W.waived)                                                # the registered universe; the would-be universe (every rule but the identity check) for [TV X2]
    days = P.D.days
    rows = A.book_rows(B, P.D)
    i0 = int(days.searchsorted(WF0))
    hy = hygiene(W, U)
    print(f"universe: {int(U.elig[i0:].sum()):,} eligible member-days over {len(days) - i0:,} sessions from {WF0:%Y-%m-%d}; the identity check (max(1 cent, 0.10%) of the official open) dropped "
          + ", ".join(f"{y}: {v['share']:.2%}" for y, v in hy["symbol_map_by_year"].items() if v["member_days"]) + (f" (years over {MAP_YEAR_MAX:.0%}: {hy['map_years_over_2pct']})" if hy["map_years_over_2pct"] else " (no year over 2%)"))
    print_hygiene(hy)
    print_share_class(hy["share_class"])
    x2 = x2_rates(W, Uw, i0)
    print_x2(x2)
    twc = twin_coverage(W, U, i0)
    print_twin_coverage(twc)
    print(f"hand audit: {len(arows)} verdict rows on file, {len(removed)} data events removed from the universe (cells AND null)")
    R = run_cells(W, U, rows, B.n, i0, NREP, SEED)
    E = evaluate(R, B, rows, WF0, PRE_END)
    null, fin = null_summary(R, B)
    R2 = E2 = null2 = fin2 = None
    if x2["triggered"]:
        R2 = run_cells(W.waived, Uw, rows, B.n, i0, NREP, SEED, untrade=Uw.elig & W.idfail)   # [TV X2]: the dropped names stay in the ranking and the pool, their slots stay EMPTY (cells and null alike)
        E2 = evaluate(R2, B, rows, WF0, PRE_END)
        null2, fin2 = null_summary(R2, B)
    print(f"baskets + {NREP} null draws done" + (" twice (the slots-left-empty reading too)" if E2 else "") + f" ({time.time() - t0:.0f}s)", flush=True)
    cands = {c: audit_rows(W, B, rows, R.nd[("P", c)], E[c]["base"]["p"], WF0, PRE_END, c, cal, P.tbis) for c in CELLS}
    if E2:                                                                                 # [TV X2] the second reading's winners are audited too
        cands2 = {c: audit_rows(W.waived, B, rows, R2.nd[("P", c)], E2[c]["base"]["p"], WF0, PRE_END, c, cal, P.tbis, reading="slots-left-empty") for c in CELLS}
        cands = merge_candidates(cands, cands2)
    os.makedirs(OUT, exist_ok=True)
    write_candidates(cands, os.path.join(OUT, "xgap_audit_candidates.csv"))
    aok, amiss = audit_status(cands, arows)
    cells, chks, chks2 = {}, {}, {}
    for cell in CELLS:
        e = E[cell]
        chk = chks[cell] = judge_a(e, null["p_used"], aok[cell])
        chk2 = chks2[cell] = judge_a(E2[cell], null2["p_used"], aok[cell]) if E2 else None
        core, verdict = verdict_of(chk, chk2, aok[cell])                                   # a cell passes only if BOTH readings pass [TV X2]
        slot = None
        if E2:
            e2 = E2[cell]
            slot = {"stats": e2["base"]["stats"], "mirror": e2["mirror"]["stats"], "stress": e2["stress"]["stats"], "twin": e2["twin"]["stats"], "twin_stress": e2["twin_stress"]["stats"], "checks": chk2,
                    "core_ok": core_ok(chk2), "null_real_percentile": float(np.mean(fin2 < e2["base"]["stats"]["roc"]) * 100) if len(fin2) else float("nan")}
        cells[cell] = {"stageA": {"stats": e["base"]["stats"], "mirror": e["mirror"]["stats"], "stress": e["stress"]["stats"], "twin": e["twin"]["stats"], "twin_stress": e["twin_stress"]["stats"],
                                  "checks": chk, "core_ok": core_ok(chk), "PASS": bool(core and aok[cell]), "verdict": verdict, "slot_empty": slot},
                       "A2": a2_eval(B, e["x"]), "null_real_percentile": float(np.mean(fin < e["base"]["stats"]["roc"]) * 100) if len(fin) else float("nan")}
    best = pick_cell(cells)                                                                # [MANAGER #56]: the Stage B candidate is decided by Stage A alone (the higher WF ROC when both pass)
    judged = all(cells[c]["stageA"]["verdict"] != "PENDING_AUDIT" for c in CELLS)
    mps = {c: map_point(B, E[c]["x"], 1.0) for c in CELLS}
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int((days[i0:] <= PRE_END).sum()):,} sessions)")
    for cell in CELLS:
        print_cell(cell, E, chks[cell], cells[cell]["stageA"]["verdict"], E2, chks2[cell])
        mp = mps[cell]
        print(f"        power line (MDL map): standalone ROC @ $30k {mp['roc']:.1f} (bin {mp['roc_bin']}), rho_dd {mp['rho_dd']:+.2f}, DO {mp['do']:+.2f} - at rho_dd near 0 a leg near 15 lifts #463 about half the time, near 30 four times in five")
        a = cells[cell]["A2"]
        print(f"        A2 REPORT (not a gate - [MANAGER #56]): c = {a['c']:.4f} (daily std over {a['c_rows']} rows: book ${a['std_book']:,.0f}, cell ${a['std_cell']:,.0f}); #463 + c x cell: WF ROC@30k {a['book_roc']:.2f} "
              f"Sortino {a['book_sortino']:.3f} max DD ${a['book_max_dd']:,.0f} (the book shadow line needs {RULES['a2_roc']:.4f} / {RULES['a2_sort']:g} / <= ${RULES['a2_dd']:,.0f}); at 0.5c {a['by_mult']['0.5']['roc']:.2f}, "
              f"at 2c {a['by_mult']['2']['roc']:.2f} -> book shadow line {'YES' if a['book_shadow_line'] else 'no'}")
    print(f"  random-pick null ({NREP} draws, seed {SEED}; max over the cells): median {null['p50']:.1f}, 95th percentile {null['p95']:.1f}, 97.5th percentile {null['p97_5']:.1f} (check (c) reads the "
          f"{RULES['null_pct']:g}th [TV X3]); ALL sits at the {cells['ALL']['null_real_percentile']:.0f}th, CAP8 at the {cells['CAP8']['null_real_percentile']:.0f}th percentile")
    if null2:
        print(f"  null of the slots-left-empty reading: median {null2['p50']:.1f}, 95th {null2['p95']:.1f}, 97.5th {null2['p97_5']:.1f}")
    print("  " + SIBLINGS["text"] + " - check (c) reads the null's 97.5th percentile (Bonferroni for two); there is no fall-back read of any runner-up (one look for one hypothesis)")
    for cell in CELLS:
        print(f"  hand audit {cell}: " + ("complete" if aok[cell] else f"NOT complete ({len(amiss[cell])} of {len(cands[cell])} candidates without a verdict) - xgap_audit_candidates.csv lists the 30 largest name-day gains of each reading; write xgap_audit.csv "
                                         "(symbol, date, cell, verdict keep|data_event, note) and run stage_a again"))
    esr = None
    try:
        es, meta = load_es(CUT_A)
        cc, oc = es_returns(days, es)
        esr = {c: es_beta(B, E[c]["x"], rows, cc, oc) for c in CELLS}
        esr["masters"] = meta
        for cell in CELLS:
            w = esr[cell]["dd_weeks"]["cc"]
            print(f"  ES beta {cell} (#463's drawdown weeks first): {w['per_1pct']:+,.0f} $ per +1% ES on {w['n']} days (corr {w['corr']:+.2f}); all WF rows {esr[cell]['all_wf_rows']['cc']['per_1pct']:+,.0f}")
    except Exception as e:                                                                 # a report, never a pass route: its failure is shown and stored, not hidden, and does not stop the verdict
        esr = {"error": f"{type(e).__name__}: {e}"}
        print(f"  ES beta NOT computed: {esr['error']}")
    pay = payer_shares(W, U, R, B, rows, WF0, PRE_END)
    if pay:
        for cell in CELLS:
            p = pay[cell]
            print(f"  [TV X5] dividend payers (a cash dividend per the calendar in the trailing 365 days) {cell}: long {p['long']['share']:.1%} ({p['long']['payers']:,} of {p['long']['n']:,}), short "
                  f"{p['short']['share']:.1%} ({p['short']['payers']:,} of {p['short']['n']:,}); from 2017-06-02 (full lookback) long {p['long_full_lookback']['share']:.1%}, short {p['short_full_lookback']['share']:.1%}")
        print(f"      the universe's own payer share: {pay['universe']['payer_share']:.1%} (from 2017-06-02: {pay['universe']['payer_share_full_lookback']:.1%})")
    ev = read_earnings(CUT_A)
    earn = earn_reading(W, U, B, rows, i0, ev) if ev is not None else None
    if earn:
        cv = earn["coverage"]
        print(f"  [TV X6] ex-earnings reading (REPORT ONLY, never judged): megacap_earnings.csv covers {len(cv['member_tickers_covered'])} member tickers ({', '.join(cv['member_tickers_covered'])}) = "
              f"{cv['wf_member_days_covered']:,} of {cv['wf_member_days']:,} WF member-days ({cv['share_of_member_days_covered']:.1%}); {cv['events_before_the_cut']:,} events {cv['first_event']} .. {cv['last_event']}; "
              f"{cv['wf_eligible_name_days_removed']:,} eligible name-days removed")
        for cell in CELLS:
            s0, s1 = cells[cell]["stageA"]["stats"], earn["cells"][cell]
            print(f"      {cell}: ROC@30k {s0['roc']:.1f} -> {s1['roc']:.1f}, net ${s0['net']:,.0f} -> ${s1['net']:,.0f}, name-days {s0['name_days']:,} -> {s1['name_days']:,}")
    else:
        print("  [TV X6] ex-earnings reading: tools/data/megacap_earnings.csv is not on file - not computed (a report, never a refusal)")
    extra = {"x2": x2, "payers": pay, "earnings": earn, "siblings": SIBLINGS, "identity": {"abs": ID_ABS, "rel": ID_REL}}
    rep = reports(W, U, R, E, B, rows, legs, WF0, PRE_END, esr, hy=hy, mps=mps, extra=extra)
    a2b = {c: {"c": cells[c]["A2"]["c"], "book_roc": cells[c]["A2"]["book_roc"], "book_sortino": cells[c]["A2"]["book_sortino"], "book_max_dd": cells[c]["A2"]["book_max_dd"],
               "book_shadow_line": cells[c]["A2"]["book_shadow_line"], "by_mult": cells[c]["A2"]["by_mult"], "checks": cells[c]["A2"]["checks"]} for c in CELLS}
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok, **stamp(), "inputs": inputs, "calendar": cinfo, "book_check": bk, "judged": bool(judged),
           "audit_complete": {c: bool(aok[c]) for c in CELLS},
           "audit": {"file": audit_path if arows else None, "rows": len(arows), "complete": aok, "missing": amiss, "data_events_removed": sorted([s, f"{d:%Y-%m-%d}"] for s, d in removed)},
           "x2": x2, "twin_coverage": twc, "identity": {"abs": ID_ABS, "rel": ID_REL}, "siblings": SIBLINGS, "null": null, "null_slot_empty": null2, "cells": cells,
           "stageA": {"PASS": best is not None, "cells": {c: cells[c]["stageA"]["verdict"] for c in CELLS}, "candidate": best, "readings": 2 if E2 else 1},
           "a2_report": {"cell": best, "c": a2b[best]["c"] if best else None, "book_roc": a2b[best]["book_roc"] if best else None, "book_sortino": a2b[best]["book_sortino"] if best else None,
                         "book_max_dd": a2b[best]["book_max_dd"] if best else None, "book_shadow_line": a2b[best]["book_shadow_line"] if best else None, "by_cell": a2b,
                         "note": "A2 is a REPORT, not a gate [MANAGER #56]: it decides only whether a forward BOOK shadow line is also opened (book_shadow_line); Stage B needs a Stage A pass + audit_complete"},
           "reports": rep}
    dump(out, "xgap_stageA.json")
    for cell in CELLS:
        nd, p = R.nd[("P", cell)], E[cell]["base"]["p"]
        k = B.mask(WF0, PRE_END)[rows[nd["i"]]]
        pd.DataFrame({"date": days[nd["i"][k]], "symbol": W.tick[nd["x"][k]], "side": nd["side"][k], "g": nd["g"][k], "raw_gap": nd["gap"][k], "fill_0935": nd["o"][k], "close": nd["c"][k], "pnl_base": p[k]}
                     ).to_csv(os.path.join(OUT, f"xgap_namedays_WF_{cell}.csv.gz"), index=False, compression="gzip")
    if best:
        a = a2b[best]
        print(f"XGAP Stage A: PASS - cell {best} clears every bar (WF ROC@30k {cells[best]['stageA']['stats']['roc']:.1f}; " + ("both readings, " if E2 else "") + "the twin veto, the hand audit complete) and is the Stage B candidate; "
              f"A2 report: c = {a['c']:.4f}, book shadow line {'YES' if a['book_shadow_line'] else 'no'} (it decides only whether a forward BOOK shadow line is also opened). Stage B may run once, on the one sealed-year day, after the sibling rule.")
    elif not judged:
        print("XGAP Stage A: NOT judged - the hand audit is incomplete for a cell that clears (a)-(g) and the twin veto; the numbers are in xgap_stageA.json (a pass cannot be read before the audit).")
    else:
        print("XGAP Stage A: FAIL (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['stageA']['checks'].items() if not v) + (
            " | slots-left-empty reading: " + ", ".join(k for k, v in cells[c]['stageA']['slot_empty']['checks'].items() if not v) if cells[c]['stageA']['slot_empty'] else "") for c in CELLS)
              + ") - XGAP r1 is dead; the lockbox stays sealed.")
    pm = A.peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


def _first_num(*vals):
    """the first finite number among `vals` (a bool is not a number) | None"""
    for v in vals:
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            return float(v)
    return None


def ddw_l2(js):
    """CHOICE (DDW r1's verdict schema was not fixed when this was written; the first reading below is the shape of its r14_ddw.py draft of 2026-10-05): {cell: (reaches DDW's Stage B / passed Stage A + A2,
    its A2 book ROC | None)}, the cells the sibling rule looks at.
    1. A `candidate` key = DDW's own pick, the ONE cell that reaches ITS Stage B: {cell, a2_book_roc | book_roc | a2_roc | roc} -> {cell: (True, roc)}; null = no cell passes with its audit complete -> {}.
    2. No `candidate` key: the cells of stageA.cells, else any dict found under a key that starts with 'L2' (searched to depth 4; the FIRST one found for a name wins - a later copy such as a look-ahead or a
       parity block never overwrites it), that carry a Stage A or an A2 flag. A cell passed when its Stage A flag (stageA.PASS | PASS) and its A2 flag (A2.pass | a2_pass) are both true; its A2 book ROC is
       A2.book_roc | A2.roc | A2.book.roc | a2_book_roc.
    Raises ValueError when nothing is readable, when a reaching / passing cell has no readable ROC, or when a cell that passed Stage A has no readable A2 verdict - the caller refuses on it (the sibling rule
    cannot be applied; a refusal costs a look at the file, a wrong 'clear' would burn the one sealed-year read)"""
    if "candidate" in js:
        cand = js["candidate"]
        if cand is None:
            return {}
        if not (isinstance(cand, dict) and isinstance(cand.get("cell"), str) and cand["cell"]):
            raise ValueError("the candidate record has no cell name")
        roc = _first_num(cand.get("a2_book_roc"), cand.get("book_roc"), cand.get("a2_roc"), cand.get("roc"))
        if roc is None:
            raise ValueError(f"candidate cell {cand['cell']} has no readable A2 book ROC")
        return {cand["cell"]: (True, roc)}
    cells = {}
    st = js.get("stageA")
    st = st.get("cells") if isinstance(st, dict) else None
    if isinstance(st, dict):
        cells = {str(k): v for k, v in st.items() if isinstance(v, dict) and re.match(r"(?i)^l2", str(k))}

    def walk(node, depth):
        if depth > 4 or not isinstance(node, dict):
            return
        for k, v in node.items():
            if isinstance(v, dict) and re.match(r"(?i)^l2", str(k)):
                cells.setdefault(str(k), v)
            elif isinstance(v, dict):
                walk(v, depth + 1)
    if not cells:
        walk(js, 0)
    out = {}
    for name, c in cells.items():
        sa, a2 = c.get("stageA"), c.get("A2")
        pa = sa.get("PASS") if isinstance(sa, dict) else None
        pa = c.get("PASS") if pa is None else pa
        a2d = a2 if isinstance(a2, dict) else {}
        p2 = a2d.get("pass")
        p2 = c.get("a2_pass") if p2 is None else p2
        if pa is None and p2 is None:                                                      # a block that carries no verdict flag (an exposure table, a parity block ...) is not a cell record
            continue
        roc = _first_num(a2d.get("book_roc"), a2d.get("roc"), (a2d.get("book") or {}).get("roc") if isinstance(a2d.get("book"), dict) else None, c.get("a2_book_roc"))
        if pa is True and p2 is None:
            raise ValueError(f"cell {name} passed Stage A but its A2 verdict is not readable")
        passed = pa is True and p2 is True
        if passed and roc is None:
            raise ValueError(f"cell {name} passed but has no readable A2 book ROC")
        out[name] = (passed, roc)
    if not out:
        raise ValueError("no L2 cell found")
    return out


def sibling_refusal(path, best_roc):
    """STAGE B's sibling rule: if a DDW r1 L2 cell reaches DDW's Stage B (it is DDW's candidate) with a HIGHER A2 book ROC than XGAP's best, only that one is read on the one sealed-year day. -> a refusal
    message, or None (clear: no L2 candidate, an L1 candidate - not the sibling - or a lower / equal L2 one). Also refuses when DDW r1's decision is not on file (no file, or not judged) or cannot be read"""
    if not os.path.exists(path):
        return f"Stage B refused: DDW r1's sibling decision is not on file ({path}) - XGAP's Stage B waits for it (the sibling rule); lockbox NOT read"
    try:
        js = read_json(path)
    except Exception as e:
        return f"Stage B refused: DDW r1's verdict file cannot be read ({type(e).__name__}) - the sibling rule cannot be applied; lockbox NOT read"
    if js.get("judged") is not True:
        return "Stage B refused: DDW r1's Stage A is not judged yet - the sibling decision is not on file (the sibling rule); lockbox NOT read"
    try:
        cells = ddw_l2(js)
    except ValueError as e:
        return f"Stage B refused: DDW r1's verdict file has no readable L2 cell record ({e}) - the sibling rule cannot be applied, MANAGER settles it; lockbox NOT read"
    beat = {n: roc for n, (ok, roc) in cells.items() if re.match(r"(?i)^l2", n) and ok and roc is not None and roc > best_roc}
    if beat:
        n = max(beat, key=beat.get)
        return (f"Stage B refused: the sibling rule - DDW r1's L2 cell {n} reaches its Stage B (passed Stage A + A2) with a higher A2 book ROC ({beat[n]:.2f}) than XGAP's best ({best_roc:.2f}); only the higher is read on the "
                "one sealed-year day (one look for one hypothesis), so XGAP's Stage B does not run; lockbox NOT read")
    return None


def b_preflight(sa, flag):
    """every Stage B refusal that needs only the Stage A file, the flag and the spec (nothing is read, the flag is never written): a judged Stage A PASS with the hand audit complete for the candidate cell (A2 is a report,
    not a gate - [MANAGER #56]), the flag absent, the registered spec, the prereg sha and the harness stamp Stage A ran under -> (cell, c)"""
    st = sa.get("stageA") or {}
    if not (sa.get("judged") is True and st.get("PASS") is True):
        refuse("Stage B refused: no Stage A pass on file (judged, every bar, the twin veto, the hand audit complete) - the lockbox stays sealed.")
    cell = st.get("candidate")
    if cell not in CELLS or (sa.get("audit_complete") or {}).get(cell) is not True or ((sa.get("audit") or {}).get("complete") or {}).get(cell) is not True:
        refuse(f"Stage B refused: the hand audit of cell {cell} is not recorded complete in Stage A (audit_complete) - lockbox NOT read")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({FLAG_FILE})")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    a2c = ((sa.get("a2_report") or {}).get("by_cell") or {}).get(cell) or {}
    c = num(a2c.get("c"))
    if not (math.isfinite(c) and c > 0):
        refuse(f"Stage B refused: the frozen c ({a2c.get('c')}) is not a positive number (lockbox NOT read)")
    return cell, c


def stage_b():
    pa = os.path.join(OUT, "xgap_stageA.json")
    sa = read_json(pa) if os.path.exists(pa) else {}
    flag = os.path.join(OUT, FLAG_FILE)
    cell, c = b_preflight(sa, flag)
    cal, cinfo = load_calendar(CUT_B)                                                      # refuses when the calendar is missing or its sha256 differs from its manifest
    inputs = input_shas(cinfo)
    bad = [k for k, v in (sa.get("inputs") or {}).items() if inputs.get(k) != v]
    if bad or not sa.get("inputs"):
        refuse(f"Stage B refused: the calendar / caches differ from the ones Stage A read ({', '.join(bad) or 'no record'}) - a changed input is a different photograph of the vendor (lockbox NOT read)")
    print("calendar sha256 matches Stage A's (both files are the ones the prereg pins [MANAGER #58]); the NQBRD cache, TBIS list, membership file and SIPORB manifest are the ones Stage A read")
    best = num((((sa.get("a2_report") or {}).get("by_cell") or {}).get(cell) or {}).get("book_roc"))      # XGAP's A2-REPORT book ROC of the candidate: the number the sibling rule compares
    msg = sibling_refusal(DDW_STAGE_A, best)
    if msg:
        refuse(msg)
    print("sibling rule: DDW r1's decision is on file and no L2 cell reaches its Stage B with a higher A2 book ROC than XGAP's report")
    B, legs = A.load_463()                                                                 # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk, bkl = book_check_x(B, WF0, PRE_END, BOOK_WF, BOOK_DD), book_check_x(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 WF check {bk['roc']:.2f} / {bk['sortino']:.3f} / ${bk['max_dd']:,.0f}; LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bkl['roc']:.2f} Sortino {bkl['sortino']:.3f}")
    if CHECK_BOOK and not (bk["ok"] and bkl["ok"]):
        refuse("Stage B refused: the #463 records do not reproduce its WF / LB numbers - settle the end-date convention first (lockbox NOT read)")
    arows, removed = read_audit(os.path.join(OUT, "xgap_audit.csv"), CUT_B)
    if sorted([s, f"{d:%Y-%m-%d}"] for s, d in removed) != (sa.get("audit") or {}).get("data_events_removed"):
        refuse("Stage B refused: the hand audit's data events differ from the ones Stage A removed - run stage_a again (lockbox NOT read)")
    P = prepare(CUT_B, cal, cinfo)
    W = assemble(P, removed)
    U = universe(W)
    days = P.D.days
    rows = A.book_rows(B, P.D)
    lb = np.asarray((days >= LB0) & (days <= LB1))
    have = np.isfinite(W.o930).any(axis=1)
    cov = float(have[lb].mean()) if lb.any() else float("nan")
    print(f"the member cache has bars on {int(have[lb].sum()):,} of {int(lb.sum()):,} lockbox sessions ({cov:.1%}; needs >= 98%)")
    if not cov >= 0.98:                                                                    # CHOICE: a gap in the pull stops the one read BEFORE it (r13_attn's coverage gate)
        refuse("Stage B refused: the NQBRD member cache is missing too many lockbox sessions - fix the pull first (lockbox NOT read)")
    i0 = int(days.searchsorted(WF0))
    R = run_cells(W, U, rows, B.n, i0, 0)                                                  # no null in Stage B
    Ew = evaluate(R, B, rows, WF0, PRE_END)
    for cc in CELLS:                                                                       # CHOICE: Stage A's WF numbers must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
        a0, w = sa["cells"][cc]["stageA"]["stats"], Ew[cc]["base"]["stats"]
        if w["name_days"] != a0["name_days"] or w["sessions"] != a0["sessions"] or abs(w["net"] - num(a0["net"])) > 0.5:
            refuse(f"Stage B refused: cell {cc}'s WF numbers do not reproduce on Stage B's data (name-days {w['name_days']} vs {a0['name_days']}, net ${w['net']:,.2f} vs ${num(a0['net']):,.2f}) - the cache or the code "
                   "changed since Stage A (lockbox NOT read)")
    print("WF numbers re-computed on Stage B's data equal Stage A's (both cells)")
    E = evaluate(R, B, rows, LB0, LB1)                                                     # CHOICE (r13_attn / r10_spread's order): the whole LB result is computed, nothing shown, BEFORE the flag
    e, nd = E[cell], R.nd[("P", cell)]
    leg = cell_stats(B, nd, e["base"]["p"], rows, LB0, LB1, years=(2025,))
    k_in = B.mask(LB0, LB1)[rows[nd["i"]]]
    kb = B.mask(LB0, LB1)
    bs = R11.stats((B.raw + c * e["x"])[kb], B.index[kb])
    base = R11.stats(B.raw[kb], B.index[kb])
    chk = {f"leg name-days>={RULES['b_namedays']}": bool(leg["name_days"] >= RULES["b_namedays"]), f"leg traded sessions>={RULES['b_sessions']}": bool(leg["sessions"] >= RULES["b_sessions"]),
           "leg net>0": bool(leg["net"] > 0), "leg net>0 without its top name-day": bool(leg["net_ex_top_nameday"] > 0)}
    ok = all(chk.values())
    book_rep = {"roc": bs["roc"], "sortino": bs["sort"], "net": bs["net"], "max_dd": bs["max_dd"], "c": c, "cell": cell, "book_alone": {"roc": base["roc"], "sortino": base["sort"], "net": base["net"], "max_dd": base["max_dd"]},
                "reported_only": True, "note": "#463 + c x the cell on the sealed year at the frozen c: REPORTED, never part of the pass (after BOOK LOOKS r1 a seat swap clears the old bar 42% of the time) - the forward record decides any book add"}
    rep = {"sides": by_side(nd, e["base"]["p"], k_in), "buckets": by_bucket(nd, e["base"]["p"], k_in), "top_gains": top_gains(W, nd, e["base"]["p"], k_in), "stress": e["stress"]["stats"], "cents": e["cents"]["stats"],
           "mirror": e["mirror"]["stats"], "twin": e["twin"]["stats"], "hygiene": hygiene(W, U)}
    text = {"cell": cell, "c": c, "book_check": {"WF": bk, "LB": bkl}, "inputs": inputs, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": book_rep, "wf_recheck": "equal", "sibling": "clear",
            "reports": rep, **stamp(), "prereg_sha256_lf": PREREG_SHA}
    js_text = json.dumps(MDL._clean(text), indent=1, default=R11.js)
    buf = io.StringIO()                                                                    # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print(f"Stage B (lockbox, read once) - cell {cell}, frozen c = {c:.4f}")
        print("  " + fmt_row("leg standalone LB", leg))
        print(f"  the leg's best name-day ${leg['top_nameday']:,.0f}; net without it ${leg['net_ex_top_nameday']:,.0f}; long {rep['sides']['long']['net']:,.0f} / short {rep['sides']['short']['net']:,.0f} (net $)")
        print(f"  #463 + c x leg on the sealed year (REPORTED, never a pass - [B48]): LB ROC@30k {bs['roc']:.2f} Sortino {bs['sort']:.3f} net ${bs['net']:,.0f}; #463 alone {base['roc']:.2f} / {base['sort']:.3f}")
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print("XGAP Stage B: " + ("the LEG survives its sealed year - a computed no-order forward SHADOW line decides any book add (owner call; opening an account is the owner's decision)."
                                  if ok else "FAIL - the leg fails its sealed year: XGAP r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                             # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "xgap_stageB.json"), "w") as f:
        f.write(js_text)
    print(buf.getvalue().rstrip())
    pm = A.peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ dryload: outcome-free counts of the real caches
def twin_coverage(W, U, i0, k=NPOS):
    """[TV X4] how much of the walk-forward the beta twin can see: by year, the share of the eligible name-days with a full 60-session beta and the sessions on which the twin trades (at least 2k eligible names with
    one) - counts only"""
    yr = W.days.year.to_numpy()
    el = U.elig.copy()
    el[:i0] = False
    fin = np.isfinite(W.beta) & el
    n_et = fin.sum(axis=1)
    trade = n_et >= 2 * k
    trade[:i0] = False
    out = {"by_year": {}, "eligible_with_beta": int(fin.sum()), "eligible": int(el.sum()), "twin_sessions": int(trade.sum()), "wf_sessions": int(len(yr) - i0)}
    for y in sorted(set(yr[i0:])):
        s = yr == y
        s[:i0] = False
        out["by_year"][int(y)] = {"beta_share": float(fin[s].sum() / max(el[s].sum(), 1)), "twin_sessions": int(trade[s].sum()), "sessions": int(s.sum())}
    return out


def print_twin_coverage(tw):
    print(f"[TV X4] beta twin coverage (its 60-session betas read from SIPORB's returns through the symbol chosen without the identity check, one array for both readings): {tw['eligible_with_beta']:,} of {tw['eligible']:,} "
          f"eligible WF name-days have a full beta ({tw['eligible_with_beta'] / max(tw['eligible'], 1):.1%}); the twin trades on {tw['twin_sessions']:,} of {tw['wf_sessions']:,} WF sessions; by year (beta share / twin sessions): "
          + ", ".join(f"{y}: {v['beta_share']:.1%} / {v['twin_sessions']} of {v['sessions']}" for y, v in tw["by_year"].items()))


def dryload():
    """sessions, members per session, the identity check's agreement, eligible names per session, the exclusions by reason, the share-class report and the X2 identity-drop rates - by year, pre-lockbox, COUNTS AND RATES
    ONLY: no price, gap value, return or P&L is printed (the X2 rates are by |g| bucket and side). A missing calendar is said so and the other counts still run (then the ex-dividend and calendar-split rules are off and
    the map uses the same ticker only)"""
    cal, cinfo = load_calendar(CUT_A, need=False)
    if cal is None:
        print("calendar: NOT ON FILE (capull has not been run): the ex-dividend and calendar-split exclusions are off and the symbol map uses the same ticker only - every other count below is real")
    else:
        pin = cinfo["pinned"]
        print(f"calendar: {cinfo['rows_read']:,} rows read (by type: " + ", ".join(f"{k} {v:,}" for k, v in sorted(cinfo['rows_by_type'].items())) + f"), csv sha256 {cinfo['csv_sha256'][:12]}...; the files the prereg pins "
              f"[MANAGER #58] (stage_a and stage_b refuse unless both match): csv {'matches' if pin['csv'] else 'DIFFERS'}, raw jsonl " + ("matches" if pin["raw"] else ("DIFFERS" if cinfo["raw_sha256"] else "NOT ON FILE")))
    P = prepare(CUT_A, cal, cinfo)
    W = assemble(P, None)
    U, Uw = universe(W), universe(W.waived)
    H = hygiene(W, U)
    days, yr = W.days, W.days.year.to_numpy()
    ci = W.cache_info
    print(f"member cache: {ci['bars']:,} bars on the session grid, {ci['sessions_with_bars']:,} sessions with bars, {ci['bars_off_grid']:,} bars off the grid, {ci['dup_dropped']} duplicated bars dropped, "
          f"{ci['et_day_differs_from_day']} rows whose Eastern date differs from their day column; membership: {len(W.tick)} tickers; TBIS list: {len(P.tbis)} rows ({int(P.tbis['split_like'].sum())} volume-confirmed) before the cut")
    print(f"sessions on SIPORB's calendar before the cut: {len(days):,} ({days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}); with member-cache bars: {ci['sessions_with_bars']:,}")
    live = np.isfinite(W.o930).any(axis=1)
    chk = np.isfinite(W.o930) & ~W.nodata & W.member
    agree = chk & (W.ksel >= 0)
    print("by year: sessions | members a session | identity-check agreement (of member-days with a 09:30 bar and a SIPORB bar; |open difference| <= max(1 cent, 0.10%)) | dropped by the identity check | no SIPORB bar (survivorship) | eligible a session (median)")
    for y in sorted(set(yr)):
        s = (yr == y) & live
        if not s.any():
            continue
        mv = H["symbol_map_by_year"][int(y)]
        el = np.median(U.elig[s].sum(axis=1))
        print(f"  {y}: {int(s.sum()):>4} | {W.member[s].sum(axis=1).mean():6.1f} | {agree[s].sum() / max(chk[s].sum(), 1):7.2%} | {mv['identity_drops']:>5,} of {mv['member_days']:>8,} ({mv['share']:.2%}) | "
              f"{mv['no_data']:>6,} ({mv['no_data_share']:.1%}) | {el:5.0f}")
    print(f"  years with more than {MAP_YEAR_MAX:.0%} of member-days dropped by the identity check (the 2% rule counts these only): {H['map_years_over_2pct'] or 'none'}")
    print_hygiene(H, cal is not None)
    print_share_class(H["share_class"])
    i0 = int(days.searchsorted(WF0))
    x2 = x2_rates(W, Uw, i0)
    print_x2(x2)
    tw = twin_coverage(W, U, i0)
    H["twin_coverage"] = tw
    print_twin_coverage(tw)
    if cal is not None:
        late = (days >= TS("2017-06-02")) & (days <= PRE_END)
        el = U.elig & late[:, None]
        print(f"[TV X5] dividend payers (a cash dividend in the trailing 365 days) are {float(W.payer[el].mean()):.1%} of the eligible member-days from 2017-06-02 on (the whole lookback inside the calendar)")
    ev = read_earnings(CUT_A)
    if ev is not None:
        mask, covered = earn_mask(ev, days, W.tick, W.comp)
        wf = (days >= WF0) & (days <= PRE_END)
        mem = W.member & wf[:, None]
        print(f"[TV X6] megacap_earnings.csv: {len(ev):,} events before the cut ({ev['acc'].min():%Y-%m-%d} .. {ev['acc'].max():%Y-%m-%d}); covers {int(covered.sum())} of {len(W.tick)} member tickers = "
              f"{int((mem & covered[None, :]).sum()):,} of {int(mem.sum()):,} WF member-days; it would remove {int((U.elig & mask & wf[:, None]).sum()):,} eligible name-days (a report, never judged)")
    else:
        print("[TV X6] megacap_earnings.csv is not on file")
    return H


# ------------------------------------------------------------------ selftest: hand-made worlds, no real files, no data
def mini(T=14, X=8):
    """a clean world: T sessions from Mon 2024-03-04 x X names, every name a member with both bars, a daily bar on t and t-1, a split factor of 1, no flag; the tests then break one thing at a time"""
    days = pd.bdate_range("2024-03-04", periods=T)
    one = lambda v: np.full((T, X), v, float)
    W = SimpleNamespace(days=days, tick=np.array([f"N{i}" for i in range(X)], dtype=object), member=np.ones((T, X), bool), o930=one(100.0), o935=one(100.0), ksel=np.tile(np.arange(X), (T, 1)),
                        nodata=np.zeros((T, X), bool), csyms=[f"S{i}" for i in range(X)], Od=one(100.0), Cl=one(100.0), Cl_prev=one(100.0), F=one(1.0), F_prev=one(1.0), beta=one(1.0))
    for n in ("exdiv", "cal6", "reg6", "gap6", "tbis6", "tbis6_prior", "g506", "audit", "cal_ev", "reg_ev", "gap_ev", "tbis_ev", "g50_ev"):
        setattr(W, n, np.zeros((T, X), bool))
    W.gap = split_safe_gap(W.Od, W.Cl_prev, W.F, W.F_prev)
    return W


def book_stub(idx, raw=None):
    """a stand-in for r11_risk.Book with just what the statistics read: index, n, mask, raw"""
    idx = pd.DatetimeIndex(idx)
    return SimpleNamespace(index=idx, n=len(idx), raw=np.zeros(len(idx)) if raw is None else np.asarray(raw, float), mask=lambda lo, hi: np.asarray((idx >= lo) & (idx <= hi)))


def t_constants():
    assert (NPOS, SLOT, CAP, COST, CELLS, NREP, SEED, FLAG_WIN, BETA_WIN, ID_ABS, ID_REL, MAP_YEAR_MAX, GAP_MAX, X2_RATIO) == (10, 5000.0, 0.08, {"base": (10.0, 5.0), "stress": (20.0, 10.0)}, ("ALL", "CAP8"), 500, 20261005, 6, 60, 0.01, 0.0010, 0.02, 0.5, 1.5)
    assert PREREG_SHA == "7e29938e069271efcc9dadffe0da9cb8e4c83378a8696b4bac0a33ce336cf81f" and SIBLINGS["cells_tried"] == 4 and SIBLINGS["text"] == "sibling cells tried: 4 (DDW r1 L2-F, L2-S - dead at Stage A; XGAP ALL, CAP8)"
    assert SHARE_CLASS == (("GOOG", "GOOGL"), ("FOX", "FOXA"), ("NWS", "NWSA"), ("LBTYA", "LBTYB", "LBTYK"), ("DISCA", "DISCB", "DISCK"), ("LILA", "LILAK"), ("BATRA", "BATRK"), ("LBRDA", "LBRDK"), ("VIAC", "VIACA")) and CLASS_LETTERS == "ABCKL"
    assert (RULES["null_pct"], RULES["twin_half"], RULES["x2_ratio"]) == (97.5, 0.5, 1.5) and all(RULES[k] is True for k in ("twin", "x2")) and EARN_CSV.endswith(os.path.join("tools", "data", "megacap_earnings.csv"))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (CUT_A, CUT_B) == (LB0, TS("2026-07-01")) and YEARS == tuple(range(2016, 2025))
    assert (BOOK_WF, BOOK_LB, TOL, BOOK_DD) == ((93.81, 3.816), (155.54, 4.15), (0.006, 0.0006), 44849.0) and (C_TARGET, C_ROWS) == (0.25, (TS("2016-07-01"), TS("2018-06-29")))
    assert abs(RULES["a2_roc"] - 98.5005) < 1e-9 and RULES["a2_sort"] == 3.816 and abs(RULES["a2_dd"] - 1.10 * 44849.0) < 1e-6 and RULES["nw_lags"] == 5 and CHECK_BOOK is True
    assert (RULES["sessions"], RULES["roc"], RULES["pf"], RULES["t"], RULES["best_days"], RULES["best_pct"], RULES["years"], RULES["b_namedays"], RULES["b_sessions"]) == (1800, 15.0, 1.10, 2.0, 5, 1, 6, 50, 30)
    assert all(RULES[k] is True for k in ("null", "mirror", "stress", "exbest", "halves", "x2020", "audit"))
    assert HALVES == ((TS("2016-07-01"), TS("2020-12-31")), (TS("2021-01-01"), PRE_END)) and len(PREREG_SHA) == 64 and len(CA_TYPES) == 7 and CA_BATCH == 50 and CA_LIMIT == 1000
    assert (CA_START, CA_END, CA_PROBE) == ("2016-06-01", "2026-06-30", ("AAPL,NVDA,TSLA,FB,META", "2019-01-01", "2024-12-31")) and CA_COLS[0] == "type" and len(CA_COLS) == 13
    assert (CAL_RAW_SHA, CAL_CSV_SHA) == ("eac8ccef7d6c22315b2fe5cc770534aa48eab988dc04c0903892f253c7c61f8d", "d7acffbe5de0c5eccf3e13625c55d30ab4a173b9ce7952f576d1f0ac659b81b2"), "[MANAGER #58] the pinned calendar files"
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        assert prereg_ok() is True
    st = stamp()
    assert all(len(st[k]) == 64 for k in ("harness_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "attn_sha256")) and "2023-11-24" in st["early_close"]
    assert (S.COMM, S.SLIP) == (0.0035, 0.01) and MDL.G_WINDOW == 20 and R11.X20 == (TS("2020-02-15"), TS("2020-04-30"))


def t_calendar_parser():
    page = {"corporate_actions": {
        "cash_dividends": [{"symbol": "AAPL", "cusip": "037833100", "rate": 0.24, "special": False, "foreign": False, "process_date": "2024-02-15", "ex_date": "2024-02-09", "record_date": "2024-02-12", "payable_date": "2024-02-15"},
                           {"symbol": "AAPL", "rate": 0.25, "ex_date": "2024-05-10"}],
        "forward_splits": [{"symbol": "NVDA", "new_rate": 10, "old_rate": 1, "process_date": "2024-06-10", "ex_date": "2024-06-10", "record_date": "2024-06-06", "payable_date": "2024-06-07"}],
        "reverse_splits": [{"symbol": "ZZ", "new_rate": 1, "old_rate": 8, "ex_date": "2023-01-03"}],
        "unit_splits": [{"old_symbol": "UA", "new_symbol": "UB", "alternate_symbol": "UC", "old_rate": 1, "new_rate": 1.1, "effective_date": "2024-01-02", "process_date": "2024-01-02"}],
        "stock_dividends": [{"symbol": "XX", "rate": 0.05, "ex_date": "2024-03-01"}], "name_changes": [{"old_symbol": "FB", "new_symbol": "META", "new_cusip": "c", "process_date": "2022-06-09"}],
        "spin_offs": [{"source_symbol": "GE", "new_symbol": "GEHC", "source_rate": 1, "new_rate": 0.25, "ex_date": "2023-01-04", "process_date": "2023-01-04"}],
        "cash_mergers": [{"acquirer_symbol": "Q", "target": "R"}]}, "next_page_token": "tok", "weird_top": 1}
    recs, info = ca_parse(page)
    by = Counter(t for t, _ in recs)
    assert by == {"cash_dividend": 2, "forward_split": 1, "reverse_split": 1, "unit_split": 1, "stock_dividend": 1, "name_change": 1, "spin_off": 1, "cash_mergers": 1}, by
    assert dict(info["unknown_types"]) == {"cash_mergers": 1} and info["unknown_top_keys"] == ["weird_top"], "an unknown type is kept raw and listed; so is an unknown top-level key"
    rows = {(t, r.get("symbol") or r.get("old_symbol") or r.get("source_symbol") or r.get("acquirer_symbol")): ca_flatten(t, r) for t, r in recs[1:]}      # (recs[0] is AAPL's first dividend, flattened on its own below)
    d0, un0 = ca_flatten(*recs[0])
    assert d0["special"] is False and d0["rate"] == 0.24 and d0["ex_date"] == "2024-02-09" and d0["process_date"] == "2024-02-15" and d0["new_rate"] is None and un0 == ["cusip", "foreign"]
    assert ca_flatten("cash_dividend", {"symbol": "A", "rate": 1.0, "ex_date": "2024-05-10"})[0]["special"] is None, "a missing field is None"
    u, unf = rows[("unit_split", "UA")]
    assert u["ex_date"] == "2024-01-02" and u["old_symbol"] == "UA" and u["new_symbol"] == "UB" and u["symbol"] is None and unf == ["alternate_symbol"]
    sp, _ = rows[("spin_off", "GE")]
    assert sp["symbol"] == "GE" and sp["new_symbol"] == "GEHC" and sp["old_rate"] == 1 and sp["new_rate"] == 0.25 and sp["ex_date"] == "2023-01-04"
    nc, _ = rows[("name_change", "FB")]
    assert nc["old_symbol"] == "FB" and nc["new_symbol"] == "META" and nc["ex_date"] is None and nc["process_date"] == "2022-06-09"
    assert ca_year(nc) == "2022" and ca_year(d0) == "2024" and ca_year({"type": "x"}) == "n/a"
    r2, i2 = ca_parse({"corporate_actions": [{"ca_type": "forward_splits", "symbol": "A"}, {"type": "mystery"}]})
    assert [t for t, _ in r2] == ["forward_split", "mystery"] and dict(i2["unknown_types"]) == {"mystery": 1}, "a flat list of records is grouped by its type field"
    assert ca_parse([1, 2])[0] == [] and ca_parse({})[0] == [] and ca_parse({"corporate_actions": None})[0] == []
    rr, dup = ca_rows(recs + recs[:2])
    assert dup == 2 and len(rr) == len(recs) and rr == ca_rows(list(reversed(recs)))[0], "exact duplicates are dropped, the order is reproducible"
    assert ca_new_names(recs, ["FB"]) == ["META"] and ca_new_names(recs, ["FB", "META"]) == [] and ca_new_names([], []) == []
    assert scrub("x ABCDEF123 y") == "x ABCDEF123 y"
    global _SECRETS
    old, _SECRETS = _SECRETS, ("ABCDEF123", "")
    try:
        assert scrub("HTTP 400: key ABCDEF123 bad") == "HTTP 400: key <key> bad"
    finally:
        _SECRETS = old


class FakeGet:
    """a stand-in for r5_siporb._get on the corporate-actions endpoint: pages of `size` records in the documented shape, a name it rejects outright (400 'invalid symbol'), a type it rejects (400 without a symbol)"""
    def __init__(self, records, size=3, bad=("BAD",), reject_type=None):
        self.records, self.size, self.bad, self.reject_type, self.calls = records, size, set(bad), reject_type, []

    def __call__(self, url, params, key, secret):
        assert url == CA_URL and params["types"] == ",".join(CA_TYPES) and params["limit"] == CA_LIMIT and params["start"] in (CA_START, CA_PROBE[1]) and "asof" not in params
        self.calls.append(dict(params))
        syms = params["symbols"].split(",")
        if self.reject_type:
            raise S.BadRequest(f"HTTP 400: unknown type {self.reject_type}")
        if self.bad & set(syms):
            raise S.BadRequest("HTTP 400: invalid symbol: " + ",".join(sorted(self.bad & set(syms))))
        hit = [(t, r) for t, r in self.records if (r.get("symbol") or r.get("old_symbol") or r.get("source_symbol")) in syms]
        off = int(params.get("page_token") or 0)
        out = defaultdict(list)
        for t, r in hit[off:off + self.size]:
            out[next(k for k, v in CA_KEYS.items() if v == t)].append(r)
        return {"corporate_actions": dict(out), "next_page_token": str(off + self.size) if off + self.size < len(hit) else None}


def t_calendar_pull():
    recs = [("cash_dividend", {"symbol": s, "rate": 0.1, "ex_date": f"2024-0{k + 1}-10"}) for s in ("A", "B", "C", "D") for k in range(3)] + [("name_change", {"old_symbol": "A", "new_symbol": "A2", "process_date": "2024-03-01"})]
    fg = FakeGet(recs)
    sink = CaPull(os.path.join(tempfile.mkdtemp(), "raw.part"))
    with A.patched(S, _get=fg):
        ca_fetch(["A", "B", "BAD", "C", "D"], "k", "s", sink, 1)
    sink.close()
    assert sink.bad == ["BAD"] and len(sink.recs) == len(recs), "a rejected symbol is bisected out and logged; every page of the others is read (paging on next_page_token)"
    assert sink.requests == sink.pages and sink.requests > len(fg.calls) - 6 and any(c.get("page_token") for c in fg.calls) and len(sink.recs) == 13
    lines = [json.loads(l) for l in open(sink.f.name, encoding="utf-8")]
    assert len(lines) == sink.pages and all({"i", "round", "params", "page"} <= set(l) for l in lines) and "page_token" not in lines[0]["params"] and "key" not in json.dumps(lines).lower()
    assert ca_new_names(sink.recs, ["A", "B", "C", "D"]) == ["A2"]
    try:
        with A.patched(S, _get=FakeGet(recs, reject_type="cash_foo")):
            ca_fetch(["A"], "k", "s", CaPull(os.path.join(tempfile.mkdtemp(), "x.part")), 1)
        raise AssertionError("a rejected TYPE must stop the pull")
    except S.BadRequest as e:
        assert "cash_foo" in str(e)
    buf = io.StringIO()                                                                                  # the probe: status, keys, counts, field NAMES - no value
    with A.patched(S, _get=FakeGet([("cash_dividend", {"symbol": "AAPL", "rate": 0.987654, "ex_date": "2024-02-09", "cusip": "SECRETVAL"}), ("name_change", {"old_symbol": "AAPL", "new_symbol": "AAPL2"})], size=10)):
        with contextlib.redirect_stdout(buf):
            js = ca_probe("k", "s")
    txt = buf.getvalue()
    assert "HTTP status: 200" in txt and "top-level keys: corporate_actions, next_page_token" in txt and "cash_dividend 1" in txt and "first record's fields: cusip, ex_date, rate, symbol" in txt
    assert "0.987654" not in txt and "SECRETVAL" not in txt and "2024-02-09" not in txt, "the probe prints names, never values"
    buf = io.StringIO()
    with A.patched(S, _get=FakeGet([], reject_type="cash_foo")):
        with contextlib.redirect_stdout(buf):
            assert ca_probe("k", "s") is None
    assert "400/422" in buf.getvalue() and "cash_foo" in buf.getvalue() and "CA_TYPES" in buf.getvalue()


def t_capull_wide():
    """capull's WIDE mode [for the other lanes]: the command line, the names file, the per-tag files, the stop on rejected symbols that scales with the list, the whole pull through a mocked transport"""
    me = sys.modules[__name__]
    assert capull_args([]) == (False, False, None, None) and capull_args(["--probe"]) == (True, False, None, None) and capull_args(["--force", "--probe"]) == (True, True, None, None)
    assert capull_args(["--names", "f.txt", "--tag", "wide", "--probe"]) == (True, False, "f.txt", "wide") and capull_args(["--tag=wide", "--names=C:\\x\\f.txt", "--force"]) == (False, True, "C:\\x\\f.txt", "wide")

    def refuses(fn, frag):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                fn()
            raise AssertionError(f"must refuse: {frag}")
        except SystemExit as e:
            assert frag in str(e), (frag, str(e))
    for bad, frag in ((["--names", "f.txt"], "go together"), (["--tag", "wide"], "go together"), (["--names", "f.txt", "--tag", "../x"], "must be 1 to 40"), (["--names", "f.txt", "--tag", ""], "takes exactly one value"),
                      (["--names", "--tag", "x"], "takes exactly one value"), (["--names", "a", "--names", "b", "--tag", "t"], "takes exactly one value"), (["--tag", "a b", "--names", "f"], "must be 1 to 40"),
                      (["--wide"], "unknown argument"), (["--tag", "x" * 41, "--names", "f"], "must be 1 to 40"), (["--tag"], "takes exactly one value"), (["--names", "f", "--tag", "a\\b"], "must be 1 to 40")):
        refuses(lambda: capull_args(bad), frag)
    root = tempfile.mkdtemp()
    old = S.CACHE
    S.CACHE = root
    try:
        N = ca_paths()
        W = ca_paths("wide")
        assert [os.path.basename(W[k]) for k in ("raw", "csv", "manifest")] == ["corporate_actions_wide_raw.jsonl", "corporate_actions_wide.csv", "corporate_actions_wide_manifest.json"] and W["dir"] == N["dir"]
        assert [os.path.basename(N[k]) for k in ("raw", "csv", "manifest")] == ["corporate_actions_raw.jsonl", "corporate_actions.csv", "corporate_actions_manifest.json"]
        for tag in ("raw", "manifest", "csv", "wide", "a_b", "X1", "prev"):                                  # no tagged file can be an untagged one
            assert not {ca_paths(tag)[k] for k in ("raw", "csv", "manifest")} & {N[k] for k in ("raw", "csv", "manifest")}, tag
        # ---- the names file
        f = os.path.join(root, "names.txt")
        open(f, "wb").write(b"\xef\xbb\xbf# a comment\r\nA\r\naa\r\n\r\nAABA\r\nA\r\nBRK.B\r\n   MSFT  \r\n")
        syms, info = read_names(f)
        assert syms == ["A", "AA", "AABA", "BRK.B", "MSFT"] and info["blank_or_comment_lines"] == 2 and info["duplicates_dropped"] == 1 and info["lowercase_folded"] == 1 and info["symbols"] == 5, info
        assert info["first"] == "A" and info["last"] == "MSFT" and info["sha256"] == sha_file(f) and info["bytes"] == os.path.getsize(f) and info["path"] == os.path.abspath(f)
        open(f, "wb").write(b"A\nAA\nAABA\nBRK.B\nMSFT")                                                    # LF, no trailing newline: the same symbols
        assert read_names(f)[0] == syms
        for body, frag in ((b"", "holds no symbol"), (b"# only a comment\n\n", "holds no symbol"), (b"AAPL,MSFT\n", "line 1"), (b"AAPL\nAA PL\n", "line 2"), (b"AAPL\nTOOLONGSYMBOL123\n", "line 2"),
                           (b"\xff\xfe\x00bad", "not UTF-8"), (b"AAPL\nB/C\n", "line 2")):
            open(f, "wb").write(body)
            refuses(lambda: read_names(f), frag)
        refuses(lambda: read_names(os.path.join(root, "absent.txt")), "is not on file")
        # ---- the stop on rejected symbols scales with the list (the wide pull's cap is 2% of the names when that is more than CA_MAXBAD); the whole pull through a mocked transport
        recs = [("cash_dividend", {"symbol": s, "rate": 0.1, "ex_date": f"2024-{k + 1:02d}-10"}) for s in ("A", "B", "C", "D") for k in range(12)] + [("name_change", {"old_symbol": "A", "new_symbol": "A2", "process_date": "2024-03-01"}),
                ("cash_dividend", {"symbol": "A2", "rate": 0.2, "ex_date": "2024-05-10"})]
        bad = tuple(f"B{n:02d}" for n in range(12))

        def names_file(n_extra, with_bad=True):
            p = os.path.join(root, f"names_{n_extra}.txt")
            body = ["a", "B", "C", "D"] + (list(bad) if with_bad else []) + [f"N{n:04d}" for n in range(n_extra)]
            open(p, "wb").write(("\r\n".join(body) + "\r\n").encode())
            return p, [s.upper() for s in body]
        nf, ns = names_file(0)
        buf = io.StringIO()
        fg = FakeGet(recs, size=2, bad=bad)
        with A.patched(S, keys=lambda: ("k", "s"), _get=fg), contextlib.redirect_stdout(buf):
            man = capull("--names", nf, "--tag", "t1")
        txt = buf.getvalue()
        T1 = ca_paths("t1")
        assert all(os.path.exists(T1[k]) for k in ("raw", "csv", "manifest")) and not [x for x in os.listdir(T1["dir"]) if x.endswith(".part")], "files renamed into place, no .part left"
        assert not any(os.path.exists(N[k]) for k in ("raw", "csv", "manifest")), "a wide pull never writes the NDX pull's files"
        assert man["mode"] == "wide" and man["tag"] == "t1" and man["names_file"]["sha256"] == sha_file(nf) == read_json(T1["manifest"])["names_file"]["sha256"] and man["names_file"]["symbols"] == len(ns) == man["tickers_round1"]
        assert man["names_round2"] == 1 and man["rejected_symbols"] == sorted(bad) and man["rows"] == len(recs) and man["max_rejected_symbols"] == CA_MAXBAD, man
        assert man["sha256"] == {"corporate_actions_t1_raw.jsonl": sha_file(T1["raw"]), "corporate_actions_t1.csv": sha_file(T1["csv"])} == read_json(T1["manifest"])["sha256"]
        assert any(c["symbols"] == "A2" for c in fg.calls if "page_token" not in c) and "names file names_0.txt (tag t1)" in txt and "  ... 20 requests, 20 pages" in txt and "capull done" in txt, txt
        calw, infow = load_calendar(CUT_A, tag="t1")
        assert infow["pinned"] is None and infow["rows_on_file"] == len(recs) and infow["raw_sha256"] == man["sha256"]["corporate_actions_t1_raw.jsonl"]
        # the overwrite refusal is per tag; --force replaces this tag's pull only and keeps its old files
        calls0 = len(fg.calls)
        with A.patched(S, keys=lambda: ("k", "s"), _get=fg):
            refuses(lambda: capull("--names", nf, "--tag", "t1"), "already on file for tag 't1'")
            assert len(fg.calls) == calls0, "refused before any request"
            with contextlib.redirect_stdout(io.StringIO()):
                man2 = capull("--names", nf, "--tag", "t2")
                man3 = capull("--force", "--names", nf, "--tag", "t1")
        assert all(os.path.exists(ca_paths("t2")[k]) for k in ("raw", "csv", "manifest")) and man3["sha256"] == man["sha256"] and man2["tag"] == "t2", "the same pages give the same file"
        prev = [x for x in os.listdir(T1["dir"]) if ".prev-" in x]
        assert len(prev) == 3 and all(x.startswith("corporate_actions_t1") for x in prev), prev
        assert not any(os.path.exists(N[k]) for k in ("raw", "csv", "manifest")), "still no NDX file"
        # --probe with a names file: the names report, one request, nothing saved
        before = sorted(os.listdir(T1["dir"]))
        fg4 = FakeGet(recs, size=10)
        buf = io.StringIO()
        with A.patched(S, keys=lambda: ("k", "s"), _get=fg4), contextlib.redirect_stdout(buf):
            capull("--names", nf, "--tag", "t4", "--probe")
        assert len(fg4.calls) == 1 and sorted(os.listdir(T1["dir"])) == before and "names file names_0.txt (tag t4)" in buf.getvalue() and "HTTP status: 200" in buf.getvalue()
        # a bad names file stops before any key is touched or request made
        with A.patched(S, keys=lambda: (_ for _ in ()).throw(AssertionError("keys read")), _get=fg4):
            refuses(lambda: capull("--names", os.path.join(root, "absent.txt"), "--tag", "t5"), "is not on file")
        # ---- the cap: 12 rejected names of 16 symbols stop a pull capped at 10; the same 12 among 700 symbols (cap 2% = 14) do not
        with A.patched(me, CA_MAXBAD=10):
            nf16, _ = names_file(0)
            with A.patched(S, keys=lambda: ("k", "s"), _get=FakeGet(recs, size=2, bad=bad)):
                refuses(lambda: capull("--names", nf16, "--tag", "t6"), "more than 10 symbols rejected")
            assert not os.path.exists(ca_paths("t6")["manifest"]) and os.path.exists(ca_paths("t6")["raw"] + ".part"), "nothing renamed into place; the partial raw file stays"
            nf700, ns700 = names_file(684)
            assert len(ns700) == 700
            with A.patched(S, keys=lambda: ("k", "s"), _get=FakeGet(recs, size=2, bad=bad)), contextlib.redirect_stdout(io.StringIO()):
                man7 = capull("--names", nf700, "--tag", "t7")
            assert man7["max_rejected_symbols"] == 14 and len(man7["rejected_symbols"]) == 12 and man7["tickers_round1"] == 700 and man7["rows"] == len(recs), man7["max_rejected_symbols"]
    finally:
        S.CACHE = old


def t_calendar_loader():
    root = tempfile.mkdtemp()
    old = S.CACHE
    S.CACHE = root
    try:
        P = ca_paths()
        try:
            load_calendar(CUT_A)
            raise AssertionError("a missing calendar must refuse")
        except SystemExit as e:
            assert "not on file" in str(e)
        assert load_calendar(CUT_A, need=False) == (None, {"present": False})
        os.makedirs(P["dir"])
        me = sys.modules[__name__]
        rows, _ = ca_rows([("cash_dividend", {"symbol": "A", "rate": 1.0, "ex_date": "2024-03-08"}), ("cash_dividend", {"symbol": "A", "rate": 1.0, "ex_date": "2025-07-15"}),
                           ("forward_split", {"symbol": "B", "new_rate": 2, "old_rate": 1, "ex_date": "2026-01-05"}), ("name_change", {"old_symbol": "OLD", "new_symbol": "NEW", "process_date": "2026-02-02"}),
                           ("forward_split", {"symbol": "C", "new_rate": 2, "old_rate": 1})])
        ca_write_csv(rows, P["csv"])
        man = {"sha256": {"corporate_actions.csv": sha_file(P["csv"])}, "created": "x"}
        json.dump(man, open(P["manifest"], "w"))
        pins = {"CAL_CSV_SHA": sha_file(P["csv"]), "CAL_RAW_SHA": "0" * 64}
        _, i0_ = load_calendar(CUT_A, need=False)                                                     # dryload: no raw file, the real pins: reported, never a refusal
        assert i0_["pinned"] == {"csv": False, "raw": False} and i0_["warnings"] == ["the raw jsonl is not on file"]
        with A.patched(me, **pins):
            try:
                load_calendar(CUT_A)
                raise AssertionError("[MANAGER #58] the pinned raw file is not on file: stage_a / stage_b must refuse")
            except SystemExit as e:
                assert "pre-registration pins" in str(e) and "NOT ON FILE" in str(e) and "is the pinned file" in str(e), str(e)
        open(P["raw"], "w").write("{}\n")
        man["sha256"]["corporate_actions_raw.jsonl"] = sha_file(P["raw"])
        json.dump(man, open(P["manifest"], "w"))
        pins = {"CAL_CSV_SHA": sha_file(P["csv"]), "CAL_RAW_SHA": sha_file(P["raw"])}
        with A.patched(me, **pins):
            cal, info = load_calendar(CUT_A)
            assert info["csv_sha256"] == man["sha256"]["corporate_actions.csv"] and info["rows_on_file"] == 5 and info["rows_without_ex_date"] == 1 and info["warnings"] == [] and info["pinned"] == {"csv": True, "raw": True}
            assert sorted(zip(cal["type"], cal["symbol"] + cal["old_symbol"])) == [("cash_dividend", "A"), ("name_change", "OLD")], \
                "cut at read time: an ex-date on/after 2025-06-30 is gone, a name change of any date stays (identity only), a row with no ex-date is unusable"
            assert cal.loc[cal["type"] == "name_change", "ev"].iloc[0] == TS("2026-02-02") and cal.loc[cal["type"] == "cash_dividend", "ev"].iloc[0] == TS("2024-03-08")
            cal2, _ = load_calendar(CUT_B)
            assert len(cal2) == 4 and (cal2["ev"].dropna() < CUT_B).all()
        for which, frag in (("CAL_CSV_SHA", "corporate_actions.csv sha256"), ("CAL_RAW_SHA", "corporate_actions_raw.jsonl sha256")):          # [MANAGER #58] a file that is not the pinned one refuses, the manifest agreeing or not
            with A.patched(me, **{**pins, which: "0" * 64}):
                try:
                    load_calendar(CUT_A)
                    raise AssertionError(f"{which}: a file that is not the pinned one must refuse")
                except SystemExit as e:
                    assert "pre-registration pins" in str(e) and "DIFFERS from the pinned" in str(e) and frag in str(e) and "lockbox NOT read" in str(e), str(e)
                _, i1_ = load_calendar(CUT_A, need=False)
                assert i1_["pinned"] == {"csv": which != "CAL_CSV_SHA", "raw": which != "CAL_RAW_SHA"}, "dryload only reports it"
        try:
            load_calendar(CUT_A)                                                                      # the REAL pins against this synthetic calendar
            raise AssertionError("the real pins must refuse a synthetic calendar")
        except SystemExit as e:
            assert "pre-registration pins" in str(e)
        # a WIDE pull's calendar: the manifest check alone - the pins are the NDX pull's - and the NDX files are not read
        Pw = ca_paths("wide")
        ca_write_csv(rows[:2], Pw["csv"])
        open(Pw["raw"], "w").write("{}\n")
        json.dump({"sha256": {"corporate_actions_wide.csv": sha_file(Pw["csv"]), "corporate_actions_wide_raw.jsonl": sha_file(Pw["raw"])}}, open(Pw["manifest"], "w"))
        calw, infow = load_calendar(CUT_A, tag="wide")
        assert infow["pinned"] is None and infow["tag"] == "wide" and infow["rows_on_file"] == 2 and len(calw) <= 2 and infow["warnings"] == [], infow
        assert load_calendar(CUT_A, need=False, tag="nope") == (None, {"present": False})
        try:
            load_calendar(CUT_A, tag="nope")
            raise AssertionError("a tag with no pull must refuse")
        except SystemExit as e:
            assert "not on file" in str(e) and "--tag nope" in str(e)
        open(Pw["csv"], "a").write("tampered\n")
        try:
            load_calendar(CUT_A, tag="wide")
            raise AssertionError("a tagged csv that differs from its manifest must refuse")
        except SystemExit as e:
            assert "corporate_actions_wide.csv does not match the sha256" in str(e)
        with A.patched(me, **pins):
            open(P["csv"], "a").write("tampered\n")                                                  # the manifest check comes before the pin check
            try:
                load_calendar(CUT_A)
                raise AssertionError("a csv that differs from its manifest must refuse")
            except SystemExit as e:
                assert "does not match the sha256" in str(e)
            ca_write_csv(rows, P["csv"])
            open(P["raw"], "w").write("{x}\n")
            try:
                load_calendar(CUT_A)
                raise AssertionError("a raw file that differs from its manifest must refuse")
            except SystemExit as e:
                assert "corporate_actions_raw.jsonl" in str(e) and "manifest" in str(e)
    finally:
        S.CACHE = old


def t_symbol_map():
    nxt = chain_next(pd.DataFrame({"type": ["name_change", "name_change", "cash_dividend", "name_change"], "old_symbol": ["FB", "META", "", "X"], "new_symbol": ["META", "META2", "", "X"],
                                   "proc": pd.to_datetime(["2022-06-09", "2030-01-01", None, "2020-01-01"])}))
    assert nxt == {"FB": "META", "META": "META2"} and chain_next(None) == {} and forward_chain("FB", nxt) == ["FB", "META", "META2"] and forward_chain("Q", nxt) == ["Q"]
    assert forward_chain("A", {"A": "B", "B": "A"}) == ["A", "B"], "a cycle stops"
    cal = pd.DataFrame({"type": ["name_change", "name_change"], "old_symbol": ["FB", "PCLN"], "new_symbol": ["META", "BKNG"], "proc": pd.to_datetime(["2022-06-09", "2018-03-01"])})
    comp = alias_components(cal)
    assert comp["FB"] == comp["META"] == frozenset({"FB", "META"}) and comp["PCLN"] == frozenset({"PCLN", "BKNG"}) and "AAPL" not in comp and alias_components(None) == {}
    T = 6
    od_k = np.full((T, 4), np.nan)
    od_k[:, 1] = 100.0                                   # K1 = META: bars every session
    od_k[:, 2] = [50, 50, 50, 50, 50, 50]                # K2 = AAPL
    od_k[:, 3] = [100, 100, 100, 100, np.nan, 100]       # K3 = a second candidate that has data too
    o930 = np.full((T, 5), np.nan)
    o930[:, 0] = [100.0, 100.10, 100.11, 99.90, 99.89, np.nan]        # FB: no K0 bars - the chain (K1) is the only candidate with data; the 0.10% boundary on K1 [TV X1]
    o930[:, 1] = 50.0                                                  # AAPL: the same ticker passes
    o930[:, 2] = 100.0                                                 # a name whose candidates are [K3, K1]: same ticker first
    o930[:, 3] = 120.0                                                 # a name with data that never agrees
    o930[:, 4] = 100.0                                                 # a name with no candidate at all
    ksel, nodata = choose_map(o930, od_k, [[0, 1], [2], [3, 1], [2], []])
    assert ksel[:, 0].tolist() == [1, 1, -1, 1, -1, -1], ksel[:, 0]        # 100.10 vs 100 passes (exactly 0.10%), 100.11 fails, 99.90 passes, 99.89 fails, no 09:30 bar fails
    assert (ksel[:, 1] == 2).all() and ksel[:, 2].tolist() == [3, 3, 3, 3, 1, 3], "the same ticker first (column 3); when its bar is missing the chain's candidate takes over"
    assert (ksel[:, 3] == -1).all() and not nodata[:, 3].any(), "data but no agreement: a disagreement, not 'no data'"
    assert (ksel[:, 4] == -1).all() and nodata[:, 4].all() and not nodata[:, 0].any() and nodata[:, 1:3].sum() == 0
    cks = [[0, 1], [2], [3, 1], [2], []]
    kw = fallback_map(od_k, cks, ksel)
    assert kw[:, 0].tolist() == [1] * 6 and kw[:, 3].tolist() == [2] * 6 and (kw[:, 4] == -1).all() and (kw[:, 1] == 2).all() and kw[:, 2].tolist() == [3, 3, 3, 3, 1, 3], \
        "[TV X2] the waived map: the chosen symbol where the check passed, else the first candidate (the same ticker first) with an official open; -1 = no data at all"
    assert ((ksel >= 0) <= (kw >= 0)).all() and (kw[ksel >= 0] == ksel[ksel >= 0]).all(), "a name-day that passed keeps its symbol"
    assert identity_ok(100.10, 100.0) and not identity_ok(100.11, 100.0) and identity_ok(5.01, 5.0) and not identity_ok(5.02, 5.0) and identity_ok(1000.99, 1000.0) and not identity_ok(1001.01, 1000.0), \
        "[TV X1] max(1 cent, 0.10% of the official open)"
    assert identity_ok(100.01, 100.0) and identity_ok(1.01, 1.0) and identity_ok(0.50, 0.51) and not identity_ok(1.02, 1.0), "a cent always passes (the floor), float noise inside it included"
    assert not identity_ok(np.nan, 1.0) and not identity_ok(1.0, np.nan) and identity_ok(np.array([10.0, 20.0]), np.array([10.0, 20.03])).tolist() == [True, False]
    a = np.arange(12.0).reshape(6, 2)
    ks = np.array([[0, -1], [1, 0], [-1, -1], [0, 1], [1, 1], [0, 0]])
    g = gather(a, ks)
    assert np.isnan(g[0, 1]) and g[1, 0] == a[1, 1] == 3.0 and g[1, 1] == a[1, 0] and np.isnan(g[2]).all() and g[3, 1] == a[3, 1] and g.shape == (6, 2)
    assert gather(a > 5, ks).dtype == bool and not gather(a > 5, ks)[2].any(), "boolean arrays gather to False where no symbol was chosen"


def t_calendar_flags():
    days = pd.bdate_range("2024-03-04", periods=10)
    tick = np.array(["N0", "N1", "FB", "N3"], dtype=object)
    cal = pd.DataFrame({"type": ["cash_dividend", "forward_split", "cash_dividend", "stock_dividend", "spin_off", "cash_dividend", "unit_split", "name_change", "forward_split"],
                        "symbol": ["N0", "META", "N1", "N3", "N0", "N0", "", "", "N0"], "old_symbol": ["", "", "", "", "", "", "UA", "FB", ""], "new_symbol": ["", "", "", "", "SPUN", "", "N3", "META", ""],
                        "ev": pd.to_datetime(["2024-03-08", "2024-03-06", "2024-03-09", "2024-03-05", "2024-03-12", "2024-02-01", "2024-03-07", "2022-06-09", "2024-03-20"])})
    comp = alias_components(cal)
    exdiv, split = cal_flags(cal, tick, days, comp)
    assert exdiv.shape == (10, 4) and split.shape == (10, 4)
    got = sorted((str(days[r].date()), tick[c]) for r, c in np.argwhere(exdiv))
    assert got == [("2024-03-05", "N3"), ("2024-03-08", "N0"), ("2024-03-11", "N1"), ("2024-03-12", "N0")], got      # a Saturday ex-date reads the next session (Monday); the spin-off's ex-date; one before the data is ignored
    sp = sorted((str(days[r].date()), tick[c]) for r, c in np.argwhere(split))
    assert sp == [("2024-03-06", "FB"), ("2024-03-07", "N3")], sp                                                       # META's split attaches to FB (the same company); a unit split to its new_symbol; one after the data is ignored
    e0, s0 = cal_flags(None, tick, days, {})
    assert not e0.any() and not s0.any()
    bt = exdiv_by_type(cal, tick, days, comp)
    asl = lambda m: sorted((str(days[r].date()), tick[c]) for r, c in np.argwhere(m))
    assert set(bt) == set(DIV_TYPES) and asl(bt["cash_dividend"]) == [("2024-03-08", "N0"), ("2024-03-11", "N1")] and asl(bt["stock_dividend"]) == [("2024-03-05", "N3")] and asl(bt["spin_off"]) == [("2024-03-12", "N0")], \
        "the ex-dividend flags apart by type: cash dividends, stock dividends, spin-offs"
    assert (bt["cash_dividend"] | bt["stock_dividend"] | bt["spin_off"] == exdiv).all() and not any(m.any() for m in exdiv_by_type(None, tick, days, {}).values())


def t_windows():
    a = np.zeros((14, 2), bool)
    a[4, 0] = True
    r = roll_any(a)
    assert np.flatnonzero(r[:, 0]).tolist() == [4, 5, 6, 7, 8, 9] and not r[:, 1].any(), "a flag on session s excludes sessions s .. s+5 (a name's window t-5 .. t holds it)"
    p = roll_any(a, FLAG_WIN - 1, lag=1)
    assert np.flatnonzero(p[:, 0]).tolist() == [5, 6, 7, 8, 9], "the prior-only variant (t-5 .. t-1): the day-t flag alone does not count"
    pv = prev(np.array([[1.0], [2.0]]))
    assert np.isnan(pv[0, 0]) and pv[1, 0] == 1.0
    assert prev(np.array([[True], [False]])).tolist() == [[False], [True]]
    nr = _near(np.array([[0, 1, 0, 0, 0, 1]], bool).T)
    assert nr[:, 0].tolist() == [True, True, True, False, True, True]


def t_gap():
    assert abs(float(split_safe_gap(51.0, 100.0, 1.0, 2.0)) - 0.02) < 1e-12 and abs(51.0 / 100.0 - 1 + 0.49) < 1e-12, "2-for-1 between the prints: +2%, a naive book reads -49%"
    assert abs(float(split_safe_gap(100.0, 12.0, 1.0, 1.0 / 8.0)) - (12.5 / 12.0 - 1)) < 1e-12, "1-for-8 reverse split: the true +4.2%, not +733%"
    assert abs(float(split_safe_gap(103.0, 100.0, 1.0, 1.0)) - 0.03) < 1e-12 and np.isnan(split_safe_gap(1.0, np.nan, 1.0, 1.0)) and np.isnan(split_safe_gap(1.0, 1.0, np.nan, 1.0))


def t_universe():
    W = mini(14, 14)
    t = 3
    W.o930[t, 0] = np.nan                                  # 1 no_bar (09:30)
    W.o935[t, 1] = np.nan                                  # 1 no_bar (09:35)
    W.nodata[t, 2] = True                                  # 2 map_nodata
    W.ksel[t, 3] = -1                                      # 3 map_open
    W.Cl_prev[t, 4] = np.nan                               # 4 no_prior
    W.F_prev[t, 5] = np.nan                                # 5 no_factor
    W.exdiv[t, 6] = True                                   # 6 ex_div
    W.cal6[t, 7] = True                                    # 7 split_cal
    W.reg6[t, 8] = True                                    # 8 split_reg
    W.gap6[t, 9] = True                                    # 9 split_gap
    W.tbis6_prior[t, 10] = True                            # 10 split_tbis (the registered window t-5 .. t-1, [NOISE H1])
    W.g506[t, 11] = True                                   # 11 gap50
    W.audit[t, 12] = True                                  # 12 audit
    W.member[t, 13] = False                                # not a member
    why = why_codes(W)
    assert why[t].tolist() == [1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, -1] and not why[t + 1].any() and (why[:t] == 0).all() and len(WHY) == 13
    U = universe(W)
    assert not U.elig[t].any() and U.elig[t + 1].all() and U.elig[:t].all()
    W2 = mini(14, 3)
    W2.exdiv[5, 0] = W2.reg6[5, 0] = W2.audit[5, 0] = True
    assert why_codes(W2)[5, 0] == 6, "the FIRST failing rule is the one counted (ex-dividend before the split flags and the audit)"
    W2.exdiv[5, 0] = False
    assert why_codes(W2)[5, 0] == 8 and why_codes(W2, tbis=np.ones((14, 3), bool))[0, 0] == 10, "the TBIS window can be swapped (the H1 variant)"
    W3 = mini(14, 3)
    W3.tbis6[6, 0] = True                                 # a flag dated t itself: in the window t-5 .. t, not in the registered t-5 .. t-1 (its volume ratio needs a full session)
    assert why_codes(W3)[6, 0] == 0 and why_codes(W3, W3.tbis6)[6, 0] == 10, "[NOISE H1] the registered TBIS window is t-5 .. t-1; the draft's t-5 .. t is the swapped variant"
    W3.gap6[6, 0] = W3.reg6[6, 1] = W3.g506[6, 2] = True
    assert why_codes(W3)[6].tolist() == [9, 8, 11], "the gap scan, the registered split and the +-50% rule stay on t (known by the open)"


def t_cells():
    k = 2
    W = mini(8, 9)
    gap = np.array([0.05, -0.03, 0.00, 0.02, -0.10, 0.12, 0.01, -0.01, 0.03])      # median 0.01
    W.gap[4] = gap
    W.Cl[4] = 100.0 + np.arange(9)
    W.o935[4] = 100.0
    U = SimpleNamespace(elig=np.zeros((8, 9), bool))
    U.elig[4] = True                                                                # only session 4 has a universe
    W.beta[4] = [np.nan, 1, 1, 1, 1, 1, 1, 1, 1]
    rows = np.arange(8)
    R = run_cells(W, U, rows, 8, 2, k=k)
    p = R.nd[("P", "ALL")]
    assert p["i"].tolist() == [4] * 4 and p["x"].tolist() == [4, 1, 0, 5] and p["side"].tolist() == [1, 1, -1, -1], (p["x"].tolist(), p["side"].tolist())
    assert np.allclose(p["g"], [-0.11, -0.04, 0.04, 0.11]) and np.allclose(p["gap"], gap[[4, 1, 0, 5]]) and np.allclose(p["c"], 100.0 + np.array([4, 1, 0, 5])) and (p["o"] == 100.0).all()
    c8 = R.nd[("P", "CAP8")]
    assert c8["x"].tolist() == [1, 7, 8, 0] and c8["side"].tolist() == [1, 1, -1, -1], "CAP8: |g| <= 8% drops the two 11% gappers; the pool's two lowest are long, its two highest short"
    m = R.nd[("M", "ALL")]
    assert m["x"].tolist() == [0, 5, 4, 1] and m["side"].tolist() == [1, 1, -1, -1], "the mirror: the opposite baskets"
    t = R.nd[("T", "ALL")]
    assert t["x"].tolist() == [4, 1, 8, 5] and np.allclose(t["g"], gap[[4, 1, 8, 5]] - 1.0 * 0.01), "twin: beta 1 reads like the primary, a name with no beta is out of its pool"
    W.gap[4, 3] = 0.01 + CAP                                                         # name 3 at |g| = 8% exactly (the median stays 0.01): inside CAP8, the pool's highest g, so a short
    R = run_cells(W, U, rows, 8, 2, k=k)
    assert R.nd[("P", "CAP8")]["x"].tolist() == [1, 7, 0, 3], "the 8% edge belongs to CAP8 (|g| <= 8%)"
    W.gap[4, 3] = 0.01 + CAP + 1e-6
    R = run_cells(W, U, rows, 8, 2, k=k)
    assert R.nd[("P", "CAP8")]["x"].tolist() == [1, 7, 8, 0], "just beyond 8% it is out"
    W.gap[4] = gap
    U.elig[4] = False
    U.elig[4, [0, 1, 2]] = True                                                      # three names: under 2k = 4
    R = run_cells(W, U, rows, 8, 2, k=k)
    assert len(R.nd[("P", "ALL")]["i"]) == 0 and len(R.nd[("P", "CAP8")]["i"]) == 0, "a pool under 2k names cannot fill both sides: no trade"
    U.elig[4] = True
    R = run_cells(W, U, rows, 8, 5, k=k)
    assert len(R.nd[("P", "ALL")]["i"]) == 0, "sessions before i0 are not run"
    # a CAP8 pool that shrinks below 2k while ALL still trades
    W2 = mini(6, 6)
    W2.gap[3] = [0.0, 0.01, -0.01, 0.2, -0.2, 0.3]
    U2 = SimpleNamespace(elig=np.zeros((6, 6), bool))
    U2.elig[3] = True
    R2 = run_cells(W2, U2, np.arange(6), 6, 0, k=2, twin=False)
    assert len(R2.nd[("P", "ALL")]["i"]) == 4 and len(R2.nd[("P", "CAP8")]["i"]) == 0, "CAP8 keeps 3 names (|g| <= 8%): no basket; ALL still trades"


def t_costs():
    lng, sht = name_pnl(1.0, 100.0, 102.0, COST["base"]), name_pnl(-1.0, 100.0, 102.0, COST["base"])
    assert abs(lng - (100.0 - 5.0 - 2.55)) < 1e-9 and abs(sht - (-100.0 - 5.0 - 2.55)) < 1e-9, (lng, sht)            # 50 shares: exit value 5,100; 10 bps of 5,000 in, 5 bps of 5,100 out
    assert abs(name_pnl(1.0, 100.0, 102.0, COST["stress"]) - (100.0 - 10.0 - 5.1)) < 1e-9 and abs(name_pnl(-1.0, 100.0, 102.0, COST["stress"]) - (-100.0 - 10.0 - 5.1)) < 1e-9
    assert abs(cents_pnl(1.0, 100.0, 102.0) - (100.0 - 50 * 2 * 0.0135)) < 1e-9 and abs(cents_pnl(-1.0, 100.0, 102.0) - (-100.0 - 50 * 2 * 0.0135)) < 1e-9, "SIPORB's cents: 1.35 cents a share a side"
    assert abs(name_pnl(1.0, 20.0, 20.0, (0.0, 0.0))) < 1e-9 and np.allclose(name_pnl(np.array([1.0, -1.0]), np.array([10.0, 10.0]), np.array([11.0, 11.0]), (0, 0)), [500.0, -500.0]), "fractional shares: $5,000 buys 500 at $10"


def t_null():
    rng = np.random.default_rng(1)
    d = draw_picks(rng, 10, 3, 200)
    assert d.shape == (200, 6) and (d >= 0).all() and (d < 10).all() and all(len(set(r)) == 6 for r in d.tolist()), "2k distinct names a draw"
    assert (draw_picks(np.random.default_rng(1), 10, 3, 200) == d).all(), "seeded"
    big = draw_picks(np.random.default_rng(2), 10, 3, 60000)
    lg, sh = np.bincount(big[:, :3].ravel(), minlength=10) / 60000.0, np.bincount(big[:, 3:].ravel(), minlength=10) / 60000.0
    assert np.abs(lg - 0.3).max() < 0.01 and np.abs(sh - 0.3).max() < 0.01, (lg, sh)                  # uniform: each name is long in 3 of 10 draws and short in 3 of 10
    try:
        draw_picks(rng, 5, 3, 2)
        raise AssertionError("cannot draw 6 of 5")
    except ValueError:
        pass
    T, X, k = 10, 12, 2
    W = mini(T, X)
    W.gap[3:] = np.random.default_rng(3).normal(0.0, 0.02, (T - 3, X))
    W.Cl = 100.0 * (1 + np.random.default_rng(4).normal(0, 0.02, (T, X)))
    W.Cl[3:, 4:6] = 200.0                                                             # two names that gapped far (|g| >> 8% by construction below) and made +100%
    W.gap[3:, 4:6] = 0.30
    U = SimpleNamespace(elig=np.ones((T, X), bool))
    U.elig[:3] = False
    rows = np.arange(T)
    R = run_cells(W, U, rows, T, 3, nreps=3000, seed=11, k=k, twin=False)
    assert R.acc["ALL"].shape == (3000, T) and (R.acc["ALL"][:, :3] == 0).all()
    assert R.acc["CAP8"].max() < 4000.0 <= R.acc["ALL"].max(), "the two +100% names are outside CAP8's pool (|g| >> 8%) but inside ALL's: only ALL's draws can book a +$4,000 position"
    exp = {}
    for c in CELLS:
        e = 0.0
        for i in range(3, T):
            g = W.gap[i] - np.median(W.gap[i])
            pool = np.arange(X) if c == "ALL" else np.flatnonzero(np.abs(g) <= CAP + 1e-12)
            lp, sp = name_pnl(1.0, W.o935[i], W.Cl[i], COST["base"]), name_pnl(-1.0, W.o935[i], W.Cl[i], COST["base"])
            e += k * lp[pool].mean() + k * sp[pool].mean()
        tot = R.acc[c].sum(axis=1)
        assert abs(tot.mean() - e) < 5 * tot.std() / np.sqrt(len(tot)), (c, tot.mean(), e, tot.std())
        exp[c] = e
    assert R.acc["ALL"].std() > 3 * R.acc["CAP8"].std()
    a1, a2 = run_cells(W, U, rows, T, 3, nreps=20, seed=7, k=k, twin=False), run_cells(W, U, rows, T, 3, nreps=20, seed=7, k=k, twin=False)
    assert (a1.acc["ALL"] == a2.acc["ALL"]).all() and (a1.acc["CAP8"] == a2.acc["CAP8"]).all(), "the null is seeded"
    # CAP8's pool for the null is the |g| <= 8% names: with the two +100% names out of it, no CAP8 draw can contain them
    wn = mini(6, 8)
    wn.gap[3] = [0.0, 0.01, -0.01, 0.0, 0.02, -0.02, 0.4, -0.4]
    wn.Cl[3] = [100, 100, 100, 100, 100, 100, 150, 50]
    un = SimpleNamespace(elig=np.ones((6, 8), bool))
    rn = run_cells(wn, un, np.arange(6), 6, 3, nreps=400, seed=5, k=2, twin=False)
    assert np.allclose(rn.acc["CAP8"][:, 3], -(5.0 + 2.5) * 4), "no CAP8 draw can hold a name outside |g| <= 8%: every draw is four flat positions paying costs"
    assert rn.acc["ALL"][:, 3].std() > 100.0


def t_stats():
    idx = pd.bdate_range("2016-07-01", PRE_END)
    B = book_stub(idx)
    dts = ["2017-01-16", "2018-01-16", "2019-01-16", "2020-01-16", "2020-03-16", "2021-01-19", "2022-01-17", "2023-01-16", "2024-01-16", "2025-01-16"]
    ses = idx.get_indexer(pd.DatetimeIndex(dts))
    assert (ses >= 0).all()
    p = np.array([100.0, -50.0, 200.0, -10.0, 1000.0, 30.0, 80.0, -20.0, 400.0, 60.0])
    nd = {"i": ses}
    rows = np.arange(len(idx))
    st = cell_stats(B, nd, p, rows, WF0, PRE_END)
    x = np.zeros(len(idx))
    x[ses] = p
    ref = R11.stats(x, idx)
    assert st["name_days"] == 10 and st["sessions"] == 10 and abs(st["net"] - 1790.0) < 1e-9 and abs(st["roc"] - ref["roc"]) < 1e-9 and abs(st["sortino"] - ref["sort"]) < 1e-9 and abs(st["max_dd"] - ref["max_dd"]) < 1e-9
    assert abs(st["pf"] - 1870.0 / 80.0) < 1e-12 and abs(st["t"] - A.nw_t(p)) < 1e-12, "PF and Newey-West t (5 lags) on the traded sessions' series"
    assert abs(st["net_ex_best_days"] - (1790.0 - (1000 + 400 + 200 + 100 + 80))) < 1e-9, "without the 5 best days"
    assert st["best_pct_n"] == 1 and abs(st["net_ex_best_pct"] - 790.0) < 1e-9 and abs(st["net_ex_top_nameday"] - 790.0) < 1e-9 and st["top_nameday"] == 1000.0, "1% of 10 name-days = ceil(0.1) = 1 position"
    assert abs(st["net_ex_2020"] - 790.0) < 1e-9, "Feb 15 - Apr 30 2020 removed"
    assert st["years_pos"] == 7 and st["by_year"][2016] == 100.0 and st["by_year"][2017] == -50.0 and st["by_year"][2019] == 1000.0 - 10.0 and abs(st["halves"][0] - (100 - 50 + 200 - 10 + 1000)) < 1e-9 and abs(st["halves"][1] - 550.0) < 1e-9, st
    nd2 = {"i": np.concatenate([ses, ses[:1]])}                                         # two positions in one session: sessions 10, name-days 11, the best DAY is the sum
    st2 = cell_stats(B, nd2, np.concatenate([p, [500.0]]), rows, WF0, PRE_END)
    assert st2["name_days"] == 11 and st2["sessions"] == 10 and abs(st2["net_ex_best_days"] - (2290 - (1000 + 600 + 400 + 200 + 80))) < 1e-9 and st2["best_pct_n"] == 1
    e = cell_stats(B, {"i": np.zeros(0, np.int64)}, np.zeros(0), rows, WF0, PRE_END)
    assert e["name_days"] == 0 and e["sessions"] == 0 and e["net"] == 0.0 and np.isnan(e["pf"]) and e["years_pos"] == 0
    # the null's statistic is r11_risk.stats row by row, the max over the cells
    rng = np.random.default_rng(6)
    acc = {"ALL": rng.normal(5, 60, (7, len(idx))), "CAP8": rng.normal(2, 90, (7, len(idx)))}
    mx, rocs = null_stat(acc, B)
    for r in range(7):
        want = [R11.stats(acc[c][r], idx)["roc"] for c in CELLS]
        assert np.allclose(rocs[:, r], want) and abs(mx[r] - max(want)) < 1e-9
    assert np.isnan(np.fmax.reduce(np.array([[np.nan], [np.nan]]), axis=0)[0])
    # judge_a: every check (the twin veto included), NaN never passes; verdict_of; pick_cell
    good = {"sessions": 2000, "roc": 20.0, "pf": 1.2, "t": 2.5, "net_ex_best_days": 1.0, "net_ex_best_pct": 1.0, "years_pos": 6, "halves": [1.0, 1.0], "net_ex_2020": 1.0}
    mk_e = lambda c, mirror_roc=10.0, stress_net=5.0, tw_net=3.0, tws_net=2.0, tw_roc=12.0: {"base": {"stats": c}, "mirror": {"stats": {"roc": mirror_roc}}, "stress": {"stats": {"net": stress_net}},
                                                                                         "twin": {"stats": {"net": tw_net, "roc": tw_roc}}, "twin_stress": {"stats": {"net": tws_net, "roc": tw_roc}}}
    chk = judge_a(mk_e(good), 15.0, True)
    assert all(chk.values()) and len(chk) == 16 and "(c) ROC>null p97.5" in chk and {"twin net>0 base", "twin net>0 stress", "twin ROC >= half the primary's"} <= set(chk), list(chk)
    for key, bad in (("sessions", 1799), ("roc", 14.99), ("pf", 1.099), ("t", 1.99), ("net_ex_best_days", 0.0), ("net_ex_best_pct", -1.0), ("years_pos", 5), ("halves", [1.0, 0.0]), ("net_ex_2020", 0.0), ("roc", float("nan"))):
        assert not all(judge_a(mk_e({**good, key: bad}), 15.0, True).values()), key
    assert not judge_a(mk_e(good), 20.0, True)["(c) ROC>null p97.5"] and not judge_a(mk_e(good, mirror_roc=20.0), 15.0, True)["(d) beats its mirror"] and not judge_a(mk_e(good, stress_net=0.0), 15.0, True)["(e) net>0 at the stress costs"]
    assert not judge_a(mk_e(good), 15.0, False)["(h) hand audit complete"] and not judge_a(mk_e(good), float("nan"), True)["(c) ROC>null p97.5"]
    # [TV X4] the beta twin is a VETO: a primary that clears every other bar is stopped by a twin that is not positive at the base costs, not positive at the stress costs, or under half the primary's ROC
    for kw, name in (({"tw_net": 0.0}, "twin net>0 base"), ({"tws_net": -1.0}, "twin net>0 stress"), ({"tw_roc": 9.99}, "twin ROC >= half the primary's"), ({"tw_roc": float("nan")}, "twin ROC >= half the primary's")):
        c = judge_a(mk_e(good, **kw), 15.0, True)
        assert not c[name] and [k for k, v in c.items() if not v] == [name], (name, c)
        assert verdict_of(c, None, True) == (False, "FAIL"), "the twin alone stops a cell that clears every other bar"
    assert judge_a(mk_e(good, tw_roc=10.0), 15.0, True)["twin ROC >= half the primary's"], "exactly half the primary's ROC passes"
    with A.patched(sys.modules[__name__], RULES={**RULES, "twin": False}):
        assert all(judge_a(mk_e(good, tw_net=-5.0, tws_net=-5.0, tw_roc=-9.0), 15.0, True).values()), "the veto can be waived (smoke only)"
    assert verdict_of(chk, None, True) == (True, "PASS") and verdict_of(chk, None, False) == (True, "PENDING_AUDIT") and verdict_of(chk, chk, True) == (True, "PASS")
    bad2 = judge_a(mk_e(good, tw_net=0.0), 15.0, True)
    assert verdict_of(chk, bad2, True) == (False, "FAIL") and verdict_of(bad2, chk, True) == (False, "FAIL"), "[TV X2] a cell passes only if BOTH readings pass (either one alone stops it)"
    assert verdict_of(chk, {**chk, "(h) hand audit complete": False}, True) == (True, "PASS"), "(h) is the audit's flag, not a reading's check"
    mk = lambda pa, roc: {"stageA": {"PASS": pa, "stats": {"roc": roc}}}
    assert pick_cell({"ALL": mk(True, 20.0), "CAP8": mk(True, 25.0)}) == "CAP8" and pick_cell({"ALL": mk(True, 20.0), "CAP8": mk(False, 99.0)}) == "ALL", "[MANAGER #56] the higher WF ROC among the cells that PASSED Stage A"
    assert pick_cell({"ALL": mk(True, 20.0), "CAP8": mk(True, 20.0)}) == "ALL" and pick_cell({"ALL": mk(False, 20.0), "CAP8": mk(False, 20.0)}) is None
    m = bucket_masks(np.array([0.0, 0.0199, 0.02, 0.0399, 0.04, 0.08, 0.0800001, 0.5]))
    assert [int(v.sum()) for v in m.values()] == [2, 2, 2, 2] and list(m) == ["0-2%", "2-4%", "4-8%", ">8%"], "buckets 0-2, 2-4, 4-8 (closed at 8), > 8"


def t_c_rule():
    idx = pd.bdate_range("2016-07-01", PRE_END)
    rng = np.random.default_rng(8)
    B = book_stub(idx, rng.normal(40.0, 700.0, len(idx)))
    x = rng.normal(5.0, 90.0, len(idx)) * (rng.random(len(idx)) < 0.8)
    a = a2_eval(B, x)
    kc = B.mask(*C_ROWS)
    assert a["c_rows"] == int(kc.sum()) > 400 and abs(a["std_book"] - np.std(B.raw[kc], ddof=1)) < 1e-9
    assert abs(np.std((a["c"] * x)[kc], ddof=1) / np.std(B.raw[kc], ddof=1) - 0.25) < 1e-12, "c x the cell's daily std over the first two WF years = EXACTLY 25% of #463's"
    assert abs(a["by_mult"]["0.5"]["c"] - 0.5 * a["c"]) < 1e-12 and abs(a["by_mult"]["2"]["c"] - 2 * a["c"]) < 1e-12 and abs(a["by_mult"]["1"]["c"] - a["c"]) < 1e-12
    k = B.mask(WF0, PRE_END)
    s1 = R11.stats((B.raw + a["c"] * x)[k], idx[k])
    assert abs(a["book_roc"] - s1["roc"]) < 1e-9 and abs(a["book_sortino"] - s1["sort"]) < 1e-9 and abs(a["book_max_dd"] - s1["max_dd"]) < 1e-9
    assert a["book_shadow_line"] == all(a["checks"].values()) and len(a["checks"]) == 3
    # the A2 bars: ROC >= 98.5005, Sortino >= 3.816, max drawdown <= 1.10 x 44,849 - each one alone fails it
    with A.patched(sys.modules[__name__], RULES={**RULES, "a2_roc": -1e9, "a2_sort": -1e9, "a2_dd": 1e12}):
        assert a2_eval(B, x)["book_shadow_line"] is True
    for kk, v in (("a2_roc", 1e9), ("a2_sort", 1e9), ("a2_dd", -1.0)):
        with A.patched(sys.modules[__name__], RULES={**RULES, "a2_roc": -1e9, "a2_sort": -1e9, "a2_dd": 1e12, kk: v}):
            assert a2_eval(B, x)["book_shadow_line"] is False, kk
    z = a2_eval(B, np.zeros(len(idx)))
    assert not z["book_shadow_line"] and math.isnan(z["c"]), "a cell with no volatility has no c"


def t_map_point():
    x, dates = MDL.hand_book()
    B = book_stub(dates, x)
    rng = np.random.default_rng(9)
    y = rng.normal(0.0, 8.0, len(x)) - 0.7 * x
    mp = map_point(B, y, 1.0, dates[0], dates[-1])
    S0 = MDL.hand_stretch()
    rho, do = MDL.realised(y[None, :], S0)
    nr, nd = MDL.naive_rho_do(y, x, dates, S0.dd)
    assert abs(mp["rho_dd"] - rho[0]) < 1e-12 and abs(mp["do"] - do[0]) < 1e-12 and abs(mp["rho_dd"] - nr) < 1e-9 and abs(mp["do"] - nd) < 1e-9, "DO and rho_dd are r12_mdl's, and equal its independent implementation"
    assert abs(mp["roc"] - MDL.pstats(y, dates)["roc"]) < 1e-12 and mp["dd_days"] == S0.n_dd_days and mp["dd_weeks"] == S0.n_dd_weeks and abs(map_point(B, y, 2.0, dates[0], dates[-1])["do_at_c"] - 2.0 * do[0]) < 1e-12
    mp2 = map_point(B, -x, 1.0, dates[0], dates[-1])
    assert abs(mp2["do"] - 1.0) < 1e-9 and abs(mp2["rho_dd"] + 1.0) < 1e-9, "minus the book: DO +1 (earns what it loses), rho_dd -1"


def t_es():
    days = pd.bdate_range("2024-03-04", periods=3)
    lv = [5000.0, 5050.0, 5020.0]

    def frame(off):
        ts, o, c = [], [], []
        for d, l in zip(days, lv):
            for hm in range(570, 960, 5):
                ts.append(d + pd.Timedelta(minutes=hm)); o.append(l + off); c.append(l + off + 0.5)
        return pd.DataFrame({"open": o, "close": c}, index=pd.DatetimeIndex(ts).tz_localize("US/Eastern"))
    cc, oc = es_returns(days, {"raw": frame(1000.0), "adj": frame(0.0)})
    assert np.isnan(cc[0]) and np.isnan(oc[0]) and abs(cc[1] - 50.0 / 6000.5) < 1e-12 and abs(oc[1] - 0.5 / 6000.5) < 1e-12 and abs(cc[2] + 30.0 / 6050.5) < 1e-12, "(adj 16:00 change) / the prior RAW 16:00 print"
    xx, dates = MDL.hand_book()
    B = book_stub(dates, xx)
    rng = np.random.default_rng(10)
    r = rng.normal(0.0, 0.01, len(xx))
    r[0] = np.nan
    y = np.where(np.isfinite(r), 5000.0 * np.nan_to_num(r), 0.0)
    e = es_beta(B, y, np.arange(len(xx)), r, r, dates[0], dates[-1])
    assert set(e) == {"dd_weeks", "dd_days", "all_wf_rows"} and abs(e["all_wf_rows"]["cc"]["slope"] - 5000.0) < 1e-6 and abs(e["dd_days"]["oc"]["per_1pct"] - 50.0) < 1e-6 and e["dd_weeks"]["cc"]["n"] >= 3
    assert abs(e["all_wf_rows"]["cc"]["corr"] - 1.0) < 1e-9 and e["all_wf_rows"]["cc"]["n"] == len(xx) - 1 and np.isnan(ols([1, 2], [1, 2])["slope"]) and np.isnan(ols([1, 2, 3], [4, 4, 4])["slope"])


def t_betas():
    T, win = 14, 5
    rng = np.random.default_rng(12)
    m = rng.normal(0.0, 0.01, T)
    mult = np.array([1.5, -0.5, 1.0, 2.0, 0.2])
    ret = m[:, None] * mult[None, :]
    ret[6, 3] = np.nan
    beta, mkt = betas(ret, np.ones((T, 5), bool), win=win, min_names=3)
    assert np.allclose(np.delete(mkt, 6), np.delete(m, 6)), "with five members of multiples 1.5, -0.5, 1, 2, 0.2 the median return IS the factor m (row 6 lost a member)"
    assert np.isnan(beta[:win]).all(), "no beta before a full window"
    assert np.allclose(beta[win], mult, atol=1e-6) and np.allclose(beta[12], mult, atol=1e-6), "beta = the slope on the universe's median daily return over the previous 60 (here 5) sessions, t-5 .. t-1"
    assert np.isnan(beta[7:12, 3]).all() and np.isfinite(beta[7:12][:, [0, 1, 2, 4]]).all(), "a missing return inside the window: no beta for that name ('all present'), the others keep theirs"
    assert np.isfinite(beta[12, 3]), "once the gap has left the window the beta is back"
    b2, _ = betas(ret, np.zeros((T, 5), bool), win=win, min_names=3)
    assert np.isnan(b2).all(), "no members, no universe median, no beta"


def t_inputs():
    root = tempfile.mkdtemp()
    p = os.path.join(root, "open_bars.csv")
    lines = ["symbol,t,o,c,day",
             "AAA,2024-03-11T13:30:00Z,100.0,101.0,2024-03-11", "AAA,2024-03-11T13:35:00Z,101.0,102.0,2024-03-11", "AAA,2024-03-11T13:40:00Z,102.0,103.0,2024-03-11",
             "AAA,2024-01-10T14:30:00Z,50.0,51.0,2024-01-10", "AAA,2024-01-10T14:35:00Z,51.0,52.0,2024-01-10", "AAA,2024-01-10T14:35:00Z,52.0,52.5,2024-01-10",
             "BBB,2024-01-10T14:30:00Z,10.0,10.5,2024-01-10", "AAA,2025-06-30T13:30:00Z,1.0,1.0,2025-06-30", "AAA,2025-06-27T13:30:00Z,77.0,78.0,2025-06-27", "AAA,2025-06-27T13:00:00Z,7.0,8.0,2025-06-27"]
    open(p, "w").write("\n".join(lines) + "\n")
    df = read_cache(CUT_A, p)
    assert len(df) == 6 and df["day"].max() == TS("2025-06-27") and set(df["hm"]) == {570, 575}, df
    g = df.set_index(["symbol", "day", "hm"])["o"]
    assert g[("AAA", TS("2024-03-11"), 570)] == 100.0 and g[("AAA", TS("2024-03-11"), 575)] == 101.0 and g[("AAA", TS("2024-01-10"), 570)] == 50.0, "13:30Z in EDT and 14:30Z in EST are both 09:30 ET"
    assert g[("AAA", TS("2024-01-10"), 575)] == 52.0 and df.attrs["dup_dropped"] == 1 and ("AAA", TS("2025-06-30"), 570) not in g.index, "a duplicated bar keeps the last row; a day on/after the cut is never kept"
    assert len(read_cache(CUT_B, p)) == 7
    days = pd.DatetimeIndex(["2024-01-10", "2024-03-11"])
    o930, o935, info = cache_arrays(df, days, np.array(["AAA", "BBB", "CCC"], dtype=object))
    assert o930[0, 0] == 50.0 and o935[0, 0] == 52.0 and o930[1, 0] == 100.0 and o930[0, 1] == 10.0 and np.isnan(o935[0, 1]) and np.isnan(o930[:, 2]).all() and info["bars_off_grid"] == 1
    mem = pd.DataFrame({"ticker": ["FB", "META", "AAPL", "AAPL"], "from": ["2016-06-01", "2022-07-01", "2016-06-01", "2023-01-01"], "to": ["2022-07-01", "", "2020-05-01", ""]})
    mm = member_mask(pd.DatetimeIndex(["2016-05-31", "2016-06-01", "2022-06-30", "2022-07-01", "2020-04-30", "2020-05-01", "2023-01-02"]), np.array(["AAPL", "FB", "META"], dtype=object), mem)
    assert mm.tolist() == [[False, False, False], [True, True, False], [False, True, False], [False, False, True], [True, True, False], [False, True, False], [True, False, True]], mm.tolist()
    tp = os.path.join(root, "tbis.csv")
    open(tp, "w").write("symbol,day,price_ratio,vol_ratio,split_like\nAAA,2024-03-11,0.5,2.0,True\nBBB,2024-03-12,0.5,2.0,False\nCCC,2025-06-30,0.5,2.0,True\n")
    q = read_tbis(CUT_A, tp)
    assert len(q) == 2 and q["split_like"].tolist() == [True, False] and q["day"].max() < CUT_A, "the volume-confirmed rows are split_like; the list is cut at read time"
    try:
        read_tbis(CUT_A, os.path.join(root, "missing.csv"))
        raise AssertionError("a missing TBIS list must refuse")
    except SystemExit as e:
        assert "TBIS" in str(e)
    try:
        read_cache(CUT_A, os.path.join(root, "nope.csv"))
        raise AssertionError("a missing member cache must refuse")
    except SystemExit as e:
        assert "member cache" in str(e)


def t_hygiene():
    days = pd.bdate_range("2023-12-18", periods=14)                                       # 2023-12-18 .. 2024-01-04
    W = mini(14, 10)
    W.days = days
    W.o930[:, 9] = np.nan                                                                 # a name with no bars at all this period
    W.o930[:5, 9] = 100.0
    for t in range(0, 5):                                                                 # 2023: the identity check drops two names a day
        W.ksel[t, :2] = -1
    W.nodata[0:3, 2] = True                                                               # 2023: three member-days with no SIPORB bar at all (survivorship); 2024: four more
    W.nodata[10:14, 2] = True
    W.exdiv[11, 3] = True                                                                 # 2024 (rows 10 .. 13)
    W.reg6[12, 4] = True
    W.tbis6[13, 5] = True                                                                 # a TBIS flag dated t itself: the registered window t-5 .. t-1 does NOT hold it [NOISE H1]
    W.tbis6_prior[13, 5] = False
    W.tbis6[10, 6] = W.tbis6_prior[10, 6] = True                                          # one in both windows
    W.cal_ev[12, 4] = True                                                                # a calendar split the price rules also see (reg_ev on the same name-day) ...
    W.reg_ev[12, 4] = True
    W.cal_ev[13, 7] = True                                                                # ... and one they do not
    W.gap_ev[10, 8] = True                                                                # ... and a price event with no calendar split
    W.nodata_own, W.ksel_own = W.nodata.copy(), W.ksel.copy()                             # the same-ticker map alone: it also lacks name 2's no-data cells, and more
    W.nodata_own[0:2, 3] = True                                                           # 2023: N3's own ticker has no SIPORB bar on two sessions - the chain recovers both, the identity check passes
    W.nodata_own[1, 0] = True                                                             # 2023: N0's own ticker has none on one session, the chain recovers it but the identity check dropped it (ksel -1)
    W.nodata_own[12, 5] = True                                                            # 2024: N5, recovered and passing
    W.ksel_own[3, 6] = -1                                                                 # 2023: N6's own bar fails the identity check, a chain symbol passes: RESCUED
    W.ksel_own[11, 4] = -1                                                                # 2024: the same for N4
    W.exdiv_type = {"cash_dividend": W.exdiv.copy(), "stock_dividend": np.zeros_like(W.exdiv), "spin_off": np.zeros_like(W.exdiv)}
    U = universe(W)
    H = hygiene(W, U)
    assert H["sessions_by_year"] == {2023: 10, 2024: 4} and H["member_days_by_year"] == {2023: 100, 2024: 40}, H["member_days_by_year"]
    cr = H["chain_recovery"]
    assert cr["by_year"] == {2023: {"member_days": 100, "no_data_same_ticker": 6, "no_data_after_chain": 3, "recovered": 3, "recovered_identity_ok": 2, "rescued_from_identity_drop": 1},
                             2024: {"member_days": 40, "no_data_same_ticker": 5, "no_data_after_chain": 4, "recovered": 1, "recovered_identity_ok": 1, "rescued_from_identity_drop": 1}}, cr
    assert cr["tickers_recovered"] == {"N0": 1, "N3": 2, "N5": 1} and cr["tickers_rescued"] == {"N4": 1, "N6": 1} and cr["tickers_no_data_after_chain"] == {"N2": 7}, "no_data_same_ticker counts only member-days with both cache bars"
    assert H["ex_div_by_type"] == {"cash_dividend": {2023: 0, 2024: 1}, "stock_dividend": {2023: 0, 2024: 0}, "spin_off": {2023: 0, 2024: 0}}, H["ex_div_by_type"]
    f = H["excluded_first_rule_by_year"]
    assert f["map_open"] == {2023: 10, 2024: 0} and f["map_nodata"] == {2023: 3, 2024: 4} and f["ex_div"] == {2023: 0, 2024: 1} and f["split_reg"] == {2023: 0, 2024: 1} and f["split_tbis"] == {2023: 0, 2024: 1} \
        and f["no_bar"] == {2023: 5, 2024: 4}, f
    mp = H["symbol_map_by_year"]
    assert mp[2023]["identity_drops"] == 10 and mp[2023]["share"] == 0.1 and mp[2023]["no_data"] == 3 and abs(mp[2023]["no_data_share"] - 0.03) < 1e-12, mp[2023]
    assert mp[2024]["identity_drops"] == 0 and mp[2024]["share"] == 0 and mp[2024]["no_data"] == 4 and abs(mp[2024]["no_data_share"] - 0.1) < 1e-12, mp[2024]
    assert H["map_years_over_2pct"] == [2023], "[NOISE H3] the 2% rule counts the identity-check drops only: 2024 has 10% no-data member-days (the survivorship line) and is NOT named"
    assert H["tbis"]["registered_t5_to_t1_removals"] == {2023: 0, 2024: 1} and H["tbis"]["through_t_removals"] == {2023: 0, 2024: 2} and H["tbis"]["removed_only_by_a_flag_dated_t"] == {2023: 0, 2024: 1}, \
        "[NOISE H1] day-t removals counted under both windows; only the flag dated t itself (not also in the prior window) is the difference"
    cv = H["calendar_vs_price"]
    assert cv["calendar_split_events"] == {2023: 0, 2024: 2} and cv["calendar_only"] == {2023: 0, 2024: 1} and cv["price_only"] == {2023: 0, 2024: 1}, cv
    assert H["eligible_by_year"] == {2023: 100 - 5 - 10 - 3, 2024: 40 - 4 - 4 - 1 - 1 - 1} and sum(H["excluded_any_rule_by_year"]["ex_div"].values()) == 1, H["eligible_by_year"]
    assert H["share_class"] is None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_hygiene(H)
    t_ = buf.getvalue()
    assert "no-data (survivorship) drops by year [NOISE H3]" in t_ and "2024: 4 (10.0%)" in t_ and "TBIS volume-confirmed flag [NOISE H1]" in t_ and "removed only by a flag dated t itself" in t_
    assert "symbol map through the name-change chain [X1]" in t_ and "2023: 6 (6.0%) -> 3 (3.0%); recovered 3 (3.00% of member-days), 2 of them pass the identity check; rescued from an identity drop 1" in t_ \
        and "tickers with member-days recovered from no-data by the chain: N3 2, N0 1, N5 1" in t_ and "rescued from an identity drop by the chain: N4 1, N6 1" in t_         and "still without a SIPORB bar after the chain (the survivorship; all years): N2 7" in t_, t_
    assert "ex-dividend exclusions [X1] (member-days) by year - dropped on this rule first: 2023: 0, 2024: 1" in t_ and "2024: 1 (2.5%)" in t_ and "cash_dividend 2023: 0, 2024: 1 (total 1)" in t_, t_
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_hygiene(H, False)
    assert "name-change chain" not in buf.getvalue() and "ex-dividend exclusions" not in buf.getvalue(), "without a calendar there is no chain and no ex-dividend rule to report"


def t_audit():
    root = tempfile.mkdtemp()
    p = os.path.join(root, "xgap_audit.csv")
    assert read_audit(p) == ([], set())
    open(p, "w").write("symbol,date,cell,verdict,note\nAAA,2020-03-16,ALL,keep,ok\nBBB,2021-05-03,all,Data_Event,unadjusted split\nBBB,2021-05-03,CAP8,keep,\n")
    rows, rem = read_audit(p, CUT_A)
    assert len(rows) == 3 and rem == {("BBB", TS("2021-05-03"))} and rows[1]["cell"] == "ALL" and rows[1]["verdict"] == "data_event"
    for body, frag in (("symbol,date,cell,verdict\nA,2020-03-16,ALL,maybe\n", "needs symbol"), ("symbol,date,cell,verdict\nA,2020-03-16,BOTH,keep\n", "needs symbol"), ("symbol,date,cell,verdict\nA,notadate,ALL,keep\n", "needs symbol"),
                       ("symbol,date,cell,verdict\nA,2020-03-16,ALL,keep\nA,2020-03-16,ALL,data_event\n", "two verdicts"), ("symbol,date,cell\nA,2020-03-16,ALL\n", "no column verdict"),
                       ("symbol,date,cell,verdict\nA,2025-06-30,ALL,keep\n", "on/after the cut")):
        open(p, "w").write(body)
        try:
            read_audit(p, CUT_A)
            raise AssertionError(f"must refuse: {frag}")
        except SystemExit as e:
            assert frag in str(e), (frag, str(e))
    c = {"ALL": [{"symbol": "AAA", "siporb_symbol": "AAA", "date": "2020-03-16"}, {"symbol": "FB", "siporb_symbol": "META", "date": "2019-01-02"}], "CAP8": [{"symbol": "AAA", "siporb_symbol": "AAA", "date": "2020-03-16"}]}
    rr = [{"symbol": "AAA", "date": TS("2020-03-16"), "cell": "ALL", "verdict": "keep"}, {"symbol": "META", "date": TS("2019-01-02"), "cell": "ALL", "verdict": "keep"}]
    ok, miss = audit_status(c, rr)
    assert ok == {"ALL": True, "CAP8": False} and miss == {"ALL": [], "CAP8": ["AAA 2020-03-16"]}, "complete per cell; a verdict may use the ticker or the SIPORB symbol; one cell's verdict does not cover the other"
    assert audit_status({}, rr)[0] == {"ALL": False, "CAP8": False}, "no candidates is not 'complete'"
    mk = lambda s, d, rd_: {"symbol": s, "siporb_symbol": s, "date": d, "reading": rd_}
    m = merge_candidates({"ALL": [mk("A", "2020-01-02", "registered"), mk("B", "2020-01-03", "registered")], "CAP8": [mk("A", "2020-01-02", "registered")]},
                         {"ALL": [mk("B", "2020-01-03", "slots-left-empty"), mk("C", "2020-01-06", "slots-left-empty")], "CAP8": []})
    assert [(r["symbol"], r["reading"]) for r in m["ALL"]] == [("A", "registered"), ("B", "both"), ("C", "slots-left-empty")] and [r["symbol"] for r in m["CAP8"]] == ["A"], m
    assert merge_candidates({"ALL": [mk("A", "2020-01-02", "registered")]}, {})["ALL"][0]["reading"] == "registered" and "reading" in AUDIT_COLS, "no second reading: the registered rows unchanged"


def t_sibling_and_preflight():
    root = tempfile.mkdtemp()
    p = os.path.join(root, "ddw_stageA.json")
    assert "not on file" in sibling_refusal(p, 100.0)
    open(p, "w").write("{not json")
    assert "cannot be read" in sibling_refusal(p, 100.0)
    for body, frag in (({"judged": False}, "not judged yet"), ({"judged": True, "stageA": {"PASS": False}}, "no readable L2 cell"),
                       ({"judged": True, "cells": {"L2-F": {"stageA": {"PASS": True}, "A2": {"pass": True}}}}, "no readable A2 book ROC")):
        json.dump(body, open(p, "w"))
        assert frag in sibling_refusal(p, 100.0), (body, sibling_refusal(p, 100.0))
    cell = lambda pa, p2, roc: {"stageA": {"PASS": pa}, "A2": {"pass": p2, "book_roc": roc}}
    js = {"judged": True, "cells": {"L1-F": cell(True, True, 500.0), "L2-F": cell(True, True, 99.0), "L2-S": cell(True, False, 300.0)}}
    json.dump(js, open(p, "w"))
    assert sibling_refusal(p, 100.0) is None, "L1 is not the sibling; an L2 cell that failed A2 does not count; one with a LOWER A2 book ROC does not take the day"
    m = sibling_refusal(p, 98.0)
    assert m and "sibling rule" in m and "L2-F" in m and "99.00" in m and "98.00" in m and "lockbox NOT read" in m, m
    js["cells"]["L2-F"] = cell(True, True, 100.0)
    json.dump(js, open(p, "w"))
    assert sibling_refusal(p, 100.0) is None, "a tie is not higher"
    js = {"judged": True, "stageA": {"L2-S": {"PASS": True, "A2": {"pass": True, "roc": 120.0}}}}
    json.dump(js, open(p, "w"))
    assert ddw_l2(js) == {"L2-S": (True, 120.0)} and "L2-S" in sibling_refusal(p, 100.0)
    js = {"judged": True, "x": {"L2": {"stageA": {"PASS": True}, "A2": {"pass": True}}}}
    json.dump(js, open(p, "w"))
    assert "no readable A2 book ROC" in sibling_refusal(p, 100.0), "a passing L2 cell whose ROC cannot be read fails closed"
    assert ddw_l2({"a": {"b": {"c": {"d": {"L2-F": {"PASS": True, "a2_pass": True, "a2_book_roc": 7.0}}}}}}) == {"L2-F": (True, 7.0)}
    # DDW r1's r14_ddw.py draft (2026-10-05): judged, candidate {cell, a2_book_roc} = the ONE cell that reaches its Stage B (null = none), stageA.cells.<cell>.{PASS, A2.{pass, roc}}, and look-ahead / parity copies
    # of the same cell names further down the file
    ddw = lambda cand, **cells: {"judged": True, "pending_audit": [], "candidate": cand, "stageA": {"cells": {n: {"PASS": v[0], "A2": {"pass": v[1], "roc": v[2]}, "audit": {"audit_complete": True}} for n, v in cells.items()}},
                                 "parity": {n: {"net": 1.0, "n_pos": 5} for n in cells}, "look_ahead_reading": {"cells": {n: {"PASS": True, "A2_pass": False} for n in cells}}}
    for cand, cells, best, clear in (({"cell": "L2-F", "c": 0.5, "a2_book_roc": 120.0}, {"L2-F": (True, True, 120.0), "L1-F": (True, True, 90.0)}, 100.0, False),
                                      ({"cell": "L2-F", "c": 0.5, "a2_book_roc": 100.0}, {"L2-F": (True, True, 100.0)}, 100.0, True),                      # a tie is not higher
                                      ({"cell": "L2-F", "c": 0.5, "a2_book_roc": 90.0}, {"L2-F": (True, True, 90.0)}, 100.0, True),                       # DDW's own Stage B yields to the higher XGAP
                                      ({"cell": "L1-S", "c": 0.5, "a2_book_roc": 150.0}, {"L1-S": (True, True, 150.0), "L2-F": (True, True, 130.0)}, 100.0, True),   # an L1 pick: no L2 cell reaches Stage B
                                      (None, {"L2-F": (True, False, 80.0), "L2-S": (False, False, None)}, 100.0, True)):                                   # nothing passes: nothing reaches Stage B
        json.dump(ddw(cand, **cells), open(p, "w"))
        m = sibling_refusal(p, best)
        assert (m is None) == clear, (cand, m)
        if not clear:
            assert "L2-F" in m and "120.00" in m and "reaches its Stage B" in m and "lockbox NOT read" in m, m
    for bad, frag in (({"cell": "L2-F"}, "no readable A2 book ROC"), ({"a2_book_roc": 5.0}, "no cell name"), ("L2-F", "no cell name"), ({"cell": "L2-F", "a2_book_roc": float("nan")}, "no readable A2 book ROC")):
        js = ddw(None, **{"L2-F": (True, True, 130.0)})
        js["candidate"] = bad
        json.dump(js, open(p, "w"))
        assert frag in sibling_refusal(p, 100.0), (bad, sibling_refusal(p, 100.0))
    js = ddw(None, **{"L2-F": (True, True, 130.0)})                                          # no 'candidate' key at all: the cells are read, the FIRST copy of a name wins (stageA.cells over the look-ahead block)
    del js["candidate"]
    json.dump(js, open(p, "w"))
    assert ddw_l2(js) == {"L2-F": (True, 130.0)} and "L2-F" in sibling_refusal(p, 100.0)
    js2 = {"judged": True, "reports": {"l2_exposure": {"traded_days": 40}}, "stageA": {"L2-F": {"PASS": True, "A2": {"roc": 3.0}}}}
    json.dump(js2, open(p, "w"))
    assert "A2 verdict is not readable" in sibling_refusal(p, 100.0), "a cell that passed Stage A with no readable A2 verdict fails closed"
    assert ddw_l2({"judged": True, "reports": {"l2_exposure": {"traded_days": 40}}, "stageA": {"L2-F": {"PASS": False}}}) == {"L2-F": (False, None)}, "a block with no flag (an exposure table) is not a cell"
    # the Stage B preflight: nothing but the Stage A file, the flag and the spec - and it never writes the flag. [MANAGER #56] A2 is a REPORT: a Stage A pass + audit_complete is enough
    flag = os.path.join(root, FLAG_FILE)
    a2r = {"cell": "CAP8", "c": 0.7, "book_roc": 100.0, "book_shadow_line": False, "by_cell": {"ALL": {"c": 0.9, "book_roc": 50.0, "book_shadow_line": False}, "CAP8": {"c": 0.7, "book_roc": 100.0, "book_shadow_line": False}}}
    good = {"judged": True, "stageA": {"PASS": True, "candidate": "CAP8", "cells": {"ALL": "FAIL", "CAP8": "PASS"}}, "a2_report": a2r, "audit_complete": {"ALL": False, "CAP8": True},
            "audit": {"complete": {"ALL": False, "CAP8": True}}, "prereg_sha256_lf": PREREG_SHA, **stamp()}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert b_preflight(good, flag) == ("CAP8", 0.7), "a Stage A pass with the audit complete goes to Stage B although the book shadow line failed (A2 is a report)"
    cases = [(lambda s: s.update(judged=False), "no Stage A pass"), (lambda s: s["stageA"].update(PASS=False), "no Stage A pass"), (lambda s: s.pop("stageA"), "no Stage A pass"),
             (lambda s: s["stageA"].update(candidate=None), "hand audit"), (lambda s: s["stageA"].update(candidate="X"), "hand audit"),
             (lambda s: s["audit"]["complete"].update(CAP8=False), "hand audit"), (lambda s: s.pop("audit"), "hand audit"), (lambda s: s["audit_complete"].update(CAP8=False), "hand audit"),
             (lambda s: s.pop("audit_complete"), "hand audit"), (lambda s: s["audit_complete"].update(CAP8="yes"), "hand audit"),
             (lambda s: s.update(prereg_sha256_lf="0" * 64), "another pre-registration"), (lambda s: s.update(harness_sha256="0" * 64), "different harness version"),
             (lambda s: s.update(early_close=s["early_close"][1:]), "different harness version"), (lambda s: [s.pop(k) for k in stamp()], "different harness version"),
             (lambda s: s["a2_report"]["by_cell"]["CAP8"].update(c=None), "frozen c"), (lambda s: s["a2_report"]["by_cell"]["CAP8"].update(c=-1.0), "frozen c"),
             (lambda s: s["a2_report"]["by_cell"]["CAP8"].update(c=float("nan")), "frozen c"), (lambda s: s.pop("a2_report"), "frozen c")]
    for edit, frag in cases:
        s = json.loads(json.dumps(good))
        edit(s)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                b_preflight(s, flag)
            raise AssertionError(f"Stage B must refuse ({frag})")
        except SystemExit as e:
            assert frag in str(e), (frag, str(e))
    open(flag, "w").write("x")
    try:
        b_preflight(json.loads(json.dumps(good)), flag)
        raise AssertionError("a second read must be refused")
    except SystemExit as e:
        assert "already read" in str(e)
    with A.patched(sys.modules[__name__], PREREG_SHA="0" * 64):
        os.remove(flag)
        try:
            b_preflight(good, flag)
            raise AssertionError("a changed spec must refuse")
        except SystemExit as e:
            assert "DIFFERS" in str(e)
    assert not os.path.exists(flag), "a refusal never writes the flag"


def t_cut():
    A.assert_cut("x", pd.DatetimeIndex(["2025-06-26", "2025-06-27"]), CUT_A)
    def stub(t_end, open5=True):
        assert t_end == CUT_A and open5 is False, "Stage A asks for data cut at 2025-06-30 and no 09:30 file of SIPORB's"
        return SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"]))
    with A.patched(S, Data=stub):
        try:
            load_data(CUT_A)
            raise AssertionError("a session on/after the cut must be refused")
        except SystemExit as e:
            assert "on/after the cut" in str(e)
    seen = {}
    me = sys.modules[__name__]
    def stop(cut, cal, cinfo):
        seen["cut"] = cut
        raise SystemExit("stop")
    cal0 = pd.DataFrame({"type": ["cash_dividend"], "ev": pd.to_datetime(["2024-03-08"]), "symbol": ["A"], "old_symbol": [""], "new_symbol": [""], "proc": pd.to_datetime([None])})
    with A.patched(me, load_calendar=lambda cut, need=True: (cal0, {"rows_read": 1, "rows_by_type": {"cash_dividend": 1}, "csv_sha256": "0" * 64}), prepare=stop, read_audit=lambda p, cut=None: (seen.update(audit_cut=cut) or [], set()),
                   book_check_x=lambda *a, **k: {"roc": 0.0, "sortino": 0.0, "max_dd": 0.0, "ok": True}), A.patched(A, load_463=lambda: (SimpleNamespace(), [])):
        try:
            with contextlib.redirect_stdout(open(os.devnull, "w")):
                stage_a()
            raise AssertionError("stub must stop Stage A")
        except SystemExit as e:
            assert str(e) == "stop" and seen["cut"] == CUT_A and seen["audit_cut"] == CUT_A, (str(e), seen)


def t_share_classes():
    tk = ["AAPL", "GOOG", "GOOGL", "FOX", "FOXA", "LBTYA", "LBTYK", "LILA", "LILAK", "TFCF", "TFCFA", "LMCA", "LMCK", "TRI", "TRIP", "INTC", "INTU", "NWSA", "MSFT", "WBA", "WBD"]
    groups, rep = share_class_groups(tk)
    assert groups == [("FOX", "FOXA"), ("GOOG", "GOOGL"), ("LBTYA", "LBTYK"), ("LILA", "LILAK"), ("LMCA", "LMCK"), ("NWSA",), ("TFCF", "TFCFA")], groups
    assert rep["explicit_pairs_on_file"] == [("FOX", "FOXA"), ("GOOG", "GOOGL"), ("LBTYA", "LBTYK"), ("LILA", "LILAK")], "the addendum's list: the families with two or more members on file"
    assert rep["explicit_names_on_file"] == ["FOX", "FOXA", "GOOG", "GOOGL", "LBTYA", "LBTYK", "LILA", "LILAK", "NWSA"] and ("NWSA",) in groups, "a listed name is a class member even when its partner is not on file"
    assert rep["explicit_families_with_no_member"] == [["DISCA", "DISCB", "DISCK"], ["BATRA", "BATRK"], ["LBRDA", "LBRDK"], ["VIAC", "VIACA"]]
    assert rep["detected_beyond_the_list"] == [("LMCA", "LMCK"), ("TFCF", "TFCFA")], "the detector finds the pairs the list lacks: a trailing class letter (TFCF / TFCFA), a shared stem with two class letters (LMCA / LMCK)"
    assert rep["shared_root_not_taken"] == [("INTC", "INTU"), ("TRI", "TRIP"), ("WBA", "WBD")], "other shared-root pairs are PRINTED, not enforced (the last letter is no class letter)"
    flat = {s for g in groups for s in g}
    assert not flat & {"AAPL", "MSFT", "TRI", "TRIP", "INTC", "INTU", "WBA", "WBD", "TFCFB"} and share_class_groups(["AAPL", "MSFT"])[0] == []
    assert share_class_groups(["LBTYA", "LBTYB", "LBTYK"])[0] == [("LBTYA", "LBTYB", "LBTYK")] and share_class_groups(["GOOG", "GOOG", "GOOGL"])[0] == [("GOOG", "GOOGL")]
    # [TV X1] the candidates: a class member keeps its OWN ticker only (no chain may carry it across classes); nobody keeps a class member's symbol as a successor
    tick = ["FB", "FOX", "TFCFA", "X", "GOOG", "GOOGL", "LBTYA"]
    full = [["FB", "META"], ["FOX", "FOXA"], ["TFCFA"], ["X", "GOOGL", "Y"], ["GOOG", "GOOGL"], ["GOOGL"], ["LBTYA", "LBYAV", "LBTYK"]]
    cand, edges = restrict_candidates(tick, full, {"FOX", "FOXA", "GOOG", "GOOGL", "LBTYA", "LBTYK", "TFCFA"})
    assert cand == [["FB", "META"], ["FOX"], ["TFCFA"], ["X", "Y"], ["GOOG"], ["GOOGL"], ["LBTYA"]], cand
    assert edges == [("FOX", "FOXA"), ("GOOG", "GOOGL"), ("LBTYA", "LBTYK"), ("LBTYA", "LBYAV"), ("X", "GOOGL")], edges
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_share_class({**rep, "chain_edges_refused": [list(e) for e in edges], "refused_cross_class_name_days": [{"ticker": "GOOG", "symbol": "GOOGL", "year": 2019, "name_days": 7}]})
    t_ = buf.getvalue()
    assert "FOX/FOXA" in t_ and "TFCF/TFCFA" in t_ and "INTC/INTU" in t_ and "refused cross-class mappings: 7 name-days" in t_ and "GOOG -> GOOGL 2019: 7" in t_ and "name-change edges not followed for class members: 5" in t_


def recount_x2(gapw, elig, idf, k, i0=0):
    """plain python: the X2 counts the long way (sorted lists, no arrays)"""
    bk = {b: {"long": [0, 0], "short": [0, 0]} for b in ("0-2%", "2-4%", "4-8%", ">8%")}
    tl = {c: {"tail": [0, 0], "rest": [0, 0]} for c in CELLS}
    for i in range(i0, len(gapw)):
        names = [x for x in range(len(gapw[i])) if elig[i][x]]
        if not names:
            continue
        v = sorted(float(gapw[i][x]) for x in names)
        n = len(v)
        med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
        g = {x: float(gapw[i][x]) - med for x in names}
        for x in names:
            a = abs(g[x])
            b = "0-2%" if a < 0.02 else "2-4%" if a < 0.04 else "4-8%" if a <= 0.08 + 1e-12 else ">8%"
            cell = bk[b]["long" if g[x] < 0 else "short"]
            cell[0] += 1
            cell[1] += int(idf[i][x])
        for c in CELLS:
            pool = names if c == "ALL" else [x for x in names if abs(g[x]) <= 0.08 + 1e-12]
            if len(pool) < 2 * k:
                continue
            o = sorted(pool, key=lambda x: (g[x], x))
            tail = set(o[:k]) | set(o[-k:])
            for x in pool:
                grp = tl[c]["tail" if x in tail else "rest"]
                grp[0] += 1
                grp[1] += int(idf[i][x])
    return bk, tl


def t_x2():
    T, X, k = 3, 12, 2
    gap = (np.arange(X) - 5.5) * 0.01                                  # -5.5% .. +5.5% in 1% steps: the median is 0, so g = gap; names 0-5 are long candidates, 6-11 short ones

    def world(drops):
        W = mini(T, X)
        W.waived = mini(T, X)
        W.waived.gap[:] = gap
        W.idfail = np.zeros((T, X), bool)
        for i, x in drops:
            W.idfail[i, x] = True
        return W, SimpleNamespace(elig=np.ones((T, X), bool))
    # a tail-correlated drop: the four most extreme names fall out in session 0 (+ one name inside the pack there, one in session 1)
    W, Uw = world([(0, 0), (0, 1), (0, 10), (0, 11), (0, 5), (1, 3)])
    r = x2_rates(W, Uw, 0, k=k)
    assert r["sessions"] == 3 and r["would_be_name_days"] == 36 and r["identity_dropped"] == 6 and abs(r["rate"] - 6 / 36) < 1e-12
    for c in CELLS:
        t = r["tails"][c]
        assert t["tail"] == {"n": 12, "dropped": 4, "rate": 4 / 12} and t["rest"] == {"n": 24, "dropped": 2, "rate": 2 / 24} and abs(t["ratio"] - 4.0) < 1e-12, (c, t)
    assert r["triggered"] is True and abs(r["ratio_all_pool"] - 4.0) < 1e-12
    b = r["by_bucket_side"]
    assert b["4-8%"]["long"] == {"n": 6, "dropped": 2, "rate": 1 / 3} and b["4-8%"]["short"] == {"n": 6, "dropped": 2, "rate": 1 / 3} and b["0-2%"]["long"]["n"] == 6 and b["0-2%"]["short"]["dropped"] == 0, b
    assert sum(v[s]["n"] for v in b.values() for s in v) == 36 and sum(v[s]["dropped"] for v in b.values() for s in v) == 6
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_x2(r)
    t_ = buf.getvalue()
    assert "6 of 36 would-be member-days dropped" in t_ and "ratio 4.00 (threshold 1.5)" in t_ and "TRIGGERED" in t_ and "left EMPTY" in t_ and "4-8%" in t_ and "$" not in t_
    # an even drop (inside the pack only): ratio 0, no second reading
    W, Uw = world([(i, x) for i in range(T) for x in (2, 7)])
    r = x2_rates(W, Uw, 0, k=k)
    assert r["tails"]["ALL"]["ratio"] == 0.0 and r["triggered"] is False
    # the rest never drops, the tail does: an infinite ratio triggers; nothing dropped anywhere: no ratio, no trigger
    W, Uw = world([(0, 0)])
    r = x2_rates(W, Uw, 0, k=k)
    assert r["tails"]["ALL"]["ratio"] == float("inf") and r["triggered"] is True
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_x2(r)
    assert "ratio inf" in buf.getvalue()
    W, Uw = world([])
    r = x2_rates(W, Uw, 0, k=k)
    assert math.isnan(r["tails"]["ALL"]["ratio"]) and r["triggered"] is False and r["identity_dropped"] == 0
    # the threshold is a strict 'above'; the switch; sessions before i0 are not read
    W, Uw = world([(0, 0), (0, 1), (0, 10), (0, 11), (0, 5), (1, 3)])
    for thr, want in ((4.0, False), (3.99, True), (1.5, True)):
        with A.patched(sys.modules[__name__], RULES={**RULES, "x2_ratio": thr}):
            assert x2_rates(W, Uw, 0, k=k)["triggered"] is want, thr
    with A.patched(sys.modules[__name__], RULES={**RULES, "x2": False}):
        assert x2_rates(W, Uw, 0, k=k)["triggered"] is False
    assert x2_rates(W, Uw, 1, k=k)["sessions"] == 2 and x2_rates(W, Uw, 1, k=k)["identity_dropped"] == 1
    # an independent recount on random data (CAP8's pool differs from ALL's here: gaps beyond 8%; some sessions with no universe; a pool under 2k)
    T2, X2 = 40, 26
    rng = np.random.default_rng(32)
    W = mini(T2, X2)
    W.waived = mini(T2, X2)
    W.waived.gap[:] = rng.normal(0.0, 0.045, (T2, X2))
    W.idfail = rng.random((T2, X2)) < np.where(np.abs(W.waived.gap - np.median(W.waived.gap, axis=1)[:, None]) > 0.05, 0.4, 0.1)
    Uw = SimpleNamespace(elig=rng.random((T2, X2)) < 0.8)
    Uw.elig[5] = False
    Uw.elig[6, :7] = True
    Uw.elig[6, 7:] = False
    for kk in (2, 4):
        r = x2_rates(W, Uw, 3, k=kk)
        bk, tl = recount_x2(W.waived.gap, Uw.elig, W.idfail, kk, 3)
        assert all([r["by_bucket_side"][bn][s]["n"], r["by_bucket_side"][bn][s]["dropped"]] == bk[bn][s] for bn in bk for s in ("long", "short")), (kk, r["by_bucket_side"], bk)
        assert all([r["tails"][c][g]["n"], r["tails"][c][g]["dropped"]] == tl[c][g] for c in CELLS for g in ("tail", "rest")), (kk, r["tails"], tl)
        assert r["tails"]["ALL"]["tail"]["n"] != r["tails"]["CAP8"]["tail"]["n"] or r["tails"]["ALL"]["rest"]["n"] != r["tails"]["CAP8"]["rest"]["n"], "CAP8's pool differs from ALL's"


def t_empty_slots():
    k = 2
    W = mini(8, 9)
    gap = np.array([0.05, -0.03, 0.00, 0.02, -0.10, 0.12, 0.01, -0.01, 0.03])        # the median is 0.01
    W.gap[4] = gap
    W.Cl[4] = 100.0
    W.o935[4] = 100.0                                                                  # every position pays only its costs: -$7.50
    U = SimpleNamespace(elig=np.zeros((8, 9), bool))
    U.elig[4] = True
    W.beta[4] = 1.0
    rows = np.arange(8)
    un = np.zeros((8, 9), bool)
    un[4, [4, 5]] = True                                                               # name 4 (the lowest g: a long) and name 5 (the highest g: a short) cannot be traded
    R0, R1 = run_cells(W, U, rows, 8, 2, k=k), run_cells(W, U, rows, 8, 2, k=k, untrade=un)
    assert R0.nd[("P", "ALL")]["x"].tolist() == [4, 1, 0, 5]
    p = R1.nd[("P", "ALL")]
    assert p["x"].tolist() == [1, 0] and p["side"].tolist() == [1, -1] and np.allclose(p["g"], [-0.04, 0.04]), "[TV X2] the slots of the untradeable names stay EMPTY: nothing takes their place (the next name does not step in), g is still the pool's"
    assert R1.nd[("M", "ALL")]["x"].tolist() == [0, 1] and R1.nd[("M", "ALL")]["side"].tolist() == [1, -1], "the mirror leaves the same names out"
    assert R1.nd[("T", "ALL")]["x"].tolist() == [1, 0] and R1.nd[("P", "CAP8")]["x"].tolist() == R0.nd[("P", "CAP8")]["x"].tolist(), "the twin too; CAP8's pool never held the two (|g| > 8%)"
    un2 = np.zeros((8, 9), bool)
    un2[4, [4, 1, 0]] = True                                                           # a whole side empty: the other trades alone (no dollar-neutrality is forced)
    q = run_cells(W, U, rows, 8, 2, k=k, untrade=un2).nd[("P", "ALL")]
    assert q["x"].tolist() == [5] and q["side"].tolist() == [-1]
    # the null: a draw's untradeable picks book nothing (every position here costs 7.5)
    nreps = 4000
    a0 = run_cells(W, U, rows, 8, 2, nreps=nreps, seed=3, k=k, twin=False)
    a1 = run_cells(W, U, rows, 8, 2, nreps=nreps, seed=3, k=k, twin=False, untrade=un)
    assert np.allclose(a0.acc["ALL"][:, 4], -30.0) and a1.acc["ALL"][:, 4].min() == -30.0 and a1.acc["ALL"][:, 4].max() > -30.0
    want = -7.5 * (4 - 4 * 2 / 9)                                                      # four distinct names a draw, two of nine untradeable
    m, sd = a1.acc["ALL"][:, 4].mean(), a1.acc["ALL"][:, 4].std()
    assert abs(m - want) < 5 * sd / np.sqrt(nreps), (m, want)
    allun = np.zeros((8, 9), bool)
    allun[4] = True
    a2 = run_cells(W, U, rows, 8, 2, nreps=50, seed=3, k=k, twin=False, untrade=allun)
    assert (a2.acc["ALL"] == 0).all() and len(a2.nd[("P", "ALL")]["i"]) == 0


def t_payers_earnings():
    days = pd.bdate_range("2024-01-02", periods=30)
    tick = np.array(["AAA", "FB", "BBB", "GOOG", "GOOGL"], dtype=object)
    cal = pd.DataFrame({"type": ["cash_dividend", "cash_dividend", "cash_dividend", "name_change"], "symbol": ["AAA", "META", "GOOGL", ""], "old_symbol": ["", "", "", "FB"], "new_symbol": ["", "", "", "META"],
                        "ev": pd.to_datetime(["2023-01-09", "2024-01-10", "2024-01-12", "2022-06-09"])})
    comp = {**alias_components(cal), "GOOG": frozenset({"GOOG"}), "GOOGL": frozenset({"GOOGL"})}               # a share-class member's alias set is its own ticker
    pf = payer_flags(cal, tick, days, comp)
    assert pf[:6, 0].all() and not pf[6:, 0].any(), "ex-date 2023-01-09: a payer for sessions after it up to ex-date + 365 days (2024-01-09, inclusive)"
    assert not pf[:7, 1].any() and pf[7:, 1].all(), "FB: its dividend is filed under META (the same company); a payer from the session AFTER the ex-date"
    assert not pf[:, 2].any() and not pf[:, 3].any() and not pf[:9, 4].any() and pf[9:, 4].all(), "GOOGL's dividend is not GOOG's; a Friday ex-date reads the next session (Monday)"
    assert not payer_flags(None, tick, days, {}).any()
    W = mini(30, 5)
    W.days, W.payer, W.has_calendar = days, pf, True
    nd = {"i": np.array([1, 1, 8, 8]), "x": np.array([0, 2, 1, 4]), "side": np.array([1.0, -1.0, 1.0, -1.0])}
    R = SimpleNamespace(nd={("P", c): nd for c in CELLS})
    U = SimpleNamespace(elig=np.ones((30, 5), bool))
    out = payer_shares(W, U, R, book_stub(days), np.arange(30), days[0], days[-1])
    assert out["ALL"]["long"] == {"n": 2, "payers": 2, "share": 1.0} and out["ALL"]["short"] == {"n": 2, "payers": 0, "share": 0.0} and out["CAP8"] == out["ALL"]
    assert abs(out["universe"]["payer_share"] - float(pf.mean())) < 1e-12 and out["ALL"]["long_full_lookback"]["n"] == 2
    W.has_calendar = False
    assert payer_shares(W, U, R, book_stub(days), np.arange(30), days[0], days[-1]) == {}
    # [TV X6] earnings: after 16:00 ET on day d removes session d+1, before 09:30 the same session; (CHOICE) during the session the same session too; 16:00 sharp is not 'after'
    days = pd.bdate_range("2024-03-04", periods=10)                                      # Mon Mar 4 .. Fri Mar 15
    ev = pd.DataFrame({"ticker": ["AAPL"] * 6 + ["META", "ZZZ", "AAPL"],
                       "acc": pd.to_datetime(["2024-03-07 16:04", "2024-03-08 16:30", "2024-03-12 07:00", "2024-03-13 10:30", "2024-03-06 16:00", "2024-03-15 17:00", "2024-03-09 18:00", "2024-03-05 16:10", "2024-03-04 09:30"])})
    tick = np.array(["AAPL", "FB", "BBB"], dtype=object)
    comp = {"FB": frozenset({"FB", "META"}), "META": frozenset({"FB", "META"})}
    mask, cov = earn_mask(ev, days, tick, comp)
    assert np.flatnonzero(mask[:, 0]).tolist() == [0, 2, 4, 5, 6, 7], "Thu 16:04 -> Fri; Fri 16:30 -> Mon; Tue 07:00 -> Tue; Wed 10:30 -> Wed; Wed 16:00 sharp -> Wed; a release after the last session is out of range; Mon 09:30 -> Mon"
    assert np.flatnonzero(mask[:, 1]).tolist() == [5] and not mask[:, 2].any() and cov.tolist() == [True, True, False], "META's release attaches to FB (a Saturday after 16:00 reads Monday); ZZZ is no member"
    root = tempfile.mkdtemp()
    p = os.path.join(root, "megacap_earnings.csv")
    open(p, "w").write("ticker,accepted_et,items\nAAPL,2025-06-27 16:20,\"2.02,9.01\"\nAAPL,2025-06-30 10:00,2.02\nAAPL,not a date,2.02\nMSFT,2024-01-25 16:06,\"2.02,9.01\"\n")
    got = read_earnings(CUT_A, p)
    assert len(got) == 2 and got["acc"].max() == TS("2025-06-27 16:20") and list(got["ticker"]) == ["AAPL", "MSFT"], "cut at read time (an event on/after 2025-06-30 is never kept); an unreadable date is dropped"
    assert len(read_earnings(CUT_B, p)) == 3 and read_earnings(CUT_A, os.path.join(root, "nope.csv")) is None
    open(p, "w").write("ticker,when\nA,2024-01-01\n")
    try:
        read_earnings(CUT_A, p)
        raise AssertionError("a file with no accepted_et column must refuse")
    except SystemExit as e:
        assert "accepted_et" in str(e)


def t_null_percentile():
    idx = pd.bdate_range("2016-07-01", PRE_END)
    B = book_stub(idx)
    rng = np.random.default_rng(33)
    R = SimpleNamespace(acc={"ALL": rng.normal(5, 60, (300, len(idx))), "CAP8": rng.normal(2, 90, (300, len(idx)))})
    n, fin = null_summary(R, B)
    mx, _ = null_stat(R.acc, B)
    ref = mx[np.isfinite(mx)]
    assert n["finite"] == len(ref) == len(fin) and abs(n["p97_5"] - np.percentile(ref, 97.5)) < 1e-12 and abs(n["p95"] - np.percentile(ref, 95)) < 1e-12 and n["p95"] <= n["p97_5"], n
    assert n["pct_used"] == 97.5 and n["p_used"] == n["p97_5"] and n["draws"] == NREP and n["seed"] == SEED, "[TV X3] check (c) reads the 97.5th percentile; the 95th stays beside it"
    with A.patched(sys.modules[__name__], RULES={**RULES, "null_pct": 95.0}):
        assert null_summary(R, B)[0]["p_used"] == n["p95"]


def t_mocks_guard():
    assert callable(S._get) and S.BadRequest is not None
    with A.patched(S, SMOKE=True):
        assert S.keys() == ("smoke", "smoke")


def selftest():
    tests = [("constants as registered", t_constants), ("calendar parser: canned response, unknown types / fields, flat rows, dedupe, scrub", t_calendar_parser),
             ("calendar pull: paging, a rejected symbol bisected out, a rejected type stops, the probe prints names only", t_calendar_pull),
             ("calendar loader: refuses without it / on a sha mismatch / unless it is the pinned file [MANAGER #58], cut at read time, name changes kept, a tagged calendar", t_calendar_loader),
             ("capull WIDE mode: the command line, the names file, per-tag files and refusals, the scaled stop on rejected symbols, a whole pull through a mocked transport", t_capull_wide),
             ("symbol map: the identity check max(1 cent, 0.10%), same ticker first, the chain, no data vs disagreement, the waived map; chain, cycle, aliases", t_symbol_map),
             ("share-class members: the addendum's list, the detector, own-ticker-only candidates, what is refused", t_share_classes),
             ("calendar flags: ex-dividend / split attach by alias, weekend dates, out-of-range dates", t_calendar_flags), ("flag windows t-5 .. t and the prior-only variant", t_windows),
             ("split-safe gap across 2-for-1 and 1-for-8 splits", t_gap), ("universe: every exclusion rule, first failing rule counted, the TBIS window swap", t_universe),
             ("cells: median removal, ALL / CAP8 / mirror / twin baskets, ties, the 8% edge, pools under 2k, i0", t_cells), ("empty slots [TV X2]: untradeable names leave their slots empty in the cells and the null", t_empty_slots),
             ("fills and costs: base, stress, SIPORB cents, fractional shares", t_costs),
             ("null: uniform without replacement, seeded, long / short assignment, the CAP8 pool, expectation", t_null),
             ("statistics: ROC / PF / NW t / best 5 days / best 1% of name-days / halves / 2020 / years; null statistic = r11_risk.stats; judge_a with the twin veto; both readings; pick_cell", t_stats),
             ("null percentiles: (c) reads the 97.5th, the 95th beside it", t_null_percentile), ("identity drops against the signal [TV X2]: buckets, tails, the trigger, an independent recount", t_x2),
             ("dividend payers [TV X5] and the ex-earnings mask [TV X6]", t_payers_earnings),
             ("c rule: the volatility ratio hits exactly 25%; A2 bars each bite", t_c_rule), ("MDL map point: DO / rho_dd equal r12_mdl's and its independent implementation", t_map_point),
             ("ES returns and the realised beta", t_es), ("beta windows: the slope on the universe median, all present", t_betas),
             ("inputs: the member cache (DST, cut, duplicates), membership, TBIS list", t_inputs), ("hygiene counts by reason and year, the 2% identity rule, the no-data line, TBIS under both windows, calendar vs price rules", t_hygiene),
             ("hand audit: file parsing, refusals, completeness per cell", t_audit), ("sibling rule, Stage B preflight refusals (A2 is a report; no flag written)", t_sibling_and_preflight), ("the cut: Stage A reads nothing on/after 2025-06-30", t_cut),
             ("transport guard", t_mocks_guard)]
    for name, fn in tests:
        t = time.time()
        fn()
        print(f"  ok  {name} ({time.time() - t:.1f}s)", flush=True)
    print("selftest ok: constants as registered; the calendar parser / pull / loader (the pinned files) / the wide pull; the identity check and the symbol map; the share-class rule; every universe rule; the split-safe gap; the median removal, ALL / CAP8, "
          "mirror and twin baskets; empty slots; fills and costs; the seeded uniform null and its 97.5th percentile; the statistics and bars with the twin veto and both readings; the X2 identity-drop rates; the c rule at "
          "exactly 25% (A2 a report); DO / rho_dd as MDL r1; payers and earnings; the audit; the sibling rule and the Stage B refusals; the cut")


# ------------------------------------------------------------------ smoke: an offline end-to-end run on a SYNTHETIC world (every number means nothing)
SMOKE_SPANS = (("2015-11-02", "2015-12-31"), ("2016-01-04", "2016-03-31"), ("2016-05-02", "2016-09-30"), ("2017-03-01", "2017-06-30"), ("2018-04-02", "2018-09-28"), ("2023-10-02", "2023-12-29"),
               ("2024-01-02", "2024-06-28"), ("2025-04-01", "2025-06-27"), ("2025-06-30", "2025-08-29"))      # warm-up, 2016 H1, the first WF months, 2017, 2018 (the c rows), 2023-24, the last WF weeks, lockbox days
GAP_PLANTS = (("S10", "2016-07-12", 1.12), ("S11", "2016-07-14", 0.90), ("S12", "2024-02-13", 1.15), ("S13", "2017-03-15", 0.88), ("S24", "2018-05-10", 1.30))   # official + 09:30 / 09:35 opens x factor: real relative gaps
MAP_PLANTS = (("S07", "2016-08-01"), ("S07", "2016-08-02"), ("S07", "2024-03-20"))                           # the cache's opens x 1.05: the symbol map must drop the name that day
MISSING_BARS = (("S02", "2016-07-15", 575), ("S03", "2016-07-18", 570))                                       # no 09:35 bar / no 09:30 bar in the member cache
SMOKE_TBIS = "symbol,day,price_ratio,vol_ratio,split_like\nS19,2024-04-10,0.5,2.0,True\nS21,2024-04-11,0.5,1.0,False\nS22,2025-07-01,0.5,2.0,True\n"
SMOKE_MEMBERS = [("OLD05", "2016-06-01", "2024-05-01"), ("S05", "2024-05-01", ""), ("GHOST", "2016-06-01", ""), ("TFCF", "2016-06-01", ""), ("PCLS", "2016-06-01", ""), ("PCLSA", "2016-06-01", "")]
SMOKE_PAIR = ("PCLS", "PCLSA")                                                                  # the planted share-class pair (the detector reads PCLSA = PCLS + a class letter)
RENAME = {"S30": "PCLS", "S31": "PCLSA"}                                                        # SIPORB's symbols for the two fake names ...
SWAP = {"PCLS": "S31", "PCLSA": "S30"}                                                          # ... and a CLASS SWAP: the cache's PCLS bars are the fake name S31's, which SIPORB calls PCLSA (and the other way round)
SMOKE_EARN = "ticker,accepted_et,items\nS02,2016-07-14 16:05,\"2.02,9.01\"\nS02,2017-03-02 07:00,2.02\nS16,2016-08-03 16:20,\"2.02,9.01\"\nS16,2024-02-14 12:00,2.02\nS16,2025-07-02 16:10,2.02\n"


def smoke_records():
    """the synthetic calendar (the endpoint's documented shape, built by CAFake): dividends (one on a WF session of S08, one filed under a renamed company's NEW symbol), a split the price rules also see (SPL: the vendor's ex-date is a session after the registered split's), a calendar-only split (S09), a name change that reveals a name nobody asked for (S14 -> S14X: round 2), a stock dividend, a spin-off, a unit split, a record without an ex-date and a type the parser does not know"""
    R = [("cash_dividend", {"symbol": "S08", "cusip": "x", "rate": 0.2, "special": False, "foreign": False, "process_date": "2016-07-15", "ex_date": "2016-07-13", "record_date": "2016-07-14", "payable_date": "2016-07-15"}),
         ("cash_dividend", {"symbol": "S08", "rate": 0.2, "ex_date": "2024-03-13"}), ("cash_dividend", {"symbol": "S20", "rate": 0.5, "special": True, "ex_date": "2024-02-13"}),
         ("cash_dividend", {"symbol": "S14X", "rate": 0.3, "ex_date": "2024-03-19"}), ("cash_dividend", {"symbol": "S16", "rate": 0.3}), ("cash_dividend", {"symbol": "S04", "rate": 0.4, "ex_date": "2017-03-15"}),
         ("forward_split", {"symbol": "SPL", "new_rate": 2, "old_rate": 1, "process_date": "2024-03-18", "ex_date": "2024-03-18", "record_date": "2024-03-11", "payable_date": "2024-03-14"}),
         ("forward_split", {"symbol": "S09", "new_rate": 3, "old_rate": 1, "ex_date": "2024-04-02", "process_date": "2024-04-02"}),
         ("name_change", {"old_symbol": "OLD05", "new_symbol": "S05", "process_date": "2024-04-15"}), ("name_change", {"old_symbol": "S14", "new_symbol": "S14X", "process_date": "2024-03-01"}),
         ("name_change", {"old_symbol": "PCLS", "new_symbol": "PCLSA", "process_date": "2024-02-01"}),                    # a name-change chain from one class to the other: the share-class rule must refuse it
         ("stock_dividend", {"symbol": "S11", "rate": 0.05, "ex_date": "2024-05-02"}), ("spin_off", {"source_symbol": "S12", "new_symbol": "SPIN1", "source_rate": 1, "new_rate": 0.1, "ex_date": "2024-05-09"}),
         ("unit_split", {"old_symbol": "S13", "new_symbol": "S13U", "alternate_symbol": "S13V", "old_rate": 1, "new_rate": 1.1, "effective_date": "2024-05-20", "process_date": "2024-05-20"}),
         ("cash_mergers", {"acquirer_symbol": "S15", "target": "ZZZ", "ex_date": "2024-05-21"}), ("cash_dividend", {"symbol": "S06", "rate": 0.3, "ex_date": "2025-07-15"})]
    return R


class CAFake:
    """the corporate-actions endpoint of the smoke: the synthetic calendar in the documented shape, `page` records a page, a 429 now and then, a symbol it rejects outright (400); anything else goes to the fake Alpaca"""
    def __init__(self, records, other, reject=("TFCF",), page=7):
        self.records, self.other, self.reject, self.page, self.n, self.asked = records, other, set(reject), page, 0, []

    def handle(self, url, heads, params):
        if url != CA_URL:
            return self.other(url, heads, params)
        self.n += 1
        assert heads.get("APCA-API-KEY-ID") and heads.get("APCA-API-SECRET-KEY") and "asof" not in params
        if self.n % 5 == 3:
            return S._Reply(429, {"message": "too many requests"})
        syms = params["symbols"].split(",")
        if self.reject & set(syms):
            return S._Reply(400, {"message": "invalid symbol: " + ",".join(sorted(self.reject & set(syms)))})
        types = params["types"].split(",")
        assert set(types) <= set(CA_TYPES) and params["start"] <= params["end"] and int(params["limit"]) == CA_LIMIT
        self.asked.append(tuple(syms))
        rev = {v: k for k, v in CA_KEYS.items()}
        hit = []
        for t, r in self.records:
            who = r.get("symbol") or r.get("old_symbol") or r.get("source_symbol") or r.get("acquirer_symbol")
            d = r.get("ex_date") or r.get("effective_date") or r.get("process_date") or params["start"]
            if who in syms and (t in types or t not in rev) and params["start"] <= d <= params["end"]:
                hit.append((t, r))
        off = int(params.get("page_token") or 0)
        out = defaultdict(list)
        for t, r in hit[off:off + self.page]:
            out[rev.get(t, t)].append(r)
        return S._Reply(200, {"corporate_actions": dict(out), "next_page_token": str(off + self.page) if off + self.page < len(hit) else None})


def smoke_members(fk, path):
    """the synthetic membership file: every fake name from 2016-06-01 (S05 as OLD05 until 2024-05-01), plus GHOST (bars in the member cache, none in SIPORB's), TFCF (nothing anywhere, rejected by the endpoint)"""
    rows = [(n, "2016-06-01", "") for n in fk.names if n not in ("S05", "S30", "S31")] + SMOKE_MEMBERS
    pd.DataFrame(rows, columns=["ticker", "from", "to"]).to_csv(path, index=False)


def smoke_cache(fk, path):
    """the synthetic NQBRD member cache from the fake's own minute bars: the 09:30 bar (open of minute 0, close of minute 4) and the 09:35 bar (open of its first traded minute) of every member-day, labelled with the
    membership file's name that month (OLD05 / S05, GHOST = S01's bars), with the planted gaps, mapping disagreements and missing bars; only the days the member has a listing"""
    gp = {(n, d): f for n, d, f in GAP_PLANTS}
    mp = set(MAP_PLANTS)
    miss = {(n, d): hm for n, d, hm in MISSING_BARS}
    lab = [(n, n) for n in fk.names if n not in ("S05", "S30", "S31")] + [("OLD05", "S05"), ("S05", "S05"), ("GHOST", "S01")] + [(t, SWAP[t]) for t in SMOKE_PAIR]
    tailp = tail_plant(fk, lab, set(gp) | mp | set(miss) | {("S19", "2024-04-10")})                  # S19's TBIS flag day must stay a clean name-day (the day-t removal count of [NOISE H1] reads it)
    rows = []
    for tick, src in lab:
        k = fk.k[src]
        for d, day in enumerate(fk.days):
            if np.isnan(fk.daily[k, d, 0]):
                continue
            ms = day[:7] + "-01"
            if (tick == "OLD05" and not ms < "2024-05-01") or (tick == "S05" and ms < "2024-05-01"):
                continue
            o, h, l, c, v, has = fk.minutes(k, d)
            f = gp.get((tick, day), 1.0) * (1.05 if ((tick, day) in mp or (tick, day) in tailp) else 1.0) * fk.g(k, d, "raw") * fk.unadj(k, d)       # the vendor's own RAW basis: SPL's pre-split x2, S18's never-adjusted x4
            st = fk.stamps(d)
            first = int(np.flatnonzero(has[5:10])[0]) + 5 if has[5:10].any() else None
            if miss.get((tick, day)) != 570:
                rows.append((tick, st[0], o[0] * f, c[4] * f, day))
            if first is not None and miss.get((tick, day)) != 575:
                rows.append((tick, st[5], o[first] * f, c[9] * f, day))
    pd.DataFrame(rows, columns=["symbol", "t", "o", "c", "day"]).to_csv(path, index=False)
    return len(rows)


def plant_gaps(fk):
    """the official opens of the planted name-days x their factor in BOTH daily files (raw and split-adjusted alike, so the split factor is untouched): a real relative gap the member cache's opens agree with"""
    for kind in ("raw", "split"):
        base = S.path_of(f"daily_{kind}")
        df = S.load_df(base)
        df["date"] = pd.to_datetime(df["date"])
        for n, d, f in GAP_PLANTS:
            m = (df["symbol"] == n) & (df["date"] == TS(d))
            assert m.sum() == 1, (kind, n, d)
            df.loc[m, "o"] *= f
        S.save_df(df, base)


def plant_swap(fk):
    """SIPORB's symbols for the two class-swap names (RENAME: S30 -> PCLS, S31 -> PCLSA) in both daily files; the member cache keeps the swapped labels (smoke_cache: its PCLS bars ARE the PCLSA ones)"""
    for kind in ("raw", "split"):
        base = S.path_of(f"daily_{kind}")
        df = S.load_df(base)
        df["symbol"] = df["symbol"].astype(str).replace(RENAME)
        S.save_df(df, base)


def tail_plant(fk, lab, exempt):
    """a TAIL-CORRELATED identity failure [TV X2]: each session the 8 names with the most negative and the 8 with the most positive overnight move (the fake's own path, before any plant) have their cache opens put
    5% off on alternate days, and one name in 41 inside the pack the same - so the names that rank at the tails of g drop far more often than the rest. `exempt` = the (name, day)s other plants rely on"""
    tailp = set()
    for d in range(1, len(fk.days)):
        g = {}
        for tick, src in lab:
            k = fk.k[src]
            o, c0 = fk.daily[k, d, 0], fk.daily[k, d - 1, 3]
            if np.isfinite(o) and np.isfinite(c0):
                g[tick] = o / c0 - 1.0
        order = sorted(g, key=lambda t: (g[t], t))
        tails = set(order[:8]) | set(order[-8:])
        for tick, src in lab:
            if tick not in g or (tick, fk.days[d]) in exempt:
                continue
            k = fk.k[src]
            if (tick in tails and (d + k) % 2 == 0) or (tick not in tails and (d * 7 + k * 3) % 41 == 0):
                tailp.add((tick, fk.days[d]))
    return tailp


# ------------------------------------------------------------------ the independent recount: plain python from the long frames, the member-cache rows and the calendar rows
def brute_world(P, removed, k=NPOS):
    """every member-day's first failing rule and split-safe gap, and every session's baskets, recounted WITHOUT the arrays (dict lookups and python loops over the raw inputs). It shares only what is imported from
    r5_siporb: Data's days / split rule / gap scan (chg, msplit), and name_pnl. The identity check is max(1 cent, 0.10%) written out again here, the share-class members are the ones the smoke planted (SMOKE_PAIR:
    own ticker only), the TBIS flag reads t-5 .. t-1 and every other flag t-5 .. t. It recounts the registered reading AND the one with the identity check waived [TV X2] (a dropped name-day read through its fallback
    symbol: the first candidate with a bar).
    The twin's BETAS [TV X4] are recounted too: the split-safe close-to-close return through the symbol chosen WITHOUT the identity check, dropped on a day any split rule fired, the median over the members with a
    return that session (at least 10), the OLS slope over the previous 60 sessions with all present.
    -> (why {(row, ticker): code}, gap {(row, ticker): float}, chosen {(row, ticker): (SIPORB symbol, the 09:35 open, the official close)} for the eligible ones, the ticker order,
        waived = (ww: the code with the identity check waived, gapw, chosen_w, dropped {(row, ticker): True where the check dropped it}, beta {(row, ticker): the 60-session beta, NaN where not all present},
                  cr {(year, kind): the name-change chain's recovery counts}))"""
    D, cal, days = P.D, P.cal, P.D.days
    raw, spl = S.read_long("raw", P.cut), S.read_long("split", P.cut)
    raw["symbol"], spl["symbol"] = raw["symbol"].astype(str), spl["symbol"].astype(str)
    Rw = {s: g.set_index("date") for s, g in raw.groupby("symbol")}
    Sp = {s: g.set_index("date") for s, g in spl.groupby("symbol")}
    col = {s: j for j, s in enumerate(D.syms)}
    bar = {(r.symbol, r.day, r.hm): r.o for r in P.cache.itertuples()}
    mem = [(r.ticker, r._2, r.to) for r in P.members.itertuples()]
    tbis = {(r.symbol, r.day) for r in P.tbis.itertuples() if r.split_like}
    pair = set(SMOKE_PAIR)
    nxt = {}
    if cal is not None:
        for r in cal[cal["type"] == "name_change"].sort_values("proc", kind="stable").itertuples():
            if r.old_symbol and r.new_symbol and r.old_symbol != r.new_symbol:
                nxt[r.old_symbol] = r.new_symbol
    adj = defaultdict(set)
    for o, n in nxt.items():
        adj[o].add(n)
        adj[n].add(o)

    def aliases(sym):
        seen, todo = {sym}, [sym]
        while todo:
            for q in adj[todo.pop()]:
                if q not in seen:
                    seen.add(q)
                    todo.append(q)
        return seen

    def chain(sym):
        out = [sym]
        while out[-1] in nxt and nxt[out[-1]] not in out:
            out.append(nxt[out[-1]])
        return out
    ev = defaultdict(set)                                                                   # (kind, symbol) -> {session row}
    if cal is not None:
        for r in cal.itertuples():
            if r.type in DIV_TYPES + SPLIT_TYPES and pd.notna(r.ev) and r.ev >= days[0]:
                row = int(days.searchsorted(r.ev))
                if row < len(days):
                    for s in (r.symbol, r.old_symbol, r.new_symbol):
                        if s:
                            ev["div" if r.type in DIV_TYPES else "split", s].add(row)
    tick = sorted({m[0] for m in mem})
    why, gap, chosen, ww, gapw, chosen_w, dropped = {}, {}, {}, {}, {}, {}, {}
    cr = Counter()                                                                          # (year, kind) -> member-days (with both cache bars): the name-change chain's recovery, recounted
    rem = {(s, TS(d)) for s, d in removed}

    def after(i, day, tk, s, o935):
        """the rules after the identity check, for the SIPORB symbol s -> (code, gap, chosen)"""
        p = days[i - 1] if i else None
        if p is None or p not in Rw[s].index:
            return 4, None, None
        if day not in Sp[s].index or p not in Sp[s].index:
            return 5, None, None
        Ft, Fp = Rw[s].at[day, "o"] / Sp[s].at[day, "o"], Rw[s].at[p, "o"] / Sp[s].at[p, "o"]
        al = ({tk} if tk in pair else aliases(tk)) | {s}
        win = range(max(i - 5, 0), i + 1)
        win_prior = range(max(i - 5, 0), i)                                                 # [NOISE H1] the TBIS flag: t-5 .. t-1
        g50 = False
        for u in win:
            if u and days[u] in Rw[s].index and days[u - 1] in Rw[s].index:
                r = Rw[s].at[days[u], "o"] / Rw[s].at[days[u - 1], "c"]
                g50 |= abs(r - 1.0) > GAP_MAX and not D.chg[u, col[s]]
        code = 0
        for c, hit in ((6, any(i in ev["div", a] for a in al)), (7, any(u in ev["split", a] for a in al for u in win)), (8, any(D.chg[u, col[s]] for u in win)), (9, any(D.msplit[u, col[s]] for u in win)),
                       (10, any((s, days[u]) in tbis for u in win_prior)), (11, g50), (12, (tk, day) in rem or (s, day) in rem)):
            if hit:
                code = c
                break
        if code:
            return code, None, None
        return 0, Rw[s].at[day, "o"] * Fp / Ft / Rw[s].at[p, "c"] - 1.0, (s, o935, Rw[s].at[day, "c"])
    for i, day in enumerate(days):
        ms = f"{day:%Y-%m-01}"
        for x, tk in enumerate(tick):
            if not any(t == tk and f <= ms and (e == "" or ms < e) for t, f, e in mem):
                continue
            o930, o935 = bar.get((tk, day, 570)), bar.get((tk, day, 575))
            if o930 is None or o935 is None:
                why[i, tk] = ww[i, tk] = 1
                continue
            cands = [tk] if tk in pair else [s for s in chain(tk) if s == tk or s not in pair]       # [TV X1] a class member maps to its own ticker only
            has = [s for s in cands if s in col and day in Rw[s].index]
            own_has = tk in col and day in Rw[tk].index                                      # the ticker's OWN symbol has a SIPORB bar that day
            cr[day.year, "own_nodata"] += not own_has
            cr[day.year, "after_nodata"] += not has
            cr[day.year, "recovered"] += (not own_has) and bool(has)
            if not has:
                why[i, tk] = ww[i, tk] = 2
                continue
            pick = next((s for s in has if abs(o930 - Rw[s].at[day, "o"]) <= max(0.01, 0.0010 * Rw[s].at[day, "o"]) + 1e-9), None)
            cr[day.year, "recovered_ok"] += (not own_has) and pick is not None
            cr[day.year, "rescued"] += own_has and pick is not None and pick != tk           # the own bar fails the identity check (the own symbol is tried first), a chain symbol passes
            code, g_, ch = after(i, day, tk, pick or has[0], o935)
            ww[i, tk], dropped[i, tk] = code, pick is None
            why[i, tk] = 3 if pick is None else code
            if code == 0:
                gapw[i, tk], chosen_w[i, tk] = g_, ch
                if pick is not None:
                    gap[i, tk], chosen[i, tk] = g_, ch
    # ---- the twin's betas [TV X4]
    T = len(days)
    ret, ismem = {}, {}
    for i, day in enumerate(days):
        ms = f"{day:%Y-%m-01}"
        p = days[i - 1] if i else None
        for tk in tick:
            ismem[i, tk] = any(t == tk and f <= ms and (e == "" or ms < e) for t, f, e in mem)
            cands = [tk] if tk in pair else [s for s in chain(tk) if s == tk or s not in pair]
            has = [s for s in cands if s in col and day in Rw[s].index and Rw[s].at[day, "o"] > 0]
            if not has or p is None:
                continue
            o930 = bar.get((tk, day, 570))
            s = next((s for s in has if o930 is not None and abs(o930 - Rw[s].at[day, "o"]) <= max(0.01, 0.0010 * Rw[s].at[day, "o"]) + 1e-9), has[0])
            if day not in Sp[s].index or p not in Sp[s].index:
                continue
            r = Sp[s].at[day, "c"] / Sp[s].at[p, "c"] - 1.0
            g50 = p in Rw[s].index and abs(Rw[s].at[day, "o"] / Rw[s].at[p, "c"] - 1.0) > GAP_MAX and not D.chg[i, col[s]]
            al = ({tk} if tk in pair else aliases(tk)) | {s}
            bad = D.chg[i, col[s]] or D.msplit[i, col[s]] or (s, day) in tbis or g50 or any(i in ev["split", a] for a in al)
            if not bad:
                ret[i, tk] = r
    mkt = {}
    for i in range(T):
        v = [ret[i, tk] for tk in tick if ismem[i, tk] and (i, tk) in ret]
        if len(v) >= 10:
            mkt[i] = float(np.median(v))
    beta = {}
    for i in range(BETA_WIN, T):
        for tk in tick:
            rows = range(i - BETA_WIN, i)
            if not all((u, tk) in ret and u in mkt for u in rows):
                beta[i, tk] = float("nan")
                continue
            y, x = [ret[u, tk] for u in rows], [mkt[u] for u in rows]
            n, sx, sy = len(rows), sum(x), sum(y)
            sxy, sxx = sum(a * b for a, b in zip(x, y)), sum(a * a for a in x)
            den = n * sxx - sx * sx
            beta[i, tk] = (n * sxy - sx * sy) / den if den > 1e-18 else float("nan")
    return why, gap, chosen, tick, (ww, gapw, chosen_w, dropped, beta, cr)


def brute_twin(P, why, gap, beta, tick, i0, k=NPOS):
    """the beta-adjusted twin baskets [TV X4] recounted from the recounted universe and betas: g_b = the split-safe gap - beta x the median gap of the session's ELIGIBLE names, the pool = the eligible names with a
    full beta (CAP8: |g_b| <= 8%), k most negative long / k most positive short, ties by ticker order -> {("T", cell): [(row, ticker, side)]}"""
    out = {("T", c): [] for c in CELLS}
    for i in range(i0, len(P.D.days)):
        el = [tk for tk in tick if why.get((i, tk)) == 0]
        if len(el) < 2 * k:
            continue
        med = float(np.median([gap[i, tk] for tk in el]))
        et = [tk for tk in el if np.isfinite(beta.get((i, tk), float("nan")))]
        if len(et) < 2 * k:
            continue
        gb = {tk: gap[i, tk] - beta[i, tk] * med for tk in et}
        for c in CELLS:
            pool = et if c == "ALL" else [tk for tk in et if abs(gb[tk]) <= CAP + 1e-12]
            if len(pool) < 2 * k:
                continue
            o = sorted(pool, key=lambda tk: (gb[tk], tick.index(tk)))
            out["T", c] += [(i, tk, 1.0) for tk in o[:k]] + [(i, tk, -1.0) for tk in o[-k:]]
    return out


def brute_baskets(P, why, gap, tick, i0, k=NPOS):
    """per session: median, g, the ALL / CAP8 baskets and their mirrors from the recounted universe -> {(variant, cell): [(row, ticker, side)]}; the pool order is the ticker order (the tie-break)"""
    out = {(v, c): [] for v in ("P", "M") for c in CELLS}
    for i in range(i0, len(P.D.days)):
        el = [tk for tk in tick if why.get((i, tk)) == 0]
        if len(el) < 2 * k:
            continue
        med = float(np.median([gap[i, tk] for tk in el]))
        g = {tk: gap[i, tk] - med for tk in el}
        for c in CELLS:
            pool = el if c == "ALL" else [tk for tk in el if abs(g[tk]) <= CAP + 1e-12]
            if len(pool) < 2 * k:
                continue
            o = sorted(pool, key=lambda tk: (g[tk], tick.index(tk)))
            out["P", c] += [(i, tk, 1.0) for tk in o[:k]] + [(i, tk, -1.0) for tk in o[-k:]]
            out["M", c] += [(i, tk, 1.0) for tk in o[-k:]] + [(i, tk, -1.0) for tk in o[:k]]
    return out


def smoke_refusal(root):
    """A.smoke_refusal's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, ATTN's OUT, the #463 records folder) + this harness's OUT,
    the calendar cache and the DDW r1 folder"""
    why = A.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    for n, q in (("XGAP OUT", OUT), ("the calendar cache", ca_paths()["dir"]), ("DDW r1's folder", os.path.dirname(DDW_STAGE_A))):
        try:
            if os.path.commonpath([real(root), real(q)]) == real(root):
                return f"smoke refused: {root} is or holds {n}"
        except ValueError:
            pass
    return None


def smoke(*a):
    import shutil
    global OUT, CHECK_BOOK, DDW_STAGE_A, MEMBERS_CSV, TBIS_QA, EARN_CSV, CAL_RAW_SHA, CAL_CSV_SHA
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "xgap_smoke"))
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    me, data = sys.modules[__name__], A.data_mod()
    keep = dict(OUT=OUT, CHECK_BOOK=CHECK_BOOK, RULES=dict(RULES), R11_OUT=R11.OUT, DDW=DDW_STAGE_A, MEM=MEMBERS_CSV, TBIS=TBIS_QA, EARN=EARN_CSV, PIN=(CAL_RAW_SHA, CAL_CSV_SHA),
                S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get), nq=(data.find_master, data.load_master_arrays))
    t_start = time.time()
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    OUT, R11.OUT = os.path.join(root, "out"), os.path.join(root, "r11")
    S.OUT, S.CACHE, S.BOOK = os.path.join(root, "siporb_out"), os.path.join(root, "cache"), os.path.join(root, "r4", "book463_daily.csv")
    DDW_STAGE_A, MEMBERS_CSV, TBIS_QA = os.path.join(root, "ddw_r1", "ddw_stageA.json"), os.path.join(root, "members.csv"), os.path.join(root, "tbis.csv")
    EARN_CSV = os.path.join(root, "earnings.csv")
    for p in (OUT, R11.OUT, S.OUT, S.CACHE, os.path.dirname(nq_cache_path())):
        os.makedirs(p)
    S.SMOKE, S.PACE, S.BACKOFF, S.RETRY = True, 0.0, 0.0, 0.0
    CHECK_BOOK = False                                                                     # the book check is off in smoke only: its synthetic book cannot reproduce #463
    inside = lambda p: os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root)
    assert all(inside(p) for p in (OUT, R11.OUT, S.OUT, S.CACHE, DDW_STAGE_A, MEMBERS_CSV, TBIS_QA, EARN_CSV, ca_paths()["dir"])), "every path the smoke writes is inside the smoke dir"
    quiet = lambda: contextlib.redirect_stdout(io.StringIO())
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    flag, sa_path = os.path.join(OUT, FLAG_FILE), os.path.join(OUT, "xgap_stageA.json")

    def capture(fn, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = fn(*args)
        return buf.getvalue(), r

    def must_refuse(fn, frag, burned=False):
        try:
            with quiet():
                fn()
            raise AssertionError(f"must refuse ({frag})")
        except SystemExit as e:
            assert frag in str(e), (frag, str(e))
            assert burned or not os.path.exists(flag), "a refused Stage B must not burn the lockbox"
    try:
        days = pd.DatetimeIndex(sorted(set().union(*[pd.bdate_range(x, y) for x, y in SMOKE_SPANS])))
        t0 = time.time()
        fk = S.Fake(days)
        ca = CAFake(smoke_records(), fk.handle)
        S._http_get = ca.handle
        print(f"synthetic market: {len(fk.names)} names x {len(days)} sessions built in {time.time() - t0:.0f}s")
        with quiet():
            S.assets()
            S.daily()                                                                      # r5_siporb's own daily pull through its fake transport: the synthetic raw + split-adjusted bars
        plant_gaps(fk)
        plant_swap(fk)
        smoke_members(fk, MEMBERS_CSV)
        nbars = smoke_cache(fk, nq_cache_path())
        open(TBIS_QA, "w").write(SMOKE_TBIS)
        open(EARN_CSV, "w").write(SMOKE_EARN)
        nqf = A.NQFake(days)
        nqf.install()
        fm = data.find_master
        data.find_master = lambda inst, tf, sess=None, source=None: fm("NQ" if inst == "ES" else inst, tf, sess, source)        # load_es asks for ES: the fake master answers (synthetic numbers)
        A.smoke_book()
        print(f"synthetic SIPORB daily cache pulled through r5_siporb ({fk.n:,} requests), member cache {nbars:,} bars, membership {len(read_members()):,} intervals")
        # ---- capull [X1]: the probe, the full pull through the mocked transport, the refusals
        with A.patched(me, CA_PROBE=("S08,S20,S09,OLD05,SPL,S14,S11,S12,S13", "2016-06-01", "2025-06-27")):
            txt, _ = capture(capull, "--probe")
        assert "HTTP status: 200" in txt and "top-level keys: corporate_actions, next_page_token" in txt and "yes (page 1 only was read)" in txt and "cash_dividend" in txt and "first record's fields:" in txt, txt
        assert "cusip" in txt and "rate" in txt and "2016-07-13" not in txt and "S08" in txt.splitlines()[0] and txt.count("S08") == 1, "the probe prints field names, never a record's values"
        assert not os.path.exists(ca_paths()["manifest"]), "the probe saves nothing"
        with A.patched(me, CA_PROBE=("TFCF,S08", "2016-06-01", "2025-06-27")):
            txt, _ = capture(capull, "--probe")
        assert "400/422" in txt and "invalid symbol: TFCF" in txt, "a refusal prints the server's message"
        t0 = time.time()
        txt, man = capture(capull)
        P_ = ca_paths()
        assert all(os.path.exists(P_[k]) for k in ("raw", "csv", "manifest")) and not [f for f in os.listdir(P_["dir"]) if f.endswith(".part")], "files renamed into place, no .part left"
        assert man["sha256"]["corporate_actions.csv"] == sha_file(P_["csv"]) == read_json(P_["manifest"])["sha256"]["corporate_actions.csv"] and man["sha256"]["corporate_actions_raw.jsonl"] == sha_file(P_["raw"])
        assert man["rejected_symbols"] == ["TFCF"] and man["names_round2"] == 1 and any("S14X" in q for q in ca.asked), "round 2 asks for the one name a name_change revealed"
        assert man["unknown_types"] == {"cash_mergers": 1} and {"cusip", "foreign", "alternate_symbol", "target", "acquirer_symbol"} <= set(man["fields_not_flattened"]) and "NOT RECOGNISED" in txt
        assert man["rows_by_type"] == {"cash_dividend": 7, "forward_split": 2, "name_change": 3, "stock_dividend": 1, "spin_off": 1, "unit_split": 1, "cash_mergers": 1}, man["rows_by_type"]
        assert man["rows_by_type_year"]["cash_dividend"] == {"2016": 1, "2017": 1, "2024": 3, "2025": 1, "n/a": 1} and man["requests"] == man["pages"] and (man["start"], man["end"]) == (CA_START, CA_END)
        raw_lines = [json.loads(l) for l in open(P_["raw"], encoding="utf-8")]
        assert len(raw_lines) == man["pages"] and raw_lines[0]["round"] == 1 and raw_lines[-1]["round"] == 2 and "smoke" not in open(P_["raw"], encoding="utf-8").read().lower().replace("synthetic", "")
        print(f"capull through the mocked transport ok ({man['requests']} requests, {man['rows']} rows, {time.time() - t0:.0f}s): 429s retried, TFCF bisected out, round 2 = S14X, an unknown type kept raw")
        must_refuse(capull, "a complete corporate-actions pull is already on file")
        txt, man2 = capture(capull, "--force")
        assert man2["sha256"] == man["sha256"] and len([f for f in os.listdir(P_["dir"]) if ".prev-" in f]) == 3, "--force replaces the pull and keeps the old files; the same pages give the same file"
        # ---- capull WIDE mode [for the other lanes]: --names FILE --tag TAG through the same mocked transport; the NDX files are never touched
        ndx0 = {k: (sha_file(P_[k]), os.path.getmtime(P_[k])) for k in ("raw", "csv", "manifest")}
        wnames = ["S08", "s20", "S09", "S04", "S11", "S12", "S13", "S08", "OLD05", "TFCF", "S14", "SPL"] + [f"Q{n:04d}" for n in range(1, 61)]      # a lower-case name, a repeated one, one the endpoint rejects, 60 it never heard of
        names_f = os.path.join(root, "wide_names.txt")
        open(names_f, "wb").write(b"\xef\xbb\xbf# the smoke's wide names\r\n" + "\r\n".join(wnames).encode() + b"\r\n\r\n")
        PW = ca_paths("wide")
        asked0, t0 = len(ca.asked), time.time()
        with A.patched(me, CA_BATCH=7):
            txt, wm = capture(capull, "--names", names_f, "--tag", "wide")
        uniq = list(dict.fromkeys(n.upper() for n in wnames))
        want = {"S05", "S14X"} | set(uniq)                                                   # round 2 = the new names the two name_change records reveal (OLD05 -> S05, S14 -> S14X)
        who = lambda r: r.get("symbol") or r.get("old_symbol") or r.get("source_symbol") or r.get("acquirer_symbol")
        assert all(os.path.exists(PW[k]) for k in ("raw", "csv", "manifest")) and not [f for f in os.listdir(PW["dir"]) if f.endswith(".part")], "the tagged files renamed into place, no .part left"
        assert wm["mode"] == "wide" and wm["tag"] == "wide" and wm["names_file"]["sha256"] == sha_file(names_f) == read_json(PW["manifest"])["names_file"]["sha256"], wm["names_file"]
        assert (wm["names_file"]["symbols"], wm["tickers_round1"], wm["names_file"]["duplicates_dropped"], wm["names_file"]["lowercase_folded"], wm["names_file"]["blank_or_comment_lines"]) == (71, 71, 1, 1, 2), wm["names_file"]
        assert wm["names_round2"] == 2 and wm["rejected_symbols"] == ["TFCF"] and wm["records"] == sum(1 for t, r in smoke_records() if who(r) in want) and wm["batch"] == 7, (wm["names_round2"], wm["records"])
        assert max(len(q) for q in ca.asked[asked0:]) <= 7 and any("S14X" in q for q in ca.asked[asked0:]) and any(q == ("S05", "S14X") for q in ca.asked[asked0:]), "batches of CA_BATCH names; round 2 asks the revealed names"
        assert all((sha_file(P_[k]), os.path.getmtime(P_[k])) == ndx0[k] for k in ("raw", "csv", "manifest")), "the NDX files are untouched"
        assert not any(f.startswith("corporate_actions_wide") and ".prev-" in f for f in os.listdir(PW["dir"])) and "names file wide_names.txt (tag wide)" in txt and "capull done" in txt
        calw, infow = load_calendar(CUT_A, tag="wide")
        assert infow["pinned"] is None and infow["rows_on_file"] == wm["rows"] and sorted(calw["type"].unique()) == sorted(set(wm["rows_by_type"]) - {"cash_mergers"}) , (infow["rows_on_file"], wm["rows_by_type"])
        must_refuse(lambda: capull("--names", names_f, "--tag", "wide"), "already on file for tag 'wide'")
        with A.patched(me, CA_BATCH=7):
            txt, wf = capture(capull, "--force", "--names", names_f, "--tag", "wide")
        prev_w = [f for f in os.listdir(PW["dir"]) if ".prev-" in f and f.startswith("corporate_actions_wide")]
        prev_n = [f for f in os.listdir(PW["dir"]) if ".prev-" in f and not f.startswith("corporate_actions_wide")]
        assert wf["sha256"] == wm["sha256"] and len(prev_w) == 3 and len(prev_n) == 3, "--force: this tag's pull only (the NDX pull's three .prev- files are the earlier --force test's), the same pages give the same file"
        nfiles = sorted(os.listdir(PW["dir"]))
        with A.patched(me, CA_PROBE=("S08,S20", "2016-06-01", "2025-06-27")):
            txt, _ = capture(capull, "--names", names_f, "--tag", "other", "--probe")
        assert sorted(os.listdir(PW["dir"])) == nfiles and "names file wide_names.txt (tag other)" in txt and "HTTP status: 200" in txt, "a wide probe saves nothing"
        for args_, frag in ((("--names", names_f), "go together"), (("--tag", "wide"), "go together"), (("--names", names_f, "--tag", "../wide"), "must be 1 to 40"), (("--names", os.path.join(root, "absent.txt"), "--tag", "x"), "is not on file")):
            must_refuse(lambda: capull(*args_), frag)
        assert sorted(os.listdir(PW["dir"])) == nfiles
        bad_f = os.path.join(root, "bad_names.txt")
        open(bad_f, "w").write("S08\nS09,S11\n")
        must_refuse(lambda: capull("--names", bad_f, "--tag", "bad"), "line 2")
        print(f"capull WIDE through the mocked transport ok ({wm['requests']} requests, {wm['rows']} rows, {time.time() - t0:.0f}s): batches of 7, one name rejected, round 2 = S05 + S14X, --force per tag, the NDX files byte-identical")
        # ---- dryload: counts only; with and without the calendar
        txt, H = capture(dryload)
        assert "by year:" in txt and "exclusions by reason" in txt and "calendar vs price rules" in txt and "$" not in txt and "ROC" not in txt and "net " not in txt.replace("net dollar", ""), "dryload prints counts only"
        assert "csv DIFFERS, raw jsonl DIFFERS" in txt and "stage_a and stage_b refuse unless both match" in txt, "[MANAGER #58] the synthetic calendar is not the pinned one: dryload says so and goes on"
        cr = H["chain_recovery"]
        assert "symbol map through the name-change chain [X1]" in txt and set(cr["tickers_recovered"]) == {"OLD05"} and cr["tickers_rescued"] == {} and cr["by_year"][2016]["recovered"] > 0 and cr["by_year"][2025]["recovered"] == 0 and "GHOST" in cr["tickers_no_data_after_chain"] and "OLD05" not in cr["tickers_no_data_after_chain"], cr
        assert all(v["no_data_same_ticker"] >= v["no_data_after_chain"] and v["no_data_same_ticker"] - v["no_data_after_chain"] == v["recovered"] for v in cr["by_year"].values()), "the chain recovers exactly the no-data it removes"
        assert "ex-dividend exclusions [X1] (member-days) by year" in txt and "the ex-date flag fired, by type: cash_dividend" in txt and sum(H["ex_div_by_type"]["cash_dividend"].values()) > 0 and sum(H["ex_div_by_type"]["spin_off"].values()) > 0 \
            and sum(H["ex_div_by_type"]["stock_dividend"].values()) > 0, H["ex_div_by_type"]
        assert all(d < "2025-06-30" for d in dates_of(txt)) and H["member_days_by_year"] and H["map_years_over_2pct"], (H["map_years_over_2pct"], txt[:300])
        assert "[TV X2] identity drops against the signal" in txt and "TRIGGERED" in txt and "no-data (survivorship) drops by year [NOISE H3]" in txt and "TBIS volume-confirmed flag [NOISE H1]" in txt and "[TV X6] megacap_earnings.csv" in txt
        assert "[TV X4] beta twin coverage" in txt and H["twin_coverage"]["twin_sessions"] > 100 and H["twin_coverage"]["eligible_with_beta"] > 3000, H["twin_coverage"]
        assert "share-class members [TV X1]" in txt and "PCLS/PCLSA" in txt and H["share_class"]["groups"] == [list(SMOKE_PAIR)] and "refused cross-class mappings:" in txt and "PCLS -> PCLSA" in txt, txt
        assert sum(r["name_days"] for r in H["share_class"]["refused_cross_class_name_days"]) > 50, H["share_class"]
        assert sum(H["tbis"]["removed_only_by_a_flag_dated_t"].values()) == 1, ("S19's flag day: removed only by the draft's window (t-5 .. t)", H["tbis"])
        os.replace(P_["manifest"], P_["manifest"] + ".away")
        txt0, H0 = capture(dryload)
        os.replace(P_["manifest"] + ".away", P_["manifest"])
        assert "NOT ON FILE" in txt0 and "exclusions by reason" in txt0 and sum(H0["excluded_first_rule_by_year"]["ex_div"].values()) == 0 and sum(H["excluded_first_rule_by_year"]["ex_div"].values()) > 0
        assert "name-change chain" not in txt0 and "ex-dividend exclusions" not in txt0 and sum(v["recovered"] for v in H0["chain_recovery"]["by_year"].values()) == 0, "without a calendar there is no chain"
        assert H0["share_class"]["refused_cross_class_name_days"] == [] and H0["share_class"]["groups"] == [list(SMOKE_PAIR)], "without a calendar there is no chain to refuse; the pair is still a pair"
        print("dryload ok: counts only, with the calendar and without it (then the ex-dividend rule is off and the map is same-ticker only)")
        # ---- stage_a refuses without a usable calendar, under a changed spec and unless the calendar is the pinned one (nothing computed)
        must_refuse(stage_a, "pre-registration pins")                                       # [MANAGER #58] the REAL pinned shas are still in place: this synthetic calendar is not the pinned one
        os.replace(P_["csv"], P_["csv"] + ".away")
        must_refuse(stage_a, "not on file")
        os.replace(P_["csv"] + ".away", P_["csv"])
        csv0 = open(P_["csv"], "rb").read()
        open(P_["csv"], "ab").write(b"x\n")
        must_refuse(stage_a, "does not match the sha256")
        open(P_["csv"], "wb").write(csv0)
        with A.patched(me, PREREG_SHA="0" * 64):
            must_refuse(stage_a, "DIFFERS")
        CAL_RAW_SHA, CAL_CSV_SHA = man["sha256"]["corporate_actions_raw.jsonl"], man["sha256"]["corporate_actions.csv"]       # from here on the smoke's calendar IS the pinned one (restored at the end)
        txt, _ = capture(dryload)
        assert "csv matches, raw jsonl matches" in txt
        assert not os.path.exists(sa_path) and load_calendar(CUT_A)[1]["csv_sha256"] == man["sha256"]["corporate_actions.csv"]
        # ---- Stage A, every bar as registered (the synthetic world cannot pass them): the FAIL path
        print("--- Stage A, every bar as registered: the FAIL path")
        txt, out = capture(stage_a)
        print(txt.rstrip())
        assert out["judged"] is True and not out["stageA"]["PASS"] and out["stageA"]["candidate"] is None and out["a2_report"]["cell"] is None and all(v == "FAIL" for v in out["stageA"]["cells"].values()) and os.path.exists(sa_path), out["stageA"]
        assert out["twin_coverage"]["twin_sessions"] > 100 and "[TV X4] beta twin coverage" in txt, out["twin_coverage"]
        assert out["calendar"]["pinned"] == {"csv": True, "raw": True} and "both are the files the prereg pins [MANAGER #58]" in txt and "symbol map through the name-change chain [X1]" in txt and "ex-dividend exclusions [X1]" in txt
        assert out["x2"]["triggered"] is True and out["stageA"]["readings"] == 2 and out["x2"]["tails"]["ALL"]["ratio"] > 2.0 and all(out["cells"][c_]["stageA"]["slot_empty"] is not None for c_ in CELLS), out["x2"]
        assert out["siblings"]["cells_tried"] == 4 and SIBLINGS["text"] in txt and "97.5th percentile" in txt and "95th percentile" in txt and "(c) ROC>null p97.5" in txt and "twin net>0 base" in txt and "slots-left-empty reading" in txt
        assert "A2 REPORT (not a gate" in txt and "power line (MDL map)" in txt and "book shadow line" in txt and "[TV X5] dividend payers" in txt and "[TV X6] ex-earnings reading" in txt and "share-class members [TV X1]" in txt
        assert all(d < "2025-06-30" for d in dates_of(txt)), "Stage A printed a lockbox date"
        cd = pd.read_csv(os.path.join(OUT, "xgap_audit_candidates.csv"))
        reg = cd[cd["reading"].isin(["registered", "both"])]
        assert set(cd["cell"]) == {"ALL", "CAP8"} and cd["date"].max() < "2025-06-30" and set(cd["reading"]) <= {"registered", "slots-left-empty", "both"} and (reg.groupby("cell").size() == 30).all() and \
            (reg.groupby("cell")["pnl"].apply(lambda s: s.is_monotonic_decreasing)).all(), "the 30 largest name-day gains of each cell, registered reading"
        slot = cd[cd["reading"].isin(["slots-left-empty", "both"])]
        assert (slot.groupby("cell").size() <= 30).all() and (cd["reading"] == "slots-left-empty").any() and len(cd) > 60, "[TV X2] the second reading's largest gains are on the audit list too"
        must_refuse(stage_b, "no Stage A pass")
        # ---- [TV X2] NOT triggered (the real data's path: its ratio is 1.1): the registered reading alone, nothing second is computed or stored
        print("--- X2 switched off: one reading (the path a clean real run takes)")
        RULES.update(x2=False)
        txt1, out1 = capture(stage_a)
        assert out1["x2"]["triggered"] is False and out1["stageA"]["readings"] == 1 and out1["null_slot_empty"] is None and out1["judged"] is True and not out1["stageA"]["PASS"], out1["x2"]
        assert all(out1["cells"][c_]["stageA"]["slot_empty"] is None for c_ in CELLS) and "switched off: the registered reading alone" in txt1 and "slots-left-empty reading" not in txt1 and "TRIGGERED" not in txt1
        same = lambda a_, b_: json.dumps(a_, sort_keys=True, default=str) == json.dumps(b_, sort_keys=True, default=str)
        assert all(same(out1["cells"][c_]["stageA"]["checks"], out["cells"][c_]["stageA"]["checks"]) and same(out1["cells"][c_]["stageA"]["stats"], out["cells"][c_]["stageA"]["stats"]) for c_ in CELLS) and same(out1["null"], out["null"]),             "reading 1 does not depend on whether a second reading is computed"
        cd1 = pd.read_csv(os.path.join(OUT, "xgap_audit_candidates.csv"))
        assert len(cd1) == 60 and set(cd1["reading"]) == {"registered"}, "no second reading: only the registered reading's 30 largest a cell"
        RULES.update(x2=True)
        # ---- every bar waived but the audit: PENDING_AUDIT, then the audit loop (one data event) until it is complete
        print("--- every bar waived except the hand audit: not judged until the audit is complete")
        RULES.update(sessions=1, roc=-1e9, pf=0.0, t=-1e9, null=False, mirror=False, stress=False, exbest=False, years=0, halves=False, x2020=False, twin=False, a2_roc=-1e9, a2_sort=-1e9, a2_dd=1e12, b_namedays=1, b_sessions=1)
        txt, out = capture(stage_a)
        assert out["judged"] is False and all(v == "PENDING_AUDIT" for v in out["stageA"]["cells"].values()) and not out["stageA"]["PASS"] and out["audit"]["complete"] == {"ALL": False, "CAP8": False} == out["audit_complete"], out["stageA"]
        assert "NOT judged" in txt and "NOT complete" in txt and out["a2_report"]["cell"] is None and out["cells"]["ALL"]["A2"]["book_shadow_line"] is True
        must_refuse(stage_b, "no Stage A pass")
        # [TV X4] the beta twin is a VETO: the same waived world with the twin's ROC bar made impossible (NaN never passes) - the cells that were PENDING_AUDIT (they clear every other bar) now FAIL
        print("--- the beta twin is a veto: every other bar waived, the twin's ROC bar made impossible")
        RULES.update(twin=True, twin_half=float("nan"))
        txt, out_v = capture(stage_a)
        for cell in CELLS:
            s_ = out_v["cells"][cell]["stageA"]
            failing = [k for k, v in s_["checks"].items() if not v and not k.startswith("(h)")]
            assert s_["verdict"] == "FAIL" and not s_["PASS"] and s_["core_ok"] is False and "twin ROC >= half the primary's" in failing and all(k.startswith("twin") for k in failing), (cell, failing)
            f2 = [k for k, v in s_["slot_empty"]["checks"].items() if not v and not k.startswith("(h)")]
            assert "twin ROC >= half the primary's" in f2 and all(k.startswith("twin") for k in f2), (cell, f2)
        assert out_v["judged"] is True and not out_v["stageA"]["PASS"] and out_v["stageA"]["candidate"] is None
        RULES.update(twin=False, twin_half=0.5)
        # [TV X2] a cell passes only if BOTH readings pass: the slots-left-empty reading made to fail one check (the calls come ALL reading 1, ALL reading 2, CAP8 reading 1, CAP8 reading 2)
        print("--- a cell passes only if both readings pass: the slots-left-empty reading made to fail one check")
        calls, real_judge = itertools.count(), judge_a

        def judge_mut(e, p, a):
            chk = real_judge(e, p, a)
            if next(calls) % 2 == 1:
                chk[next(k for k in chk if k.startswith("(a)"))] = False
            return chk
        with A.patched(me, judge_a=judge_mut):
            txt, out_m = capture(stage_a)
        for cell in CELLS:
            s_ = out_m["cells"][cell]["stageA"]
            assert s_["core_ok"] is True and s_["slot_empty"]["core_ok"] is False and s_["verdict"] == "FAIL" and not s_["PASS"], (cell, s_["verdict"])
        assert out_m["judged"] is True and not out_m["stageA"]["PASS"]
        audit_path, verdicts, event = os.path.join(OUT, "xgap_audit.csv"), {}, None
        open(audit_path, "w").write("symbol,date,cell,verdict,note\nX,2020-01-02,ALL,maybe,\n")
        must_refuse(stage_a, "needs symbol")
        for it in range(8):
            cd = pd.read_csv(os.path.join(OUT, "xgap_audit_candidates.csv"))
            for r in cd.itertuples():
                if (r.symbol, r.date, r.cell) not in verdicts:
                    if event is None and r.cell == "ALL" and r.rank == 1:
                        event = (r.symbol, r.date)
                        verdicts[(r.symbol, r.date, r.cell)] = "data_event"
                    else:
                        verdicts[(r.symbol, r.date, r.cell)] = "keep"
            pd.DataFrame([{"symbol": s, "date": d, "cell": c, "verdict": v, "note": "smoke"} for (s, d, c), v in verdicts.items()]).to_csv(audit_path, index=False)
            txt, out = capture(stage_a)
            assert all(d < "2025-06-30" for d in dates_of(txt))
            if out["judged"]:
                break
        assert out["judged"] is True and it >= 1 and out["audit"]["complete"] == {"ALL": True, "CAP8": True} == out["audit_complete"] and out["stageA"]["PASS"] is True and out["stageA"]["candidate"] in CELLS, (it, out["audit"])
        assert out["audit"]["data_events_removed"] == [[event[0], event[1]]] and "hand audit ALL: complete" in txt
        best = out["stageA"]["candidate"]
        rocs = {c_: out["cells"][c_]["stageA"]["stats"]["roc"] for c_ in CELLS}
        assert all(out["cells"][c_]["stageA"]["PASS"] for c_ in CELLS) and best == max(CELLS, key=lambda c_: (rocs[c_], -CELLS.index(c_))), "[MANAGER #56] both cells pass Stage A: the candidate is the one with the higher WF ROC @ $30k"
        c = out["a2_report"]["c"]
        assert c > 0 and out["a2_report"]["cell"] == best and abs(out["cells"][best]["A2"]["by_mult"]["1"]["c"] - c) < 1e-12 and abs(out["a2_report"]["by_cell"][best]["c"] - c) < 1e-12
        assert out["a2_report"]["book_shadow_line"] is True and "book shadow line YES" in txt, "A2 is a report: its (waived) bars pass here, so the book shadow line is opened"
        for cell in CELLS:
            nd = pd.read_csv(os.path.join(OUT, f"xgap_namedays_WF_{cell}.csv.gz"))
            assert not ((nd["symbol"] == event[0]) & (nd["date"] == event[1])).any(), "a data event is gone from the cell"
        print(f"the audit loop: {it + 1} runs, {len(verdicts)} verdict rows, the data event {event[0]} {event[1]} removed; Stage A PASS under waived bars (A2 a report); cell {best}, c = {c:.4f}")
        # ---- the independent recount (plain python from the long frames, the cache rows and the calendar rows) against the arrays - the registered reading AND the one with the identity check waived [TV X2]
        B, legs = A.load_463()
        cal, cinfo = load_calendar(CUT_A)
        P = prepare(CUT_A, cal, cinfo)
        arows, removed = read_audit(audit_path, CUT_A)
        W = assemble(P, removed)
        U, Uw = universe(W), universe(W.waived)
        rows, i0 = A.book_rows(B, P.D), int(P.D.days.searchsorted(WF0))
        R = run_cells(W, U, rows, B.n, i0, 0)
        untrade = Uw.elig & W.idfail
        R2 = run_cells(W.waived, Uw, rows, B.n, i0, 0, untrade=untrade)
        t0 = time.time()
        why_b, gap_b, chosen, tick, (ww_b, gapw_b, chosen_w, dropped_b, beta_b, cr_b) = brute_world(P, removed)
        tl = list(W.tick)
        assert tl == tick and len(why_b) == int((U.why >= 0).sum()) and (U.why[U.why < 0] == -1).all(), "every member-day is accounted for"
        bad = [(i, tk) for (i, tk), code in why_b.items() if U.why[i, tl.index(tk)] != code]
        assert not bad, f"{len(bad)} member-days disagree on the first failing rule: {bad[:5]} {[(why_b[b], U.why[b[0], tl.index(b[1])]) for b in bad[:5]]}"
        cnt = Counter(why_b.values())
        assert all(cnt[c_] > 0 for c_ in (0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12)), f"every planted rule fired at least once: {dict(cnt)}"
        for (i, tk), (s, o935, cl) in chosen.items():
            x = tl.index(tk)
            assert abs(W.gap[i, x] - gap_b[i, tk]) < 1e-12 and sym_of(W, i, x) == s and abs(W.o935[i, x] - o935) < 1e-12 and abs(W.Cl[i, x] - cl) < 1e-12
        bb = brute_baskets(P, why_b, gap_b, tick, i0)
        for key, lst in bb.items():
            nd = R.nd[key]
            mine = list(zip(nd["i"].tolist(), [tl[x] for x in nd["x"]], nd["side"].tolist()))
            assert len(lst) > 1000 and mine == lst, (key, len(mine), len(lst), [m for m, l in zip(mine, lst) if m != l][:3])
            ref = sum(name_pnl(sd, chosen[i, tk][1], chosen[i, tk][2], COST["base"]) for i, tk, sd in lst)
            assert abs(ref - name_pnl(nd["side"], nd["o"], nd["c"], COST["base"]).sum()) < 1e-6
        hcr = hygiene(W, U)["chain_recovery"]["by_year"]                                       # the name-change chain's recovery counts against the independent recount
        for y_, v_ in hcr.items():
            assert (v_["no_data_same_ticker"], v_["no_data_after_chain"], v_["recovered"], v_["recovered_identity_ok"], v_["rescued_from_identity_drop"]) == tuple(cr_b[y_, k_] for k_ in ("own_nodata", "after_nodata", "recovered", "recovered_ok", "rescued")), (y_, v_)
        n_rec = sum(v_["recovered"] for v_ in hcr.values())
        assert n_rec > 100 and sum(v_["recovered_identity_ok"] for v_ in hcr.values()) > 0 and (np.logical_or.reduce(list(W.exdiv_type.values())) == W.exdiv).all(), "the chain recovers OLD05's member-days; the flags by type are the ex-dividend flag"
        # the twin [TV X4]: the betas (returns read through the symbol chosen WITHOUT the identity check) and the twin baskets
        fb = {(i, tk): v for (i, tk), v in beta_b.items() if np.isfinite(v)}
        mine_b = {(i, tl[x]): float(W.beta[i, x]) for i, x in zip(*np.nonzero(np.isfinite(W.beta)))}
        assert set(mine_b) == set(fb) and len(fb) > 3000 and max(abs(mine_b[k_] - fb[k_]) for k_ in fb) < 1e-8, (len(mine_b), len(fb))
        assert np.allclose(W.beta, W.waived.beta, equal_nan=True), "one beta array for both readings"
        tw = brute_twin(P, why_b, gap_b, beta_b, tick, i0)
        n_tw = 0
        for key, lst in tw.items():
            nd = R.nd[key]
            mine = list(zip(nd["i"].tolist(), [tl[x] for x in nd["x"]], nd["side"].tolist()))
            assert len(lst) > 1000 and mine == lst, (key, len(mine), len(lst), [m for m, l in zip(mine, lst) if m != l][:3])
            n_tw += len(lst)
        # the waived world and the slots-left-empty baskets
        badw = [(i, tk) for (i, tk), code in ww_b.items() if Uw.why[i, tl.index(tk)] != code]
        assert not badw, f"{len(badw)} member-days disagree on the waived reading's first failing rule: {badw[:5]}"
        assert {(i, tl[x]) for i, x in zip(*np.nonzero(Uw.elig))} == {k_ for k_, code in ww_b.items() if code == 0}, "the would-be universe is the recount's"
        assert {(i, tl[x]) for i, x in zip(*np.nonzero(untrade))} == {k_ for k_, dd in dropped_b.items() if dd and ww_b[k_] == 0} and untrade.sum() > 500, "the untradeable name-days are the ones the identity check dropped"
        assert (U.elig == (Uw.elig & ~W.idfail)).all() and not (U.elig & W.idfail).any(), "the registered universe = the would-be universe minus what the identity check dropped"
        for (i, tk), (s, o935, cl) in chosen_w.items():
            x = tl.index(tk)
            assert abs(W.waived.gap[i, x] - gapw_b[i, tk]) < 1e-12 and sym_of(W.waived, i, x) == s and abs(W.waived.o935[i, x] - o935) < 1e-12 and abs(W.waived.Cl[i, x] - cl) < 1e-12
        bb2, n2 = brute_baskets(P, ww_b, gapw_b, tick, i0), 0
        for key, lst in bb2.items():
            lst = [(i, tk, sd) for (i, tk, sd) in lst if not dropped_b.get((i, tk))]               # the dropped names' slots stay EMPTY: nothing steps in
            nd = R2.nd[key]
            mine = list(zip(nd["i"].tolist(), [tl[x] for x in nd["x"]], nd["side"].tolist()))
            assert len(lst) > 800 and mine == lst, (key, len(mine), len(lst), [m for m, l in zip(mine, lst) if m != l][:3])
            n2 += len(lst)
            if key[1] == "ALL":
                assert set(mine) <= set(zip(R.nd[key]["i"].tolist(), [tl[x] for x in R.nd[key]["x"]], R.nd[key]["side"].tolist())) and len(mine) < len(R.nd[key]["i"]), \
                    "ALL: the slots-left-empty positions are a subset of the registered reading's, and fewer"
        elig_m = [[ww_b.get((i, tk)) == 0 for tk in tick] for i in range(len(P.D.days))]
        gap_m = [[gapw_b.get((i, tk), float("nan")) for tk in tick] for i in range(len(P.D.days))]
        idf_m = [[bool(dropped_b.get((i, tk))) for tk in tick] for i in range(len(P.D.days))]
        x2 = x2_rates(W, Uw, i0)
        bk, tls = recount_x2(gap_m, elig_m, idf_m, NPOS, i0)
        assert all([x2["by_bucket_side"][bn][s_]["n"], x2["by_bucket_side"][bn][s_]["dropped"]] == bk[bn][s_] for bn in bk for s_ in ("long", "short")), (x2["by_bucket_side"], bk)
        assert all([x2["tails"][c_][g_]["n"], x2["tails"][c_][g_]["dropped"]] == tls[c_][g_] for c_ in CELLS for g_ in ("tail", "rest")) and x2["triggered"] is True and x2["tails"]["ALL"]["ratio"] > 2.0, (x2["tails"], tls)
        # the share-class rule: the planted swap (the cache's PCLS bars are SIPORB's PCLSA bars) is refused, counted, and never mapped
        assert W.pairs == [SMOKE_PAIR] and W.pair_members == set(SMOKE_PAIR) and {(a_, b_) for (a_, b_, y_) in W.refused} == {("PCLS", "PCLSA")} and sum(W.refused.values()) > 300, W.refused
        xp = tl.index("PCLS")
        assert not any(sym_of(W, i, xp) == "PCLSA" for i in range(len(P.D.days))) and not any(sym_of(W.waived, i, xp) == "PCLSA" for i in range(len(P.D.days))), "a class member never maps across classes"
        assert sum(1 for (i, tk), code in why_b.items() if tk == "PCLS" and code == 3) > 300 and W.pair_info["chain_edges_refused"] == [["PCLS", "PCLSA"]], "its own-ticker bars disagree with the cache's: dropped, not rescued by the chain"
        i_gap = {n: days.get_loc(TS(d)) for n, d, _ in GAP_PLANTS}
        s10 = R.nd[("P", "ALL")]
        assert any(tl[x] == "S10" and i == i_gap["S10"] and sd == -1 for i, x, sd in zip(s10["i"], s10["x"], s10["side"])) and not any(tl[x] == "S10" and i == i_gap["S10"] for i, x in zip(R.nd[("P", "CAP8")]["i"], R.nd[("P", "CAP8")]["x"])), \
            "the planted +12% gapper is a short in ALL and outside CAP8"
        print(f"independent recount ok ({time.time() - t0:.0f}s): {len(why_b):,} member-days agree on the first failing rule (every planted rule fired: {dict(sorted(cnt.items()))}), "
              f"{len(chosen):,} eligible name-days agree on gap / symbol / prices, {sum(len(v) for v in bb.values()):,} basket positions (ALL, CAP8, both mirrors) equal the arrays', {len(fb):,} twin betas and {n_tw:,} twin positions too, {n_rec:,} member-days the name-change chain recovers; the waived world: {len(chosen_w):,} would-be name-days, "
              f"{int(untrade.sum()):,} untradeable, {n2:,} slots-left-empty positions equal the arrays'; X2 tail ratio {x2['tails']['ALL']['ratio']:.1f}; the class swap refused on {sum(W.refused.values()):,} name-days")
        js_a = read_json(sa_path)
        assert {k: js_a.get(k) for k in stamp()} == stamp() and js_a["prereg_sha256_lf"] == PREREG_SHA and js_a["inputs"]["calendar_csv_sha256"] == man["sha256"]["corporate_actions.csv"]
        rp = js_a["reports"]
        assert "error" not in rp["es_beta"] and rp["es_beta"]["ALL"]["all_wf_rows"]["cc"]["n"] > 100 and set(rp["cells"]["ALL"]) >= {"sides", "buckets", "top_gains", "stress", "cents", "mirror", "twin", "twin_stress", "map_point", "corr_daily"}
        assert rp["x2"]["triggered"] is True and rp["payers"]["ALL"]["long"]["n"] > 0 and rp["payers"]["universe"]["member_days_eligible"] > 0 and rp["siblings"]["cells_tried"] == 4 and rp["identity"] == {"abs": 0.01, "rel": 0.001}
        assert rp["earnings"]["coverage"]["member_tickers_covered"] == ["S02", "S16"] and rp["earnings"]["coverage"]["events_before_the_cut"] == 4 and set(rp["earnings"]["cells"]) == set(CELLS) and rp["earnings"]["coverage"]["wf_eligible_name_days_removed"] > 0
        assert rp["hygiene"]["share_class"]["groups"] == [list(SMOKE_PAIR)] and rp["hygiene"]["tbis"]["registered_t5_to_t1_removals"] and js_a["x2"]["triggered"] is True and js_a["null_slot_empty"]["p97_5"] >= js_a["null_slot_empty"]["p95"]
        assert len(rp["cells"]["ALL"]["top_gains"]) == 20 and set(rp["cells"]["ALL"]["buckets"]) == {"0-2%", "2-4%", "4-8%", ">8%"} and rp["cells"]["ALL"]["buckets"][">8%"]["n"] > 0 and rp["cells"]["CAP8"]["buckets"][">8%"]["n"] == 0
        assert any(k.startswith("0:") for k in rp["cells"]["ALL"]["corr_daily"]) and rp["hygiene"]["calendar_vs_price"]["calendar_only"] and "2024" in {str(k) for k in rp["hygiene"]["calendar_vs_price"]["price_only"]}
        # ---- Stage B: every refusal leaves no flag; then the one read
        print("--- Stage B refusal paths (no flag in any of them), then the one read")
        js0 = open(sa_path).read()

        def edited(edit):
            j = json.loads(js0)
            edit(j)
            json.dump(j, open(sa_path, "w"))
        for edit, frag in ((lambda j: j.update(judged=False), "no Stage A pass"), (lambda j: j["stageA"].update(PASS=False), "no Stage A pass"), (lambda j: j["stageA"].update(candidate=None), "hand audit"), (lambda j: j["audit"]["complete"].update({best: False}), "hand audit"), (lambda j: j["audit_complete"].update({best: False}), "hand audit"), (lambda j: j.pop("audit_complete"), "hand audit"),
                           (lambda j: j.update(harness_sha256="0" * 64), "different harness version"), (lambda j: j.update(early_close=j["early_close"][1:]), "different harness version"),
                           (lambda j: j.update(prereg_sha256_lf="0" * 64), "another pre-registration"), (lambda j: j["inputs"].update(calendar_csv_sha256="0" * 64), "differ from the ones Stage A read"),
                           (lambda j: j["inputs"].update(nqbrd_cache_sha256="0" * 64), "differ from the ones Stage A read")):
            edited(edit)
            must_refuse(stage_b, frag)
        edited(lambda j: j["a2_report"]["by_cell"][best].update(book_shadow_line=False, book_roc=-5.0))
        with quiet():
            assert b_preflight(read_json(sa_path), flag) == (best, c), "A2 is a report: a failed book shadow line does not stop Stage B"
        open(sa_path, "w").write(js0)
        with A.patched(me, PREREG_SHA="0" * 64):
            must_refuse(stage_b, "DIFFERS")
        for kw in ({"CAL_CSV_SHA": "0" * 64}, {"CAL_RAW_SHA": "0" * 64}):                  # [MANAGER #58] Stage B refuses a calendar that is not the pinned one, before the flag
            with A.patched(me, **kw):
                must_refuse(stage_b, "pre-registration pins")
        must_refuse(stage_b, "sibling decision is not on file")
        os.makedirs(os.path.dirname(DDW_STAGE_A), exist_ok=True)
        json.dump({"judged": False}, open(DDW_STAGE_A, "w"))
        must_refuse(stage_b, "not judged yet")
        cellrec = lambda roc: {"stageA": {"PASS": True}, "A2": {"pass": True, "book_roc": roc}}
        json.dump({"judged": True, "cells": {"L2-S": cellrec(out["a2_report"]["book_roc"] + 1.0)}}, open(DDW_STAGE_A, "w"))
        must_refuse(stage_b, "the sibling rule - DDW r1's L2 cell L2-S")
        ddw_cells = lambda **kw: {n: {"PASS": True, "A2": {"pass": True, "roc": r}, "audit": {"audit_complete": True}} for n, r in kw.items()}
        json.dump({"judged": True, "pending_audit": [], "candidate": {"cell": "L2-F", "c": 0.5, "a2_book_roc": out["a2_report"]["book_roc"] + 1.0}, "stageA": {"cells": ddw_cells(**{"L2-F": out["a2_report"]["book_roc"] + 1.0})}},
                  open(DDW_STAGE_A, "w"))                                                  # DDW r1's own shape: its candidate is an L2 cell that beats XGAP's A2 book ROC
        must_refuse(stage_b, "L2 cell L2-F reaches its Stage B")
        edited_ddw_ok = {"judged": True, "pending_audit": [], "candidate": {"cell": "L1-F", "c": 0.5, "a2_book_roc": 1e9},
                         "stageA": {"cells": ddw_cells(**{"L1-F": 1e9, "L2-F": out["a2_report"]["book_roc"] + 5.0})}}          # DDW r1's own shape: its pick is an L1 cell, so no L2 cell reaches Stage B (a higher L2 cell that was not picked does not count)
        json.dump(edited_ddw_ok, open(DDW_STAGE_A, "w"))
        open(P_["csv"], "ab").write(b"x\n")
        must_refuse(stage_b, "does not match the sha256")
        open(P_["csv"], "wb").write(csv0)
        mem0 = open(MEMBERS_CSV, "rb").read()
        open(MEMBERS_CSV, "ab").write(b"ZZTOP,2016-06-01,\n")
        must_refuse(stage_b, "differ from the ones Stage A read")
        open(MEMBERS_CSV, "wb").write(mem0)
        assert sha_file(MEMBERS_CSV) == js_a["inputs"]["members_sha256"] and sha_file(P_["csv"]) == js_a["inputs"]["calendar_csv_sha256"]
        CHECK_BOOK = True
        must_refuse(stage_b, "do not reproduce its WF / LB numbers")
        CHECK_BOOK = False
        ap = open(audit_path).read()
        open(audit_path, "a").write(f"{event[0]},2016-07-20,CAP8,data_event,extra\n")
        must_refuse(stage_b, "data events differ")
        open(audit_path, "w").write(ap)
        edited(lambda j: j["cells"][best]["stageA"]["stats"].update(net=j["cells"][best]["stageA"]["stats"]["net"] + 1000.0))
        must_refuse(stage_b, "do not reproduce on Stage B's data")
        open(sa_path, "w").write(js0)
        print("Stage B refused before the flag in every case above (no pass / audit incomplete / stamp / spec / calendar sha / cache sha / sibling missing, unjudged, beaten / book / audit file / WF drift)")
        txt, ok = capture(stage_b)
        print(txt.rstrip())
        sb = read_json(os.path.join(OUT, "xgap_stageB.json"))
        assert os.path.exists(flag) and sb["pass"] == ok and sb["cell"] == best and abs(sb["c"] - c) < 1e-12 and sb["sibling"] == "clear" and sb["wf_recheck"] == "equal", sb["checks"]
        assert set(sb["checks"]) == {f"leg name-days>={RULES['b_namedays']}", f"leg traded sessions>={RULES['b_sessions']}", "leg net>0", "leg net>0 without its top name-day"}, "the book add is not part of the pass"
        assert sb["book_add_reported"]["reported_only"] is True and sb["book_add_reported"]["cell"] == best and np.isfinite(sb["book_add_reported"]["roc"]) and {k: sb.get(k) for k in stamp()} == stamp()
        assert sb["leg"]["name_days"] > 0 and sb["leg"]["sessions"] > 0 and "Stage B (lockbox, read once)" in txt and "REPORTED, never a pass" in txt
        must_refuse(stage_b, "already read", burned=True)
        must_refuse(stage_a, "Stage A is frozen", burned=True)
        pm = A.peak_mb()
        print("Stage B refused before the flag in every case, wrote the flag only after the load and every check, and refused a second read; Stage A is frozen after it")
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline")
    finally:
        OUT, CHECK_BOOK, DDW_STAGE_A, MEMBERS_CSV, TBIS_QA, EARN_CSV = keep["OUT"], keep["CHECK_BOOK"], keep["DDW"], keep["MEM"], keep["TBIS"], keep["EARN"]
        CAL_RAW_SHA, CAL_CSV_SHA = keep["PIN"]
        RULES.clear()
        RULES.update(keep["RULES"])
        R11.OUT = keep["R11_OUT"]
        S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get = keep["S"]
        data.find_master, data.load_master_arrays = keep["nq"]


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"capull": capull, "selftest": selftest, "smoke": globals().get("smoke"), "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r16_xgap.py capull [--probe] [--force] [--names FILE --tag TAG] | selftest | smoke DIR | dryload | stage_a | stage_b")
        return
    if cmd in ("stage_a", "stage_b"):                                                       # dryload and capull --probe write nothing
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
