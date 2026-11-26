"""nq_box_topup.py - BOX-SIDE top-up of the NQ 5m RTH master before the nightly KEEL build.

WHY (board 174, 2026-11-25). The box's ~/edgelog/nq/NOADJ_NQ_5m_RTH.csv is only refreshed by the
PC's push (tools/push_nq_master_to_box.py). When the PC (the Razer) is off, the 18:30 ET KEEL build
(edgelog-keel-state.service) trains one session stale. This runs as that service's ExecStartPre and
ADDS the missing completed sessions from Yahoo NQ=F (RAW front-month, non-adjusted - the same feed
and the same guards as tools/refresh_noadj_yahoo.py, whose helpers it reuses).

RULES (each one is a test in tests/test_nq_box_topup.py):
  * ADD ONLY. Existing rows are never rewritten - the file's existing bytes are copied verbatim and
    new lines appended after them. The PC's NT/Databento-sourced bars keep priority: the PC's next
    push replaces the whole file anyway.
  * Only bars strictly after the master's last bar.
  * Never a still-forming bar, and never a session that has not closed (16:00 ET + Yahoo's settle
    margin) - so a mid-session run (the keel-state .path trigger) never writes half a day.
  * RTH only (09:30-15:55 ET bar starts, weekdays), the master's own columns/format.
  * Refuses a bar spanning a contract switch (augur_engine.roll_guard), like the PC refresh.
  * Atomic: tmp file in the same directory + fsync + os.replace.
  * No-op when the PC already pushed the latest closed session, or Yahoo has nothing new.
  * NEVER FAILS THE KEEL BUILD: any error prints and exits 0 (the unit also uses ExecStartPre=-).

Run:  python tools/nq_box_topup.py --nq-file ~/edgelog/nq/NOADJ_NQ_5m_RTH.csv
"""
import argparse
import importlib.util
import os
import sys
import tempfile
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_SPEC = importlib.util.spec_from_file_location(
    "_refresh_noadj_yahoo_for_topup", os.path.join(ROOT, "tools", "refresh_noadj_yahoo.py"))
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)

SOURCE_TAG = "yahoo_box_topup"
TF = "5m"
SESSION_CLOSE_MIN = 16 * 60          # 16:00 ET
LAST_BAR_MIN = 15 * 60 + 55          # 15:55 ET bar start = the session's final 5m bar
FULL_BARS = 78                       # 09:30..15:55 ET, a full RTH session of 5m bars


def _log(msg):
    print("[nq_box_topup %s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def _et(times):
    return pd.to_datetime(pd.Series(times), unit="s", utc=True).dt.tz_convert("US/Eastern")


def _closed_sessions_only(df, now_s, settle_s=None):
    """Keep bars whose whole RTH session has closed (16:00 ET + settle) as of now_s."""
    if not len(df):
        return df
    settle_s = R.YAHOO_SETTLE_S if settle_s is None else settle_s
    et = _et(df["time"])
    day0 = et.dt.normalize()
    close_s = (day0 + pd.Timedelta(minutes=SESSION_CLOSE_MIN)).astype("int64") // 1_000_000_000
    return df[(close_s + settle_s <= now_s).values].reset_index(drop=True)


def _full_sessions_only(df):
    """Only FULL regular sessions: a day is added only when it is an exchange session, not a
    CME holiday short session (augur_engine.session_calendar), AND Yahoo has all 78 bars
    09:30..15:55 ET. Every partial day - Thanksgiving (PC master: 42 bars to 12:55), Black
    Friday / Dec 24 / Jul 3 (45 bars to 13:10), or a Yahoo gap - is left for the PC push,
    whose NT bars set the shape. Nothing is ever added past a skipped day (no holes)."""
    if not len(df):
        return df
    from augur_engine.session_calendar import is_exchange_session, is_holiday_session
    days = _et(df["time"]).dt.date
    counts = days.value_counts()
    keep = []
    for d in sorted(set(days)):
        if not (is_exchange_session(d) and not is_holiday_session(d) and counts[d] == FULL_BARS):
            break                      # stop at the first partial day: never leave a hole
        keep.append(d)
    return df[days.isin(keep).values].reset_index(drop=True)


class MasterChanged(RuntimeError):
    """The master file changed (a PC push landed) between our read and our write."""


def _fmt(v):
    return repr(float(v))


def _detect_newline(raw):
    return "\r\n" if b"\r\n" in raw[:4096] else "\n"


def new_bars(cur_last, yahoo_tv, now_s, settle_s=None):
    """Pure: the TV-format bars to append after `cur_last`. Returns (frame, note)."""
    new = R._drop_unclosed(yahoo_tv, TF, now_s, margin_s=settle_s)
    new = R._rth(new)
    new = _closed_sessions_only(new, now_s, settle_s)
    new = new[new["time"] > cur_last].sort_values("time").drop_duplicates("time").reset_index(drop=True)
    new = _full_sessions_only(new)
    if not len(new):
        return new, None
    new, hit = R.roll_guard.split_tv_frame(new, after_time=cur_last, root="NQ")
    new = _full_sessions_only(new)     # a roll-guard cut mid-day must not leave a partial day
    note = None
    if hit is not None:
        note = "REFUSED an in-bar contract switch: " + R.roll_guard.describe(hit)
    return new, note


def append_bars(path, new, columns, raw, st0=None):
    """Write `raw` (the file's existing bytes, untouched) + one line per new bar, atomically.
    `st0` = os.stat of the master when `raw` was read: if the file changed since (a PC push
    landed mid-run), raise MasterChanged and leave the PC's file alone."""
    nl = _detect_newline(raw)
    lines = []
    for r in new.itertuples(index=False):
        vals = {"time": str(int(r.time)), "open": _fmt(r.open), "high": _fmt(r.high),
                "low": _fmt(r.low), "close": _fmt(r.close), "volume": str(int(r.volume)),
                "source": SOURCE_TAG}
        lines.append(",".join(vals.get(c, "") for c in columns))
    body = raw
    if body and not body.endswith(b"\n"):
        body += nl.encode()
    body += (nl.join(lines) + nl).encode()
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".topup_", suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o777)
        except OSError:
            pass
        if st0 is not None:
            st1 = os.stat(path)
            if (st1.st_ino, st1.st_size, st1.st_mtime_ns) != (st0.st_ino, st0.st_size, st0.st_mtime_ns):
                raise MasterChanged("master changed since read (PC push?) - not overwriting")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _yahoo_tv():
    import yfinance as yf
    h = yf.Ticker("NQ=F").history(period="60d", interval="5m")
    if h is None or not len(h):
        return None
    return R._to_tv(h)


