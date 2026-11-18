"""Build the pinned side panel for augur_strategies/MISC_AUCSHORT_1_0.py (opus hunt 135a / 151 part A, AUCTION-AM
short), and print the frozen point-in-time auction calendar that file carries.

The plugin runs on the TLT 5m RTH master (alpaca_split_rth, engine master id 114): the master is the bar clock of
every trade and the price source of the TLT trades. This panel holds what that master does not carry, built the way
the hunt harness's load() builds it (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S135/s135_eval.py):
  * dates          the session calendar 2016-01-04 .. 2026-06-30 (yyyymmdd): the TLT 5m master, the IEF 5m master,
                   TLT_1Day_raw.csv and IEF_1Day_raw.csv must agree on every date, or nothing is written;
  * calskip        an EXCHANGE-CALENDAR fact per session, no price: 1 = an NYSE early-close session (the hunt's rule
                   i: the Friday after Thanksgiving; Dec 24 when a weekday session; July 3 when a weekday session and
                   July 4 falls Tue-Fri), 2 = the last session before a full-day NYSE closure on a weekday (rule ii:
                   augur_engine.session_calendar closed_days + holiday_sessions), 0 = neither. Rule i wins when both;
  * <F>_o935       OPEN of fund F's 5m bar stamped 09:35 ET (NaN when the session has no such bar), F in TLT, IEF;
  * <F>_o1255      OPEN of the bar stamped 12:55 ET (NaN when missing);
  * <F>_full       1 when the session has both bars and its last bar is 15:55 (the hunt's rule iii), else 0;
  * <F>_prevraw    the RAW close of the PRIOR session, C:/EdgeLog/alpaca_cache/etf_daily/<F>_1Day_raw.csv shifted one
                   row (NaN on the first session): the share-count and cost price.
The 5m masters are loaded with augur_engine.data.load_master_arrays from the shared checkout's registry, exactly as
the harness (np.asarray(open, float)), so the stored opens are the harness's numbers bit for bit.
DATA QA (ratio_qa, as tools/misc_gldmacro_panel.py): on every session, raw / split daily close (must be equal on
every row: neither fund split) and raw daily close / close of the 5m master's last bar. A level STEP in such a ratio
(21-session medians differ by more than 0.5 pct) = a split or a re-adjustment in one source: flagged, nothing written.
THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC. It stores arrays and prints shapes, calendar checks, same-session
ratio checks and the sha256 to pin in the plugin. Everything runs to 2026-06-30 so the engine's lockbox year has its
clock and prints; no morning move is formed here from any of them.

    python tools/misc_aucshort_panel.py              (writes C:/EdgeLog/alpaca_cache/aucshort_panel/aucshort_panel_v1.npz)
    python tools/misc_aucshort_panel.py --calendar   (prints the frozen calendar strings from the auction JSON; no panel)
The calendar mode reads C:/EdgeLog/_research_cache/treasury_auctions_raw.json (a 2026-10-05 pull of Treasury's auction
query) ONCE, at build time; the plugin never reads it. Filter = auction_calendar() below.
Memory: one 5m master at a time (~205k rows), under 250 MB. A rebuild writes a new zip (new sha256): the plugin then
refuses it until PANEL_SHA256 is re-pinned.
"""
import csv
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"      # the master registry lives in the shared checkout
DAILY = "C:/EdgeLog/alpaca_cache/etf_daily/%s_1Day_%s.csv"
AUCTIONS = "C:/EdgeLog/_research_cache/treasury_auctions_raw.json"
OUT = "C:/EdgeLog/alpaca_cache/aucshort_panel/aucshort_panel_v1.npz"
FUNDS = ("TLT", "IEF")
FROM, CUT = "2016-01-01", "2026-06-30"
OPEN_MIN, LAST_SLOT = 570, 955                            # 09:30 and 15:55 ET, minute of day
ENTRY_MIN, EXIT_MIN = 575, 775                            # the bars stamped 09:35 and 12:55 ET
QA_WIN, QA_STEP, QA_DAY = 21, 0.005, 0.005
TERM_FUND = {"5-Year": "IEF", "7-Year": "IEF", "10-Year": "IEF", "20-Year": "TLT", "30-Year": "TLT"}


def _sc():
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    from augur_engine import session_calendar as SC
    return SC


# ---- the NYSE calendar, exactly s135_eval.py's (PREREG rules i and ii) ---------------------------------------------
def nyse_closed(d):
    SC = _sc()
    return d.weekday() < 5 and (d in SC.closed_days(d.year) or d in SC.holiday_sessions(d.year))


def nyse_session(d):
    return d.weekday() < 5 and not nyse_closed(d)


def early_close(d):
    if not nyse_session(d):
        return False
    tg = _sc()._nth_weekday(d.year, 11, 3, 4)
    if d == tg + dt.timedelta(days=1):
        return True
    if d.month == 12 and d.day == 24:
        return True
    if d.month == 7 and d.day == 3 and dt.date(d.year, 7, 4).weekday() in (1, 2, 3, 4):
        return True
    return False


