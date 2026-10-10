# RESMOM r1 - the MONTH-END DATA PHOTOGRAPH for the forward BOOK line (PREREG_RESMOM_LINE_R1.txt [F2]: #463 + 0.264 x RES from the 2026-10-30 month-end rank, "a forward stretch needs a fresh calendar pull, pinned by its own
# dated note before it is read"). One command pulls, for ONE month-end, everything r17_resmom.py reads and publishes it as ONE dated, hashed, never-overwritten folder: raw AND split-adjusted daily bars of every name the registered
# universe could contain (the SIPORB cache's own shapes: symbol, date, o, h, l, c, v), Alpaca's corporate-actions calendar over the same window (r16_xgap's flat CSV + raw JSONL, byte for byte the same flattening), and a split cross-check
# of the two (the price side's factor changes against the calendar's splits). Nothing is fixed or dropped on the way: the harness's hygiene decides later.
# WHY SELF-CONTAINED: Alpaca re-adjusts split history between pulls (GE's 2021-07-30 daily bar read 12.95 at about 15:45 and 103.60 at about 17:20 the same afternoon), so a photograph is never stitched onto an older one: every month pulls
# its whole window - through - 430 calendar days .. through, >= 290 sessions = the 252-session regression window + the 25-session hygiene lead + margin - fresh, and a re-pull is a NEW folder (_r2, _r3 ...), never an overwrite.
#   python tools/rocfrontier/r17_resmom_pull.py plan --through 2026-10-30 [--out ROOT] [--hold FILE]     NO network, NO key, any weekday (a future one is fine): the window, the base list's count and sha check, the hold list's count, the request / time estimate
#                                                                                                       (an UPPER BOUND: the active filter below cuts it) - the scheduled task's dry check
#   python tools/rocfrontier/r17_resmom_pull.py pull --through 2026-10-30 [--out ROOT] [--hold FILE]     the pull: --through must be a completed weekday session - before today's New York date, or today with the New York clock at or after 20:00 [P1]; the key comes ONLY from
#                                                                                                       augur_engine/alpaca_keys.py (load_keys: the process environment, then HKCU Environment in the registry, then the JSON files) and is never printed, logged, written
#                                                                                                       or returned; ROOT defaults to C:\EdgeLog\alpaca_cache\resmom_fwd
#   python tools/rocfrontier/r17_resmom_pull.py selftest                                                 fakes only (a fake key lookup, fake bars / assets / calendar calls, a fake clock, a network and key-lookup tripwire): no network, no key, nothing written outside a temp folder
# SYMBOLS REQUESTED = (the base list AND the assets endpoint's ACTIVE set) + the new active listings [P3] + every symbol of the optional --hold FILE (one a line: the names the line holds from the previous rank - pulled ALWAYS, even when inactive now,
# because a name delisted mid-hold still needs its bars up to delisting). The base names dropped as inactive (count, first 20) and the inactive hold names (all) are printed and recorded in the manifest; the 2% error rule counts the requested symbols only.
# Exit codes: 0 = published; 2 = refused or failed (nothing published, no half folder). The LAST line printed is one plain sentence saying which.
# HARDENING (MANAGER #149, 2026-10-09): every Alpaca call follows NO redirect (requests would re-send the APCA-* headers to the new host);
# the key lookup's values are stripped; scrub() / import_alpaca_stocks.redact() replace the key's plain, stripped, JSON-escaped, URL-encoded
# and repr forms, and server text is redacted BEFORE it is truncated; a call gives up after MAX_429 (30) consecutive 429s and the whole
# pull after MAX_RUN_MIN (360) minutes - both printed by `plan` and at the start of `pull`. 360 = 2.3x the 09-30 rehearsal's real 156 min
# (5,693 symbols, other lanes pulling; MANAGER GO 2026-10-09 - 240 was only 1.5x and a cap refusal costs a full re-run).
# WRITTEN OUTSIDE --out (by the shared modules, not by this file): C:\EdgeLog\state\alpaca_rate.json (augur_engine/alpaca_rate.py: the
# account-wide pace every lane shares), C:\EdgeLog\state\alpaca_pulls.jsonl (augur_engine/pull_provenance.py: one receipt per bars call)
# and tools/import_alpaca_stocks.log (import_alpaca_stocks.log(): the 429 back-off and progress lines). EDGELOG_HOME moves the first two.
# Reads: the base list C:\EdgeLog\alpaca_cache\xgap\wide_symbols_siporb_floor_2016_2025.txt (its sha256 is checked first), the optional hold list, and, in `pull`, the Alpaca account through r5_siporb._get (assets, calendar: the shared account pace) and
# import_alpaca_stocks.fetch_bars (bars: pagination, 429 retry, and the PROVENANCE receipt augur_engine/pull_provenance.py files for every pull). Writes ONLY under ROOT: ROOT\_tmp_<through>_<pid>\ while it runs, renamed to ROOT\<through>\
# when - and only when - everything is complete and verified. Imports r5_siporb, r16_xgap and import_alpaca_stocks; copies none of their HTTP code and edits none of them.
# NOT DONE HERE (the forward run's job): pointing r17_resmom at a photograph. r5_siporb.read_long reads CACHE\siporb\daily_raw.parquet / daily_split.parquet (EDGELOG_ALPACA_CACHE moves CACHE; a folder named siporb that is a junction to the photograph does it without
# an edit - the selftest loads the two files through the unchanged r5_siporb.Data that way), and r17_resmom.wide_load reads CACHE\xgap\corporate_actions_wide.csv + its manifest against the pinned WIDE_CA_SHA - the forward calendar needs its own dated pin first.
# Every rule, threshold and window below is the task's specification; where it is silent the choice is marked CHOICE [P1] .. [P18] (the numbered list is repeated in the hand-over report).
import contextlib, datetime as dt, hashlib, io, json, os, re, shutil, socket, sys, tempfile, time, zlib
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", os.path.dirname(os.path.dirname(HERE)))
for _p in (REPO, os.path.join(REPO, "tools"), HERE):          # r5_siporb's own path set-up: the same engine (augur_engine) and the same shared loader (import_alpaca_stocks) wherever this file is run from
    if _p not in sys.path:
        sys.path.insert(0, _p)
import numpy as np, pandas as pd
import r5_siporb as S                  # ASSETS_URL, EXCH, why_not, _get (the shared account pace, 429 / 5xx retries, 401 / 403 stop), the cache's schema and the harness's Data / read_long (the selftest's compatibility check) - imported, never copied
import r16_xgap as X16                 # ca_fetch, CaPull, ca_rows, ca_write_csv, ca_year, ca_new_names, CA_TYPES, CA_COLS, SPLIT_TYPES - the calendar's one fetch and its flat CSV - imported, never copied
import import_alpaca_stocks as IAS     # fetch_bars: the house single-symbol bars call (pagination, 429 retry, the provenance receipt)
from augur_engine import alpaca_keys, alpaca_rate, pull_provenance

ROOT_DEFAULT = r"C:\EdgeLog\alpaca_cache\resmom_fwd"
BASE_LIST_PATH = r"C:\EdgeLog\alpaca_cache\xgap\wide_symbols_siporb_floor_2016_2025.txt"        # MANAGER's wide pull's names file: every cached stock above SIPORB's floor, 5,367 symbols
BASE_LIST_SHA = "ab646462ffc0ee256f0272b7e5203efbe631d10f83b84d3fbda632430814852c"             # its sha256 as registered (PREREG_RESMOM_R1.txt ADDENDUM 3); any other file refuses
WINDOW_DAYS, MIN_SESSIONS = 430, 290       # through - 430 calendar days .. through; the data must hold >= 290 sessions (252 + the 25-session hygiene lead + margin)
ERR_MAX_PCT = 2                            # more than 2% of the requested symbols errored (after one retry) -> exit 2, nothing published
EVENING_HOUR = 20                          # CHOICE [P1] (the same-evening rule, replacing MIN_AGE_DAYS): --through is accepted when it is before today's New York date, OR when it IS today and the New York clock reads this hour or later (20:00 = the end of the after-hours session: the day's bars are complete)
ACTIVE_MIN_PCT = 25                        # CHOICE [P17]: fewer than this percent of the base list in the assets endpoint's active set = a wrong or cut-short asset list (about 60% is expected) -> exit 2, nothing published; 0 switches the check off
INACTIVE_GUESS = 0.40                      # plan's placeholder for the share of the base list that is inactive (the coordinator's estimate, replaced by the first real pull's count)
FIRST_N = 20                               # base names dropped as inactive: the manifest and the console name this many (sorted); a count says how many there were
SIPORB_RULES = True                        # CHOICE [P3]: new listings also pass r5_siporb.why_not's common-stock rules (False = the literal 'active, tradable, on the five exchanges')
TIMEFRAME, FEED, ADJUSTMENTS = "1Day", "sip", ("raw", "split")
RETRY_WAIT = 5.0                           # CHOICE [P6]: seconds before the one retry of a failed symbol call (the selftest sets 0)
THROUGH_COVER = 0.5                        # CHOICE [P11]: --through must carry bars for at least this share of a typical session's symbols (a holiday or a half-delivered day carries none / few)
SPLIT_REL, SPLIT_TOL = 0.01, 3             # [spec 5] a factor change above 1% between consecutive sessions is a price-implied split; the calendar's is matched within +-3 sessions
PAGE_LIMIT = 10000                         # fetch_bars' page size: a symbol's ~300 daily bars are ONE page, so bars requests = 2 x symbols x 1
CA_BATCH = X16.CA_BATCH                    # 50 symbols a calendar request
NEW_ALLOWANCE = 0.25                       # CHOICE [P16]: plan's placeholder for the new listings it cannot know offline (a guess, replaced by the first real pull's count)
PROGRESS_EVERY = 250                       # a counts-only progress line every this many symbols
MAX_RUN_MIN = 360                          # MANAGER #149 (d): the whole pull gives up after this many minutes (nothing published)
_DEADLINE = None                           # set by build(): time.time() past which the pull refuses
ERR_TEXT, MAX_LIST = 160, 5000             # characters of an error message kept in the manifest; entries of a list kept in the manifest (a count always says how many there were)
RENAME_TRIES, RENAME_WAIT = 6, 1.0         # CHOICE [P14]: the final directory rename is retried on PermissionError (an indexer or a scanner holding a handle for a moment)
F_RAW, F_SPLIT, F_CA, F_CA_RAW, F_SYMS, F_MAN = "daily_raw.parquet", "daily_split.parquet", "corporate_actions.csv", "corporate_actions_raw.jsonl", "symbols.txt", "manifest.json"
OUTPUT_FILES = (F_RAW, F_SPLIT, F_CA, F_CA_RAW, F_SYMS)       # every file but the manifest, which holds their sha256
EXCH = S.EXCH                              # NYSE, NASDAQ, AMEX, ARCA, BATS
CROSS_RULE = ("factor = raw close / split-adjusted close on the sessions both frames hold; a relative change above 1% from the same symbol's previous session is a price-implied split on that date; a calendar forward / reverse / unit split "
              "(ex-date; a unit split's effective date) agrees with it within +-3 sessions of the data's own session list, one to one, nearest first; unmatched = calendar-only / price-only; nothing is fixed or dropped")
NYSE_CLOSED = {   # CHOICE [P2]: NYSE full-day closures 2025-2027 (the house's own half-day list in import_alpaca_stocks runs to 2027 as well) - an EARLY-OUT for --through only; the data check after the pull is the ground truth
    "2025-01-01": "New Year's Day", "2025-01-09": "the National Day of Mourning", "2025-01-20": "Martin Luther King Jr. Day", "2025-02-17": "Washington's Birthday", "2025-04-18": "Good Friday", "2025-05-26": "Memorial Day",
    "2025-06-19": "Juneteenth", "2025-07-04": "Independence Day", "2025-09-01": "Labor Day", "2025-11-27": "Thanksgiving Day", "2025-12-25": "Christmas Day",
    "2026-01-01": "New Year's Day", "2026-01-19": "Martin Luther King Jr. Day", "2026-02-16": "Washington's Birthday", "2026-04-03": "Good Friday", "2026-05-25": "Memorial Day", "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)", "2026-09-07": "Labor Day", "2026-11-26": "Thanksgiving Day", "2026-12-25": "Christmas Day",
    "2027-01-01": "New Year's Day", "2027-01-18": "Martin Luther King Jr. Day", "2027-02-15": "Washington's Birthday", "2027-03-26": "Good Friday", "2027-05-31": "Memorial Day", "2027-06-18": "Juneteenth (observed)",
    "2027-07-05": "Independence Day (observed)", "2027-09-06": "Labor Day", "2027-11-25": "Thanksgiving Day", "2027-12-24": "Christmas Day (observed)"}
_SECRETS = ()           # (key, secret) of this process once the lookup found them: scrub() removes them from anything about to be printed or stored - the defence if a server message or an exception ever echoed one


class Refused(Exception):
    """a refusal that ends the run with exit code 2; its message IS the last line printed (house wording: 'refused: ... (nothing pulled)' before the first request, '... (nothing published)' after)"""


def refuse(msg):
    raise Refused(msg)


def scrub(text):
    """a key never reaches a print, a log or a file: the key / secret values this process holds are replaced in any text (a server message, an exception) before it is shown or stored (r16_xgap.scrub's rule: values shorter than 6 characters are not touched)"""
    return IAS.redact(text, _SECRETS)                        # MANAGER #149 (c): plain, stripped, JSON-escaped, URL-encoded and repr forms


def one_line(text):
    return " ".join(str(text).split())


def say(msg=""):
    print(scrub(msg), flush=True)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha_lf(path):
    """the canonical (LF) sha256 of a text file - what r11_risk.sha_lf gives, so the same text hashes the same on a CRLF and an LF checkout"""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def js(o):
    """json default for the manifest: numpy scalars and timestamps"""
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(o).date())
    return str(o)


# module-level names, so a test can stub them (the selftest swaps every one of them for a fake)
fetch_bars = IAS.fetch_bars
ca_fetch = X16.ca_fetch


def load_keys():
    """the ONE key lookup (augur_engine/alpaca_keys.py: the process environment, then the Windows user environment in the registry, then the JSON files). The value goes to the callers that need it and nowhere else - never printed, logged or written"""
    key, secret = alpaca_keys.load_keys()
    return (key.strip() if isinstance(key, str) else key), (secret.strip() if isinstance(secret, str) else secret)   # MANAGER #149 (b)


def fetch_assets(key, secret):
    """ONE small function (the selftest stubs it): Alpaca's ACTIVE us_equity assets as the list of records the endpoint returns - the ACTIVE SET the base list is filtered by (inactive / delisted base names are not requested) and the source of the new listings.
    CHOICE [P4]: reuses r5_siporb's transport (_get: the shared account pace, retries) and its endpoint; r5_siporb.assets() itself writes the SIPORB cache's assets.csv and so cannot be called here. Inactive assets are not asked for"""
    return S._get(S.ASSETS_URL, {"status": "active", "asset_class": "us_equity"}, key, secret)


def now_et():
    """the New York wall clock right now as a naive datetime - the ONE clock the --through rule reads (the selftest swaps it for a fake)"""
    return pd.Timestamp.now(tz="US/Eastern").tz_localize(None).to_pydatetime()


def have_pyarrow():
    """the photograph is parquet (the SIPORB cache's format): without pyarrow the run refuses before the first request, not after an hour of them"""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return False
    return pq is not None