def run(nq_file, now_s=None, fetch=_yahoo_tv, settle_s=None):
    """Returns the number of bars appended (0 = no-op)."""
    now_s = int(time.time()) if now_s is None else int(now_s)
    st0 = os.stat(nq_file)
    with open(nq_file, "rb") as fh:
        raw = fh.read()
    cur = pd.read_csv(nq_file)
    if not len(cur):
        _log("master is empty - not topping up an empty file"); return 0
    cur_last = int(cur["time"].max())
    last_et = _et([cur_last]).iloc[0]
    # PC already pushed the latest closed session in full -> nothing to do, no network either.
    if (last_et.hour * 60 + last_et.minute == LAST_BAR_MIN
            and last_et.date() >= _latest_closed_session(now_s, settle_s)):
        _log("master already holds the full %s session (PC push) - no-op" % last_et.date())
        return 0
    try:
        yt = fetch()
    except Exception as e:
        _log("Yahoo pull failed: %s - no-op" % str(e)[:120]); return 0
    if yt is None or not len(yt):
        _log("no Yahoo data - no-op"); return 0
    new, note = new_bars(cur_last, yt, now_s, settle_s)
    if note:
        _log(note)
    if not len(new):
        _log("nothing new after %s ET - no-op" % last_et); return 0
    try:
        append_bars(nq_file, new, list(cur.columns), raw, st0=st0)
    except MasterChanged as e:
        _log(str(e)); return 0
    a, b = _et([new["time"].iloc[0]]).iloc[0], _et([new["time"].iloc[-1]]).iloc[0]
    _log("+%d bars (%s .. %s ET) -> %d rows" % (len(new), a, b, len(cur) + len(new)))
    return len(new)


def _latest_closed_session(now_s, settle_s=None):
    """ET date of the newest weekday whose RTH session has closed (holidays not modelled: a
    holiday just means Yahoo has nothing new, which is the same no-op)."""
    import datetime as dt
    settle_s = R.YAHOO_SETTLE_S if settle_s is None else settle_s
    now_et = _et([now_s]).iloc[0]
    d = now_et.date()
    closed_today = (now_et.hour * 60 + now_et.minute) * 60 + now_et.second >= SESSION_CLOSE_MIN * 60 + settle_s
    if not (d.weekday() < 5 and closed_today):
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nq-file", required=True)
    a = ap.parse_args(argv)
    try:
        run(os.path.expanduser(a.nq_file))
    except Exception as e:   # never block the KEEL build
        _log("ERROR %s: %s - master left as it was" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
