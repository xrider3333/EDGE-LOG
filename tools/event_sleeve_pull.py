"""
EVENT SLEEVE forward feeds - the two pulls the owner approved (MANAGER #1041) for tools/event_sleeve_shadow.py `forward`
(docs/PREREG_event_sleeve_forward_2026-10-11.md). The scorer never touches the network; this tool is the only thing that does.

    python tools/event_sleeve_pull.py yahoo      # daily, after 16:30 ET: SPY / TLT / IEF adjusted daily closes
    python tools/event_sleeve_pull.py auctions   # weekly: the Treasury note + bond auction calendar (Fiscal Data API)

Writes ONLY under <EDGELOG_EVENT_SLEEVE, default C:\\EdgeLog\\event_sleeve>\\fwd_data\\ (the scorer's own out dir + fwd_data):
  yahoo_daily_<YYYYMMDD>_<HHMMSS>.csv         date,SPY,TLT,IEF: yfinance auto_adjust=True Close, verbatim - the house convention
                                              of tools/build_etf_masters.py (split + dividend total return, the yahoo_adj masters)
  treasury_auctions_<YYYYMMDD>_<HHMMSS>.json   the API response byte for byte, as tvnt2_triage.fetch() saved the snapshot
  provenance.jsonl                             one record per pull (kind, url or tickers + params, fetched_at, bytes, sha256,
                                              rows, first / last date, file), append-only - the scorer reads the newest
                                              record of each kind and refuses a file whose sha256 is no longer the recorded one

Rules:
  * Every pull is a NEW file (exclusive create; an existing name refuses). The research-cache snapshots
    (C:\\EdgeLog\\_research_cache\\nonequity_close.csv, treasury_auctions_raw.json, the yahoo_adj masters) are photographs and
    are never written - nothing here even opens them.
  * The data file and its record are written together under an OS lock on fwd_data\\provenance.jsonl.lock (house rule:
    cross-process locks are OS locks). A lock that cannot be taken refuses BEFORE anything is written: a pull without its
    record would be invisible to the scorer.
  * yahoo: start 2025-06-01, end = tomorrow (exclusive), Close only. A row dated today (New York) is dropped when the pull
    runs before 16:30 ET (an incomplete session). An empty frame or an all-empty ticker column refuses.
  * auctions: a response without a non-empty "data" list, or one whose meta total-count says rows were cut, refuses.
  * Network access sits in _yf_download and _http_get only (the tests replace both).
"""
import argparse
import contextlib
import datetime
import hashlib
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import event_sleeve_shadow as S  # noqa: E402  (FWD_SUBDIR / FWD_PROV / sha helpers: one definition for writer and reader)

DEFAULT_OUT = r"C:\EdgeLog\event_sleeve"               # the scorer's default OUT_DIR
TICKERS = ("SPY", "TLT", "IEF")
YAHOO_START = "2025-06-01"
SESSION_DONE_ET = datetime.time(16, 30)
LOCK_WAIT_SECONDS = 10.0

# COPIED VERBATIM from tools/tvnt2_triage.py fetch() (its `u1`): the same fields, filter, sort and page size, so a forward
# calendar is the same query as the 2026-10-05 snapshot (treasury_auctions_raw.json), only read later.
q = {"fields": "cusip,security_type,security_term,original_security_term,auction_date,announcemt_date,issue_date,reopening,"
               "offering_amt,inflation_index_security,floating_rate",
     "filter": "security_type:in:(Note,Bond),auction_date:gte:2005-01-01", "sort": "auction_date", "page[size]": "10000"}
u1 = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?" + urllib.parse.urlencode(q, safe=":(),[]")
AUCTIONS_URL = u1
del q


class Refused(SystemExit):
    pass


def refuse(msg):
    raise Refused("REFUSED: " + msg)


def fwd_dir():
    """<EDGELOG_EVENT_SLEEVE or the scorer's default>\\fwd_data - read at call time, so a test's env var applies."""
    return os.path.join(os.environ.get("EDGELOG_EVENT_SLEEVE", DEFAULT_OUT), S.FWD_SUBDIR)