def pre_closure(d):
    n = d + dt.timedelta(days=1)
    while n.weekday() >= 5:
        n += dt.timedelta(days=1)
    return nyse_closed(n)


def prior_session(d):
    p = d - dt.timedelta(days=1)
    while not nyse_session(p):
        p -= dt.timedelta(days=1)
    return p


def calskip(d):
    return 1 if early_close(d) else (2 if pre_closure(d) else 0)


# ---- the point-in-time auction calendar ----------------------------------------------------------------------------
def auction_calendar(path=AUCTIONS, first="2016-01-01"):
    """(kept, late): rows (auction yyyymmdd, announcement yyyymmdd, fund, original term) of every auction from `first`
    to the file's last date with security_type Note / Bond, inflation_index_security = No, floating_rate = No and an
    original_security_term of 5 / 7 / 10 (IEF) or 20 / 30 (TLT) years, whose ANNOUNCEMENT date is on or before the
    NYSE session before the auction date (knowable by the prior session's close). `late` = the rows that pass every
    other test but were announced later than that. Sorted by auction date, fund, term."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)["data"]
    kept, late = [], []
    for r in data:
        if r["auction_date"] < first:
            continue
        if r["security_type"] not in ("Note", "Bond"):
            continue
        if r.get("inflation_index_security") != "No" or r.get("floating_rate") != "No":
            continue
        fund = TERM_FUND.get(r["original_security_term"])
        if fund is None:
            continue
        ad, an = dt.date.fromisoformat(r["auction_date"]), dt.date.fromisoformat(r["announcemt_date"])
        row = (int(ad.strftime("%Y%m%d")), int(an.strftime("%Y%m%d")), fund, r["original_security_term"])
        (kept if an <= prior_session(ad) else late).append(row)
    key = lambda z: (z[0], z[2], z[3])
    return sorted(kept, key=key), sorted(late, key=key)


def frozen_strings(kept):
    """{fund: text}: 'auction:announcement:years' tokens, the format the plugin freezes."""
    out = {}
    for f in FUNDS:
        toks = ["%d:%d:%s" % (a, n, t.split("-")[0]) for a, n, ff, t in kept if ff == f]
        out[f] = toks
    return out


def print_calendar():
    kept, late = auction_calendar()
    print("auction rows kept %d (%s .. %s) | IEF %d, TLT %d | dropped, announced after the prior session: %s" % (
        len(kept), kept[0][0], kept[-1][0], sum(1 for k in kept if k[2] == "IEF"),
        sum(1 for k in kept if k[2] == "TLT"), late))
    for f, toks in frozen_strings(kept).items():
        print("_%s_AUCTIONS = (" % f)
        for i in range(0, len(toks), 5):
            print('    "%s "' % " ".join(toks[i:i + 5]))
        print(")")
    return 0


# ---- the panel -----------------------------------------------------------------------------------------------------
def ratio_qa(label, num, den, dates, exact=False):
    """DATA QA - no return: q = num / den, two closes of the SAME session from two sources (see the GLD builder)."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    q = num / den
    n = len(q)
    hits = []
    for t in range(QA_WIN, n - QA_WIN + 1):
        before, after = np.median(q[t - QA_WIN:t]), np.median(q[t:t + QA_WIN])
        if abs(after / before - 1.0) > QA_STEP:
            hits.append((t, abs(after / before - 1.0)))
    steps, run = [], []
    for h in hits + [None]:
        if run and (h is None or h[0] != run[-1][0] + 1):
            t = max(run, key=lambda z: z[1])[0]
            steps.append((t, float(np.median(q[t - QA_WIN:t])), float(np.median(q[t:t + QA_WIN]))))
            run = []
        if h is not None:
            run.append(h)
    med = float(np.median(q))
    off = np.flatnonzero(np.abs(q / med - 1.0) > QA_DAY)
    differ = int((num != den).sum())
    flags = len(steps) + (differ if exact else 0)
    print("QA %s: %d sessions | ratio %.6f .. %.6f (median %.6f)%s | sessions off the median by more than %.1f pct: "
          "%d %s | level steps %d -> %s" % (
              label, n, float(q.min()), float(q.max()), med,
              (" | rows where the two differ %d" % differ) if exact else "", 100 * QA_DAY, len(off),
              [str(dates[k].date()) for k in off[:12]], len(steps), "FLAG" if flags else "OK"))
    for t, b, a in steps:
        print("  QA FLAG %s: level step at %s - ratio level %.6f before, %.6f after" % (label, dates[t].date(), b, a))
    return flags