# ------------------------------------------------------------------ the date, the window
def parse_day(text, what="--through"):
    s = str(text or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        refuse(f"refused: {what} {s!r} is not a date written YYYY-MM-DD (nothing pulled)")
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        refuse(f"refused: {what} {s!r} is not a real calendar date (nothing pulled)")


def weekdays_between(a, b):
    """the Monday-to-Friday dates of [a, b] inclusive"""
    return [a + dt.timedelta(days=i) for i in range((b - a).days + 1) if (a + dt.timedelta(days=i)).weekday() < 5]


def window_of(through):
    """the window of one photograph: through - 430 calendar days .. through (>= 290 sessions: 252 for the regression + 25 hygiene lead + margin), with the request strings fetch_bars takes (the house's own style: 00:00:00Z .. 23:59:59Z) and the
    session count the calendar days imply (weekdays less the NYSE closures on file: an estimate - a closure the table does not know makes it one too high)"""
    start = through - dt.timedelta(days=WINDOW_DAYS)
    wd = weekdays_between(start, through)
    closed = [d for d in wd if d.isoformat() in NYSE_CLOSED]
    return {"through": through.isoformat(), "start": start.isoformat(), "end": through.isoformat(), "calendar_days": WINDOW_DAYS, "bars_start": start.isoformat() + "T00:00:00Z", "bars_end": through.isoformat() + "T23:59:59Z",
            "weekdays": len(wd), "nyse_closed_days_on_file": len(closed), "sessions_expected": len(wd) - len(closed), "min_sessions": MIN_SESSIONS}


def pull_gate(d, now):
    """None when a pull of --through d is allowed at the New York wall-clock time `now` (a naive datetime); else why not, as the phrase a refusal carries. CHOICE [P1], the same-evening rule (ELWA schedules the pull inside the nightly data refresh on the
    evening of the month's last session): allowed when d is before today's New York date, OR d IS today and the New York clock reads EVENING_HOUR:00 or later (20:00 = the end of the after-hours session, so the day's bars are complete). A date after today,
    or today before that hour, is not allowed"""
    today = now.date()
    if d > today:
        return f"is in the future (today is {today} in New York): its session has not happened"
    if d == today and now.hour < EVENING_HOUR:
        return f"is today in New York and the clock there reads {now:%H:%M}: a same-day pull is accepted from {EVENING_HOUR:02d}:00 New York time, when the session's data is complete"
    return None


def validate_through(text, future_ok=False):
    """--through must be a completed weekday session date: pull_gate's rule [P1] (before today's New York date, or today from 20:00 New York time); a weekend, and a day on the NYSE closure table [P2], is not a session. `plan` lifts only the 'completed'
    rule (a future month-end can be planned)"""
    d = parse_day(text)
    if d.weekday() >= 5:
        refuse(f"refused: --through {d} is a {d:%A}, not a weekday session (nothing pulled)")
    if d.isoformat() in NYSE_CLOSED:
        refuse(f"refused: --through {d} is an NYSE holiday ({NYSE_CLOSED[d.isoformat()]}), not a session (nothing pulled)")
    if not future_ok:
        why = pull_gate(d, now_et())                 # ONE clock reading: the date and the hour come from the same instant
        if why:
            refuse(f"refused: --through {d} {why} (nothing pulled)")
    return d


def folder_name(through, n):
    return through if n == 1 else f"{through}_r{n}"


def next_target(root, through):
    """where a publish would land now: ROOT\\<through>, or _r2, _r3 ... when that name is taken -> (path, revision)"""
    n = 1
    while os.path.exists(os.path.join(root, folder_name(through, n))):
        n += 1
    return os.path.join(root, folder_name(through, n)), n


# ------------------------------------------------------------------ the base list, the hold list, the active filter and the new listings
def parse_symbols(raw, what, name):
    """the bytes of a one-symbol-a-line file (UTF-8, a BOM tolerated, blank lines and '#' comment lines skipped, repeats dropped, upper-cased) -> its symbols in file order; a line that is not one symbol, or a file with no symbol, refuses.
    `what` names the file in the refusal: 'the base list' / 'the hold list'"""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        refuse(f"refused: {what} {name} is not UTF-8 text (nothing pulled)")
    syms, seen = [], set()
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if not X16.NAME_RE.fullmatch(s):
            refuse(f"refused: {what} {name} line {n}: {s[:24]!r} is not one symbol - one a line, letters, digits, '.' and '-', at most 12 characters (nothing pulled)")
        u = s.upper()
        if u not in seen:
            seen.add(u)
            syms.append(u)
    if not syms:
        refuse(f"refused: {what} {name} holds no symbol (nothing pulled)")
    return syms


def base_list_state(path=None, registered=None):
    """what is on disk against what is registered, WITHOUT refusing (plan prints it either way): {path, exists, sha256, registered_sha256, sha_ok, symbols}. The sha is of the file's bytes (what `sha256sum` gives); the symbols are parsed only when it matches"""
    path, registered = path or BASE_LIST_PATH, registered or BASE_LIST_SHA
    st = {"path": path, "exists": os.path.isfile(path), "sha256": None, "registered_sha256": registered, "sha_ok": False, "symbols": None}
    if not st["exists"]:
        return st
    with open(path, "rb") as f:
        raw = f.read()
    st["sha256"] = hashlib.sha256(raw).hexdigest()
    st["sha_ok"] = st["sha256"] == registered
    if st["sha_ok"]:
        st["symbols"] = parse_symbols(raw, "the base list", os.path.basename(path))
    return st


def read_base_list():
    """the base symbols, after the sha check: a missing file or ANY other sha256 refuses before a key is touched (the registered list is the floor of what the photograph covers - another list is another universe)"""
    st = base_list_state()
    if not st["exists"]:
        refuse(f"refused: the base list {st['path']} is not on file (nothing pulled)")
    if not st["sha_ok"]:
        refuse(f"refused: the base list {os.path.basename(st['path'])} has sha256 {st['sha256']}, not the registered {st['registered_sha256']} (nothing pulled)")
    syms = st["symbols"]
    return syms, {"path": st["path"], "sha256": st["sha256"], "registered_sha256": st["registered_sha256"], "sha_ok": True, "count": len(syms), "first": syms[0], "last": syms[-1]}


def read_hold_list(path):
    """the optional --hold FILE -> (symbols, info): one symbol a line, the base list's file rules (parse_symbols). These are the names the line holds from the previous rank: `pull` requests them ALWAYS, even when the assets endpoint no longer lists them as
    active (a name delisted mid-hold still needs its bars up to delisting). A file that is missing, cannot be read, is not UTF-8 text, has a line that is not one symbol, or holds no symbol refuses before a key is touched. The file's sha256 is of its bytes.
    CHOICE [P18]: an EMPTY hold file refuses (the line always holds names from its second month on, so an empty file is an upstream fault: leave --hold out when there is nothing to hold)"""
    p = os.path.abspath(path)
    if not os.path.isfile(p):
        refuse(f"refused: the hold list {p} is not on file (nothing pulled)")
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except OSError as e:
        refuse(f"refused: the hold list {p} cannot be read ({type(e).__name__}) (nothing pulled)")
    syms = parse_symbols(raw, "the hold list", os.path.basename(p))
    return syms, {"path": p, "sha256": hashlib.sha256(raw).hexdigest(), "count": len(syms), "first": syms[0], "last": syms[-1]}


def active_set(assets):
    """the symbols the assets endpoint lists as ACTIVE (stripped, upper-cased): the records that are dicts with a symbol and the status 'active'. CHOICE [P17]: 'active' is the endpoint's own status field and nothing else - tradable / exchange / class decide
    only whether a NEW listing is admitted [P3], never whether a base name is kept"""
    out = set()
    for a in assets:
        if isinstance(a, dict) and str(a.get("status") or "").lower() == "active":
            s = str(a.get("symbol") or "").strip().upper()
            if s:
                out.add(s)
    return out


def choose_symbols(base, assets, new, hold):
    """THE SYMBOL RULE: requested = (base list AND the assets endpoint's active set) + the new active listings + every hold name (hold names are requested active or not, so a name delisted mid-hold keeps its bars up to delisting).
    -> {requested: the sorted names, active_listed, base_active (kept), base_inactive (all inactive base names), dropped (sorted: inactive base names that are not held = the base list minus the requested set), hold, hold_inactive (sorted: every hold name
    that is not active, in the base list or not), hold_added (hold names the other two parts do not already request: requested = base_active + new + hold_added)}. CHOICE [P18]: a hold name that errors counts toward the 2% like any requested symbol
    (it is one); the 'first 20' dropped names the manifest and the console show are the first 20 in alphabetical order"""
    act, bset, hset, nset = active_set(assets), set(base), set(hold), set(new)
    keep = bset & act
    inactive = bset - act
    return {"requested": sorted(keep | nset | hset), "active_listed": len(act), "base_active": len(keep), "base_inactive": len(inactive), "dropped": sorted(inactive - hset),
            "hold": len(hset), "hold_inactive": sorted(hset - act), "hold_added": len(hset - keep - nset)}


def new_listings(assets, base):
    """the symbols to ADD to the base list: active, tradable US-equity assets on NYSE / NASDAQ / AMEX / ARCA / BATS that are not in it -> (sorted names, counts by reason of everything left out). CHOICE [P3]: also through SIPORB's own common-stock rules
    (r5_siporb.why_not: the exchange set, dot / slash symbols, CUSIP-style placeholders, warrant / unit / right suffixes, ETF / fund / note names) - the base list was built through them, so without them the forward universe would admit ETFs and ETNs
    (SPY-like names rank among the 500 largest by dollar volume) and the dozen real stocks those rules drop by design (IVZ, BRK.B ...) that the registered backtest never had. SIPORB_RULES = False gives the literal reading (the five exchanges only)"""
    inb, why, new = set(base), Counter(), set()
    for a in assets:
        if not isinstance(a, dict):
            why["not_a_record"] += 1
            continue
        sym = str(a.get("symbol") or "").strip().upper()
        if not sym:
            why["no_symbol"] += 1
        elif sym in inb:
            why["already_in_base_list"] += 1
        elif str(a.get("status") or "").lower() != "active":
            why["not_active"] += 1
        elif not a.get("tradable"):
            why["not_tradable"] += 1
        elif a.get("class") not in (None, "", "us_equity"):
            why["not_us_equity"] += 1
        else:
            exch = str(a.get("exchange") or "")
            reason = S.why_not(sym, str(a.get("name") or ""), exch) if SIPORB_RULES else (None if exch.upper() in EXCH else "exchange")
            if reason:
                why[reason] += 1
            else:
                new.add(sym)
    return sorted(new), {"assets_rows": int(len(assets)), "excluded_by_reason": dict(sorted(why.items())), "new": len(new)}


# ------------------------------------------------------------------ the bars
def empty_daily():
    return pd.DataFrame({"symbol": pd.Series([], dtype=object), "date": pd.Series([], dtype="datetime64[ns]"), "o": pd.Series([], dtype=float), "h": pd.Series([], dtype=float),
                         "l": pd.Series([], dtype=float), "c": pd.Series([], dtype=float), "v": pd.Series([], dtype="int64")})


def to_daily(sym, df):
    """fetch_bars' frame (time = POSIX seconds, open, high, low, close, volume) -> the SIPORB cache's columns: symbol, date, o, h, l, c, v. CHOICE [P10]: date = the UTC date of the bar's stamp, naive. Daily bars are stamped at ET midnight (04:00Z
    in summer, 05:00Z in winter), so that IS the Eastern session date - r5_siporb.frame_daily's `t[:10]` on the ISO stamp, to the day"""
    if df is None or len(df) == 0:
        return empty_daily()
    date = pd.to_datetime(np.asarray(df["time"], dtype="int64"), unit="s").normalize().astype("datetime64[ns]")
    return pd.DataFrame({"symbol": sym, "date": np.asarray(date), "o": np.asarray(df["open"], dtype=float), "h": np.asarray(df["high"], dtype=float), "l": np.asarray(df["low"], dtype=float),
                         "c": np.asarray(df["close"], dtype=float), "v": np.asarray(df["volume"], dtype="int64")})


def pull_one(sym, adj, win, key, secret, calls):
    """one symbol, one adjustment, through the house call (so its provenance receipt is filed). Any exception: ONE retry after RETRY_WAIT, then it propagates and the caller records the symbol as an error. CHOICE [P6]: fetch_bars answers a 401 / 403 with
    SystemExit (not an exception) - that is the key being refused, which no retry fixes and which would otherwise repeat for every symbol, so it ends the run at once"""
    for attempt in (1, 2):
        calls[adj] += 1
        try:
            return to_daily(sym, fetch_bars(sym, TIMEFRAME, win["bars_start"], win["bars_end"], key, secret, feed=FEED, adjustment=adj))
        except SystemExit as e:
            m = re.search(r"AUTH FAILED \((\d+)\)", str(e))
            refuse(f"refused: Alpaca refused the key (HTTP {m.group(1)}) on {sym} {adj} - check the key and the data plan (nothing published)" if m
                   else f"refused: the bars call stopped the run on {sym} {adj}: {one_line(scrub(e))[:ERR_TEXT]} (nothing published)")
        except Exception:
            if attempt == 2:
                raise
            calls["retries"] += 1
            time.sleep(RETRY_WAIT)


def check_deadline(where):
    """MANAGER #149 (d): the whole pull stops once it has run MAX_RUN_MIN minutes (nothing published)"""
    if _DEADLINE is not None and time.time() > _DEADLINE:
        refuse(f"refused: the pull ran past its {MAX_RUN_MIN}-minute cap {where} (nothing published)")


def err_over(errors, requested):
    """more than ERR_MAX_PCT percent of the requested symbols (integer arithmetic: exactly 2% passes)"""
    return errors * 100 > ERR_MAX_PCT * requested


def pull_bars(symbols, win, key, secret):
    """every symbol, both adjustments, in sorted order -> a dict of the two frames and the counts. CHOICE [P5]: one fetch_bars call per symbol per adjustment (one page each), the symbols in sorted order, raw first; when the raw call errors after its retry the
    split call is not made (the symbol is an error already). 'with bars' = both adjustments returned rows, 'empty' = neither (counted, NOT an error), CHOICE [P9] 'one_sided' = exactly one (kept as returned, named in the manifest - the harness cannot read
    a split off such a name). CHOICE [P7]: a symbol that errored after its retry contributes NO rows to either file (a raw-only history would read a split as a crash; a split-only one has no factor) and is named in the manifest. CHOICE [P8]: errors are counted
    per symbol against the symbols requested, and the pull stops the moment the count makes 'more than 2%' certain - an hour of requests is not spent on a photograph that cannot be published"""
    n, t0 = len(symbols), time.time()
    raw_parts, spl_parts, calls = [], [], Counter()
    with_bars, empty, one_sided, errors = [], [], [], []
    for i, sym in enumerate(symbols, 1):
        check_deadline(f"at symbol {i:,} of {n:,}")
        got, err = {}, None
        for adj in ADJUSTMENTS:
            try:
                got[adj] = pull_one(sym, adj, win, key, secret, calls)
            except Refused:
                raise
            except Exception as e:
                err = {"symbol": sym, "adjustment": adj, "error": one_line(scrub(f"{type(e).__name__}: {e}"))[:ERR_TEXT]}
                break
        if err:
            errors.append(err)
            if err_over(len(errors), n):
                e0 = errors[0]
                refuse(f"refused: {len(errors)} of {n:,} symbols errored after a retry ({100.0 * len(errors) / n:.1f}%, more than the {ERR_MAX_PCT}% limit); the pull stopped at symbol {i:,} - first error: {e0['symbol']} {e0['adjustment']} {e0['error']} (nothing published)")
        else:
            r, s = got["raw"], got["split"]
            if len(r) and len(s):
                with_bars.append(sym)
            elif not len(r) and not len(s):
                empty.append(sym)
            else:
                one_sided.append(sym)
            if len(r):
                raw_parts.append(r)
            if len(s):
                spl_parts.append(s)
        if i % PROGRESS_EVERY == 0 or i == n:
            say(f"  {i:,} / {n:,} symbols: {len(with_bars):,} with bars, {len(empty):,} empty, {len(one_sided):,} one-sided, {len(errors):,} errors, {calls['raw'] + calls['split']:,} calls, {(time.time() - t0) / 60:.1f} min")
    raw = pd.concat(raw_parts, ignore_index=True) if raw_parts else empty_daily()
    spl = pd.concat(spl_parts, ignore_index=True) if spl_parts else empty_daily()
    dups = {}
    for nm, df in (("raw", raw), ("split", spl)):                       # one row per symbol-session: a second stamp on one date (none is expected) keeps the later bar and is counted
        dups[nm] = int(df.duplicated(["symbol", "date"]).sum())
    raw = raw.drop_duplicates(["symbol", "date"], keep="last") if dups["raw"] else raw
    spl = spl.drop_duplicates(["symbol", "date"], keep="last") if dups["split"] else spl
    return {"raw": raw, "split": spl, "with_bars": with_bars, "empty": empty, "one_sided": one_sided, "errors": errors, "calls": dict(calls), "duplicates_dropped": dups, "pulled_between_epoch": [round(t0, 3), round(time.time(), 3)]}


def sessions_of(raw):
    """the data's sessions: the dates most names have a bar on - r5_siporb.Data's own rule (a date holds a session when it carries at least max(3, 25% of the median date's bar count))"""
    cnt = raw.groupby("date").size()
    return pd.DatetimeIndex(cnt.index[cnt >= max(3, 0.25 * cnt.median())])


def check_sessions(raw, win):
    """the data must hold the window: >= 290 sessions, and --through must BE one - CHOICE [P11]: bars for at least half of a typical session's names (a holiday carries none; a day Alpaca has half-delivered carries few). Refusals say nothing published ->
    {sessions, first, last, bars_on_through, typical_bars_a_session}"""
    if not len(raw):
        refuse("refused: Alpaca returned no bar for any symbol (nothing published)")
    days = sessions_of(raw)
    if len(days) < MIN_SESSIONS:
        refuse(f"refused: the data holds {len(days)} sessions, fewer than the {MIN_SESSIONS} the window needs (252 + the hygiene lead + margin) (nothing published)")
    cnt = raw.groupby("date").size()
    on, typ = int(cnt.get(pd.Timestamp(win["through"]), 0)), float(cnt.median())
    if on < THROUGH_COVER * typ:
        refuse(f"refused: --through {win['through']} carries bars for only {on:,} symbols against a typical {typ:,.0f} a session - it is not a complete session of the data (a holiday, or a day Alpaca has not finished delivering) (nothing published)")
    return {"sessions": int(len(days)), "first": f"{days[0]:%Y-%m-%d}", "last": f"{days[-1]:%Y-%m-%d}", "bars_on_through": on, "typical_bars_a_session": typ}


# ------------------------------------------------------------------ the calendar and the split cross-check
def pull_calendar(symbols, key, secret, win, tmp, tag_every=20):
    """the corporate-actions calendar over the SAME window for the SAME symbols through r16_xgap's own fetch (all CA_TYPES), flattened exactly as its capull does: the raw pages one JSON line each, the flat CSV (CA_COLS) of the de-duplicated, sorted rows.
    CHOICE [P12]: ONE round - r16's wide capull adds a round 2 for the names its name_change records reveal; here the symbols are exactly the ones whose bars are pulled, and those names are only LISTED (name_change_names_not_asked)"""
    part, raw_path = os.path.join(tmp, F_CA_RAW + ".part"), os.path.join(tmp, F_CA_RAW)
    sink = X16.CaPull(part, maxbad=max(X16.CA_MAXBAD, -(-len(symbols) // 50)), every=tag_every)       # the wide capull's own stop on rejected symbols (2% of the names when that is more than CA_MAXBAD)
    try:
        ca_fetch(symbols, key, secret, sink, 1, start=win["start"], end=win["end"])
    finally:
        sink.close()
    os.replace(part, raw_path)
    rows, dup = X16.ca_rows(sink.recs)
    X16.ca_write_csv(rows, os.path.join(tmp, F_CA))
    ys, bytype = defaultdict(Counter), Counter()
    for r in rows:
        ys[r["type"]][X16.ca_year(r)] += 1
        bytype[r["type"]] += 1
    info = {"endpoint": X16.CA_URL, "types": list(X16.CA_TYPES), "limit": X16.CA_LIMIT, "batch": X16.CA_BATCH, "requests": sink.requests, "pages": sink.pages, "records": len(sink.recs), "duplicates_dropped": dup, "rows": len(rows),
            "rows_by_type": dict(sorted(bytype.items())), "rows_by_type_year": {t: dict(sorted(c.items())) for t, c in sorted(ys.items())}, "unknown_types": dict(sink.unknown_types), "unknown_top_keys": dict(sink.unknown_top),
            "fields_not_flattened": dict(sink.unflat), "rejected_symbols": list(sink.bad), "max_rejected_symbols": sink.maxbad, "name_change_names_not_asked": X16.ca_new_names(sink.recs, symbols)}
    return rows, info


def split_crosscheck(raw, spl, cal_rows, days):
    """[spec 5] the price side's split-adjustment changes against the calendar's splits - COUNTS AND LISTS ONLY, nothing is fixed or dropped (the harness's hygiene decides later). CHOICE [P13]: factor_t = raw close / split-adjusted close on the sessions both
    frames hold; a relative change above 1% from the SAME symbol's previous such session is a price-implied split on that date. The calendar's splits (forward / reverse / unit; the ex-date, a unit split's effective date; the symbol, else the unit
    split's new / old symbol) are placed on the data's own session list (a weekend ex-date lands on the next session) and matched one to one, nearest first, within +-3 sessions. Counted APART and never listed as a disagreement, because the price side cannot
    see them: a split on a name with no bars or one adjustment only, no ex-date, outside the window, on or before the name's first session, and exact repeats of one (symbol, session)"""
    j = raw[["symbol", "date", "c"]].merge(spl[["symbol", "date", "c"]], on=["symbol", "date"], suffixes=("_r", "_s"))
    with np.errstate(divide="ignore", invalid="ignore"):
        fac = j["c_r"].to_numpy(float) / j["c_s"].to_numpy(float)
    ok = np.isfinite(fac) & (fac > 0)
    j = j.loc[ok, ["symbol", "date"]].assign(fac=fac[ok]).sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    codes = pd.factorize(j["symbol"])[0]
    f = j["fac"].to_numpy(float)
    hit = (np.flatnonzero((codes[1:] == codes[:-1]) & (np.abs(f[1:] / f[:-1] - 1.0) > SPLIT_REL)) + 1) if len(j) > 1 else np.zeros(0, int)
    first = j.groupby("symbol")["date"].min() if len(j) else pd.Series(dtype="datetime64[ns]")
    first_idx = {s: int(days.searchsorted(d)) for s, d in first.items()}
    by_p = defaultdict(list)
    for k in hit:
        d = j["date"].iloc[k]
        by_p[j["symbol"].iloc[k]].append((int(days.searchsorted(d)), d, float(f[k] / f[k - 1])))
    has_any = set(raw["symbol"].unique()) | set(spl["symbol"].unique())
    nc, ev = Counter(), {}
    for r in cal_rows:
        if r.get("type") not in X16.SPLIT_TYPES:
            continue
        nc["calendar_split_rows"] += 1
        cands = [str(r[k]).strip() for k in ("symbol", "new_symbol", "old_symbol") if r.get(k) not in (None, "")]
        exd = r.get("ex_date")
        ex = pd.to_datetime(exd, errors="coerce") if exd not in (None, "") else pd.NaT
        sym = next((c for c in cands if c in first_idx), None)
        if pd.isna(ex):
            nc["undated"] += 1
        elif sym is None:
            nc["one_sided" if any(c in has_any for c in cands) else "no_bars"] += 1
        elif ex < days[0] or ex > days[-1]:
            nc["outside_window"] += 1
        elif int(days.searchsorted(ex)) <= first_idx[sym]:
            nc["before_first_bar"] += 1
        elif (sym, int(days.searchsorted(ex))) in ev:
            nc["duplicates_merged"] += 1
        else:
            ev[(sym, int(days.searchsorted(ex)))] = {"kind": "calendar_only", "symbol": sym, "date": f"{ex:%Y-%m-%d}", "type": r["type"], "new_rate": r.get("new_rate"), "old_rate": r.get("old_rate")}
    by_c = defaultdict(list)
    for (sym, idx), rec in ev.items():
        by_c[sym].append((idx, rec))
    agree, c_only, p_only = 0, [], []
    for sym in sorted(set(by_c) | set(by_p)):
        cs, ps = sorted(by_c.get(sym, []), key=lambda t: t[0]), sorted(by_p.get(sym, []), key=lambda t: t[0])
        used = [False] * len(ps)
        for idx, rec in cs:
            best = None
            for k, (pi, _d, _ratio) in enumerate(ps):
                if not used[k] and abs(pi - idx) <= SPLIT_TOL and (best is None or abs(pi - idx) < abs(ps[best][0] - idx)):
                    best = k
            if best is None:
                c_only.append(rec)
            else:
                used[best] = True
                agree += 1
        p_only += [{"kind": "price_only", "symbol": sym, "date": f"{ps[k][1]:%Y-%m-%d}", "factor_ratio": round(ps[k][2], 6)} for k in range(len(ps)) if not used[k]]
    lst = sorted(c_only + p_only, key=lambda e: (e["kind"], e["symbol"], e["date"]))
    return {"rule": CROSS_RULE, "relative_change": SPLIT_REL, "tolerance_sessions": SPLIT_TOL, "agree": agree, "calendar_only": len(c_only), "price_only": len(p_only), "price_implied_events": int(sum(len(v) for v in by_p.values())),
            "calendar_events_compared": len(ev), "not_comparable": dict(sorted(nc.items())), "disagreements": lst[:MAX_LIST], "disagreements_truncated": len(lst) > MAX_LIST}


# ------------------------------------------------------------------ the files
def parquet_schema():
    """exactly r5_siporb.consolidate's schema - what the harness's read_long reads"""
    import pyarrow as pa
    return pa.schema([("symbol", pa.string()), ("date", pa.timestamp("ns")), ("o", pa.float64()), ("h", pa.float64()), ("l", pa.float64()), ("c", pa.float64()), ("v", pa.int64())])


def write_parquet(df, path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    sch = parquet_schema()
    pq.write_table(pa.Table.from_pandas(df[list(sch.names)], schema=sch, preserve_index=False), path, compression="zstd")


def read_back(path, rows, through):
    """the file read the way the harness reads it (r5_siporb.read_long: a filtered read of `date`, the symbol as a dictionary) - a naive date column, the right schema and the row count written, or the pull does not publish"""
    import pyarrow.parquet as pq
    cut = (pd.Timestamp(through) + pd.Timedelta(days=1)).to_pydatetime()
    t = pq.read_table(path, filters=[("date", "<", cut)], read_dictionary=["symbol"])
    if t.num_rows != rows or t.schema.names != list(parquet_schema().names) or str(t.schema.field("date").type) != "timestamp[ns]":
        refuse(f"refused: {os.path.basename(path)} does not read back as written - {t.num_rows:,} rows read against {rows:,} written (nothing published)")


def rename_with_retry(src, dst):
    for k in range(RENAME_TRIES):
        try:
            os.rename(src, dst)
            return
        except PermissionError:
            if k == RENAME_TRIES - 1:
                raise
            time.sleep(RENAME_WAIT)


def publish(tmp, root, through):
    """the ONE atomic step: the finished folder is renamed to ROOT\\<through>, or ROOT\\<through>_r2 / _r3 ... when that name is taken - a re-pull is a new photograph, never an overwrite -> (path, revision). CHOICE [P14]: a directory rename (one
    step on one volume); the rows of both parquet files are sorted by (symbol, date) and written zstd in r5_siporb's own schema, symbols.txt is the sorted requested symbols, LF; leftover _tmp_ folders of killed runs are counted and left alone"""
    n = 1
    while True:
        target = os.path.join(root, folder_name(through, n))
        if not os.path.exists(target):
            try:
                rename_with_retry(tmp, target)
                return target, n
            except OSError:
                if not os.path.exists(target):          # not 'the name was taken meanwhile': a real failure
                    raise
        n += 1


# ------------------------------------------------------------------ the pull
def parse_args(args, cmd):
    """`--through D` (required), `--out ROOT` and `--hold FILE` (optional), each given once (`--through=D` works too); anything else is refused -> (through, out, hold)"""
    a, val, i = list(args), {}, 0
    usage = f"usage: r17_resmom_pull.py {cmd} --through YYYY-MM-DD [--out ROOT] [--hold FILE]"
    while i < len(a):
        x = a[i]
        k, eq, v = x.partition("=")
        if k not in ("--through", "--out", "--hold"):
            refuse(f"refused: unknown argument {x!r} ({usage}) (nothing pulled)")
        if not eq:
            i += 1
            v = a[i] if i < len(a) else ""
        if not v or v.startswith("--") or k in val:
            refuse(f"refused: {k} takes exactly one value, given once ({usage}) (nothing pulled)")
        val[k] = v
        i += 1
    if "--through" not in val:
        refuse(f"refused: --through is required ({usage}) (nothing pulled)")
    return val["--through"], val.get("--out"), val.get("--hold")


def names_text(names, limit):
    """a list of symbols for a console line: up to `limit` of them, then how many more the manifest holds"""
    return ", ".join(names[:limit]) + (f" ... ({len(names) - limit:,} more in the manifest)" if len(names) > limit else "")


def build(through, win, root, base, binfo, key, secret, argv, hold=(), hinfo=None):
    """everything between 'the checks passed' and 'published': assets -> the symbol rule -> bars -> data checks -> calendar -> cross-check -> files -> manifest -> the atomic rename. Any exception, a refusal included, leaves NO ROOT\\<through> and no half
    folder. `hold` / `hinfo` = the --hold list and its file facts (read_hold_list), empty / None without --hold"""
    t_start = time.time()
    global _DEADLINE
    _DEADLINE = t_start + MAX_RUN_MIN * 60.0
    say(f"  caps: a call gives up after {IAS.MAX_429} consecutive 429s; the whole pull after {MAX_RUN_MIN} minutes; no redirect is followed")
    os.makedirs(root, exist_ok=True)
    stale = sorted(d for d in os.listdir(root) if d.startswith("_tmp_"))
    tmp = os.path.join(root, f"_tmp_{win['through']}_{os.getpid()}")
    if stale:
        say(f"  note: {len(stale)} leftover _tmp_ folder(s) of earlier killed runs in {root} are ignored (delete them by hand)")
    if os.path.exists(tmp):
        shutil.rmtree(tmp, ignore_errors=True)                      # the same pid reused by a run that was killed: ours by name
    os.makedirs(tmp)
    try:
        say(f"pull: RESMOM forward photograph through {win['through']}, window {win['start']} .. {win['end']} ({win['calendar_days']} calendar days, about {win['sessions_expected']} sessions), output {root}")
        say(f"  base list: {binfo['count']:,} symbols, sha256 {binfo['sha256'][:12]}... = the registered one; key: found (never printed)")
        assets = fetch_assets(key, secret)
        if not isinstance(assets, list) or not assets:
            refuse("refused: the assets call returned no list of assets, so the active names and the new listings cannot be told (nothing published)")
        new, ainfo = new_listings(assets, base)
        pick = choose_symbols(base, assets, new, hold)                               # THE SYMBOL RULE: (base AND active) + new listings + every hold name
        symbols, dropped, hold_in = pick["requested"], pick["dropped"], pick["hold_inactive"]
        say(f"  assets: {ainfo['assets_rows']:,} rows read, {pick['active_listed']:,} symbols active; new listings added to the base list: {len(new):,} (left out: " + ", ".join(f"{k} {v:,}" for k, v in ainfo["excluded_by_reason"].items()) + ")")
        say(f"  active filter: {pick['base_active']:,} of {len(base):,} base names are active; {len(dropped):,} dropped as inactive, not requested" + (f" (first {FIRST_N}: {', '.join(dropped[:FIRST_N])})" if dropped else ""))
        if pick["base_active"] * 100 < ACTIVE_MIN_PCT * len(base):                    # a wrong or cut-short asset list would silently take the rest of the base list out of the photograph
            refuse(f"refused: only {pick['base_active']:,} of the {len(base):,} base names ({100.0 * pick['base_active'] / len(base):.1f}%) are in the assets endpoint's active set, below the {ACTIVE_MIN_PCT}% floor: the asset list looks wrong or "
                   f"cut short, and the photograph would lose the rest (nothing published)")
        if hinfo:
            say(f"  hold list: {hinfo['count']:,} names, pulled always; {len(hold_in):,} not active now" + (f": {names_text(hold_in, 40)}" if hold_in else "") + f"; {pick['hold_added']:,} of them are requested only because they are held")
        say(f"  requested: {len(symbols):,} symbols = {pick['base_active']:,} active base + {len(new):,} new listings + {pick['hold_added']:,} hold names not otherwise included")
        say(f"  bars: {len(symbols):,} symbols x raw + split ({TIMEFRAME}, feed {FEED}; the shared account pace, one request a call)")
        B = pull_bars(symbols, win, key, secret)
        nerr = len(B["errors"])
        if err_over(nerr, len(symbols)):                                              # the requested set only (pull_bars stops earlier when it is already certain; this is the same rule on the final count)
            refuse(f"refused: {nerr} of {len(symbols):,} symbols errored after a retry, more than the {ERR_MAX_PCT}% limit (nothing published)")
        raw = B["raw"].sort_values(["symbol", "date"], kind="stable", ignore_index=True)
        spl = B["split"].sort_values(["symbol", "date"], kind="stable", ignore_index=True)
        sess = check_sessions(raw, win)
        say(f"  bars done: {len(raw):,} raw rows, {len(spl):,} split rows; {sess['sessions']} sessions {sess['first']} .. {sess['last']}; {sess['bars_on_through']:,} symbols print on {win['through']}")
        say(f"  calendar: {len(symbols):,} symbols, {win['start']} .. {win['end']}, types {','.join(X16.CA_TYPES)}, {X16.CA_BATCH} symbols a request")
        cal_rows, cinfo = pull_calendar(symbols, key, secret, win, tmp)
        days = sessions_of(raw)
        cross = split_crosscheck(raw, spl, cal_rows, days)
        say(f"  calendar done: requests {cinfo['requests']}, {cinfo['records']:,} records -> {cinfo['rows']:,} rows; split cross-check: agree {cross['agree']}, calendar-only {cross['calendar_only']}, price-only {cross['price_only']}")
        write_parquet(raw, os.path.join(tmp, F_RAW))
        write_parquet(spl, os.path.join(tmp, F_SPLIT))
        with open(os.path.join(tmp, F_SYMS), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(symbols) + "\n")
        read_back(os.path.join(tmp, F_RAW), len(raw), win["through"])
        read_back(os.path.join(tmp, F_SPLIT), len(spl), win["through"])
        shas = {nm: sha_file(os.path.join(tmp, nm)) for nm in OUTPUT_FILES}
        calls = B["calls"]
        _target, rev = next_target(root, win["through"])
        me = os.path.abspath(__file__)
        import pyarrow
        # CHOICE [P15]: the manifest keeps r16's calendar-manifest keys at the top level - created, start, end (the window), rows (the calendar's), sha256 {file: sha} with exactly ONE .csv key - because r17_resmom.wide_load / calendar_start
        # read a calendar's manifest by exactly those; everything else hangs off named sections
        man = {"created": pd.Timestamp.now().isoformat(timespec="seconds"), "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "through": win["through"], "start": win["start"], "end": win["end"],
               "folder": folder_name(win["through"], rev), "revision": rev, "window": {**win, "sessions_in_data": sess},
               "symbols": {"base": len(base), "base_active": pick["base_active"], "base_inactive": pick["base_inactive"], "base_dropped_inactive": len(dropped), "hold": pick["hold"], "hold_inactive": len(hold_in), "hold_added": pick["hold_added"],
                           "new": len(new), "requested": len(symbols), "with_bars": len(B["with_bars"]), "one_sided": len(B["one_sided"]), "empty": len(B["empty"]), "errors": nerr, "error_limit_pct": ERR_MAX_PCT,
                           "error_limit_of": "the requested symbols only"},
               "symbol_rule": "requested = (base list AND the assets endpoint's active set) + the new active listings + every hold name (hold names are requested active or not); base names that are inactive and not held are not requested - "
                              "all of them = the base list minus symbols.txt",
               "base_dropped_inactive": {"count": len(dropped), "first_20": dropped[:FIRST_N]}, "hold": {"file": hinfo, "count": pick["hold"], "inactive_count": len(hold_in), "inactive": hold_in[:MAX_LIST]},
               "base_list": binfo, "new_symbols": new, "new_listing_rule": "active + tradable + on NYSE / NASDAQ / AMEX / ARCA / BATS + r5_siporb.why_not's common-stock rules + not in the base list", "assets": ainfo,
               "empty_symbols": B["empty"], "one_sided_symbols": B["one_sided"], "errors": B["errors"],
               "requests": {"assets": 1, "bars_raw": calls.get("raw", 0), "bars_split": calls.get("split", 0), "bars_retries": calls.get("retries", 0), "corporate_actions": cinfo["requests"], "corporate_actions_pages": cinfo["pages"],
                            "total": 1 + calls.get("raw", 0) + calls.get("split", 0) + cinfo["requests"], "note": "bars: one call = one request (a symbol's ~300 daily bars are one page of fetch_bars' 10,000); a 429 retried inside fetch_bars is not visible here"},
               "bars": {"timeframe": TIMEFRAME, "feed": FEED, "adjustments": list(ADJUSTMENTS), "rows_raw": len(raw), "rows_split": len(spl), "symbols_with_rows_raw": int(raw["symbol"].nunique()), "symbols_with_rows_split": int(spl["symbol"].nunique()),
                        "duplicates_dropped": B["duplicates_dropped"], "request_start": win["bars_start"], "request_end": win["bars_end"]},
               "calendar": cinfo, "rows": cinfo["rows"], "split_crosscheck": cross, "sha256": shas,
               "provenance": {"manifest_path": pull_provenance.manifest_path(), "series": "<SYMBOL>|1Day|raw|sip and <SYMBOL>|1Day|split|sip", "requested_start": win["bars_start"], "requested_end": win["bars_end"],
                              "pulled_between_epoch": B["pulled_between_epoch"], "filed_by": "import_alpaca_stocks.fetch_bars (one receipt per successful call, empty answers included)"},
               "command": {"file": os.path.basename(me), "sha256": sha_file(me), "sha256_lf": sha_lf(me), "argv": list(argv)},
               "versions": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pyarrow.__version__}, "elapsed_seconds": round(time.time() - t_start, 1)}
        mpath = os.path.join(tmp, F_MAN)
        with open(mpath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(man, f, indent=1, default=js, allow_nan=False)
        final, got = publish(tmp, root, win["through"])
        if got != rev:                                                                 # a concurrent pull took the name between the manifest and the rename: the manifest says which revision this is
            man["folder"], man["revision"] = folder_name(win["through"], got), got
            with open(os.path.join(final, F_MAN), "w", encoding="utf-8", newline="\n") as f:
                json.dump(man, f, indent=1, default=js, allow_nan=False)
        return final, got, man
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
            if os.path.isdir(tmp):
                say(f"  note: could not remove {tmp} - delete it by hand (it is not a photograph)")


def run_pull(args):
    """pull: through checked, base list sha checked, pyarrow present, the key found - all BEFORE the first request - then build(); the last line printed says published or refused. The key stays in _SECRETS until main() has printed whatever
    the run ended with (an exception message included - a server or a library might echo it), and main() clears it: clearing it here would let a failure message out unscrubbed"""
    global _SECRETS
    thr, out, hold_arg = parse_args(args, "pull")
    through = validate_through(thr)
    root = os.path.abspath(out or ROOT_DEFAULT)
    win = window_of(through)
    base, binfo = read_base_list()
    hold, hinfo = read_hold_list(hold_arg) if hold_arg else ([], None)
    if not have_pyarrow():
        refuse("refused: pyarrow is not installed - the photograph is written as parquet, the SIPORB cache's format (nothing pulled)")
    key, secret = load_keys()
    if not (key and secret):
        refuse("refused: no Alpaca key found - the engine lookup (augur_engine/alpaca_keys.py: the process environment, the Windows user environment in the registry, then the JSON files) returned nothing (nothing pulled)")
    _SECRETS = (key, secret)
    final, rev, man = build(through, win, root, base, binfo, key, secret, ["pull", "--through", win["through"]] + (["--out", out] if out else []) + (["--hold", hold_arg] if hold_arg else []), hold, hinfo)
    say("  files: " + ", ".join(f"{k} {v[:12]}..." for k, v in man["sha256"].items()) + f"; manifest {F_MAN}")
    say(f"published: the RESMOM forward photograph through {win['through']} (revision {rev}) is on file at {final}")
    return 0


def run_plan(args):
    """plan: the dry check - NO network, NO key, any weekday (a future month-end is fine): the window, the base list's count and sha check, the hold list's count, the request estimate. The estimate: bars = 2 x symbols x pages (one page a symbol), the calendar
    >= symbols / 50, one assets call; minutes at the shared account budget (augur_engine/alpaca_rate.py, 180 a minute) - response time and the other lanes' pulls come on top. Offline the ACTIVE SET is unknown, so the estimate is for the whole base list
    (plus the hold names outside it): an UPPER BOUND that the active filter will cut - `pull` knows and reports the base names it drops as inactive and the inactive hold names"""
    thr, out, hold_arg = parse_args(args, "plan")
    through = validate_through(thr, future_ok=True)
    win = window_of(through)
    root = os.path.abspath(out or ROOT_DEFAULT)
    st = base_list_state()
    say(f"plan: RESMOM forward photograph through {win['through']} ({through:%A}) - no network, no key")
    say(f"  window: {win['start']} .. {win['end']} ({win['calendar_days']} calendar days, {win['weekdays']} weekdays, {win['nyse_closed_days_on_file']} NYSE closed days on file = about {win['sessions_expected']} sessions; the pull refuses below {MIN_SESSIONS})")
    say(f"  bars request window: {win['bars_start']} .. {win['bars_end']}, {TIMEFRAME}, feed {FEED}, adjustments {' + '.join(ADJUSTMENTS)}")
    if not st["exists"]:
        say(f"  base list: {st['path']} is NOT ON FILE")
        refuse("refused: the base list is not on file (nothing pulled)")
    if not st["sha_ok"]:
        say(f"  base list: {st['path']} sha256 {st['sha256']} DIFFERS from the registered {st['registered_sha256']}")
        refuse("refused: the base list's sha256 is not the registered one (nothing pulled)")
    n = len(st["symbols"])
    say(f"  base list: {st['path']}: {n:,} symbols, sha256 {st['sha256'][:12]}...{st['sha256'][-4:]} matches the registered one")
    if hold_arg:
        hold, hinfo = read_hold_list(hold_arg)
        outside = len(set(hold) - set(st["symbols"]))
        say(f"  hold list: {hinfo['path']}: {hinfo['count']:,} symbols, sha256 {hinfo['sha256'][:12]}...{hinfo['sha256'][-4:]}; pulled ALWAYS, active or not (not in the base list: {outside:,}, which add to the counts below)")
    else:
        outside = 0
        say("  hold list: none given (--hold FILE = the names the line holds from the previous rank: pulled ALWAYS, even when inactive now, so a name delisted mid-hold keeps its bars up to delisting)")
    up = n + outside
    pages = -(-win["weekdays"] // PAGE_LIMIT)
    per = alpaca_rate.per_min()

    def est(k):
        bars, cal = 2 * k * pages, -(-k // CA_BATCH)
        return bars, cal, bars + cal + 1
    b0, c0, t0 = est(up)
    extra = int(round(NEW_ALLOWANCE * n))
    b1, c1, t1 = est(up + extra)
    stay = n - int(round(INACTIVE_GUESS * n))
    say("  active filter: unknown offline (the active set is Alpaca's active-assets list, which only `pull` reads): `pull` requests the base names on it + the new listings + every hold name, so the request counts below are an UPPER BOUND that the "
        f"active filter will cut - about {INACTIVE_GUESS:.0%} of the base list is expected to be inactive (roughly {stay:,} of {n:,} base names would stay); `pull` prints and records the base names it dropped as inactive (count, first {FIRST_N}) and the "
        "inactive hold names (all of them)")
    say("  new listings: unknown offline - `pull` reads Alpaca's active assets and adds those that pass SIPORB's common-stock rules and are not in the base list; the second estimate allows "
        f"+{NEW_ALLOWANCE:.0%} ({extra:,} names, a placeholder guess until the first real pull measures it)")
    say("  requests, UPPER BOUND (the whole base list" + (f" + the hold names outside it: {outside:,}" if outside else "") + f", {up:,} symbols): bars 2 x {up:,} symbols x {pages} page = {b0:,}; calendar >= {c0:,} ({CA_BATCH} symbols a request, more for pages); assets 1; total >= {t0:,}")
    say(f"  requests, UPPER BOUND with the allowance ({up + extra:,} symbols): bars {b1:,}; calendar >= {c1:,}; assets 1; total >= {t1:,}")
    say(f"  time: the shared Alpaca budget is {per} requests a minute: the upper-bound counts take about {t0 / per:.1f} min of pace alone, about {t1 / per:.1f} min with the allowance - the active filter makes it shorter (response time and any other lane's pulls come on top)")
    say(f"  caps: a call gives up after {IAS.MAX_429} consecutive 429s; the whole pull after {MAX_RUN_MIN} minutes; no redirect is followed")
    say("  written outside --out by the shared modules: C:\\EdgeLog\\state\\alpaca_rate.json (the shared pace), "
        "C:\\EdgeLog\\state\\alpaca_pulls.jsonl (one provenance receipt per bars call), tools/import_alpaca_stocks.log (429 back-off lines)")
    tgt, rev = next_target(root, win["through"])
    say(f"  output: would publish to {tgt}" + (f" (revision {rev}: that date is already on file)" if rev > 1 else " (a re-pull would become _r2, _r3 ...)"))
    now = now_et()
    say(f"  earliest pull: {through} {EVENING_HOUR:02d}:00 New York time ([P1] --through is accepted when it is before today's New York date, or is today with the New York clock at or after {EVENING_HOUR:02d}:00); "
        f"it is {now:%Y-%m-%d %H:%M} there now: " + ("a pull would be allowed now" if pull_gate(through, now) is None else "not yet"))
    say(f"plan ok: through {win['through']}, about {win['sessions_expected']} sessions, {n:,} base symbols (sha256 verified), " + (f"{len(hold):,} hold symbols, " if hold_arg else "") +
        f"an upper bound of about {t0:,} requests ({t0 / per:.0f} min at the shared pace) before the active filter cuts it; nothing was requested and no key was read")
    return 0


# ------------------------------------------------------------------ selftest: fakes only
_MISSING = object()


@contextlib.contextmanager
def patched(obj, **kw):
    """swap attributes of a module or a class for a block and put them back exactly (an attribute that was only inherited is removed again) - the selftest never leaves anything patched"""
    old = {k: obj.__dict__.get(k, _MISSING) for k in kw}
    for k, v in kw.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is _MISSING:
                delattr(obj, k)
            else:
                setattr(obj, k, v)


@contextlib.contextmanager
def tripwire():
    """the selftest's guard: any socket connection, name lookup or HTTP request through requests, and ANY real key lookup (the engine's, r5_siporb's, the shared loader's) raises. The fakes replace every call the command makes; this proves nothing else is made.
    (Nested uses restore to the outer one.)"""
    import requests

    def boom(*a, **k):
        raise AssertionError("selftest reached the network or the real key lookup")
    with patched(socket.socket, connect=boom, connect_ex=boom), patched(socket, create_connection=boom, getaddrinfo=boom), patched(requests.sessions.Session, request=boom), \
            patched(alpaca_keys, load_keys=boom, _resolve=boom, _from_env=boom, _from_registry=boom, _from_json=boom), patched(S, keys=boom, _http_get=boom), patched(IAS, load_keys=boom):
        yield


FAKE_KEY, FAKE_SECRET = "PKFAKEKEY0123456789ABCD", "FAKESECRETvalue9876543210efghijklmnop"


def asset(sym, name="Example Holdings Inc", exch="NASDAQ", status="active", tradable=True, cls="us_equity"):
    return {"id": "x", "class": cls, "exchange": exch, "symbol": sym, "name": name, "status": status, "tradable": tradable, "shortable": True}


class Vendor:
    """a planted Alpaca: fetch_bars' signature and the frames it would return (every weekday of the window is a session, stamped at ET midnight like the real daily bars), every call recorded. special[sym]: empty, raw_only, split=(date, k) (the raw series
    is k x the adjusted one before that date), skip (dates the symbol has no bar), short (only its last n sessions), until (no bar after this date: a name delisted mid-window), fail={'raw': n, 'split': m} (the first n calls raise; 'always'),
    msg (the failure's text), auth (the key is refused)"""
    def __init__(self, through, special=None):
        self.through = pd.Timestamp(through)
        self.days = pd.bdate_range(self.through - pd.Timedelta(days=WINDOW_DAYS), self.through)
        self.special, self.calls, self.attempts, self._cache = special or {}, [], Counter(), {}

    def frame(self, sym, adj):
        sp = self.special.get(sym, {})
        if sp.get("empty") or (adj == "split" and sp.get("raw_only")):
            return pd.DataFrame()
        if (sym, adj) not in self._cache:
            days = self.days[-sp["short"]:] if "short" in sp else self.days
            if "until" in sp:
                days = days[days <= pd.Timestamp(sp["until"])]
            if "skip" in sp:
                days = days.difference(pd.DatetimeIndex(sp["skip"]))
            n = len(days)
            c = 40.0 + (zlib.crc32(sym.encode()) % 50) + 0.01 * np.arange(n)                          # the split-adjusted close path
            if adj == "raw" and "split" in sp:
                c = c * np.where(days < pd.Timestamp(sp["split"][0]), float(sp["split"][1]), 1.0)
            sec = ((days.tz_localize("US/Eastern").tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy("int64")
            self._cache[(sym, adj)] = pd.DataFrame({"time": sec, "open": np.round(c * 0.998, 4), "high": np.round(c * 1.01, 4), "low": np.round(c * 0.99, 4), "close": np.round(c, 4), "volume": (2_000_000 + 1000 * np.arange(n)).astype("int64")})
        return self._cache[(sym, adj)].copy()

    def __call__(self, sym, timeframe, start, end, key, secret, feed="sip", adjustment="split"):
        self.calls.append({"sym": sym, "timeframe": timeframe, "start": start, "end": end, "key": key, "secret": secret, "feed": feed, "adjustment": adjustment})
        sp = self.special.get(sym, {})
        self.attempts[(sym, adjustment)] += 1
        if sp.get("auth"):
            raise SystemExit("AUTH FAILED (403) - check your Alpaca key/secret. {\"message\":\"forbidden.\"}")
        nf = (sp.get("fail") or {}).get(adjustment, 0)
        if nf == "always" or self.attempts[(sym, adjustment)] <= nf:
            raise RuntimeError(sp.get("msg", "HTTP 500: planted failure"))
        return self.frame(sym, adjustment)


class FakeResponse:
    def __init__(self, body, status=200):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


class FakeHTTP:
    """the Alpaca bars endpoint under requests.get, for the REAL fetch_bars: the Vendor's frames in the real JSON shape ({'bars': {SYM: [{t, o, h, l, c, v}]}, 'next_page_token'}), a second page for the symbols in two_pages, every request recorded"""
    def __init__(self, vendor, two_pages=()):
        self.vendor, self.two_pages, self.calls = vendor, set(two_pages), []

    def __call__(self, url, headers=None, params=None, timeout=None, allow_redirects=True):
        assert allow_redirects is False, "MANAGER #149 (a): the bars call must not follow redirects"
        self.calls.append({"url": url, "headers": dict(headers or {}), "params": dict(params or {}), "timeout": timeout})
        sym, adj, token = params["symbols"], params["adjustment"], params.get("page_token")
        df = self.vendor.frame(sym, adj)
        ts = pd.to_datetime(df["time"].to_numpy("int64"), unit="s") if len(df) else []
        bars = [{"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": float(o), "h": float(h), "l": float(lo), "c": float(c), "v": int(v)} for t, o, h, lo, c, v in zip(ts, df.get("open", []), df.get("high", []), df.get("low", []), df.get("close", []), df.get("volume", []))]
        nxt = None
        if sym in self.two_pages and len(bars) > 1:
            half = len(bars) // 2
            bars, nxt = (bars[:half], "tok2") if not token else (bars[half:], None)
        return FakeResponse({"bars": {sym: bars} if bars else None, "next_page_token": nxt})


class FakeAssets:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def __call__(self, key, secret):
        self.calls.append((key, secret))
        return [dict(r) if isinstance(r, dict) else r for r in self.rows]                  # (a planted row that is not a record passes through as it is)


class FakeCA:
    """a planted ca_fetch: r16's signature, the documented response shape (the 50-symbol batches the real fetch makes), fed to the sink exactly as the real one feeds it (sink.requests, then sink(page, params, label))"""
    def __init__(self, records=None, bad=(), boom=None):
        self.records, self.bad, self.boom, self.calls = records or [], list(bad), boom, []

    def __call__(self, symbols, key, secret, sink, label, start=None, end=None):
        self.calls.append({"symbols": list(symbols), "label": label, "start": start, "end": end, "key": key, "secret": secret})
        if self.boom:
            raise self.boom
        sink.bad.extend(self.bad)
        page = defaultdict(list)
        for typ, rec in self.records:
            page[next(k for k, v in X16.CA_KEYS.items() if v == typ)].append(rec)
        for b in range(0, len(symbols), X16.CA_BATCH):
            chunk = symbols[b:b + X16.CA_BATCH]
            sink.requests += 1
            sink({"corporate_actions": dict(page) if b == 0 else {}, "next_page_token": None},
                 {"symbols": ",".join(chunk), "types": ",".join(X16.CA_TYPES), "start": start, "end": end, "limit": X16.CA_LIMIT}, label)


class World:
    """one planted universe in a temp folder: a base list file (BOM, CRLF, a comment, a blank line, a repeat, a lower-case line - all parsed away), the fakes, a fake New York clock (`now`: a Monday noon by default, so a month-end of the Friday before is
    long past and the Monday itself is not yet allowed), and run() = the command under every patch the selftest needs"""
    def __init__(self, names, special=None, assets=None, records=None, through="2026-10-30", now=dt.datetime(2026, 11, 2, 12, 0)):
        self.dir = tempfile.mkdtemp(prefix="r17pull_")
        self.root, self.through, self.now, self.names = os.path.join(self.dir, "root"), through, now, list(names)
        self.base_path = os.path.join(self.dir, "base.txt")
        with open(self.base_path, "wb") as f:
            f.write(b"\xef\xbb\xbf" + "\r\n".join(["# the planted base list", names[0].lower(), ""] + list(names) + [names[0]]).encode() + b"\r\n")
        self.base_sha = sha_file(self.base_path)
        self.vendor = Vendor(through, special)
        self.assets = FakeAssets(assets if assets is not None else [asset(s) for s in names])
        self.ca = FakeCA(records)
        self.keys = (FAKE_KEY, FAKE_SECRET)

    def hold_file(self, names, name="hold.txt"):
        """a hold list file in the world's folder (BOM, CRLF, a comment, a blank line, a lower-case repeat of the first name - all parsed away) -> its path"""
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(b"\xef\xbb\xbf" + "\r\n".join(["# the planted hold list", names[0].lower(), ""] + list(names)).encode() + b"\r\n")
        return p

    def run(self, cmd="pull", through=None, transport=None, hold=None, hold_path=None, **over):
        """-> (exit code, stdout, stderr) of main() under the fakes, the tripwire, the fake clock, a temp EDGELOG_HOME (so no provenance or pace state of the real machine is touched) and no sleeping. transport = a fake for r5_siporb._get: then the
        command's REAL fetch_assets and r16_xgap.ca_fetch run over it instead of the two fakes. hold = the names of a hold list file this writes and passes as --hold; hold_path = a --hold value used as it is (a file that is not there)"""
        fakes = {"fetch_bars": self.vendor, "fetch_assets": self.assets, "ca_fetch": self.ca, "load_keys": lambda: self.keys, "now_et": lambda: self.now, "BASE_LIST_PATH": self.base_path, "BASE_LIST_SHA": self.base_sha,
                 "RETRY_WAIT": 0.0, "RENAME_WAIT": 0.0}
        if transport is not None:
            del fakes["fetch_assets"], fakes["ca_fetch"]
        no_out = over.pop("no_out", False)                                      # no --out on the command line: ROOT is the module's default, which the test points at the world's folder
        if no_out:
            fakes["ROOT_DEFAULT"] = self.root
        fakes.update(over)
        hold_args = ["--hold", self.hold_file(hold)] if hold is not None else ["--hold", hold_path] if hold_path is not None else []
        out, err, old_home = io.StringIO(), io.StringIO(), os.environ.get("EDGELOG_HOME")
        os.environ["EDGELOG_HOME"] = os.path.join(self.dir, "home")
        try:
            with contextlib.ExitStack() as st:
                st.enter_context(tripwire())
                st.enter_context(patched(sys.modules[__name__], **fakes))
                if transport is not None:
                    st.enter_context(patched(S, _get=transport))
                st.enter_context(contextlib.redirect_stdout(out))
                st.enter_context(contextlib.redirect_stderr(err))
                code = main([cmd, "--through", through or self.through] + ([] if no_out else ["--out", self.root]) + hold_args)
        finally:
            if old_home is None:
                os.environ.pop("EDGELOG_HOME", None)
            else:
                os.environ["EDGELOG_HOME"] = old_home
        return code, out.getvalue(), err.getvalue()

    def folders(self):
        return sorted(os.listdir(self.root)) if os.path.isdir(self.root) else None

    def clean(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def refuses(fn, frag):
    try:
        fn()
    except Refused as e:
        assert frag in str(e), (frag, str(e))
        return str(e)
    raise AssertionError(f"must refuse: {frag}")


def raiser(exc):
    def f(*a, **k):
        raise exc
    return f


def assert_no_secrets(w, *texts):
    """neither the key nor the secret in any captured output, nor in a byte of anything written under the world's folder (the published photograph, the provenance state, the base list ...)"""
    for t in texts:
        assert FAKE_KEY not in t and FAKE_SECRET not in t, "a key or secret reached the captured output"
    for d, _dirs, files in os.walk(w.dir):
        for nm in files:
            with open(os.path.join(d, nm), "rb") as f:
                b = f.read()
            assert FAKE_KEY.encode() not in b and FAKE_SECRET.encode() not in b, f"a key or secret reached {os.path.join(d, nm)}"


def last_line(out):
    return [ln for ln in out.splitlines() if ln.strip()][-1]


def man_of(folder):
    with open(os.path.join(folder, F_MAN), encoding="utf-8") as f:
        return json.load(f)


def sym_counts(base, **kw):
    """the manifest's `symbols` section of a world where every base name is active, nothing is held and nothing is new (requested = base unless a keyword says otherwise)"""
    d = {"base": base, "base_active": base, "base_inactive": 0, "base_dropped_inactive": 0, "hold": 0, "hold_inactive": 0, "hold_added": 0, "new": 0, "requested": base, "with_bars": 0, "one_sided": 0, "empty": 0, "errors": 0,
         "error_limit_pct": 2, "error_limit_of": "the requested symbols only"}
    d.update(kw)
    return d


def t_constants():
    assert BASE_LIST_SHA == "ab646462ffc0ee256f0272b7e5203efbe631d10f83b84d3fbda632430814852c" and BASE_LIST_PATH == r"C:\EdgeLog\alpaca_cache\xgap\wide_symbols_siporb_floor_2016_2025.txt"
    assert ROOT_DEFAULT == r"C:\EdgeLog\alpaca_cache\resmom_fwd" and WINDOW_DAYS == 430 and MIN_SESSIONS == 290 and ERR_MAX_PCT == 2 and (TIMEFRAME, FEED, ADJUSTMENTS) == ("1Day", "sip", ("raw", "split"))
    assert OUTPUT_FILES == ("daily_raw.parquet", "daily_split.parquet", "corporate_actions.csv", "corporate_actions_raw.jsonl", "symbols.txt") and F_MAN == "manifest.json"
    assert EXCH == {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"} and SPLIT_REL == 0.01 and SPLIT_TOL == 3 and SIPORB_RULES is True and THROUGH_COVER == 0.5 and NEW_ALLOWANCE == 0.25
    assert EVENING_HOUR == 20 and ACTIVE_MIN_PCT == 25 and INACTIVE_GUESS == 0.40 and FIRST_N == 20, "the same-evening hour, the active-share floor, plan's inactive guess, the 20 names the manifest shows"
    assert "MIN_AGE_DAYS" not in globals() and "today_et" not in globals(), "the age rule and its clock are replaced by the 20:00 rule and now_et"
    assert tuple(X16.CA_COLS) == ("type", "symbol", "old_symbol", "new_symbol", "ex_date", "process_date", "record_date", "payable_date", "rate", "new_rate", "old_rate", "cash", "special")
    assert set(X16.CA_TYPES) == {"cash_dividend", "forward_split", "reverse_split", "unit_split", "stock_dividend", "name_change", "spin_off"} and X16.CA_BATCH == 50
    assert [(f.name, str(f.type)) for f in parquet_schema()] == [("symbol", "string"), ("date", "timestamp[ns]"), ("o", "double"), ("h", "double"), ("l", "double"), ("c", "double"), ("v", "int64")], "r5_siporb.consolidate's schema"
    assert all(dt.date.fromisoformat(d).weekday() < 5 for d in NYSE_CLOSED), "every closure on the table is a weekday"
    me = sys.modules[__name__]
    assert me.fetch_bars is IAS.fetch_bars and me.ca_fetch is X16.ca_fetch and not _SECRETS, "the house calls are the ones used; no key is held at rest"


def t_window():
    w = window_of(dt.date(2026, 10, 30))
    assert (w["start"], w["end"], w["through"], w["calendar_days"]) == ("2025-08-26", "2026-10-30", "2026-10-30", 430)
    assert (w["bars_start"], w["bars_end"]) == ("2025-08-26T00:00:00Z", "2026-10-30T23:59:59Z")
    assert w["weekdays"] == len(pd.bdate_range("2025-08-26", "2026-10-30")) == 309 and w["nyse_closed_days_on_file"] == 11 and w["sessions_expected"] == 298 >= MIN_SESSIONS
    for d in (dt.date(2028, 3, 1), dt.date(2027, 5, 28), dt.date(2026, 2, 27)):                       # leap years and month ends
        start = dt.date.fromisoformat(window_of(d)["start"])
        assert start == (pd.Timestamp(d) - pd.Timedelta(days=430)).date() and (d - start).days == 430
    now = dt.datetime(2026, 11, 2, 12, 0)                                                              # a Monday noon in New York (the same-evening rule has its own test, t_clock)
    today = now.date()
    with patched(sys.modules[__name__], now_et=lambda: now):
        assert validate_through("2026-10-30") == dt.date(2026, 10, 30), "last Friday is a completed session"
        assert validate_through(" 2026-10-29 ") == dt.date(2026, 10, 29)
        refuses(lambda: validate_through("2026-11-02"), "is today in New York and the clock there reads 12:00")
        refuses(lambda: validate_through("2026-11-03"), "is in the future")
        refuses(lambda: validate_through("2027-01-04"), "is in the future")
        refuses(lambda: validate_through("2026-10-31"), "Saturday")
        refuses(lambda: validate_through("2026-11-01"), "Sunday")
        refuses(lambda: validate_through("2026-09-07"), "NYSE holiday (Labor Day)")
        refuses(lambda: validate_through("2026-07-03"), "NYSE holiday (Independence Day (observed))")
        for bad in ("", "20261030", "2026-10-3", "10/30/2026", "tomorrow", "x"):
            refuses(lambda: validate_through(bad), "is not a date written YYYY-MM-DD")
        for bad in ("2026-13-01", "2026-02-30"):
            refuses(lambda: validate_through(bad), "is not a real calendar date")
        assert validate_through("2026-11-30", future_ok=True) == dt.date(2026, 11, 30), "plan accepts a future weekday"
        assert validate_through("2026-11-02", future_ok=True) == today and validate_through("2027-04-30", future_ok=True) == dt.date(2027, 4, 30)
        refuses(lambda: validate_through("2026-11-28", future_ok=True), "Saturday")
        refuses(lambda: validate_through("2026-11-26", future_ok=True), "Thanksgiving Day")
    assert folder_name("2026-10-30", 1) == "2026-10-30" and folder_name("2026-10-30", 2) == "2026-10-30_r2" and folder_name("2026-10-30", 7) == "2026-10-30_r7"
    d = tempfile.mkdtemp()
    try:
        assert next_target(d, "2026-10-30") == (os.path.join(d, "2026-10-30"), 1)
        os.makedirs(os.path.join(d, "2026-10-30"))
        os.makedirs(os.path.join(d, "2026-10-30_r2"))
        assert next_target(d, "2026-10-30") == (os.path.join(d, "2026-10-30_r3"), 3)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert parse_args(("--through", "2026-10-30"), "pull") == ("2026-10-30", None, None) and parse_args(("--out", "C:\\r", "--through", "2026-10-30"), "pull") == ("2026-10-30", "C:\\r", None)
    assert parse_args(("--through=2026-10-30", "--out=C:\\a=b"), "plan") == ("2026-10-30", "C:\\a=b", None)
    assert parse_args(("--hold", "C:\\h.txt", "--through", "2026-10-30"), "pull") == ("2026-10-30", None, "C:\\h.txt") and parse_args(("--through=2026-10-30", "--out=C:\\r", "--hold=C:\\a=b.txt"), "plan") == ("2026-10-30", "C:\\r", "C:\\a=b.txt")
    for bad, frag in (([], "is required"), (["--through"], "takes exactly one value"), (["--through", "--out", "x"], "takes exactly one value"), (["--through", "a", "--through", "b"], "takes exactly one value"),
                      (["--through", "2026-10-30", "--force"], "unknown argument"), (["2026-10-30"], "unknown argument"), (["--through", "2026-10-30", "--hold"], "takes exactly one value"),
                      (["--through", "2026-10-30", "--hold", "--out", "x"], "takes exactly one value"), (["--through", "2026-10-30", "--hold", "a", "--hold", "b"], "takes exactly one value"),
                      (["--through", "2026-10-30", "--hold="], "takes exactly one value")):
        msg = refuses(lambda: parse_args(bad, "pull"), frag)
        assert msg.endswith("(nothing pulled)")
    assert "[--hold FILE]" in refuses(lambda: parse_args(["--force"], "plan"), "unknown argument"), "the usage line names --hold"


def t_base_list():
    d = tempfile.mkdtemp()
    me = sys.modules[__name__]
    try:
        p = os.path.join(d, "b.txt")
        with open(p, "wb") as f:
            f.write(b"\xef\xbb\xbf# comment\r\nA\r\naa\r\n\r\nAABA\r\nA\r\nBRK.B\r\n   MSFT  \r\n")
        sha = sha_file(p)
        with patched(me, BASE_LIST_PATH=p, BASE_LIST_SHA=sha):
            syms, info = read_base_list()
            assert syms == ["A", "AA", "AABA", "BRK.B", "MSFT"] and info["count"] == 5 and info["sha256"] == sha == info["registered_sha256"] and info["first"] == "A" and info["last"] == "MSFT" and info["sha_ok"]
            st = base_list_state()
            assert st["exists"] and st["sha_ok"] and st["symbols"] == syms
        with patched(me, BASE_LIST_PATH=p, BASE_LIST_SHA="0" * 64):
            msg = refuses(read_base_list, "has sha256")
            assert sha in msg and "0" * 64 in msg and msg.endswith("(nothing pulled)")
            st = base_list_state()
            assert st["exists"] and not st["sha_ok"] and st["symbols"] is None and st["sha256"] == sha
        with patched(me, BASE_LIST_PATH=os.path.join(d, "absent.txt")):
            refuses(read_base_list, "is not on file")
        for body, frag in ((b"", "holds no symbol"), (b"# only a comment\n\n", "holds no symbol"), (b"AAPL,MSFT\n", "line 1"), (b"AAPL\nAA PL\n", "line 2"), (b"\xff\xfe\x00bad", "not UTF-8")):
            with open(p, "wb") as f:
                f.write(body)
            with patched(me, BASE_LIST_PATH=p, BASE_LIST_SHA=sha_file(p)):
                refuses(read_base_list, frag)
        with open(p, "wb") as f:
            f.write(b"A\nB\n")
        with patched(me, BASE_LIST_PATH=p, BASE_LIST_SHA=sha_file(p) + "0"):
            refuses(read_base_list, "has sha256")                       # a different registered sha is a different list
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_hold_list():
    """the --hold file: the base list's file rules, and a missing / unreadable / empty / malformed file refuses (before any key is touched), the facts the manifest records"""
    d = tempfile.mkdtemp()
    me = sys.modules[__name__]
    try:
        p = os.path.join(d, "hold.txt")
        with open(p, "wb") as f:
            f.write(b"\xef\xbb\xbf# held from the 2026-10-30 rank\r\nzold\r\n\r\nT070\r\nZOLD\r\nBRK.B\r\n   msft  \r\n")
        syms, info = read_hold_list(p)
        assert syms == ["ZOLD", "T070", "BRK.B", "MSFT"], "file order, upper-cased, the repeat dropped, the comment and the blank line skipped"
        assert info == {"path": os.path.abspath(p), "sha256": sha_file(p), "count": 4, "first": "ZOLD", "last": "MSFT"}, info
        old = os.getcwd()
        os.chdir(d)
        try:
            _s, rel = read_hold_list("hold.txt")                                              # a relative path is resolved against the working directory and recorded in full
        finally:
            os.chdir(old)
        assert os.path.isabs(rel["path"]) and os.path.samefile(rel["path"], p)
        refuses(lambda: read_hold_list(os.path.join(d, "absent.txt")), "is not on file")
        refuses(lambda: read_hold_list(d), "is not on file")                                  # a folder is not a file
        with patched(me, open=raiser(PermissionError("denied (planted)"))):
            msg = refuses(lambda: read_hold_list(p), "cannot be read (PermissionError)")
        assert "planted" not in msg and msg.endswith("(nothing pulled)"), msg
        for body, frag in ((b"", "holds no symbol"), (b"# nobody is held\n\n", "holds no symbol"), (b"AAPL,MSFT\n", "line 1"), (b"AAPL\nAA PL\n", "line 2"), (b"\xff\xfe\x00bad", "not UTF-8"), (b"A\n" + b"X" * 13 + b"\n", "line 2")):
            with open(p, "wb") as f:
                f.write(body)
            msg = refuses(lambda: read_hold_list(p), frag)
            assert "the hold list hold.txt" in msg and msg.endswith("(nothing pulled)"), msg
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_assets():
    base = ["AAA", "BBB"]
    rows = [asset("AAA"), asset("BBB", status="inactive"), asset("newa", "Newa Holdings Inc", "NYSE"), asset("NEWB", "Newb Technologies Corp", "NASDAQ"), asset("NEWD", "Newd Corp", "AMEX"), asset("NEWE", "Newe Corp", "ARCA"), asset("NEWF", "Newf Corp", "BATS"),
            asset("OTCX", "Otc Corp", "OTC"), asset("SPYX", "Example S&P 500 ETF Trust", "ARCA"), asset("INAC", status="inactive"), asset("NOTR", tradable=False), asset("NEWC.B", "Newc Corp", "NYSE"), asset("NEWWW", "Neww Corp Warrants", "NASDAQ"),
            asset("003CVR016", "Escrow", "NASDAQ"), asset("CRYP", cls="crypto"), asset("", "No Symbol"), asset("NEWB", "Newb Technologies Corp", "NASDAQ"), "garbage", asset("UNIT1", "Newco Units", "NYSE")]
    new, info = new_listings(rows, base)
    assert new == ["NEWA", "NEWB", "NEWD", "NEWE", "NEWF"], new
    assert info["excluded_by_reason"] == {"already_in_base_list": 2, "exchange": 1, "name:etf": 1, "name:units": 1, "no_symbol": 1, "not_a_record": 1, "not_active": 1, "not_tradable": 1, "not_us_equity": 1, "symbol:dot_slash": 1,
                                          "symbol:placeholder": 1, "symbol:suffix": 1}, info
    assert info["new"] == 5 and info["assets_rows"] == len(rows) and not (set(new) & set(base)), "a base name is never 'new' (even when the endpoint lists it as inactive)"
    assert new_listings([], base) == ([], {"assets_rows": 0, "excluded_by_reason": {}, "new": 0})
    with patched(sys.modules[__name__], SIPORB_RULES=False):                 # the knob [P3]: the literal reading - active, tradable, us_equity, on the five exchanges, not in the base list
        lit, linfo = new_listings(rows, base)
        assert lit == ["003CVR016", "NEWA", "NEWB", "NEWC.B", "NEWD", "NEWE", "NEWF", "NEWWW", "SPYX", "UNIT1"], lit
        assert linfo["excluded_by_reason"] == {"already_in_base_list": 2, "exchange": 1, "no_symbol": 1, "not_a_record": 1, "not_active": 1, "not_tradable": 1, "not_us_equity": 1}, linfo
    calls = []

    def fake_get(url, params, key, secret):                       # the shared transport, faked: r5_siporb._get
        calls.append((url, dict(params), key, secret))
        return [asset("ZZZ")]
    with patched(S, _get=fake_get):
        assert fetch_assets("k-key", "k-secret") == [asset("ZZZ")]
    assert calls == [(S.ASSETS_URL, {"status": "active", "asset_class": "us_equity"}, "k-key", "k-secret")] and S.ASSETS_URL.endswith("/v2/assets")
    # the ACTIVE SET: the status field and a symbol, nothing else (a record that is not tradable, off the five exchanges or of another class is still 'active' for the base filter)
    odd = [asset("AAA"), asset("bbb", status="Active"), asset(" CCC "), asset("DDD", status="inactive"), asset("EEE", status=""), {"symbol": "FFF"}, asset("", "No Symbol"), "garbage", None, asset("GGG", tradable=False, exch="OTC"), asset("hhh", cls="crypto")]
    assert active_set(odd) == {"AAA", "BBB", "CCC", "GGG", "HHH"} and active_set([]) == set() and active_set(["x", None, 3]) == set()
    # THE SYMBOL RULE on its own: (base AND active) + new listings + hold names
    base5 = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    rows5 = [asset("AAA"), asset("CCC"), asset("NEW1", "New One Inc", "NYSE"), asset("NEW2", "New Two Inc", "NYSE"), asset("ZNEW", "Znew Corp", "NYSE")]
    new5, _ = new_listings(rows5, base5)
    assert new5 == ["NEW1", "NEW2", "ZNEW"]
    pk = choose_symbols(base5, rows5, new5, ["BBB", "ZZZ", "NEW1", "AAA"])            # an inactive base name, an inactive name outside the base list, a new listing, an active base name
    assert pk == {"requested": ["AAA", "BBB", "CCC", "NEW1", "NEW2", "ZNEW", "ZZZ"], "active_listed": 5, "base_active": 2, "base_inactive": 3, "dropped": ["DDD", "EEE"], "hold": 4, "hold_inactive": ["BBB", "ZZZ"], "hold_added": 2}, pk
    assert len(pk["requested"]) == pk["base_active"] + len(new5) + pk["hold_added"] and set(base5) - set(pk["requested"]) == set(pk["dropped"]), "requested = active base + new + the hold names nobody else requests; dropped = base - requested"
    pk = choose_symbols(base5, rows5, new5, [])
    assert pk["requested"] == ["AAA", "CCC", "NEW1", "NEW2", "ZNEW"] and pk["dropped"] == ["BBB", "DDD", "EEE"] and pk["hold"] == 0 and pk["hold_inactive"] == [] and pk["hold_added"] == 0 and pk["base_inactive"] == 3
    pk = choose_symbols(base5, rows5, new5, ["DDD", "EEE", "BBB"])                    # every inactive base name held: none is dropped
    assert pk["dropped"] == [] and pk["hold_inactive"] == ["BBB", "DDD", "EEE"] and pk["hold_added"] == 3 and pk["base_inactive"] == 3 and len(pk["requested"]) == 8


def t_daily_frames():
    """fetch_bars' frame -> the SIPORB cache's columns: the date is the Eastern session date in both DST halves, naive, ns; an empty answer is an empty frame of the same columns"""
    wins = pd.DatetimeIndex(["2026-01-02", "2026-03-06", "2026-03-09", "2026-10-30", "2026-11-02"])           # EST, the last EST day before the 2026-03-08 change, the first EDT day, EDT, EST again
    sec = ((wins.tz_localize("US/Eastern").tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy("int64")
    assert [pd.Timestamp(s, unit="s", tz="UTC").hour for s in sec] == [5, 5, 4, 4, 5], "both stamps the real feed uses: 05:00Z in winter, 04:00Z in summer"
    out = to_daily("ABC", pd.DataFrame({"time": sec, "open": [1.0] * 5, "high": [2.0] * 5, "low": [0.5] * 5, "close": [1.5] * 5, "volume": [10, 20, 30, 40, 50]}))
    assert list(out.columns) == ["symbol", "date", "o", "h", "l", "c", "v"] and list(out["date"]) == list(wins) and str(out["date"].dtype) == "datetime64[ns]" and out["date"].dt.tz is None
    assert list(out["symbol"]) == ["ABC"] * 5 and list(out["v"]) == [10, 20, 30, 40, 50] and out["v"].dtype == "int64" and str(out["c"].dtype) == "float64"
    for e in (to_daily("ABC", pd.DataFrame()), to_daily("ABC", None)):
        assert list(e.columns) == ["symbol", "date", "o", "h", "l", "c", "v"] and len(e) == 0 and str(e["date"].dtype) == "datetime64[ns]"
    assert len(Vendor("2026-10-30").days) == 309


def t_bars_pull():
    """both adjustments per symbol with the window and the key passed through, empty symbols counted, one retry, the key refused, the error threshold"""
    names = [f"T{k:03d}" for k in range(100)]
    w = World(names, special={"T001": {"empty": True}, "T002": {"empty": True}, "T003": {"raw_only": True}, "T004": {"fail": {"raw": 1}}, "T005": {"fail": {"split": 1}}})
    try:
        code, out, err = w.run()
        assert code == 0 and last_line(out).startswith("published: "), out
        for s in names:
            mine = sorted(x["adjustment"] for x in w.vendor.calls if x["sym"] == s)
            assert mine == (["raw", "raw", "split"] if s == "T004" else ["raw", "split", "split"] if s == "T005" else ["raw", "split"]), (s, mine)
        assert all(x["timeframe"] == "1Day" and x["feed"] == "sip" and x["start"] == "2025-08-26T00:00:00Z" and x["end"] == "2026-10-30T23:59:59Z" and (x["key"], x["secret"]) == w.keys for x in w.vendor.calls)
        m = man_of(os.path.join(w.root, "2026-10-30"))
        assert m["symbols"] == sym_counts(100, with_bars=97, one_sided=1, empty=2), m["symbols"]
        assert m["empty_symbols"] == ["T001", "T002"] and m["one_sided_symbols"] == ["T003"] and m["errors"] == []
        r = m["requests"]
        assert (r["bars_raw"], r["bars_split"], r["bars_retries"], r["assets"], r["corporate_actions"], r["total"]) == (101, 101, 2, 1, 2, 1 + 202 + 2), r
        assert (m["bars"]["rows_raw"], m["bars"]["rows_split"], m["bars"]["symbols_with_rows_raw"], m["bars"]["symbols_with_rows_split"]) == (98 * 309, 97 * 309, 98, 97), m["bars"]
        assert len(w.assets.calls) == 1 and len(w.ca.calls) == 1 and w.ca.calls[0]["symbols"] == names and w.ca.calls[0]["label"] == 1
        assert (w.ca.calls[0]["start"], w.ca.calls[0]["end"]) == ("2025-08-26", "2026-10-30") and (w.ca.calls[0]["key"], w.ca.calls[0]["secret"]) == w.keys, "the calendar covers the same window and the same symbols"
        assert_no_secrets(w, out, err)
    finally:
        w.clean()
    for n_err, ok in ((0, True), (1, True), (2, True), (3, False)):                                   # 1% passes, exactly 2% passes, 3% refuses and publishes nothing
        w = World(names, special={names[k * 7 + 3]: {"fail": {"raw": "always"}} for k in range(n_err)})
        try:
            code, out, err = w.run()
            assert (code == 0) == ok and last_line(out).startswith("published: " if ok else "refused: "), (n_err, out)
            if ok:
                f = os.path.join(w.root, "2026-10-30")
                m = man_of(f)
                assert m["symbols"]["errors"] == n_err and len(m["errors"]) == n_err and m["symbols"]["with_bars"] == 100 - n_err and [e["adjustment"] for e in m["errors"]] == ["raw"] * n_err
                assert not ({e["symbol"] for e in m["errors"]} & set(pd.read_parquet(os.path.join(f, F_RAW))["symbol"])), "an errored symbol contributes no rows"
                with open(os.path.join(f, F_SYMS)) as fh:
                    assert fh.read().split() == names, "symbols.txt lists every symbol requested"
            else:
                assert last_line(out).startswith("refused: 3 of 100 symbols errored after a retry (3.0%, more than the 2% limit); the pull stopped at symbol 18 - first error: T003 raw RuntimeError: HTTP 500: planted failure") and \
                    last_line(out).endswith("(nothing published)") and w.folders() == [], (out, w.folders())
                assert w.ca.calls == [] and len(w.vendor.calls) == 36, "stopped the moment 'more than 2%' was certain: 18 symbols asked, a retry each for the three that failed, no calendar pull"
            assert_no_secrets(w, out, err)
        finally:
            w.clean()
    w = World(names, special={"T050": {"fail": {"split": "always"}}})                                  # the raw call WORKED, the split call failed twice: the symbol is an error and its raw bars are not in the photograph either
    try:
        code, out, err = w.run()
        assert code == 0, out
        f = os.path.join(w.root, "2026-10-30")
        m = man_of(f)
        assert [(e["symbol"], e["adjustment"]) for e in m["errors"]] == [("T050", "split")] and m["symbols"]["errors"] == 1 and m["symbols"]["with_bars"] == 99 and m["bars"]["rows_raw"] == 99 * 309 == m["bars"]["rows_split"]
        assert "T050" not in set(pd.read_parquet(os.path.join(f, F_RAW))["symbol"]) | set(pd.read_parquet(os.path.join(f, F_SPLIT))["symbol"])
        assert sorted(x["adjustment"] for x in w.vendor.calls if x["sym"] == "T050") == ["raw", "split", "split"] and m["requests"]["bars_retries"] == 1
    finally:
        w.clean()
    w = World(names, special={"T010": {"auth": True}})
    try:
        code, out, err = w.run()
        assert code == 2 and w.folders() == [] and len(w.vendor.calls) == 2 * 10 + 1 and len([x for x in w.vendor.calls if x["sym"] == "T010"]) == 1, "a refused key stops the run at once: no retry, no more symbols"
        assert last_line(out) == "refused: Alpaca refused the key (HTTP 403) on T010 raw - check the key and the data plan (nothing published)", last_line(out)
        assert_no_secrets(w, out, err)
    finally:
        w.clean()


def t_through_in_data():
    """after the pull: >= 290 sessions in the data, and --through must be one of them with bars for at least half a typical session's names"""
    names = [f"T{k:03d}" for k in range(20)]
    w = World(names, special={s: {"short": 200} for s in names})
    try:
        code, out, _ = w.run()
        assert code == 2 and last_line(out).startswith("refused: the data holds 200 sessions, fewer than the 290") and w.folders() == [], out
    finally:
        w.clean()
    skip = [pd.Timestamp("2026-10-30")]
    for printing, ok in ((12, True), (8, False)):                                       # 12 of 20 names print on --through (60%): fine; 8 of 20 (40%): not a complete session
        w = World(names, special={s: {"skip": skip} for s in names[printing:]})
        try:
            code, out, _ = w.run()
            assert (code == 0) == ok, out
            if not ok:
                assert last_line(out).startswith("refused: --through 2026-10-30 carries bars for only 8 symbols against a typical 20 a session") and w.folders() == [], out
        finally:
            w.clean()
    for label, special, frag in (("nobody prints on --through (a holiday)", {s: {"skip": skip} for s in names}, "carries bars for only 0 symbols"), ("no bar at all", {s: {"empty": True} for s in names}, "returned no bar for any symbol")):
        w = World(names, special=special)
        try:
            code, out, _ = w.run()
            assert code == 2 and frag in last_line(out) and last_line(out).endswith("(nothing published)") and w.folders() == [], (label, out)
        finally:
            w.clean()


CROSS_RECORDS = [
    ("forward_split", {"symbol": "B02", "new_rate": 2, "old_rate": 1, "ex_date": "2026-03-02", "process_date": "2026-03-02"}),
    ("reverse_split", {"symbol": "B03", "new_rate": 1, "old_rate": 8, "ex_date": "2026-04-06", "process_date": "2026-04-06"}),
    ("forward_split", {"symbol": "B05", "new_rate": 2, "old_rate": 1, "ex_date": "2026-06-01", "process_date": "2026-06-01"}),
    ("forward_split", {"symbol": "B06", "new_rate": 3, "old_rate": 1, "ex_date": "2026-07-06", "process_date": "2026-07-06"}),
    ("unit_split", {"old_symbol": "B11", "new_symbol": "B11U", "old_rate": 1, "new_rate": 2, "effective_date": "2026-08-03", "process_date": "2026-08-03"}),
    ("forward_split", {"symbol": "B13", "new_rate": 2, "old_rate": 1, "ex_date": "2026-01-12", "process_date": "2026-01-12"}),
    ("forward_split", {"symbol": "B13", "new_rate": 2, "old_rate": 1, "ex_date": "2026-01-12", "process_date": "2026-01-13"}),
    ("forward_split", {"symbol": "B15", "new_rate": 4, "old_rate": 1, "ex_date": "2026-09-12", "process_date": "2026-09-14"}),
    ("forward_split", {"symbol": "B12", "new_rate": 2, "old_rate": 1, "ex_date": "2025-08-20", "process_date": "2025-08-20"}),
    ("forward_split", {"symbol": "B14", "new_rate": 2, "old_rate": 1, "ex_date": "2025-08-26", "process_date": "2025-08-26"}),
    ("forward_split", {"symbol": "B07", "new_rate": 2, "old_rate": 1, "ex_date": "2026-02-02", "process_date": "2026-02-02"}),
    ("forward_split", {"symbol": "B09", "new_rate": 2, "old_rate": 1, "ex_date": "2026-02-09", "process_date": "2026-02-09"}),
    ("forward_split", {"symbol": "B16", "new_rate": 2, "old_rate": 1}),
    ("cash_dividend", {"symbol": "B01", "rate": 0.24, "special": False, "ex_date": "2026-02-09", "process_date": "2026-02-15"}),
    ("name_change", {"old_symbol": "B01", "new_symbol": "B01N", "process_date": "2026-07-01"})]
CROSS_SPECIAL = {"B02": {"split": ("2026-03-02", 2)}, "B04": {"split": ("2026-05-04", 3)}, "B05": {"split": ("2026-06-03", 2)}, "B06": {"split": ("2026-07-10", 3)}, "B11": {"split": ("2026-08-03", 2)},
                 "B13": {"split": ("2026-01-12", 2)}, "B15": {"split": ("2026-09-14", 4)}, "B07": {"empty": True}, "B08": {"empty": True}, "B09": {"raw_only": True}}


def t_crosscheck():
    """a planted 2-for-1 split (agree), a calendar-only case (no adjustment), a price-only case (no calendar row), +-3 sessions, a unit split on its new / old symbol, a weekend ex-date, and every 'cannot be compared' class - through the whole command,
    then the same frames through the HARNESS's own reader and its registered split rule"""
    names = [f"B{k:02d}" for k in range(1, 17)]
    w = World(names, special=CROSS_SPECIAL, records=CROSS_RECORDS)
    try:
        code, out, err = w.run()
        assert code == 0, out
        folder = os.path.join(w.root, "2026-10-30")
        x = man_of(folder)["split_crosscheck"]
        assert (x["agree"], x["calendar_only"], x["price_only"]) == (5, 2, 2), x
        assert x["price_implied_events"] == 7 and x["calendar_events_compared"] == 7 and x["agree"] + x["price_only"] == x["price_implied_events"] and x["agree"] + x["calendar_only"] == x["calendar_events_compared"]
        assert x["not_comparable"] == {"before_first_bar": 1, "calendar_split_rows": 13, "duplicates_merged": 1, "no_bars": 1, "one_sided": 1, "outside_window": 1, "undated": 1}, x["not_comparable"]
        assert [(e["kind"], e["symbol"], e["date"]) for e in x["disagreements"]] == [("calendar_only", "B03", "2026-04-06"), ("calendar_only", "B06", "2026-07-06"), ("price_only", "B04", "2026-05-04"), ("price_only", "B06", "2026-07-10")], x["disagreements"]
        e = {(d["kind"], d["symbol"]): d for d in x["disagreements"]}
        assert e[("price_only", "B04")]["factor_ratio"] == round(1 / 3, 6) and e[("calendar_only", "B03")]["type"] == "reverse_split" and (e[("calendar_only", "B03")]["new_rate"], e[("calendar_only", "B03")]["old_rate"]) == (1, 8)
        assert x["relative_change"] == 0.01 and x["tolerance_sessions"] == 3 and x["disagreements_truncated"] is False and "nothing is fixed or dropped" in x["rule"]
        cache = os.path.join(w.dir, "cache")
        os.makedirs(os.path.join(cache, "siporb"))
        shutil.copy(os.path.join(folder, F_RAW), os.path.join(cache, "siporb", "daily_raw.parquet"))
        shutil.copy(os.path.join(folder, F_SPLIT), os.path.join(cache, "siporb", "daily_split.parquet"))
        with patched(S, CACHE=cache), contextlib.redirect_stdout(io.StringIO()):
            D = S.Data(pd.Timestamp("2026-10-31"), open5=False)
        hits = sorted((str(D.syms[c]), f"{D.days[t_]:%Y-%m-%d}") for t_, c in zip(*np.nonzero(D.chg)))
        assert hits == [("B02", "2026-03-02"), ("B04", "2026-05-04"), ("B05", "2026-06-03"), ("B06", "2026-07-10"), ("B11", "2026-08-03"), ("B13", "2026-01-12"), ("B15", "2026-09-14")], hits
        assert len(D.days) == 309 and str(D.days[0].date()) == "2025-08-26" and str(D.days[-1].date()) == "2026-10-30" and "B07" not in set(D.syms) and "B09" in set(D.syms), "the harness's own reader loads the photograph"
        assert_no_secrets(w, out, err)
    finally:
        w.clean()


def t_calendar_files():
    """the calendar flattened exactly like r16's: the CSV against a hand-written expectation, the raw pages one JSON line each, the manifest's counts by type and year; then the REAL r16 ca_fetch and the real fetch_assets over a faked shared transport"""
    repeat = {"symbol": "S001", "cusip": "x", "rate": 0.24, "special": False, "foreign": False, "process_date": "2026-02-15", "ex_date": "2026-02-09", "record_date": "2026-02-10", "payable_date": "2026-02-15"}
    recs = [("cash_dividend", dict(repeat)),
            ("forward_split", {"symbol": "S002", "new_rate": 2, "old_rate": 1, "process_date": "2026-03-02", "ex_date": "2026-03-02", "record_date": "2026-02-27", "payable_date": "2026-02-27"}),
            ("reverse_split", {"symbol": "S003", "new_rate": 1, "old_rate": 8, "ex_date": "2026-04-06", "process_date": "2026-04-06"}),
            ("unit_split", {"old_symbol": "S004", "new_symbol": "S004U", "alternate_symbol": "ALT", "old_rate": 1, "new_rate": 1.1, "effective_date": "2026-05-04", "process_date": "2026-05-04"}),
            ("stock_dividend", {"symbol": "S005", "rate": 0.05, "ex_date": "2026-06-01"}), ("name_change", {"old_symbol": "S006", "new_symbol": "S006N", "process_date": "2026-07-01"}),
            ("spin_off", {"source_symbol": "S007", "new_symbol": "S007X", "source_rate": 1, "new_rate": 0.25, "ex_date": "2026-08-03", "process_date": "2026-08-03"}), ("cash_dividend", dict(repeat))]       # an exact repeat
    want = ("type,symbol,old_symbol,new_symbol,ex_date,process_date,record_date,payable_date,rate,new_rate,old_rate,cash,special\n"
            "cash_dividend,S001,,,2026-02-09,2026-02-15,2026-02-10,2026-02-15,0.24,,,,False\n"
            "forward_split,S002,,,2026-03-02,2026-03-02,2026-02-27,2026-02-27,,2,1,,\n"
            "name_change,,S006,S006N,,2026-07-01,,,,,,,\n"
            "reverse_split,S003,,,2026-04-06,2026-04-06,,,,1,8,,\n"
            "spin_off,S007,,S007X,2026-08-03,2026-08-03,,,,0.25,1,,\n"
            "stock_dividend,S005,,,2026-06-01,,,,0.05,,,,\n"
            "unit_split,,S004,S004U,2026-05-04,2026-05-04,,,,1.1,1,,\n")
    w = World(["S001", "S002", "S003"], records=recs)
    try:
        w.ca.bad = ["S003"]
        code, out, err = w.run()
        assert code == 0, out
        f = os.path.join(w.root, "2026-10-30")
        with open(os.path.join(f, F_CA), "rb") as fh:
            raw = fh.read()
        assert raw.decode() == want and b"\r" not in raw, "the flat CSV is r16's: CA_COLS header, the rows sorted, exact repeats dropped, LF; a spin-off's source_symbol is `symbol`, a unit split's effective_date is `ex_date`"
        with open(os.path.join(f, F_CA_RAW), encoding="utf-8") as fh:
            lines = [json.loads(ln) for ln in fh.read().splitlines()]
        assert [ln["i"] for ln in lines] == [0] and all(set(ln) == {"i", "round", "params", "page"} and ln["round"] == 1 for ln in lines)
        assert lines[0]["params"] == {"symbols": "S001,S002,S003", "types": ",".join(X16.CA_TYPES), "start": "2025-08-26", "end": "2026-10-30", "limit": 1000} and "page_token" not in lines[0]["params"]
        assert sorted(lines[0]["page"]["corporate_actions"]) == ["cash_dividends", "forward_splits", "name_changes", "reverse_splits", "spin_offs", "stock_dividends", "unit_splits"]
        m = man_of(f)
        c = m["calendar"]
        assert c["rows"] == 7 == m["rows"] and c["records"] == 8 and c["duplicates_dropped"] == 1 and c["requests"] == 1 and c["pages"] == 1 and c["rejected_symbols"] == ["S003"]
        assert c["rows_by_type"] == {"cash_dividend": 1, "forward_split": 1, "name_change": 1, "reverse_split": 1, "spin_off": 1, "stock_dividend": 1, "unit_split": 1}
        assert c["rows_by_type_year"] == {t: {"2026": 1} for t in c["rows_by_type"]}
        assert c["name_change_names_not_asked"] == ["S006", "S006N"] and c["types"] == list(X16.CA_TYPES) and c["endpoint"] == X16.CA_URL and c["batch"] == 50 and c["limit"] == 1000
        assert c["fields_not_flattened"] == {"alternate_symbol": 1, "cusip": 2, "foreign": 2} and c["unknown_types"] == {} and c["unknown_top_keys"] == {}
        assert_no_secrets(w, out, err)
    finally:
        w.clean()
    names = [f"S{k:03d}" for k in range(120)]
    seen = []

    def fake_get(url, params, key, secret):                                    # r5_siporb._get, faked: the assets list, and the calendar's pages (a second page for the first batch)
        seen.append((url, dict(params), key, secret))
        if url == S.ASSETS_URL:
            return [asset(s) for s in names[:100]] + [asset("NEWA", "Newa Inc", "NYSE")]                  # the last 20 of the 120 base names are not active
        first, second = params["symbols"].split(",")[0], "page_token" in params
        return {"corporate_actions": {"cash_dividends": [{"symbol": first, "rate": 0.2 if second else 0.1, "ex_date": "2026-05-01"}]}, "next_page_token": "p2" if first == "NEWA" and not second else None}
    w = World(names)
    try:
        code, out, err = w.run(transport=fake_get)
        assert code == 0, out
        assets_calls, ca_calls = [c for c in seen if c[0] == S.ASSETS_URL], [c for c in seen if c[0] == X16.CA_URL]
        assert len(assets_calls) == 1 and assets_calls[0][1] == {"status": "active", "asset_class": "us_equity"} and assets_calls[0][2:] == w.keys and len(seen) == 5
        assert len([c for c in ca_calls if "page_token" not in c[1]]) == 3 and len(ca_calls) == 4, "101 symbols (100 active base names + one new listing; the other 20 are inactive) = batches of 50, 50 and 1, plus the first batch's second page"
        assert all(c[1]["types"] == ",".join(X16.CA_TYPES) and c[1]["start"] == "2025-08-26" and c[1]["end"] == "2026-10-30" and c[1]["limit"] == 1000 and len(c[1]["symbols"].split(",")) <= 50 and c[2:] == w.keys for c in ca_calls)
        assert ca_calls[1][1]["page_token"] == "p2" and ca_calls[1][1]["symbols"] == ca_calls[0][1]["symbols"]
        m = man_of(os.path.join(w.root, "2026-10-30"))
        assert m["new_symbols"] == ["NEWA"] and m["symbols"]["requested"] == 101 and (m["calendar"]["requests"], m["calendar"]["pages"], m["calendar"]["rows"]) == (4, 4, 4)
        assert m["symbols"]["base_active"] == 100 and m["base_dropped_inactive"] == {"count": 20, "first_20": names[100:]}
        assert w.vendor.calls and len({x["sym"] for x in w.vendor.calls}) == 101 and not ({x["sym"] for x in w.vendor.calls} & set(names[100:])), "the new listing is pulled like the base names; the inactive base names are not"
        assert_no_secrets(w, out, err)
    finally:
        w.clean()


def t_new_listings_run():
    names = [f"B{k:02d}" for k in range(1, 6)]
    rows = [asset(s) for s in names[:3]] + [asset("NEWA", "Newa Holdings Inc", "NYSE"), asset("NEWB", "Newb Technologies Corp", "NASDAQ"), asset("OTCX", "Otc Corp", "OTC"), asset("SPYX", "Example S&P 500 ETF Trust", "ARCA"), asset("INAC", status="inactive")]
    w = World(names, assets=rows)
    try:
        code, out, err = w.run()
        assert code == 0, out
        f = os.path.join(w.root, "2026-10-30")
        m = man_of(f)
        assert m["new_symbols"] == ["NEWA", "NEWB"] and (m["symbols"]["base"], m["symbols"]["new"], m["symbols"]["requested"], m["base_list"]["count"]) == (5, 2, 5, 5)
        assert m["symbols"] == sym_counts(5, base_active=3, base_inactive=2, base_dropped_inactive=2, new=2, requested=5, with_bars=5), m["symbols"]
        assert m["base_dropped_inactive"] == {"count": 2, "first_20": ["B04", "B05"]} and m["hold"] == {"file": None, "count": 0, "inactive_count": 0, "inactive": []}
        assert m["assets"] == {"assets_rows": 8, "excluded_by_reason": {"already_in_base_list": 3, "exchange": 1, "name:etf": 1, "not_active": 1}, "new": 2}, m["assets"]
        with open(os.path.join(f, F_SYMS)) as fh:
            assert fh.read() == "B01\nB02\nB03\nNEWA\nNEWB\n", "B04 and B05 are not in the assets endpoint's active set: not requested"
        want = ["B01", "B02", "B03", "NEWA", "NEWB"]
        assert sorted({x["sym"] for x in w.vendor.calls}) == want and len(w.vendor.calls) == 10, "the new listings are pulled in both adjustments like the active base names; the inactive ones are not asked for"
        assert m["base_list"]["sha256"] == w.base_sha == m["base_list"]["registered_sha256"] and m["base_list"]["sha_ok"] is True
        assert m["calendar"]["requests"] == 1 and w.ca.calls[0]["symbols"] == want
    finally:
        w.clean()
    for bad in ([], None, "x", {"message": "forbidden"}):                                                  # no usable asset list = the new listings cannot be told = no photograph
        w = World(names)
        try:
            code, out, err = w.run(fetch_assets=lambda key, secret, _b=bad: _b)
            assert code == 2 and last_line(out) == "refused: the assets call returned no list of assets, so the active names and the new listings cannot be told (nothing published)" and w.folders() == [], out
            assert w.vendor.calls == [], "no bars were pulled before the assets were known"
        finally:
            w.clean()


def t_symbols():
    """THE SYMBOL RULE through the whole command: requested = (base list AND active) + new listings + every hold name. An inactive base name is not requested, an inactive hold name IS (its bars up to the delisting are kept); the counts, the manifest and
    the console report; the 2% rule counts the requested set only; the active-share floor"""
    base = [f"T{k:03d}" for k in range(100)]
    live = base[:60]                                                      # T000..T059 are active; the other 40 are not (T061 is even listed as inactive)
    rows = [asset(s) for s in live] + [asset("T061", status="inactive"), asset("NEWA", "Newa Holdings Inc", "NYSE"), asset("NEWB", "Newb Technologies Corp", "NASDAQ"), asset("SPYX", "Example S&P 500 ETF Trust", "ARCA")]
    hold = ["T005", "T070", "ZOLD", "NEWA", "T010"]                         # active base, INACTIVE base, INACTIVE and outside the base list, a new listing, active base
    gone = {"T070": {"until": "2026-10-14"}, "ZOLD": {"until": "2026-09-30"}}      # both were delisted inside the window: bars up to the delisting date, none after
    want = sorted(live + ["NEWA", "NEWB", "T070", "ZOLD"])
    dropped = [s for s in base[60:] if s != "T070"]                         # T060..T099 less the held T070
    assert len(want) == 64 and len(dropped) == 39
    w = World(base, assets=rows, special=gone)
    try:
        code, out, err = w.run(hold=hold)
        assert code == 0 and last_line(out).startswith("published: "), out
        called = {x["sym"] for x in w.vendor.calls}
        assert called == set(want) and len(w.vendor.calls) == 2 * 64 and not (called & set(dropped)), "a dropped name is never asked for; an inactive hold name is, in both adjustments"
        assert sorted(x["adjustment"] for x in w.vendor.calls if x["sym"] in ("T070", "ZOLD")) == ["raw", "raw", "split", "split"]
        f = os.path.join(w.root, "2026-10-30")
        m = man_of(f)
        assert m["symbols"] == {"base": 100, "base_active": 60, "base_inactive": 40, "base_dropped_inactive": 39, "hold": 5, "hold_inactive": 2, "hold_added": 2, "new": 2, "requested": 64, "with_bars": 64, "one_sided": 0, "empty": 0,
                                "errors": 0, "error_limit_pct": 2, "error_limit_of": "the requested symbols only"}, m["symbols"]
        assert len(want) == m["symbols"]["base_active"] + m["symbols"]["new"] + m["symbols"]["hold_added"], "requested = active base + new + the hold names nobody else requests"
        assert m["base_dropped_inactive"] == {"count": 39, "first_20": dropped[:20]} and dropped[:11] == [f"T{k:03d}" for k in range(60, 70)] + ["T071"] and len(m["base_dropped_inactive"]["first_20"]) == 20
        assert m["hold"]["inactive"] == ["T070", "ZOLD"] and m["hold"]["inactive_count"] == 2 and m["hold"]["count"] == 5
        hf = m["hold"]["file"]
        assert hf == {"path": os.path.join(w.dir, "hold.txt"), "sha256": sha_file(os.path.join(w.dir, "hold.txt")), "count": 5, "first": "T005", "last": "T010"}, hf
        assert m["symbol_rule"].startswith("requested = (base list AND the assets endpoint's active set) + the new active listings + every hold name")
        assert m["command"]["argv"] == ["pull", "--through", "2026-10-30", "--out", w.root, "--hold", hf["path"]], m["command"]["argv"]
        with open(os.path.join(f, F_SYMS)) as fh:
            assert fh.read().split() == want, "symbols.txt = the requested set: every dropped name is absent, every inactive hold name is there"
        assert set(base) - set(want) == set(dropped), "the dropped names = the base list minus symbols.txt (the manifest's own definition)"
        assert len(w.ca.calls) == 1 and w.ca.calls[0]["symbols"] == want and w.assets.calls == [w.keys], "the calendar covers the requested set; one assets call"
        raw = pd.read_parquet(os.path.join(f, F_RAW))
        days = pd.bdate_range("2025-08-26", "2026-10-30")
        for sym, last in (("T070", "2026-10-14"), ("ZOLD", "2026-09-30")):
            mine = raw[raw["symbol"] == sym]
            assert len(mine) == int((days <= pd.Timestamp(last)).sum()) and mine["date"].max() == pd.Timestamp(last), f"{sym}: delisted mid-hold, its bars up to {last} are in the photograph"
        assert not (set(raw["symbol"]) & set(dropped)) and set(raw["symbol"]) == set(want)
        for frag in ("  assets: 64 rows read, 63 symbols active; new listings added to the base list: 2 (left out: already_in_base_list 61, name:etf 1)",
                     f"  active filter: 60 of 100 base names are active; 39 dropped as inactive, not requested (first 20: {', '.join(dropped[:20])})",
                     "  hold list: 5 names, pulled always; 2 not active now: T070, ZOLD; 2 of them are requested only because they are held",
                     "  requested: 64 symbols = 60 active base + 2 new listings + 2 hold names not otherwise included", "  bars: 64 symbols x raw + split"):
            assert frag in out, (frag, out)
        assert dropped[20] not in out.split("first 20:")[1].split("\n")[0], "the console names the first 20 only"
        assert_no_secrets(w, out, err)
    finally:
        w.clean()
    w = World(base, assets=rows)                                            # the same universe without a hold list: the other 38 inactive names and T070 are all dropped
    try:
        code, out, err = w.run()
        assert code == 0, out
        f = os.path.join(w.root, "2026-10-30")
        m = man_of(f)
        assert m["symbols"] == sym_counts(100, base_active=60, base_inactive=40, base_dropped_inactive=40, new=2, requested=62, with_bars=62), m["symbols"]
        assert m["hold"] == {"file": None, "count": 0, "inactive_count": 0, "inactive": []} and m["base_dropped_inactive"] == {"count": 40, "first_20": base[60:80]}, (m["hold"], m["base_dropped_inactive"])
        assert "hold list:" not in out and m["command"]["argv"] == ["pull", "--through", "2026-10-30", "--out", w.root] and "  requested: 62 symbols = 60 active base + 2 new listings + 0 hold names not otherwise included" in out
        assert {x["sym"] for x in w.vendor.calls} == set(live + ["NEWA", "NEWB"]) and len(w.vendor.calls) == 124
    finally:
        w.clean()
    # the 2% error rule counts the REQUESTED set (62 here), not the base list (100): 1 error = 1.6% passes; 2 = 3.2% refuses - on the base list it would be 2.0% and pass
    for n_err, ok in ((1, True), (2, False)):
        w = World(base, assets=rows, special={live[3 + 10 * k]: {"fail": {"raw": "always"}} for k in range(n_err)})
        try:
            code, out, err = w.run()
            assert (code == 0) == ok and last_line(out).startswith("published: " if ok else "refused: "), (n_err, out)
            if ok:
                m = man_of(os.path.join(w.root, "2026-10-30"))
                assert m["symbols"]["errors"] == 1 and m["symbols"]["requested"] == 62 and m["symbols"]["with_bars"] == 61 and [e["symbol"] for e in m["errors"]] == ["T003"]
            else:
                assert last_line(out).startswith("refused: 2 of 62 symbols errored after a retry (3.2%, more than the 2% limit); the pull stopped at symbol 16 - first error: T003 raw RuntimeError: HTTP 500: planted failure") and w.folders() == [] and w.ca.calls == [], out
        finally:
            w.clean()
    # an inactive hold name that errors counts like any other requested symbol, and is named in the manifest: 1 of 63 = 1.6% passes, 2 of 64 = 3.1% refuses
    w = World(base, assets=rows, special={"T070": {"fail": {"raw": "always"}}})
    try:
        code, out, err = w.run(hold=["T070"])
        assert code == 0, out
        m = man_of(os.path.join(w.root, "2026-10-30"))
        assert m["symbols"]["requested"] == 63 and m["symbols"]["errors"] == 1 and m["symbols"]["hold_inactive"] == 1 and [(e["symbol"], e["adjustment"]) for e in m["errors"]] == [("T070", "raw")] and m["hold"]["inactive"] == ["T070"]
        assert "T070" not in set(pd.read_parquet(os.path.join(w.root, "2026-10-30", F_RAW))["symbol"]), "an errored hold name contributes no rows"
    finally:
        w.clean()
    w = World(base, assets=rows, special={"T070": {"fail": {"raw": "always"}}, "T071": {"fail": {"raw": "always"}}})
    try:
        code, out, err = w.run(hold=["T070", "T071"])
        assert code == 2 and last_line(out).startswith("refused: 2 of 64 symbols errored after a retry (3.1%, more than the 2% limit); the pull stopped at symbol 64 - first error: T070 raw") and w.folders() == [], out
    finally:
        w.clean()
    # the active-share floor: a wrong or cut-short asset list must not silently take the base list out of the photograph; hold names do not count towards it; ACTIVE_MIN_PCT = 0 switches it off
    cases = (("20% active", [asset(s) for s in base[:20]], None, 20, False), ("24% active", [asset(s) for s in base[:24]], None, 24, False), ("exactly 25% active", [asset(s) for s in base[:25]], None, 25, True),
             ("20% active, 20 inactive names held", [asset(s) for s in base[:20]], base[20:40], 20, False), ("no usable active record", ["garbage", {"symbol": "T000"}], None, 0, False))
    for label, rows_, hold_, kept, ok in cases:
        w = World(base, assets=rows_)
        try:
            code, out, err = w.run(hold=hold_)
            assert (code == 0) == ok, (label, out)
            if not ok:
                assert last_line(out) == (f"refused: only {kept} of the 100 base names ({kept:.1f}%) are in the assets endpoint's active set, below the 25% floor: the asset list looks wrong or cut short, and the photograph would lose the rest "
                                          "(nothing published)") and w.vendor.calls == [] and w.folders() == [] and w.ca.calls == [], (label, out)
        finally:
            w.clean()
    w = World(base, assets=[asset(s) for s in base[:5]])
    try:
        code, out, _ = w.run(ACTIVE_MIN_PCT=0)
        assert code == 0 and man_of(os.path.join(w.root, "2026-10-30"))["symbols"]["requested"] == 5, out
    finally:
        w.clean()
    assert names_text(["A", "B", "C"], 2) == "A, B ... (1 more in the manifest)" and names_text(["A", "B"], 2) == "A, B" and names_text([], 2) == ""


def t_clock():
    """the same-evening rule [P1]: --through is accepted before today's New York date, or today with the New York clock at or after 20:00 - both sides of 20:00 with a faked clock, through validate_through, the whole command and the real clock's shape"""
    me = sys.modules[__name__]
    mon = dt.date(2026, 11, 2)

    def at(h, m=0, s=0, us=0):
        return dt.datetime(2026, 11, 2, h, m, s, us)                                 # Monday 2026-11-02, New York wall clock
    for now, ok in ((at(0), False), (at(9, 30), False), (at(16, 0), False), (at(19, 0), False), (at(19, 59), False), (at(19, 59, 59, 999999), False), (at(20), True), (at(20, 0, 0, 1), True), (at(20, 1), True), (at(23, 59, 59, 999999), True)):
        with patched(me, now_et=lambda now=now: now):
            if ok:
                assert validate_through("2026-11-02") == mon, now
                assert pull_gate(mon, now) is None
            else:
                msg = refuses(lambda: validate_through("2026-11-02"), f"is today in New York and the clock there reads {now:%H:%M}: a same-day pull is accepted from 20:00 New York time, when the session's data is complete")
                assert msg.startswith("refused: --through 2026-11-02 ") and msg.endswith("(nothing pulled)") and pull_gate(mon, now) is not None, msg
            assert validate_through("2026-11-02", future_ok=True) == mon, "plan takes any hour"
            assert validate_through("2026-10-30") == dt.date(2026, 10, 30), "a past session is accepted at every hour"
    with patched(me, now_et=lambda: dt.datetime(2026, 11, 3, 0, 0)):                 # the date rolled over: Monday's session is simply in the past; Tuesday is today before 20:00
        assert validate_through("2026-11-02") == mon
        refuses(lambda: validate_through("2026-11-03"), "is today in New York and the clock there reads 00:00")
    for h in (0, 12, 19, 20, 23):                                                    # the future is refused at every hour, 20:00 included
        with patched(me, now_et=lambda h=h: at(h, 59)):
            refuses(lambda: validate_through("2026-11-03"), "is in the future (today is 2026-11-02 in New York): its session has not happened")
            refuses(lambda: validate_through("2027-01-04"), "is in the future")
    with patched(me, now_et=lambda: dt.datetime(2026, 11, 26, 21, 0)):               # Thanksgiving evening: after 20:00 and still no session
        refuses(lambda: validate_through("2026-11-26"), "NYSE holiday (Thanksgiving Day)")
    with patched(me, now_et=lambda: dt.datetime(2026, 10, 31, 21, 0)):               # a Saturday evening
        refuses(lambda: validate_through("2026-10-31"), "Saturday")
    assert pull_gate(dt.date(2026, 10, 30), at(0)) is None and "is in the future" in pull_gate(dt.date(2026, 11, 3), at(23, 59))
    # the whole command: a pull of the Monday itself, a minute before and at 20:00 (a Monday that is the month's last session, say)
    names = [f"B{k:02d}" for k in range(1, 5)]
    w = World(names, through="2026-11-02", now=at(19, 59))
    try:
        code, out, err = w.run()
        assert code == 2 and last_line(out) == ("refused: --through 2026-11-02 is today in New York and the clock there reads 19:59: a same-day pull is accepted from 20:00 New York time, when the session's data is complete (nothing pulled)"), out
        assert w.vendor.calls == [] and w.assets.calls == [] and not os.path.exists(w.root), "refused before the base list, the key and the first request"
        w.now = at(20, 0)
        code, out, err = w.run()
        assert code == 0 and last_line(out) == f"published: the RESMOM forward photograph through 2026-11-02 (revision 1) is on file at {os.path.join(w.root, '2026-11-02')}", out
        m = man_of(os.path.join(w.root, "2026-11-02"))
        assert (m["through"], m["end"], m["start"]) == ("2026-11-02", "2026-11-02", "2025-08-29") and m["window"]["sessions_in_data"]["last"] == "2026-11-02"
        w.now = at(23, 59, 59)
        code, out, err = w.run()
        assert code == 0 and w.folders() == ["2026-11-02", "2026-11-02_r2"], out
        w.now = dt.datetime(2026, 11, 3, 0, 0)
        code, out, err = w.run()
        assert code == 0 and w.folders() == ["2026-11-02", "2026-11-02_r2", "2026-11-02_r3"], out
        w.now = at(9, 0)
        code, out, err = w.run(through="2026-11-03")
        assert code == 2 and "is in the future" in last_line(out) and w.folders() == ["2026-11-02", "2026-11-02_r2", "2026-11-02_r3"]
        assert_no_secrets(w, out, err)
    finally:
        w.clean()
    # the real clock: a naive datetime on New York wall time (4 or 5 hours behind UTC, whichever applies today) - no network, the machine's own clock
    lo = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    real = now_et()
    hi = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    assert isinstance(real, dt.datetime) and real.tzinfo is None
    assert any(abs((lo - real).total_seconds() - h * 3600) < 5 and abs((hi - real).total_seconds() - h * 3600) < 5 for h in (4, 5)), (lo, real, hi)


def t_outputs():
    """every manifest sha against its file, exactly the registered file set, the manifest's fields, the parquet files in the SIPORB cache's own schema, naive dates, one row per symbol-session; the _r2 / _r3 rule; a rename race"""
    names = [f"B{k:02d}" for k in range(1, 9)]
    w = World(names, special={"B03": {"empty": True}}, records=CROSS_RECORDS[:3])
    try:
        code, out, err = w.run()
        assert code == 0 and w.folders() == ["2026-10-30"], out
        f = os.path.join(w.root, "2026-10-30")
        m = man_of(f)
        assert sorted(os.listdir(f)) == sorted(list(OUTPUT_FILES) + [F_MAN]) and not [x for x in os.listdir(f) if ".part" in x or x.startswith("_tmp")]
        assert set(m["sha256"]) == set(OUTPUT_FILES) and all(sha_file(os.path.join(f, nm)) == sh for nm, sh in m["sha256"].items()), "every manifest sha matches its file"
        assert len([k for k in m["sha256"] if k.lower().endswith(".csv")]) == 1, "exactly one .csv key: the harness's wide_load reads a calendar manifest's csv sha that way"
        assert (m["through"], m["start"], m["end"], m["folder"], m["revision"]) == ("2026-10-30", "2025-08-26", "2026-10-30", "2026-10-30", 1) and m["window"]["calendar_days"] == 430 and m["window"]["sessions_in_data"]["sessions"] == 309
        assert m["created"][:2] == "20" and m["created_utc"].endswith("Z") and m["rows"] == m["calendar"]["rows"] == 3
        assert m["symbols"] == sym_counts(8, with_bars=7, empty=1)
        me = os.path.abspath(__file__)
        assert m["command"]["sha256"] == sha_file(me) and m["command"]["sha256_lf"] == sha_lf(me) and m["command"]["file"] == "r17_resmom_pull.py" and m["command"]["argv"] == ["pull", "--through", "2026-10-30", "--out", w.root]
        assert m["provenance"]["manifest_path"] == os.path.join(w.dir, "home", "state", "alpaca_pulls.jsonl") and (m["provenance"]["requested_start"], m["provenance"]["requested_end"]) == ("2025-08-26T00:00:00Z", "2026-10-30T23:59:59Z")
        assert m["versions"]["pyarrow"] and m["requests"]["total"] == 1 + 8 * 2 + 1 and m["bars"]["rows_raw"] == 7 * 309 == m["bars"]["rows_split"]
        import pyarrow.parquet as pq
        for nm in (F_RAW, F_SPLIT):
            t = pq.read_table(os.path.join(f, nm))
            assert t.schema.equals(parquet_schema()), t.schema
            df = t.to_pandas()
            assert not df.duplicated(["symbol", "date"]).any() and df["date"].dt.tz is None and df.equals(df.sort_values(["symbol", "date"], ignore_index=True)) and len(df) == 7 * 309
            assert set(df["symbol"]) == set(names) - {"B03"} and df["v"].dtype == "int64"
        a, b = pd.read_parquet(os.path.join(f, F_RAW)), pd.read_parquet(os.path.join(f, F_SPLIT))
        assert (a["date"] == b["date"]).all() and (a["symbol"] == b["symbol"]).all() and a["c"].equals(b["c"]), "no split planted: raw == split"
        first = a[a["symbol"] == "B01"].iloc[0]
        assert str(first["date"].date()) == "2025-08-26" and abs(first["c"] - (40.0 + zlib.crc32(b"B01") % 50)) < 1e-9
        # a second photograph of the same data is a NEW folder, the data files are byte for byte the same, the first is untouched
        code2, out2, _ = w.run()
        assert code2 == 0 and w.folders() == ["2026-10-30", "2026-10-30_r2"], w.folders()
        m2 = man_of(os.path.join(w.root, "2026-10-30_r2"))
        assert m2["folder"] == "2026-10-30_r2" and m2["revision"] == 2 and m2["sha256"] == m["sha256"] and last_line(out2).startswith("published: ") and "(revision 2)" in last_line(out2)
        code3, out3, _ = w.run()
        assert code3 == 0 and w.folders() == ["2026-10-30", "2026-10-30_r2", "2026-10-30_r3"] and man_of(os.path.join(w.root, "2026-10-30_r3"))["revision"] == 3
        assert man_of(f) == m and all(sha_file(os.path.join(f, nm)) == sh for nm, sh in m["sha256"].items()), "the first photograph is untouched by the re-pulls"
        real = rename_with_retry

        def racing(src, dst):                                                      # a concurrent pull publishes this name between our manifest and our rename
            if os.path.basename(dst) == "2026-10-30_r4":
                os.makedirs(os.path.join(dst, "x"))
            real(src, dst)
        code4, out4, _ = w.run(rename_with_retry=racing)
        assert code4 == 0 and w.folders() == ["2026-10-30", "2026-10-30_r2", "2026-10-30_r3", "2026-10-30_r4", "2026-10-30_r5"], w.folders()
        m5 = man_of(os.path.join(w.root, "2026-10-30_r5"))
        assert (m5["revision"], m5["folder"]) == (5, "2026-10-30_r5") and os.listdir(os.path.join(w.root, "2026-10-30_r4")) == ["x"] and "(revision 5)" in last_line(out4)
        assert_no_secrets(w, out, out2, out3, out4)
    finally:
        w.clean()


def t_publish_details():
    """ROOT defaults to the module's default when --out is not given; the directory rename is retried on PermissionError and gives up after RENAME_TRIES; a name taken by a FILE is skipped too"""
    me = sys.modules[__name__]
    w = World([f"B{k:02d}" for k in range(1, 4)])
    try:
        code, out, _ = w.run(no_out=True)
        assert code == 0 and w.folders() == ["2026-10-30"] and man_of(os.path.join(w.root, "2026-10-30"))["command"]["argv"] == ["pull", "--through", "2026-10-30"], out
        assert ROOT_DEFAULT == r"C:\EdgeLog\alpaca_cache\resmom_fwd" and not os.path.exists(ROOT_DEFAULT), "the real default root was not touched"
        with open(os.path.join(w.root, "2026-10-30_r2"), "w") as fh:                       # a stray FILE holds the _r2 name: the next free name is used, the file is left alone
            fh.write("not a folder")
        code, out, _ = w.run(no_out=True)
        assert code == 0 and w.folders() == ["2026-10-30", "2026-10-30_r2", "2026-10-30_r3"] and os.path.isfile(os.path.join(w.root, "2026-10-30_r2")), w.folders()
    finally:
        w.clean()
    d = tempfile.mkdtemp()
    try:
        src, dst, real, n = os.path.join(d, "a"), os.path.join(d, "b"), os.rename, {"k": 0}
        os.makedirs(src)

        def flaky(s, t):
            n["k"] += 1
            if n["k"] <= 2:
                raise PermissionError("locked by a scanner (planted)")
            return real(s, t)
        with patched(me, RENAME_WAIT=0.0), patched(os, rename=flaky):
            rename_with_retry(src, dst)
        assert n["k"] == 3 and os.path.isdir(dst) and not os.path.exists(src), "two PermissionErrors, then it went through"
        n["k"] = 0
        os.makedirs(src)

        def stuck(s, t):
            n["k"] += 1
            raise PermissionError("locked (planted)")
        with patched(me, RENAME_WAIT=0.0), patched(os, rename=stuck):
            try:
                rename_with_retry(src, os.path.join(d, "c"))
            except PermissionError:
                pass
            else:
                raise AssertionError("a lock that never lets go must surface")
        assert n["k"] == RENAME_TRIES and os.path.isdir(src) and not os.path.exists(os.path.join(d, "c"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_read_back():
    """the pull reads BOTH parquet files back the way the harness reads them (a filtered read of `date`, the symbol as a dictionary) BEFORE the rename, against the rows written; and the check itself refuses a short file and a wrong date type"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    names = [f"B{k:02d}" for k in range(1, 5)]
    w, reads, real = World(names), [], read_back
    try:
        code, out, _ = w.run(read_back=lambda p, rows, thr: (reads.append((os.path.basename(p), rows, thr)), real(p, rows, thr))[1])
        assert code == 0 and reads == [(F_RAW, 4 * 309, "2026-10-30"), (F_SPLIT, 4 * 309, "2026-10-30")], (reads, out)
    finally:
        w.clean()
    d = tempfile.mkdtemp()
    try:
        df = to_daily("AAA", Vendor("2026-10-30").frame("AAA", "raw"))
        p = os.path.join(d, "ok.parquet")
        write_parquet(df, p)
        read_back(p, len(df), "2026-10-30")
        refuses(lambda: read_back(p, len(df) + 1, "2026-10-30"), "does not read back as written")
        refuses(lambda: read_back(p, len(df), "2026-03-01"), "does not read back as written")                  # a date column that holds days after --through is not what was written for this month-end
        bad = os.path.join(d, "tz.parquet")
        pq.write_table(pa.Table.from_pandas(df.assign(date=df["date"].dt.tz_localize("UTC")), preserve_index=False), bad)
        try:
            read_back(bad, len(df), "2026-10-30")
        except (Refused, pa.ArrowException):
            pass
        else:
            raise AssertionError("a tz-aware date column must not pass the read-back")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_atomic():
    """an exception at any point leaves no ROOT\\<through> and no half folder; a leftover _tmp_ of a killed run is counted, never touched; a refusal before the first request creates nothing at all"""
    names = [f"B{k:02d}" for k in range(1, 7)]
    me = sys.modules[__name__]
    base_write, seen = write_parquet, {"n": 0}

    def write_then_die(df, path):
        seen["n"] += 1
        if seen["n"] == 2:
            raise OSError("disk full (planted)")
        return base_write(df, path)
    cases = (("the calendar fetch raises mid-way", {"ca_fetch": FakeCA(boom=RuntimeError("calendar exploded (planted)"))}, "failed: RuntimeError: calendar exploded (planted) (nothing published)"),
             ("the second parquet file cannot be written", {"write_parquet": write_then_die}, "failed: OSError: disk full (planted) (nothing published)"),
             ("the final rename fails", {"rename_with_retry": raiser(PermissionError("access denied (planted)"))}, "failed: PermissionError: access denied (planted) (nothing published)"),
             ("the read-back finds a bad file", {"read_back": lambda p, rows, thr: refuse("refused: planted read-back failure (nothing published)")}, "refused: planted read-back failure (nothing published)"),
             ("the run is interrupted inside a bars call", {"fetch_bars": raiser(KeyboardInterrupt())}, "failed: interrupted (nothing published)"),
             ("a house helper stops the run (SystemExit)", {"ca_fetch": FakeCA(boom=SystemExit("AUTH FAILED (401) planted"))}, "refused: a house helper stopped the run: AUTH FAILED (401) planted (nothing published)"))
    for label, over, want in cases:
        seen["n"] = 0
        w = World(names)
        try:
            leftover = os.path.join(w.root, "_tmp_2025-01-01_999")                           # an earlier killed run's folder
            os.makedirs(leftover)
            code, out, err = w.run(**over)
            assert code == 2 and last_line(out) == want, (label, out)
            assert w.folders() == ["_tmp_2025-01-01_999"], (label, w.folders())
            assert os.path.isdir(leftover) and "1 leftover _tmp_ folder(s)" in out, "a killed run's leftover is reported and left alone"
            assert_no_secrets(w, out, err)
        finally:
            w.clean()
    for label, over, frag in (("keys: nothing", {"load_keys": lambda: (None, None)}, "no Alpaca key found"), ("keys: empty strings", {"load_keys": lambda: ("", "")}, "no Alpaca key found"),
                              ("keys: key only", {"load_keys": lambda: (FAKE_KEY, None)}, "no Alpaca key found"), ("keys: secret only", {"load_keys": lambda: (None, FAKE_SECRET)}, "no Alpaca key found"),
                              ("base list sha differs", {"BASE_LIST_SHA": "f" * 64}, "has sha256"), ("pyarrow missing", {"have_pyarrow": lambda: False}, "pyarrow is not installed")):
        w = World(names)
        try:
            code, out, err = w.run(**over)
            assert code == 2 and last_line(out).startswith("refused: ") and frag in last_line(out) and last_line(out).endswith("(nothing pulled)"), (label, out)
            assert w.vendor.calls == [] and w.assets.calls == [] and w.ca.calls == [] and not os.path.exists(w.root), (label, "refused before the first request and before any folder")
            assert_no_secrets(w, out, err)
        finally:
            w.clean()
    for label, body, frag in (("hold list missing", None, "is not on file"), ("hold list empty", b"# nobody\n", "holds no symbol"), ("hold list malformed", b"AAPL\nA B\n", "line 2")):
        w = World(names)
        try:
            hp = os.path.join(w.dir, "h.txt")
            if body is not None:
                with open(hp, "wb") as fh:
                    fh.write(body)
            code, out, err = w.run(hold_path=hp, load_keys=raiser(AssertionError("the hold list was checked after the key lookup")))
            assert code == 2 and last_line(out).startswith("refused: ") and frag in last_line(out) and last_line(out).endswith("(nothing pulled)"), (label, out)
            assert w.vendor.calls == [] and w.assets.calls == [] and w.ca.calls == [] and not os.path.exists(w.root), (label, "refused before the key lookup, the first request and any folder")
        finally:
            w.clean()
    for label, through, frag in (("a weekend", "2026-10-31", "Saturday"), ("today, before 20:00", "2026-11-02", "is today in New York and the clock there reads 12:00"), ("the future", "2026-11-03", "is in the future"), ("a holiday", "2026-09-07", "NYSE holiday"),
                                 ("not a date", "soon", "not a date written YYYY-MM-DD")):
        w = World(names)
        try:
            code, out, err = w.run(through=through)
            assert code == 2 and frag in last_line(out) and last_line(out).endswith("(nothing pulled)") and w.vendor.calls == [] and not os.path.exists(w.root), (label, out)
        finally:
            w.clean()
    assert me.__dict__["write_parquet"] is base_write and not _SECRETS


def t_exit_codes():
    names = [f"B{k:02d}" for k in range(1, 5)]
    w = World(names)
    try:
        for argv, frag in (([], "refused: no such command"), (["frobnicate"], "refused: no such command"), (["pull"], "--through is required"), (["plan", "--through", "2026-10-30", "--force"], "unknown argument")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), patched(sys.modules[__name__], BASE_LIST_PATH=w.base_path, BASE_LIST_SHA=w.base_sha):
                assert main(argv) == 2, argv
            assert frag in last_line(out.getvalue()) and last_line(out.getvalue()).endswith("(nothing pulled)"), (argv, out.getvalue())
        code, out, _ = w.run()
        assert code == 0 and last_line(out) == f"published: the RESMOM forward photograph through 2026-10-30 (revision 1) is on file at {os.path.join(w.root, '2026-10-30')}", last_line(out)
        for over in ({"load_keys": lambda: (None, None)}, {"ca_fetch": FakeCA(boom=ValueError("x"))}, {"ca_fetch": FakeCA(boom=SystemExit("AUTH FAILED (401) planted"))}):
            code, out, _ = w.run(through="2026-10-29", **over)
            assert code == 2 and last_line(out).split(":")[0] in ("refused", "failed") and last_line(out).endswith(("(nothing pulled)", "(nothing published)")), out
            assert w.folders() == ["2026-10-30"], "nothing published under that date"
    finally:
        w.clean()


def t_plan():
    """plan: NO network, NO key (a load_keys that raises is planted, and the tripwire guards the real one), any weekday - a future one included - the window, the base list's count and sha check, the hold list, the estimate (an UPPER BOUND: the active
    filter cuts it), the earliest-pull line on both sides of 20:00"""
    names = [f"B{k:03d}" for k in range(1, 101)]
    w = World(names)
    nokey = {"load_keys": raiser(AssertionError("plan read the key"))}
    try:
        code, out, err = w.run("plan", **nokey)
        assert code == 0 and err == "" and not os.path.exists(w.root), (out, "plan writes nothing")
        for frag in ("window: 2025-08-26 .. 2026-10-30 (430 calendar days, 309 weekdays, 11 NYSE closed days on file = about 298 sessions; the pull refuses below 290)",
                     "bars request window: 2025-08-26T00:00:00Z .. 2026-10-30T23:59:59Z, 1Day, feed sip, adjustments raw + split",
                     "base list: " + w.base_path + ": 100 symbols, sha256 " + w.base_sha[:12] + "..." + w.base_sha[-4:] + " matches the registered one",
                     "hold list: none given (--hold FILE = the names the line holds from the previous rank: pulled ALWAYS, even when inactive now, so a name delisted mid-hold keeps its bars up to delisting)",
                     "active filter: unknown offline (the active set is Alpaca's active-assets list, which only `pull` reads): `pull` requests the base names on it + the new listings + every hold name, so the request counts below are an UPPER BOUND that the "
                     "active filter will cut - about 40% of the base list is expected to be inactive (roughly 60 of 100 base names would stay); `pull` prints and records the base names it dropped as inactive (count, first 20) and the inactive hold names "
                     "(all of them)",
                     "requests, UPPER BOUND (the whole base list, 100 symbols): bars 2 x 100 symbols x 1 page = 200; calendar >= 2 (50 symbols a request, more for pages); assets 1; total >= 203",
                     "requests, UPPER BOUND with the allowance (125 symbols): bars 250; calendar >= 3; assets 1; total >= 254",
                     "the shared Alpaca budget is 180 requests a minute: the upper-bound counts take about 1.1 min of pace alone, about 1.4 min with the allowance - the active filter makes it shorter",
                     "caps: a call gives up after 30 consecutive 429s; the whole pull after 360 minutes; no redirect is followed",
                     "written outside --out by the shared modules: C:\\EdgeLog\\state\\alpaca_rate.json (the shared pace)",
                     "output: would publish to " + os.path.join(w.root, "2026-10-30") + " (a re-pull would become _r2, _r3 ...)",
                     "earliest pull: 2026-10-30 20:00 New York time ([P1] --through is accepted when it is before today's New York date, or is today with the New York clock at or after 20:00); it is 2026-11-02 12:00 there now: a pull would be allowed now"):
            assert frag in out, (frag, out)
        assert last_line(out) == ("plan ok: through 2026-10-30, about 298 sessions, 100 base symbols (sha256 verified), an upper bound of about 203 requests (1 min at the shared pace) before the active filter cuts it; "
                                  "nothing was requested and no key was read"), last_line(out)
        assert "UPPER BOUND" in out and "hold names outside it" not in out and "hold symbols" not in last_line(out)
        assert w.vendor.calls == [] and w.assets.calls == [] and w.ca.calls == []
        code, out, _ = w.run("plan", through="2026-11-30", **nokey)                                       # a future month-end: planned, not pulled
        assert code == 0 and "window: 2025-09-26 .. 2026-11-30" in out and last_line(out).startswith("plan ok: through 2026-11-30") and "earliest pull: 2026-11-30 20:00 New York time ([P1]" in out and "it is 2026-11-02 12:00 there now: not yet" in out
        for now, frag in ((dt.datetime(2026, 11, 2, 19, 59), "it is 2026-11-02 19:59 there now: not yet"), (dt.datetime(2026, 11, 2, 20, 0), "it is 2026-11-02 20:00 there now: a pull would be allowed now"),
                          (dt.datetime(2026, 11, 3, 0, 5), "it is 2026-11-03 00:05 there now: a pull would be allowed now")):          # both sides of 20:00 on the day itself, and after midnight
            w.now = now
            code, out, _ = w.run("plan", through="2026-11-02", **nokey)
            assert code == 0 and "earliest pull: 2026-11-02 20:00 New York time ([P1]" in out and frag in out, (now, out)
        w.now = dt.datetime(2026, 11, 2, 12, 0)
        code, out, perr = w.run("plan", hold=["B001", "ZOLD", "YOLD", "B050"], **nokey)                    # a hold list: 4 names, 2 of them outside the base list
        hp = os.path.join(w.dir, "hold.txt")
        assert code == 0 and perr == "" and w.vendor.calls == [] and w.assets.calls == [], out
        for frag in (f"hold list: {hp}: 4 symbols, sha256 {sha_file(hp)[:12]}...{sha_file(hp)[-4:]}; pulled ALWAYS, active or not (not in the base list: 2, which add to the counts below)",
                     "requests, UPPER BOUND (the whole base list + the hold names outside it: 2, 102 symbols): bars 2 x 102 symbols x 1 page = 204; calendar >= 3 (50 symbols a request, more for pages); assets 1; total >= 208",
                     "requests, UPPER BOUND with the allowance (127 symbols): bars 254; calendar >= 3; assets 1; total >= 258"):
            assert frag in out, (frag, out)
        assert last_line(out) == ("plan ok: through 2026-10-30, about 298 sessions, 100 base symbols (sha256 verified), 4 hold symbols, an upper bound of about 208 requests (1 min at the shared pace) before the active filter cuts it; "
                                  "nothing was requested and no key was read"), last_line(out)
        absent = os.path.join(w.dir, "nohold.txt")
        code, out, _ = w.run("plan", hold_path=absent, **nokey)
        assert code == 2 and last_line(out) == f"refused: the hold list {absent} is not on file (nothing pulled)", out
        empty = os.path.join(w.dir, "empty.txt")
        with open(empty, "w") as fh:
            fh.write("# nobody\n")
        code, out, _ = w.run("plan", hold_path=empty, **nokey)
        assert code == 2 and last_line(out) == "refused: the hold list empty.txt holds no symbol (nothing pulled)", out
        for through, frag in (("2026-11-28", "Saturday"), ("2026-11-26", "Thanksgiving Day"), ("nope", "not a date")):
            code, out, _ = w.run("plan", through=through, **nokey)
            assert code == 2 and frag in last_line(out) and last_line(out).startswith("refused: "), out
        code, out, _ = w.run("plan", BASE_LIST_SHA="e" * 64, **nokey)
        assert code == 2 and "DIFFERS from the registered " + "e" * 64 in out and last_line(out) == "refused: the base list's sha256 is not the registered one (nothing pulled)", out
        code, out, _ = w.run("plan", BASE_LIST_PATH=os.path.join(w.dir, "absent.txt"), **nokey)
        assert code == 2 and "NOT ON FILE" in out and last_line(out) == "refused: the base list is not on file (nothing pulled)", out
        os.makedirs(os.path.join(w.root, "2026-10-30"))
        code, out, _ = w.run("plan", **nokey)
        assert code == 0 and "(revision 2: that date is already on file)" in out and os.path.join(w.root, "2026-10-30_r2") in out
        assert_no_secrets(w, out)
    finally:
        w.clean()


def t_secrets():
    """the fake key and secret reach fetch_bars, the assets call and the calendar (they must) and NOTHING else: a symbol whose error message echoes both is recorded scrubbed, a refusal and a failure line are scrubbed, and no captured line and no written byte holds either"""
    names = [f"B{k:03d}" for k in range(1, 101)]
    leak = f"HTTP 500: upstream echoed {FAKE_KEY} and {FAKE_SECRET} in its body"
    w = World(names, special={"B007": {"fail": {"raw": "always"}, "msg": leak}})
    try:
        code, out, err = w.run()
        assert code == 0, out
        m = man_of(os.path.join(w.root, "2026-10-30"))
        assert len(m["errors"]) == 1 and m["errors"][0]["symbol"] == "B007" and m["errors"][0]["error"] == "RuntimeError: HTTP 500: upstream echoed <key> and <key> in its body", m["errors"]
        assert_no_secrets(w, out, err)
        assert not _SECRETS, "no key is held once the run is over"
    finally:
        w.clean()
    w = World(names, special={s: {"fail": {"raw": "always"}, "msg": leak} for s in ("B007", "B008", "B009")})
    try:
        code, out, err = w.run()                                  # three failures: refused, and the refusal line itself must not carry the secrets
        assert code == 2 and "first error: B007 raw RuntimeError: HTTP 500: upstream echoed <key> and <key> in its body" in last_line(out) and w.folders() == [], out
        assert_no_secrets(w, out, err)
    finally:
        w.clean()
    w = World(names)
    try:
        code, out, err = w.run(ca_fetch=FakeCA(boom=RuntimeError(f"calendar said {FAKE_SECRET}")))
        assert code == 2 and last_line(out) == "failed: RuntimeError: calendar said <key> (nothing published)", last_line(out)
        assert_no_secrets(w, out, err)
        code, out, err = w.run(through="2026-10-29", ca_fetch=FakeCA(boom=SystemExit(f"AUTH FAILED {FAKE_KEY}")))
        assert code == 2 and last_line(out) == "refused: a house helper stopped the run: AUTH FAILED <key> (nothing published)", last_line(out)
        assert_no_secrets(w, out, err)
    finally:
        w.clean()
    assert scrub(f"a {FAKE_KEY} b") == f"a {FAKE_KEY} b", "scrub is inert while no key is held"
    with patched(sys.modules[__name__], _SECRETS=(FAKE_KEY, FAKE_SECRET, "", "short")):
        assert scrub(f"{FAKE_KEY}/{FAKE_SECRET}/short") == "<key>/<key>/short"
    # MANAGER #149 (c): the stripped, JSON-escaped, URL-encoded and repr forms are scrubbed too
    import json as _json
    from urllib.parse import quote, quote_plus
    odd = FAKE_SECRET[:10] + "/+= " + FAKE_SECRET[10:]                      # a secret with characters that change under escaping
    with patched(sys.modules[__name__], _SECRETS=("  " + FAKE_KEY + "\n", odd)):
        txt = scrub(" | ".join([FAKE_KEY, _json.dumps({"k": odd}), quote(odd, safe=""), quote_plus(odd), repr(odd)]))
        assert FAKE_KEY not in txt and FAKE_SECRET[:10] not in txt and FAKE_SECRET[10:] not in txt, txt
    # MANAGER #149 (b): the pull's key lookup strips the values
    with patched(alpaca_keys, load_keys=lambda: ("  " + FAKE_KEY + "  ", FAKE_SECRET + "\r\n")):
        assert load_keys() == (FAKE_KEY, FAKE_SECRET)
    # MANAGER #149 (c) + (d): r5_siporb._get redacts server text BEFORE its [:300] cut, and gives up after MAX_429 consecutive 429s
    class _R:
        def __init__(self, code, text=""):
            self.status_code, self.text = code, text
    edge = "x" * 290 + FAKE_KEY                                              # the key straddles the 300-character cut
    with patched(S, _http_get=lambda url, heads, params: _R(422, edge), PACE=0.0, RETRY=0.0, BACKOFF=0.0):
        try:
            S._get("https://example.invalid", {}, FAKE_KEY, FAKE_SECRET); raise AssertionError("a 422 was accepted")
        except S.BadRequest as e:
            assert FAKE_KEY[:8] not in str(e) and "<key>" in str(e), str(e)[-40:]
    with patched(S, _http_get=lambda url, heads, params: _R(429), PACE=0.0, RETRY=0.0, BACKOFF=0.0):
        try:
            S._get("https://example.invalid", {}, FAKE_KEY, FAKE_SECRET); raise AssertionError("an endless 429 storm was waited out")
        except RuntimeError as e:
            assert "429" in str(e) and str(IAS.MAX_429) in str(e), str(e)
    # MANAGER #149 (a) + (d): the bars call follows no redirect (a 302 is an error, never fetched), and gives up after MAX_429
    import requests
    seen = []

    def _no_redirect(url, headers=None, params=None, timeout=None, allow_redirects=True):
        seen.append(allow_redirects)
        return _R(302, "moved")
    with patched(requests, get=_no_redirect), patched(IAS, log=lambda m: None), patched(IAS.time, sleep=lambda s: None):
        try:
            IAS.fetch_bars("T01", "1Day", "a", "b", FAKE_KEY, FAKE_SECRET); raise AssertionError("a redirect was accepted")
        except RuntimeError as e:
            assert "HTTP 302" in str(e) and seen == [False], (str(e), seen)
    with patched(requests, get=lambda *a, **k: _R(429)), patched(IAS, log=lambda m: None), patched(IAS.time, sleep=lambda s: None):
        try:
            IAS.fetch_bars("T01", "1Day", "a", "b", FAKE_KEY, FAKE_SECRET); raise AssertionError("an endless 429 storm was waited out")
        except RuntimeError as e:
            assert "429" in str(e) and str(IAS.MAX_429) in str(e), str(e)
    # MANAGER #149 (d): the run-time cap refuses (nothing published)
    with patched(sys.modules[__name__], _DEADLINE=time.time() - 1.0):
        try:
            check_deadline("at symbol 1 of 1"); raise AssertionError("the run-time cap did not refuse")
        except Refused as e:
            assert f"{MAX_RUN_MIN}-minute cap" in str(e) and "(nothing published)" in str(e), str(e)


def t_real_fetch_bars():
    """the REAL import_alpaca_stocks.fetch_bars (pagination, the rate pace, the provenance receipt) over a faked requests.get: the key travels in the headers only, a second page is joined, empty answers are empty, every call files one receipt whose hash is the
    hash of the rows that ended up in the photograph"""
    import requests
    names = [f"R{k:02d}" for k in range(1, 7)]
    w = World(names, special={"R02": {"empty": True}, "R03": {"split": ("2026-03-02", 2)}})
    http = FakeHTTP(w.vendor, two_pages=("R01",))
    try:
        with patched(requests, get=http), patched(IAS, log=lambda m: None):                 # IAS.log would append to tools/import_alpaca_stocks.log
            code, out, err = w.run(fetch_bars=IAS.fetch_bars)
        assert code == 0, out
        assert len(http.calls) == 2 * 6 + 2 and all(c["url"] == IAS.BARS_URL and c["headers"] == {"APCA-API-KEY-ID": FAKE_KEY, "APCA-API-SECRET-KEY": FAKE_SECRET} for c in http.calls)
        assert all(FAKE_KEY not in json.dumps(c["params"]) and FAKE_SECRET not in json.dumps(c["params"]) and FAKE_KEY not in c["url"] for c in http.calls), "the key is in the headers only"
        p = http.calls[0]["params"]
        assert (p["timeframe"], p["feed"], p["limit"], p["sort"], p["start"], p["end"]) == ("1Day", "sip", 10000, "asc", "2025-08-26T00:00:00Z", "2026-10-30T23:59:59Z")
        assert sorted((c["params"]["symbols"], c["params"]["adjustment"], "page_token" in c["params"]) for c in http.calls if c["params"]["symbols"] == "R01") == [("R01", "raw", False), ("R01", "raw", True), ("R01", "split", False), ("R01", "split", True)]
        f = os.path.join(w.root, "2026-10-30")
        m = man_of(f)
        raw = pd.read_parquet(os.path.join(f, F_RAW))
        assert m["symbols"]["with_bars"] == 5 and m["symbols"]["empty"] == 1 and len(raw[raw["symbol"] == "R01"]) == 309, "both pages of R01 are joined"
        # the receipts: one per call that returned, in the state folder of the (temp) EDGELOG_HOME, named by the manifest
        path = m["provenance"]["manifest_path"]
        assert path == os.path.join(w.dir, "home", "state", "alpaca_pulls.jsonl"), path
        rec = pull_provenance.read_all(path)
        assert len(rec) == 12 and sorted(r["series"] for r in rec) == sorted(f"{s}|1Day|{a}|sip" for s in names for a in ADJUSTMENTS), [r["series"] for r in rec]
        t0, t1 = m["provenance"]["pulled_between_epoch"]
        for r in rec:
            assert (r["requested_start"], r["requested_end"], r["feed"], r["timeframe"]) == (m["provenance"]["requested_start"], m["provenance"]["requested_end"], "sip", "1Day")
            assert t0 - 0.01 <= r["pulled_at_epoch"] <= t1 + 0.01, "every receipt was filed inside the pull's own time span"
            fr = w.vendor.frame(r["symbol"], r["adjustment"])
            assert r["rows"] == len(fr) and r["content_hash"] == pull_provenance.content_hash(fr), (r["series"], "the receipt hashes the rows that went into the photograph")
        assert {r["content_hash"] for r in rec if r["symbol"] == "R02"} == {"sha256:empty"}, "an empty answer files its receipt too"
        assert_no_secrets(w, out, err)
    finally:
        w.clean()


def t_mocks_guard():
    """the tripwire itself works: a socket, a requests call and every real key lookup raise inside it - and everything is put back after"""
    import requests

    def state():
        return (alpaca_keys.load_keys, alpaca_keys._resolve, S.keys, S._http_get, IAS.load_keys, socket.create_connection, socket.getaddrinfo, socket.socket.__dict__.get("connect"), requests.sessions.Session.request)
    before = state()
    with tripwire():
        assert state() != before
        for fn in (lambda: socket.create_connection(("127.0.0.1", 9)), lambda: requests.get("http://127.0.0.1:9/", timeout=1), alpaca_keys.load_keys, S.keys, lambda: S._http_get("u", {}, {}), IAS.load_keys,
                   lambda: socket.getaddrinfo("example.invalid", 80)):
            try:
                fn()
            except AssertionError as e:
                assert "network or the real key lookup" in str(e)
            else:
                raise AssertionError("the tripwire did not fire")
    assert state() == before, "everything the tripwire patched is back exactly as it was"


def selftest():
    tests = [("constants as specified", t_constants), ("window arithmetic; --through: weekday, session; the command line", t_window), ("--through: before today's New York date, or today from 20:00 (a faked clock, both sides of 20:00)", t_clock),
             ("base list: sha refusal, parsing", t_base_list), ("hold list: parsing, refusals", t_hold_list),
             ("assets: the new-listing rules, exclusions by reason, the one call, the active set, the symbol rule", t_assets), ("daily frames: Eastern session date, naive, the cache's columns", t_daily_frames),
             ("bars: both adjustments, the window, empties counted, one retry, the key refused, the 2% threshold (1% passes, 3% refuses)", t_bars_pull),
             ("data checks: >= 290 sessions, --through is a session", t_through_in_data), ("new listings through a whole run; no asset list = no photograph", t_new_listings_run),
             ("symbols: inactive base names dropped, inactive hold names requested, the counts, the 2% rule on the requested set, the active-share floor", t_symbols),
             ("split cross-check: agree, calendar-only, price-only, +-3 sessions, unit split, weekend, not-comparable; the harness's own reader agrees", t_crosscheck),
             ("calendar: flattened like r16's, raw pages, counts by type and year; the real ca_fetch and fetch_assets over a faked transport", t_calendar_files),
             ("outputs: every sha, the file set, the parquet schema, the _r2 / _r3 rule, a rename race", t_outputs), ("publish: the default ROOT, a file on an _rN name, the rename retry on PermissionError", t_publish_details),
             ("read-back: both parquet files, the way the harness reads them, before the rename", t_read_back),
             ("atomic: no half folder, no ROOT\\<through> on any failure; refusals before the first request", t_atomic),
             ("exit codes and the last line", t_exit_codes), ("plan: no network, no key, any weekday", t_plan), ("the key never appears in any output or file", t_secrets),
             ("the real fetch_bars over a faked requests.get: the key in headers only, pages joined, one provenance receipt per call", t_real_fetch_bars), ("the tripwire", t_mocks_guard)]
    with tripwire():
        for name, fn in tests:
            t = time.time()
            fn()
            print(f"  ok  {name} ({time.time() - t:.1f}s)", flush=True)
    assert not _SECRETS
    print("selftest ok: the window arithmetic and the --through refusals (both sides of 20:00 New York time on the day itself); the base-list sha refusal; the symbol rule (inactive base names not requested, inactive hold names requested, the counts); "
          "both adjustments per symbol with the right windows; empty symbols counted; the 2% error threshold on the requested set (1% passes, 3% refuses, nothing published); the calendar flattened like r16's; the split cross-check (agree, "
          "calendar-only, price-only); the atomic publish and the _r2 rule; every manifest sha; the exit codes; no key or secret in any output or file")
    return 0


def main(argv):
    global _SECRETS
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")                 # a console that cannot show a character must not turn a message into a crash
        except (AttributeError, ValueError):
            pass
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "selftest":                                        # a failed test is a failed SELFTEST (message, traceback, non-zero exit) - never a 'pull failed (nothing published)' line
        try:
            return selftest()
        except Exception as e:
            print(one_line(scrub(f"selftest FAILED: {type(e).__name__}: {e}"))[:900], flush=True)
            raise
        finally:
            _SECRETS = ()
    try:
        if cmd == "pull":
            return run_pull(args)
        if cmd == "plan":
            return run_plan(args)
        print("usage: r17_resmom_pull.py plan --through YYYY-MM-DD [--out ROOT] [--hold FILE] | pull --through YYYY-MM-DD [--out ROOT] [--hold FILE] | selftest")
        print("refused: no such command (nothing pulled)")
        return 2
    except Refused as e:
        print(one_line(scrub(e)), flush=True)
        return 2
    except KeyboardInterrupt:
        print("failed: interrupted (nothing published)", flush=True)
        return 2
    except SystemExit as e:                                      # a house helper (r5_siporb._get, r16's ca_fetch) stopping the run with its own message
        print(one_line(scrub(f"refused: a house helper stopped the run: {e.code} (nothing published)")), flush=True)
        return 2
    except Exception as e:
        print(one_line(scrub(f"failed: {type(e).__name__}: {e} (nothing published)"))[:600], flush=True)
        return 2
    finally:
        _SECRETS = ()                                            # cleared only now: every message above was scrubbed while the key was still known


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