# ------------------------------------------------------------------------------------------------ network (isolated)
def _yf_download(tickers, start, end):
    import yfinance as yf
    return yf.download(list(tickers), start=start, end=end, interval="1d", auto_adjust=True, actions=False,
                       progress=False, threads=False)


def _http_get(url):
    """tvnt2_triage._get's request (a plain GET, 120 s timeout), with this tool's User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": "EdgeLog research (event sleeve forward feeds)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _yf_version():
    try:
        import yfinance as yf
        return str(getattr(yf, "__version__", "?"))
    except Exception:
        return "?"


# ------------------------------------------------------------------------------------------------ the OS lock
# COPIED from augur_engine/alpaca_rate.py _lock_fd / _unlock_fd (importing augur_engine loads the whole engine package).
def _lock_fd(fd):
    try:
        import fcntl
    except ImportError:
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_fd(fd):
    try:
        import fcntl
    except ImportError:
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass


@contextlib.contextmanager
def _os_lock(lock_path, timeout=LOCK_WAIT_SECONDS):
    """Yields True while held, False when it could not be taken in `timeout` (the caller refuses: nothing is written)."""
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.time() + timeout
        while True:
            try:
                _lock_fd(fd)
                break
            except OSError:
                if time.time() >= deadline:
                    yield False
                    return
                time.sleep(0.05)
        try:
            yield True
        finally:
            _unlock_fd(fd)
    finally:
        os.close(fd)


# ------------------------------------------------------------------------------------------------ pure pieces
def _now(now=None):
    """The fetch moment, tz-aware local time (tests pass a fixed one)."""
    return (now or datetime.datetime.now()).astimezone()


def stamp(now):
    return now.strftime("%Y%m%d_%H%M%S")


def yahoo_closes(raw, now):
    """yfinance frame -> Close-only frame (columns SPY, TLT, IEF; tz-naive date index), today's row dropped when `now` is before
    16:30 New York time. Rows empty in every ticker are dropped. Refuses an empty frame or an all-empty ticker column.
    -> (frame, dropped_day or None)."""
    if raw is None or len(raw) == 0:
        refuse("yfinance returned an empty frame")
    if isinstance(raw.columns, pd.MultiIndex):
        lv0 = raw.columns.get_level_values(0)
        c = raw.xs("Close", axis=1, level=0) if "Close" in set(lv0) else raw.xs("Close", axis=1, level=1)
    else:
        if len(TICKERS) != 1 or "Close" not in raw.columns:
            refuse("yfinance frame has no per-ticker Close columns: %s" % list(raw.columns)[:8])
        c = raw[["Close"]].rename(columns={"Close": TICKERS[0]})
    missing = [t for t in TICKERS if t not in c.columns]
    if missing:
        refuse("yfinance frame has no Close column for %s" % missing)
    c = c[list(TICKERS)].astype(float)
    idx = pd.DatetimeIndex(c.index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    c.index = idx.normalize()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    ny = pd.Timestamp(now).tz_convert("America/New_York")
    today = pd.Timestamp(ny.date())
    dropped = None
    if ny.time() < SESSION_DONE_ET and today in c.index:
        c = c.drop(index=today)
        dropped = str(today.date())
    c = c.dropna(how="all")
    if len(c) == 0:
        refuse("no rows left after dropping the incomplete session")
    empty = [t for t in TICKERS if c[t].notna().sum() == 0]
    if empty:
        refuse("ticker column(s) %s empty" % empty)
    return c, dropped


def yahoo_csv_bytes(c):
    out = c.copy()
    out.index = [d.strftime("%Y-%m-%d") for d in out.index]
    out.index.name = "date"
    buf = io.StringIO()
    out.to_csv(buf, lineterminator="\n")
    return buf.getvalue().encode("utf-8")


def auctions_summary(raw):
    """Parse the API response and refuse it when it has no non-empty "data" list or says rows were cut. -> summary dict."""
    try:
        A = json.loads(raw)
    except ValueError as e:
        refuse("the auction response is not JSON (%s)" % e)
    data = A.get("data") if isinstance(A, dict) else None
    if not isinstance(data, list) or not data:
        refuse("the auction response has no \"data\" list")
    total = (A.get("meta") or {}).get("total-count")
    if total is not None and int(total) > len(data):
        refuse("the auction response holds %d of %s rows (the page size cut it)" % (len(data), total))
    ad = sorted(str(r.get("auction_date"))[:10] for r in data if isinstance(r, dict) and r.get("auction_date"))
    an = sorted(str(r.get("announcemt_date"))[:10] for r in data
                if isinstance(r, dict) and r.get("announcemt_date") not in (None, "", "null"))
    return dict(rows=len(data), first_date=ad[0] if ad else None, last_date=ad[-1] if ad else None,
                last_announced=an[-1] if an else None, total_count=total)


# ------------------------------------------------------------------------------------------------ writing
def _sha256(b):
    return hashlib.sha256(b).hexdigest()


def write_pull(name, payload, record):
    """Under the OS lock: create `name` exclusively (never overwrite), hash what is on disk, append the record."""
    d = fwd_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    prov = os.path.join(d, S.FWD_PROV)
    with _os_lock(prov + ".lock") as got:
        if not got:
            refuse("could not take the lock on %s within %.0f s - nothing written" % (prov, LOCK_WAIT_SECONDS))
        try:
            with open(path, "xb") as f:
                f.write(payload)
        except FileExistsError:
            refuse("%s exists - a pull is never overwritten" % path)
        with open(path, "rb") as f:
            on_disk = f.read()
        rec = dict(record, file=name, bytes=len(on_disk), sha256=_sha256(on_disk))
        with open(prov, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec, path


def _base_record(kind, now):
    return dict(kind=kind, fetched_at=now.isoformat(timespec="seconds"), fetched_at_epoch=round(now.timestamp(), 6),
                tool="tools/event_sleeve_pull.py", tool_sha256_lf=S.sha256_lf(os.path.abspath(__file__)))


def pull_yahoo(now=None):
    end = str((datetime.date.today() if now is None else _now(now).date()) + datetime.timedelta(days=1))
    raw = _yf_download(TICKERS, YAHOO_START, end)
    now = _now(now)
    c, dropped = yahoo_closes(raw, now)
    payload = yahoo_csv_bytes(c)
    rec = dict(_base_record("yahoo", now), tickers=list(TICKERS), source="yfinance %s" % _yf_version(),
               params=dict(start=YAHOO_START, end=end, interval="1d", auto_adjust=True, actions=False, kept="Close"),
               rows=int(len(c)), first_date=str(c.index[0].date()), last_date=str(c.index[-1].date()),
               last_date_by_ticker={t: str(pd.Timestamp(c[t].last_valid_index()).date()) for t in TICKERS},
               dropped_incomplete_today=dropped)
    rec, path = write_pull("yahoo_daily_%s.csv" % stamp(now), payload, rec)
    print("yahoo: %s  %d rows %s..%s%s  %d bytes  sha256 %s" % (
        path, rec["rows"], rec["first_date"], rec["last_date"],
        "  (dropped %s: before 16:30 ET)" % dropped if dropped else "", rec["bytes"], rec["sha256"]))
    return rec


def pull_auctions(now=None):
    raw = _http_get(AUCTIONS_URL)
    now = _now(now)
    summ = auctions_summary(raw)
    rec = dict(_base_record("auctions", now), url=AUCTIONS_URL, **summ)
    rec, path = write_pull("treasury_auctions_%s.json" % stamp(now), raw, rec)
    print("auctions: %s  %d rows, auctions %s..%s, last announced %s  %d bytes  sha256 %s" % (
        path, rec["rows"], rec["first_date"], rec["last_date"], rec["last_announced"], rec["bytes"], rec["sha256"]))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="EVENT SLEEVE forward feeds (owner-approved pulls; writes only fwd_data)")
    sub = ap.add_subparsers(dest="kind", required=True)
    sub.add_parser("yahoo", help="SPY / TLT / IEF daily adjusted closes (yfinance auto_adjust=True)")
    sub.add_parser("auctions", help="Treasury note + bond auction calendar (tvnt2_triage.fetch's query)")
    a = ap.parse_args(argv)
    (pull_yahoo if a.kind == "yahoo" else pull_auctions)()
    print("provenance: %s" % os.path.join(fwd_dir(), S.FWD_PROV))
    return 0


if __name__ == "__main__":
    sys.exit(main())