def read_daily(path):
    dts, cl = [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["date"][:10] > CUT:
                break
            dts.append(r["date"][:10])
            cl.append(float(r["close"]))
    s = pd.Series(cl, index=pd.to_datetime(dts))
    assert s.index.is_monotonic_increasing and not s.index.duplicated().any(), path
    assert s.index.max() <= pd.Timestamp(CUT), path
    return s[s.index >= pd.Timestamp(FROM)]


def fund_sessions(D, sym):
    """Per session of one fund's 5m master: o935, o1255, full, the last bar's minute and close (the close for the
    data QA only)."""
    m = D.find_master(sym, "5m", "rth", "alpaca_split_rth")
    assert m is not None, "%s 5m master not registered" % sym
    a = D.load_master_arrays(m, date_from=FROM, date_to=CUT)
    idx = pd.DatetimeIndex(a["index"]).tz_convert("US/Eastern")
    assert idx.is_monotonic_increasing, "%s 5m master bars out of time order" % sym
    keep = np.asarray(idx < pd.Timestamp(CUT, tz="US/Eastern") + pd.Timedelta(days=1))
    idx = idx[keep]
    df = pd.DataFrame({"d": idx.tz_localize(None).normalize(), "m": np.asarray(idx.hour * 60 + idx.minute),
                       "o": np.asarray(a["open"], float)[keep], "c": np.asarray(a["close"], float)[keep]})
    del a
    assert ((df.m >= OPEN_MIN) & (df.m <= LAST_SLOT)).all(), "%s 5m master has bars outside 09:30 .. 15:55" % sym
    assert not df.duplicated(["d", "m"]).any(), "%s duplicate 5m bars" % sym
    g = df.groupby("d")
    S = pd.DataFrame({"last": g.m.max(), "last_close": g.c.last(), "bars": g.m.size()})
    S["o935"] = df[df.m == ENTRY_MIN].set_index("d").o.reindex(S.index)
    S["o1255"] = df[df.m == EXIT_MIN].set_index("d").o.reindex(S.index)
    S["full"] = S.o935.notna() & S.o1255.notna() & (S["last"] == LAST_SLOT)
    print("%s 5m master id %s (%s): %d bars, %d sessions %s .. %s, full %d" % (
        sym, m["id"], m["filename"], len(df), len(S), S.index[0].date(), S.index[-1].date(), int(S.full.sum())))
    return S


def main():
    if "--calendar" in sys.argv[1:]:
        return print_calendar()
    cwd = os.getcwd()
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    try:
        S = {f: fund_sessions(D, f) for f in FUNDS}
    finally:
        os.chdir(cwd)
    cal = pd.DatetimeIndex(S["TLT"].index)
    out = {}
    flags = 0
    for f in FUNDS:
        raw, spl = read_daily(DAILY % (f, "raw")), read_daily(DAILY % (f, "split"))
        for nm, other in (("%s 5m master sessions" % f, pd.DatetimeIndex(S[f].index)), ("%s_1Day_raw.csv" % f, raw.index),
                          ("%s_1Day_split.csv" % f, spl.index)):
            if not cal.equals(other):
                sys.exit("calendar mismatch: TLT 5m master vs %s: only TLT %s, only other %s" % (
                    nm, [str(x.date()) for x in cal.difference(other)][:10],
                    [str(x.date()) for x in other.difference(cal)][:10]))
        if not (np.isfinite(raw.values).all() and (raw.values > 0).all()):
            sys.exit("non-finite or non-positive %s raw close" % f)
        flags += ratio_qa("%s raw / split (the two alpaca daily files)" % f, raw.values, spl.values, cal, exact=True)
        flags += ratio_qa("%s raw / close of the 5m master's last bar" % f, raw.values, S[f].last_close.values, cal)
        short = S[f][~S[f].full]
        print("%s sessions that are not full (no 09:35 or 12:55 bar, or last bar not 15:55): %d -> %s" % (
            f, len(short), {str(k.date()): "%02d:%02d/%d" % (divmod(int(v["last"]), 60) + (int(v["bars"]),))
                            for k, v in short.iterrows()}))
        out["%s_o935" % f] = S[f].o935.to_numpy(np.float64)
        out["%s_o1255" % f] = S[f].o1255.to_numpy(np.float64)
        out["%s_full" % f] = S[f].full.to_numpy().astype("int8")
        out["%s_prevraw" % f] = raw.shift(1).to_numpy(np.float64)
    if flags:
        sys.exit("DATA QA: %d flag(s) above - a split or a re-adjustment step in a source; refusing to write" % flags)
    days = [x.date() for x in cal]
    notsess = [str(d) for d in days if not nyse_session(d)]
    if notsess:
        sys.exit("panel dates that are not NYSE sessions on the house calendar: %s" % notsess[:10])
    skip = np.array([calskip(d) for d in days], dtype="int8")
    print("calendar: %d sessions %s .. %s; both 5m masters and the four daily files agree on every date; all are NYSE "
          "sessions | calskip: early close %d %s | before a closure %d" % (
              len(cal), cal[0].date(), cal[-1].date(), int((skip == 1).sum()),
              [str(d) for d, s in zip(days, skip) if s == 1], int((skip == 2).sum())))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype="int64"), calskip=skip, **out)
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    print("%s  sessions %d  sha256 %s" % (OUT, len(cal), sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
