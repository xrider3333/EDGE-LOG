"""RUN RECORD - the one JSONL line a lane or the Qwen Lab appends when a run finishes (W47, owner ask 2026-10-18).

WHY THIS EXISTS. The COMPARE scatter plots users/{uid}/runs, and only the web runner writes there
(api/runner.py _persist_run). A lane harness and the Qwen Lab run the same engine on the same
masters, and their results never reach the plot - so a month of work is invisible wherever it ran.
Each lane appends one record per finished run under C:/EdgeLog/run_records/ and W47's sync tool
uploads them. The runner is NOT a caller: its runs are already in Firestore, and the equity it
saves is a thinned, UNDATED per-trade curve in POINTS, so there is no daily series to measure there.

THE SCHEMA IS FROZEN (MANAGER #127 + addendum #1447). This module is its only writer, so every
vocabulary and unit check lives here instead of being re-typed in five harness tails.

THE FOUR NUMBERS ARE NOT RE-IMPLEMENTED. Hand this tool the stretch's DAILY $ series and it calls
augur_engine.drawdowns.four_numbers, the one definition (MANAGER #170). A caller that already holds
the four numbers may hand them in instead, and then they are STORED exactly as given and never
re-derived - the rule tools/runboard_watch.py stretch_numbers states: a percentage is never derived
from dollars, because the worst % drop need not be the worst $ drop.

THREE OF THE FOUR NUMBERS IS NOT A ROW. The scatter cannot tell a figure that does not exist from one
that was never measured, so a handed-in dict is checked against what its OWN figures make possible: a
null Sortino or a null ROC @ $30k beside a real drawdown is refused by name (a stretch that drew down
has a losing day, and a drawdown to divide by); DD5 has to sit inside [max_dd / 5, max_dd], which is
the window a PERCENT falls out of when it reaches the dollars field; and the DD % cannot beat
100 x max_dd_usd / start_usd, the most an account whose equity high starts at the account can fall.
The honest over-100% reading still goes through - it is bounded by its own dollars, not by 100.

PER-TRADE P&L IS REFUSED. four_numbers exists to stop that mistake (ENGU-Q's hold-cap rows, 10-15):
valued per trade, the Sortino is a different number. A daily series has EVERY day of the stretch
present, zero days included, so rows that share a date, rows out of order, or a stretch most of
whose days are missing are refused by name.

A PROVISIONAL RUN ID IS REFUSED. During a Firestore outage the runner's run id becomes
int(time.time()), and the run is later re-saved under its real sequential number (api/runner.py
_persist_run, repair_provisional_run_ids). A record written against the provisional id would point
at a run number that never exists, forever - so a run_id has to look like a run number (the real
ones are small integers; today's newest is 491).

NEVER RAISES INTO A HARNESS TAIL. The caller is the last line of someone's save path, so the
default is forgiving: a refused record returns None and writes one line to stderr. Tests - and a
human at a prompt - pass strict=True / --strict to have the refusal raised instead.

No credential is read and no network call is made: this is a local append under EDGELOG_HOME.

USAGE
-----
From a lane harness tail (tools/disc_ctxshort_r1.py:522, tools/rocfrontier/r30_calmtape.py:378),
passing the DAILY series and letting this tool measure it - the preferred path, because it is the
only one that fills the data window:

    import tools.run_record as run_record          # or: sys.path.insert(.../tools); import run_record
    run_record.write_record(
        "STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y", "lane", "WF",
        strategy="disc_ctxshort_r1", family="DISC", instrument="NQ", timeframe="1m",
        daily=du,                                  # pd.Series of $ per day, zero days included
        trades=b["trades"], gross_pt=b["gross_pts_per_trade"], cost_pt=COST_NQ,
        ledger_row="2.195", note="ctxshort r1 primary rule, NQ cost")

A tail that already holds the four numbers hands its own dict in; the numbers are stored as given.
The read dicts of both live lane patterns are understood as they are (`roc30`/`dd5`/`dd_pct_peak`,
and calmtape's `dd` for the worst drawdown):

    run_record.write_record(lane, "lane", "WF", strategy=..., family=..., instrument=...,
                            timeframe=..., numbers=b, trades=n, cost_pt=COST_NQ)

From the Qwen Lab (tools/qwen_lab.py:5155). Its own four_numbers (:3280) is keyed 'roc_30k' and its
one_episode may be the 'NOT TESTABLE' sentinel (MANAGER #160a); both are understood, and trades /
gross_pt / cost_pt are read out of the same dict:

    pr = self.idea["proposal"]
    run_record.write_record(lane, "lab", "WF", strategy=pr["name"], family="QWEN",
                            instrument=pr["instrument"], timeframe=pr["timeframe"],
                            numbers=nm, note=self.idea["id"])

From a shell:

    python tools/run_record.py --lane LANE --where lane --stage WF --strategy S --family F \\
        --instrument NQ --timeframe 5m --daily-csv daily.csv --trades 210 --cost-pt 0.533
    python tools/run_record.py ... --dry        # print the record, write nothing
"""
import argparse
import contextlib
import csv
import datetime
import json
import math
import os
import platform
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:                      # so `python tools/run_record.py` can import augur_engine
    sys.path.insert(0, ROOT)

SCHEMA_V = 1
WHERE = ("runner", "lane", "lab", "box")
STAGES = ("IS", "WF", "LB", "preWF", "forward", "full", "preLB")
# full = the whole run read as ONE stretch; preLB = everything before the lockbox. Both were already in use by
#   DISC and FRONTIER when this writer landed (58 and 15 of the 1,199 lines on 2026-10-19), and the page draws
#   each with its own mark rather than bucketing it, so a FULL total is never added into a walk-forward figure.
#   The SPELLING is closed here on purpose: tools/run_records_sync.py canonicalises what the old lines wrote,
#   but a lane calling this writer gets one spelling per stretch and no synonyms to drift between.
TS_FMT = "%Y-%m-%d %H:%M"                     # the runs docs' own shape (api/runner.py:1632)
DAY_FMT = "%Y-%m-%d"
DEFAULT_START_USD = 100_000.0                 # augur_engine.drawdowns.DEFAULT_START_USD, restated for the CLI help
LOCK_WAIT_SECONDS = 10.0                      # as tools/event_sleeve_pull.py waits
NOTE_MAX = 200

# A run number is a small integer from the runner's counter; a PROVISIONAL id is int(time.time()),
# about 1.79e9 today. Today's newest run is 491, so this ceiling leaves ~200x headroom for real runs
# and still sits 17,000x below any provisional id.
MAX_RUN_ID = 100_000

# A daily series has EVERY day of the stretch present. A sessions-only series covers ~96% of the
# business days in its span (weekends are already out; ~9 US holidays in 252), and a calendar-day
# series covers ~145%. So 0.9 passes every honest daily series and fails a per-trade list, which is
# the only thing that arrives with a third of its days missing.
MIN_DAILY_COVERAGE = 0.9

# ROC @ $30k IS 30 x (net / years) / worst drawdown in all three producers (augur_engine.drawdowns
# four_numbers, augur_engine.book_sizing.stretch_reading, tools/power_line.roc30), so when a
# handed-in record carries all four figures the identity is checkable. 2% absorbs their rounding
# (stretch_reading rounds the ROC to 3 dp and the dollars to the cent) and still catches a ROC that
# was measured on a different curve than the dollars beside it.
ROC_IDENTITY_TOL = 0.02

# The percent field is where a DOLLAR figure lands when a caller mixes the two up, and a 33612 there
# would plot as a drawdown without complaint. dd_pct_peak is deliberately NOT capped at 100 - an
# account that fell below zero really did fall more than 100% from the high before it, and that is
# the honest reading (augur_engine/drawdowns.py dd_pct_peak) - so the ceiling is not a constant: it
# comes off the record's OWN dollars. THE INVARIANT: dd_pct_peak's high-water mark starts AT
# start_usd and only rises, so every fall is measured against a peak >= start_usd and
#     ddpct <= 100 x max_dd_usd / start_usd.
# MEASURED over 400 random daily series straight from augur_engine.drawdowns.four_numbers: the worst
# excess over that bound was +0.000044, which is dd_pct_peak's own rounding to 4 dp - hence the cent
# of slack. The bound still admits the honest over-100% reading: a $100k account taken to -$200k fell
# $200k from a $100k high, so ddpct 200 against a bound of 200.
DDPCT_BOUND_SLACK = 0.01

# When a handed-in record carries no max_dd_usd there is nothing to take that ceiling from, so the
# blunt bar stays as the backstop: above it, the number in the percent field is dollars. 1000 is the
# figure tools/run_records_sync.py refuses above, settled (ELWA, W47 owner, 2026-10-18). The READER
# half of W47 only ever sees the line and cannot do better than this bar; the WRITER knows the
# dollars and the account, so here it is the fallback and not the rule.
DDPCT_ABSURD = 1000.0

# dd_pct_peak rounds to 4 dp, so a fall under 0.00005% reads as a flat 0.0 - which is the honest
# output for a sub-cent drawdown, while DD5 rounds to the CENT and so reads 0.01 beside it (a $0.01
# fall on $100k is 0.00001%). Under this floor a zero percent beside a nonzero dd5 is that rounding,
# not an impossible pair, and the measured path must never refuse its own four_numbers output.
DDPCT_ROUNDING_FLOOR = 0.00005

# DD5 averages AT MOST 5 episode depths and the worst one IS one of them, so dd5 >= max_dd / 5
# ALWAYS. MEASURED over the same 400 series: the smallest dd5 / max_dd was 0.2004, never under 1/5.
# This floor is what catches a PERCENT landing in the dollars field - with a worst drawdown of
# $12,000 the floor is $2,400, and 13.09, 0.1309 and 2399.9 all sit below it.
DD5_FLOOR_EPISODES = 5.0

LAB_NOT_TESTABLE = "NOT TESTABLE"             # tools/qwen_lab.py ONE_EPISODE_NOT_TESTABLE (MANAGER #160a)

# The frozen field order, so the file reads the same way every day and a diff of two records lines up.
FIELDS = ("ts", "lane", "host", "where", "strategy", "family", "instrument", "timeframe", "stage",
          "roc30k", "dd5", "ddpct", "sortino", "trades", "gross_pt", "cost_pt", "one_episode",
          "ledger_row", "run_id", "sha", "note",
          "start_usd", "net_usd", "max_dd_usd", "years", "win_start", "win_end", "schema_v")

# The key each producer in this repo uses for the same figure, so a lane hands in its own read dict
# unchanged rather than re-keying it at the call site (where a typo would silently write a null).
#   four_numbers        roc30 / dd5_usd / dd_pct_peak / net / max_dd / from / to
#   qwen_lab            roc_30k / dd5_usd / dd_pct_peak / net_usd / max_dd_usd
#   disc_ctxshort read  roc30 / dd5 / dd_pct_peak / net_usd
#   calmtape figs       roc30 / dd5 / dd (the worst drawdown)
#   stretch_reading     roc_30k / max_drawdown / from / to
NUMBER_KEYS = {
    "roc30k": ("roc30k", "roc30", "roc_30k"),
    "dd5": ("dd5", "dd5_usd"),
    "ddpct": ("ddpct", "dd_pct_peak"),
    "sortino": ("sortino",),
    "one_episode": ("one_episode",),
    "net_usd": ("net_usd", "net"),
    "max_dd_usd": ("max_dd_usd", "max_dd", "max_drawdown", "dd"),
    "years": ("years",),
    "win_start": ("win_start", "from"),
    "win_end": ("win_end", "to"),
}
# The five a handed-in dict must carry: the four numbers plus the flag that says whether the ROC
# rests on one episode. The window fields above are optional - calmtape's figs() and the lane read
# dicts do not hold them - and are written as null when the tail has none.
REQUIRED_NUMBERS = ("roc30k", "dd5", "ddpct", "sortino", "one_episode")
COUNT_KEYS = {
    "trades": ("trades",),
    "gross_pt": ("gross_pt", "gross_pts_per_trade"),
    "cost_pt": ("cost_pt", "cost_pts"),
}


class RunRecordError(Exception):
    """A record this tool refuses to write. Raised in strict mode; in forgiving mode its message is
    the one line that goes to stderr."""


def _refuse(msg):
    raise RunRecordError("run_record: " + msg)


# ================================================================================ where the records live
def records_root():
    """<EDGELOG_RUN_RECORDS, else EDGELOG_HOME, else C:\\EdgeLog>\\run_records - read at CALL time, so a
    test's env var applies (the tmp dir idiom of tools/event_sleeve_pull.py). A test must never land
    in the real directory: tests/conftest.py's live-system guard fails any write under EDGELOG_HOME."""
    override = os.environ.get("EDGELOG_RUN_RECORDS")
    if override and override.strip():
        return override.strip()
    home = os.environ.get("EDGELOG_HOME") or (r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog")
    return os.path.join(home, "run_records")


def lane_slug(lane):
    """A lane name as a filename: lowercased, every other character a dash, collapsed and trimmed.

    The record keeps the lane name VERBATIM in its `lane` field - this is only the file it lands in,
    so two spellings of one lane never end up in two files. Capped at 80 characters because Windows
    still has a path limit and a lane name has no limit at all."""
    s = re.sub(r"[^a-z0-9]+", "-", str(lane or "").strip().lower()).strip("-")
    if not s:
        _refuse("lane is empty (or has no letters or digits): %r - the chat-inbox lane name is what "
                "files a record" % (lane,))
    return s[:80].rstrip("-")


def record_path(lane, ts, records_dir=None):
    """<records dir>/<lane>_YYYYMM.jsonl. The month comes from the record's OWN ts, not from today:
    a record written just after midnight for a run that finished before it belongs in the run's month."""
    return os.path.join(records_dir or records_root(), "%s_%s%s.jsonl" % (lane_slug(lane), ts[:4], ts[5:7]))


# ================================================================================ host and code sha
def host_id():
    """EDGELOG_HOST_ID, else the OS hostname.

    The same rule as api.cloud_signal._host_id / api.qqq_exec._lease_host_id, DUPLICATED rather than
    imported: importing either of those pulls the live trading engine into a harness tail whose only
    job is to append a line."""
    override = os.environ.get("EDGELOG_HOST_ID")
    if override and override.strip():
        return override.strip()
    try:
        return platform.node() or "unknown-host"
    except Exception:
        return "unknown-host"


_SHA_CACHE = {}


def code_sha(root=None):
    """The CODE commit the run came from: `git rev-parse HEAD` in the checkout this file lives in.

    NOT a hash of the record line. A line hash would look just as sha-shaped while telling nobody
    which engine produced the numbers, which is the one question the field exists to answer. Cached
    per checkout - a harness tail that writes several records runs git once."""
    root = root or ROOT
    if root not in _SHA_CACHE:
        sha = None
        try:
            p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                               text=True, timeout=20)
            if p.returncode == 0:
                sha = (p.stdout or "").strip()
        except Exception:
            sha = None
        _SHA_CACHE[root] = sha if sha and re.fullmatch(r"[0-9a-fA-F]{7,40}", sha) else None
    if not _SHA_CACHE[root]:
        _refuse("could not read the code sha from %s (`git rev-parse HEAD`) - pass sha= yourself; the "
                "record has to say which code produced the numbers" % root)
    return _SHA_CACHE[root].lower()


# ================================================================================ the OS lock
# COPIED from tools/event_sleeve_pull.py (which copied it from augur_engine/alpaca_rate.py): one
# idiom for "an OS lock around an append", not a new one per tool.
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
    """Yields True while held, False when it could not be taken in `timeout` (then the caller refuses
    and nothing is written).

    The lock is its own file beside the JSONL, never the JSONL itself. On Windows msvcrt unlocks the
    byte at the handle's CURRENT position, so locking a file that is then appended to unlocks the
    wrong byte (the trap tests/test_push_lock.py and tests/test_wt.py both record). This handle is
    opened, locked and closed without a single write, so its position stays at byte 0."""
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


# ================================================================================ small validators
def _num(v, field, allow_none=False):
    """A finite number, or None when the field allows one. NaN is refused everywhere: json.dumps
    writes it as the bare token NaN, which is not valid JSON, so a NaN would land as a line no
    reader can parse - a record that is silently unreadable is worse than one that was refused."""
    if v is None:
        if allow_none:
            return None
        _refuse("%s is required" % field)
    if isinstance(v, bool):
        _refuse("%s is a number, got the boolean %r" % (field, v))
    try:
        x = float(v)
    except (TypeError, ValueError):
        _refuse("%s is not a number: %r" % (field, v))
    if math.isnan(x):
        _refuse("%s is NaN - pass None when the figure does not exist" % field)
    if math.isinf(x):
        _refuse("%s is infinite (%r)" % (field, v))
    return x


def _undefined_to_none(v, field):
    """NaN -> None for the two figures that legitimately have no value.

    ROC @ $30k has none when the curve never draws down and Sortino has none when no day loses.
    four_numbers and stretch_reading both say that with None; the numpy producers say it with NaN
    (tools/power_line.roc30 returns nan when dd == 0, and calmtape's figs() a nan sortino when no day
    loses). Same state, two spellings - so a NaN arriving in exactly these two fields is read as
    "no value", and every other field still refuses one."""
    if v is None:
        return None
    try:
        if isinstance(v, bool):
            _refuse("%s is a number, got the boolean %r" % (field, v))
        if math.isnan(float(v)):
            return None
    except (TypeError, ValueError):
        pass
    return _num(v, field, allow_none=True)


def _text(v, field, required=True):
    s = "" if v is None else str(v).strip()
    if required and not s:
        _refuse("%s is required" % field)
    return s or None


def _ts(ts):
    if ts is None:
        return time.strftime(TS_FMT)
    s = str(ts).strip()
    try:
        datetime.datetime.strptime(s, TS_FMT)
    except ValueError:
        _refuse("ts must be local '%s' like the runs docs' own timestamp (api/runner.py:1632), got %r"
                % (TS_FMT.replace("%Y", "YYYY").replace("%m", "MM").replace("%d", "DD")
                   .replace("%H", "HH").replace("%M", "MM"), ts))
    return s


def _day_str(v, field, allow_none=True):
    if v is None:
        if allow_none:
            return None
        _refuse("%s is required" % field)
    s = str(v).strip()[:10]
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        _refuse("%s must be a date 'YYYY-MM-DD', got %r" % (field, v))
    return s


def _ledger_row(v):
    """The research-ledger row as TEXT, e.g. '2.195'.

    A number is refused: a row handed over as the float 2.20 stringifies to '2.2', which is a
    different row, and nothing downstream could tell that it had been renamed."""
    if v is None:
        return None
    if not isinstance(v, str):
        _refuse("ledger_row is text like '2.195', got %r (%s) - handed over as a number, row 2.20 "
                "becomes '2.2', a different row" % (v, type(v).__name__))
    return v.strip() or None


def _run_id(v):
    """A plausible run number, or None.

    THE RULE: reject a PROVISIONAL id. api/runner.py falls back to int(time.time()) when the run-id
    counter cannot be read, and repair_provisional_run_ids later re-saves that run under its real
    sequential number - so a record written against the provisional id would point at a run number
    that never exists, and would keep pointing at it forever."""
    if v is None:
        return None
    if isinstance(v, bool):
        _refuse("run_id is a run number, got the boolean %r" % (v,))
    try:
        x = float(v)
    except (TypeError, ValueError):
        _refuse("run_id is not a run number: %r" % (v,))
    if not math.isfinite(x) or x != int(x):
        _refuse("run_id is not a whole run number: %r" % (v,))
    n = int(x)
    if n < 1 or n > MAX_RUN_ID:
        _refuse("run_id %d is not a plausible run number (1..%d; today's newest is 491). A run id of "
                "about 1.79e9 is the runner's PROVISIONAL id, int(time.time()), handed out while "
                "Firestore reads were failing - that run is re-saved under a different number, so a "
                "record against this one would point at the wrong run forever. Pass the real number, "
                "or run_id=None for a run that has none." % (n, MAX_RUN_ID))
    return n


def _one_episode(v):
    """The one-episode flag: a bool, or None for the lab's 'NOT TESTABLE'.

    MANAGER #160a: with one drawdown episode (or a curve that never makes a new high) one drawdown
    cannot be compared with others, and tools/qwen_lab.py says so with the string sentinel. That is
    not False - False would claim the ROC was tested and does not rest on one episode - so it is
    written as null, the same "no value" the schema already uses for ledger_row and run_id.
    Everything else is refused: a dollar figure here reads as truthy and would quietly flag every
    record as one-episode."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().upper() == LAB_NOT_TESTABLE:
        return None
    item = getattr(v, "item", None)                  # numpy spells a boolean np.bool_; still a boolean
    if item is not None and isinstance(item(), bool):
        return bool(v)
    _refuse("one_episode is a boolean (or the lab's %r), got %r of type %s - the worst episode being "
            "more than 1.3x DD5 is a yes/no; a number here would flag the record one-episode and "
            "break the plot silently" % (LAB_NOT_TESTABLE, v, type(v).__name__))


def _note(note, computed):
    """One short line, plus the provenance tag.

    The tag says whether the four numbers were MEASURED here from a daily series or handed in by the
    lane, which a reader has to know before trusting them - and the schema is frozen, so it rides in
    the free-text field rather than in a field of its own.

    Whitespace is collapsed and the caller's text truncated instead of refused: a tidy-up of a
    cosmetic field must never cost a whole record."""
    tag = " | numbers: %s" % ("computed" if computed else "given")
    s = re.sub(r"\s+", " ", str(note or "")).strip()
    if len(s) > NOTE_MAX:
        s = s[:NOTE_MAX - 3].rstrip() + "..."
    return (s + tag) if s else tag.lstrip(" |").strip()


# ================================================================================ the daily series
def _as_day(d):
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    try:
        return datetime.date.fromisoformat(str(d)[:10])
    except ValueError:
        _refuse("daily series: %r is not a date 'YYYY-MM-DD'" % (d,))


def _business_days(d0, d1):
    """Weekdays from d0 to d1 inclusive, holidays not removed. A day loop: a research stretch is a
    few thousand days, so there is nothing to optimise and nothing to get wrong."""
    n, d, step = 0, d0, datetime.timedelta(days=1)
    while d <= d1:
        if d.weekday() < 5:
            n += 1
        d += step
    return n


def check_daily(values, dates):
    """Refuse anything that cannot be the stretch's DAILY $ series, naming what was wrong.

    WHY THIS IS A REFUSAL AND NOT A WARNING. four_numbers exists to stop per-trade P&L being read as
    a curve (ENGU-Q's hold-cap rows, 10-15): valued per trade the Sortino is a different number and
    nothing on the record says which it was. The three things that give it away:
      * no dates - then nothing here is a day, and the record has no data window either;
      * two rows on one date - a daily series has one row per day, a trade list has several;
      * most of the stretch's days missing - the contract is EVERY day present, zero days included.
    Returns the dates as date objects, in order."""
    if dates is None:
        _refuse("the daily series has no dates. Pass a pd.Series indexed by date, (date, $) pairs, or "
                "dates=[...] - the four numbers are read off a DATED daily curve and the record's data "
                "window comes from those dates")
    if len(dates) != len(values):
        _refuse("the daily series has %d dates for %d values" % (len(dates), len(values)))
    if len(values) < 2:
        _refuse("a stretch needs at least 2 daily rows (%d given)" % len(values))
    days = [_as_day(d) for d in dates]
    for i in range(1, len(days)):
        if days[i] == days[i - 1]:
            _refuse("two rows share %s - that is per-trade P&L, not a daily series. Sum the trades "
                    "into one row a day (every day of the stretch, zero days included): valued per "
                    "trade the Sortino is a different number, which is the mistake "
                    "augur_engine.drawdowns.four_numbers exists to stop" % days[i])
        if days[i] < days[i - 1]:
            _refuse("the daily series is not sorted by date (%s comes after %s) - rows are taken in "
                    "the order given, so an unsorted curve measures a drawdown that never happened"
                    % (days[i], days[i - 1]))
    span = _business_days(days[0], days[-1]) or ((days[-1] - days[0]).days + 1)
    cover = len(days) / float(span)
    if cover < MIN_DAILY_COVERAGE:
        _refuse("%d rows over %s..%s (%d business days) cover %.0f%% of the stretch, under the %.0f%% "
                "a daily series has to. A daily curve has EVERY day present, zero days included; this "
                "looks like per-trade P&L, or a series with its zero days dropped - either way the "
                "Sortino would be measured on the wrong rows"
                % (len(days), days[0], days[-1], span, 100 * cover, 100 * MIN_DAILY_COVERAGE))
    return days


_DRAWDOWNS = None


def drawdowns_module():
    """augur_engine/drawdowns.py loaded as a FILE, not through the package.

    WHY NOT `from augur_engine.drawdowns import ...`. That import runs augur_engine/__init__.py,
    which pulls the whole engine: MEASURED on this box, 2.80 s and 46 -> 1335 modules, bringing in
    numpy, pandas, requests, scipy and sqlite3 - to reach a module whose own docstring says "Stdlib
    only". The file alone is 0.015 s and 3 modules. The cost is not the point: write_record is
    forgiving by default and swallows ANY exception, so an unrelated ImportError anywhere in the
    engine would silently lose a lane's record. host_id() already refuses this coupling on the same
    ground - a harness tail whose only job is to append a line does not import the trading engine.

    The one definition stays the one definition: this is the same file four_numbers lives in. It is
    NOT registered in sys.modules, so nothing else can pick it up as a second augur_engine.drawdowns.
    Falls back to the ordinary import when the file cannot be loaded (a relocated or zipped
    checkout). Cached: a tail writing several records loads it once."""
    global _DRAWDOWNS
    if _DRAWDOWNS is None:
        mod = None
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_run_record_drawdowns", os.path.join(ROOT, "augur_engine", "drawdowns.py"))
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
        except Exception:                            # noqa: BLE001 - any failure falls back, below
            mod = None
        if mod is None or not hasattr(mod, "four_numbers") or not hasattr(mod, "_rows"):
            from augur_engine import drawdowns as mod
        _DRAWDOWNS = mod
    return _DRAWDOWNS


def numbers_from_daily(daily, dates=None, start_usd=DEFAULT_START_USD, years=None):
    """The four numbers MEASURED from a daily $ series, by calling the one definition.

    Everything is augur_engine.drawdowns.four_numbers' own output, re-keyed onto the frozen field
    names (roc30 -> roc30k, dd5_usd -> dd5, dd_pct_peak -> ddpct, net -> net_usd, max_dd ->
    max_dd_usd, from/to -> win_start/win_end). Nothing is computed here."""
    # _rows is the engine's OWN input parser, used rather than copied so this tool and four_numbers
    # cannot disagree about which rows they are looking at. Both come off the FILE (drawdowns_module),
    # never the augur_engine package - see that function.
    dd = drawdowns_module()
    _rows, four_numbers = dd._rows, dd.four_numbers
    try:
        vals, dts = _rows(daily, dates)
    except Exception as e:
        _refuse("could not read the daily series (%s: %s). Pass a pd.Series of $ per day indexed by "
                "date, a sequence of (date, $) pairs, or values with dates=[...]"
                % (type(e).__name__, e))
    check_daily(vals, dts)
    try:
        f = four_numbers(vals, dates=dts, start=start_usd, years=years)
    except ValueError as e:
        _refuse("four_numbers refused the series: %s" % e)
    return {"roc30k": f["roc30"], "dd5": f["dd5_usd"], "ddpct": f["dd_pct_peak"],
            "sortino": f["sortino"], "one_episode": f["one_episode"], "net_usd": f["net"],
            "max_dd_usd": f["max_dd"], "years": f["years"],
            "win_start": f["from"], "win_end": f["to"]}


def _pick(d, names):
    for k in names:
        if k in d:
            return d[k], True
    return None, False


def numbers_given(numbers):
    """The four numbers as a lane hands them in - STORED, never re-derived.

    The house rule (tools/runboard_watch.py stretch_numbers): a percentage is never derived from
    dollars, because the worst % drop need not be the worst $ drop. So a dict missing one of the
    four is refused rather than filled in from the others."""
    if not isinstance(numbers, dict):
        _refuse("numbers= takes the read dict a lane already has, got %s" % type(numbers).__name__)
    out, missing = {}, []
    for field, names in NUMBER_KEYS.items():
        v, found = _pick(numbers, names)
        if not found and field in REQUIRED_NUMBERS:
            missing.append("%s (any of %s)" % (field, "/".join(names)))
        out[field] = v if found else None
    if missing:
        _refuse("numbers= is missing %s. A stretch's four numbers travel together - a record with one "
                "of them derived from the others would be a different curve's reading. Pass daily= "
                "instead and they are all measured from the series" % "; ".join(missing))
    return out


# ================================================================================ the record
def build_record(lane, where, stage, *, strategy, family, instrument, timeframe,
                 daily=None, dates=None, numbers=None, trades=None,
                 gross_pt=None, cost_pt=None, start_usd=None, years=None,
                 run_id=None, ledger_row=None, sha=None, note="", ts=None, host=None,
                 verdict=None, prereg=None, run_start=None):
    """One validated record, or RunRecordError. Pure: nothing is written and nothing is read but the
    host name and the code sha.

    Exactly one of daily= (measured here) or numbers= (stored as given). Everything after `stage` is
    keyword-only on purpose: strategy, family, instrument and timeframe are four strings in a row,
    and a positional swap of two of them is invisible in the finished record.

    trades / gross_pt / cost_pt are read out of numbers= when they are not passed (the lab's dict and
    the lane read dicts carry them). gross_pt and cost_pt may be None, meaning "the tail did not hold
    it" - a cost of 0 is a claim that the run was costless, which is not the same thing.

    start_usd=None means "not named". On the daily= path it becomes the engine's own default and is
    then the REAL account, because dd_pct_peak is handed exactly that figure. On the numbers= path
    nothing here measured anything, so the default is only an assumption about someone else's run -
    it is still written (the schema has no null there), but a DD % the assumed account would refuse
    is sent back for the account rather than refused on a guess (_check_units start_given)."""
    if (daily is None) == (numbers is None):
        _refuse("pass either daily= (the stretch's daily $ series, measured here by four_numbers) or "
                "numbers= (a read dict you already have), not both and not neither")
    if dates is not None and daily is None:
        _refuse("dates= belongs with daily=")
    start_given = start_usd is not None or daily is not None
    if start_usd is None:
        start_usd = DEFAULT_START_USD

    if daily is not None:
        nums = numbers_from_daily(daily, dates, start_usd=start_usd, years=years)
    else:
        nums = numbers_given(numbers)
        if nums["years"] is None and years is not None:
            nums["years"] = years                    # calmtape holds YEARS beside figs(), not inside it
    src = numbers if isinstance(numbers, dict) else {}
    if trades is None:
        trades, _ = _pick(src, COUNT_KEYS["trades"])
    if gross_pt is None:
        gross_pt, _ = _pick(src, COUNT_KEYS["gross_pt"])
    if cost_pt is None:
        cost_pt, _ = _pick(src, COUNT_KEYS["cost_pt"])

    stamp = _ts(ts)
    rec = {
        "ts": stamp,
        "lane": _text(lane, "lane"),
        "host": _text(host, "host", required=False) or host_id(),
        "where": _text(where, "where"),
        "strategy": _text(strategy, "strategy"),
        "family": _text(family, "family"),
        "instrument": _text(instrument, "instrument"),
        "timeframe": _text(timeframe, "timeframe"),
        "stage": _text(stage, "stage"),
        "roc30k": _undefined_to_none(nums["roc30k"], "roc30k"),
        "dd5": _num(nums["dd5"], "dd5"),
        "ddpct": _num(nums["ddpct"], "ddpct"),
        "sortino": _undefined_to_none(nums["sortino"], "sortino"),
        "trades": _trades(trades),
        "gross_pt": _num(gross_pt, "gross_pt", allow_none=True),
        "cost_pt": _num(cost_pt, "cost_pt", allow_none=True),
        "one_episode": _one_episode(nums["one_episode"]),
        "ledger_row": _ledger_row(ledger_row),
        "run_id": _run_id(run_id),
        "sha": _sha(sha),
        "note": _note(note, computed=daily is not None),
        "start_usd": _num(start_usd, "start_usd"),
        "net_usd": _num(nums["net_usd"], "net_usd", allow_none=True),
        "max_dd_usd": _num(nums["max_dd_usd"], "max_dd_usd", allow_none=True),
        "years": _num(nums["years"], "years", allow_none=True),
        "win_start": _day_str(nums["win_start"], "win_start"),
        "win_end": _day_str(nums["win_end"], "win_end"),
        "schema_v": SCHEMA_V,
    }
    _check_units(rec, start_given=start_given)
    out = {k: rec[k] for k in FIELDS}
    # BOARD C8 - NO VERDICT WITHOUT A LOCKED PREREG. A record with no verdict is untouched (no new keys, so
    # its sync content hash is what it always was). A verdict needs prereg= naming a lock made BEFORE
    # run_start (else the record's own ts) whose file still matches; prereg="none - exploratory" stores
    # the verdict as EXPLORATORY instead.
    if verdict is not None and str(verdict).strip():
        out["verdict"] = _verdict(verdict, prereg, run_start or stamp)
        out["prereg"] = str(prereg).strip()
    return out


def _verdict(verdict, prereg, run_start):
    try:
        from tools import prereg_lock
    except ImportError:                              # run as a script from tools/
        import prereg_lock
    try:
        return prereg_lock.verdict_gate(verdict, prereg, run_start)
    except prereg_lock.PreregError as e:
        _refuse(str(e))
    except ValueError as e:
        _refuse("run_start %r is not a time (%s)" % (run_start, e))


def _trades(v):
    if v is None:
        _refuse("trades is required - the record says how many round trips the numbers rest on, and "
                "a missing count would plot as zero")
    if isinstance(v, bool):
        _refuse("trades is a count, got the boolean %r" % (v,))
    x = _num(v, "trades")
    if x != int(x) or x < 0:
        _refuse("trades is a whole count of round trips, got %r" % (v,))
    return int(x)


def _sha(sha):
    if sha is None:
        return code_sha()
    s = str(sha).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{7,40}", s):
        _refuse("sha must be a git commit sha (7-40 hex characters), got %r. It is the CODE commit the "
                "run came from - not a hash of this line" % (sha,))
    return s


def _check_units(rec, start_given=True):
    """The unit checks, in one place: each one catches a figure that would plot without complaint.

    What is deliberately NOT checked: a DD % over 100. augur_engine.drawdowns.dd_pct_peak is not
    capped on purpose - an account that fell below zero really did fall more than 100% from its high,
    and that is the honest reading. What IS checked is that the percent does not beat its own
    dollars over the account (see DDPCT_BOUND_SLACK), which lets that reading through.

    start_given says whether the caller named the account the DD % was measured on. On the daily=
    path it is always true - dd_pct_peak was handed exactly that figure - but on the numbers= path
    an unnamed account means the bound below rests on this module's $100k DEFAULT, which is an
    assumption about someone else's run, so a record it would refuse is sent back for the account
    rather than refused on a guess."""
    if rec["where"] not in WHERE:
        _refuse("where must be one of %s, got %r" % ("/".join(WHERE), rec["where"]))
    if rec["stage"] not in STAGES:
        _refuse("stage must be one of %s, got %r" % ("/".join(STAGES), rec["stage"]))
    if rec["start_usd"] <= 0:
        _refuse("start_usd is the account the DD %% was measured on, in dollars, got %r" % (rec["start_usd"],))
    if rec["years"] is not None and rec["years"] <= 0:
        _refuse("years must be a positive length of stretch, got %r" % (rec["years"],))
    if rec["dd5"] < 0:
        _refuse("dd5 is a positive depth in DOLLARS (the average of the 5 deepest episodes), got %r"
                % (rec["dd5"],))
    if rec["max_dd_usd"] is not None and rec["max_dd_usd"] < 0:
        _refuse("max_dd_usd is a positive depth in dollars, got %r" % (rec["max_dd_usd"],))
    # DD5 averages the deepest episodes and the deepest one IS the worst drawdown, so it can never
    # exceed it (the same check tools/runboard_watch.py stretch_numbers makes).
    if rec["max_dd_usd"] is not None and rec["dd5"] > rec["max_dd_usd"] + 0.01:
        _refuse("dd5 $%.2f is deeper than the worst drawdown $%.2f - an average of the 5 worst "
                "drawdowns cannot beat the worst one, so these two came off different curves"
                % (rec["dd5"], rec["max_dd_usd"]))
    # ...and the same average cannot be SHALLOWER than a fifth of the worst, because it averages at
    # most 5 depths and the worst is one of them. This is the floor a PERCENT falls through when it
    # lands in the dollars field (13.09 against a worst drawdown of $12,000, whose floor is $2,400).
    if rec["max_dd_usd"] is not None and rec["dd5"] < rec["max_dd_usd"] / DD5_FLOOR_EPISODES - 0.01:
        _refuse("dd5 $%.2f is shallower than $%.2f = the worst drawdown $%.2f / %d. DD5 averages AT "
                "MOST %d episode depths and the worst one IS one of them, so it can never fall below "
                "a fifth of it (measured over 400 series from four_numbers: the smallest dd5/max_dd "
                "was 0.2004). A figure under that floor is a PERCENT in the DOLLARS field, or two "
                "figures off different curves - dd5 is the average depth of the 5 deepest episodes, "
                "in dollars" % (rec["dd5"], rec["max_dd_usd"] / DD5_FLOOR_EPISODES, rec["max_dd_usd"],
                                int(DD5_FLOOR_EPISODES), int(DD5_FLOOR_EPISODES)))
    if rec["ddpct"] < 0:
        _refuse("ddpct is a percent of the equity high (13.09 means 13.09%%), got %r" % (rec["ddpct"],))
    # THE CEILING COMES OFF THE RECORD'S OWN DOLLARS: the equity high starts AT the account and only
    # rises, so a fall from a high is at most 100 x max_dd / start_usd. An over-100% reading still
    # gets through on its own dollars; only a figure that beats them is dollars in the percent field.
    ddpct_max = (None if rec["max_dd_usd"] is None
                 else 100.0 * rec["max_dd_usd"] / rec["start_usd"] + DDPCT_BOUND_SLACK)
    if ddpct_max is None:
        if rec["ddpct"] > DDPCT_ABSURD:              # no dollars to bound it: the blunt backstop
            _refuse("ddpct is %r with no max_dd_usd beside it - that is a dollar figure in the percent "
                    "field. ddpct is the fall from the equity HIGH in percent (13.09 means 13.09%%); "
                    "the dollars belong in max_dd_usd, and passing them is also what lets this tool "
                    "check the percent against its own account instead of this %.0f bar"
                    % (rec["ddpct"], DDPCT_ABSURD))
    elif rec["ddpct"] > ddpct_max:
        # Asking for the account only helps while an account could still explain the figure. Above
        # the blunt bar none can - a 33612 beside a $12,000 worst drawdown would need a $35 account -
        # so that one is named as what it is instead of sent back for a figure that cannot rescue it.
        if not start_given and rec["ddpct"] <= DDPCT_ABSURD:
            _refuse("ddpct %r is above 100 x max_dd $%.2f / start_usd $%.2f = %.4f%%, but start_usd was "
                    "NOT passed - that is this tool's $%.0f DEFAULT, not the account your DD %% was "
                    "measured on, and the bound is only as good as the account. Pass start_usd= "
                    "(--start-usd from a shell) - the `start` four_numbers / dd_pct_peak was given - "
                    "and this record is checked against the real one"
                    % (rec["ddpct"], rec["max_dd_usd"], rec["start_usd"],
                                      ddpct_max - DDPCT_BOUND_SLACK, DEFAULT_START_USD))
        _refuse("ddpct %r is impossible beside a worst drawdown of $%.2f on a $%.2f account: that is a "
                "dollar figure in the percent field, or two figures off different curves. The equity "
                "high starts AT the account and only rises (augur_engine.drawdowns.dd_pct_peak), so "
                "the fall from a high is at most 100 x $%.2f / $%.2f = %.4f%% - and an account taken "
                "below zero still gets through on its own dollars, which is the over-100%% reading"
                % (rec["ddpct"], rec["max_dd_usd"], rec["start_usd"], rec["max_dd_usd"],
                   rec["start_usd"], ddpct_max - DDPCT_BOUND_SLACK))
    # A zero percent beside a real dollar drawdown is impossible - EXCEPT by rounding: dd_pct_peak
    # rounds to 4 dp while DD5 rounds to the cent, so a $0.01 fall on $100k measures 0.0% beside
    # dd5 $0.01. The measured path must never refuse its own four_numbers output, so the clause fires
    # only above that rounding floor. The dollars are not turned into a percent here (the house rule:
    # a percentage is never derived from dollars) - they only say whether a 0 could be rounding.
    if rec["dd5"] > 0 and rec["ddpct"] <= 0 and \
            100.0 * rec["dd5"] / rec["start_usd"] > DDPCT_ROUNDING_FLOOR:
        _refuse("ddpct is 0 but the stretch drew down $%.2f on a $%.2f account - a curve with a dollar "
                "drawdown that size has a percent drawdown too (only a fall under %.5f%%, which is "
                "dd_pct_peak's 4-dp rounding, reads as a flat 0). Take it from "
                "augur_engine.drawdowns.dd_pct_peak, never from dollars / the starting account"
                % (rec["dd5"], rec["start_usd"], DDPCT_ROUNDING_FLOOR))
    if rec["dd5"] > 0 and rec["roc30k"] is None:
        _refuse("roc30k is null but the stretch drew down $%.2f - null is for a curve that never draws "
                "down and so has no ROC @ $30k. A run with a drawdown and no ROC cannot go on the "
                "scatter at all" % rec["dd5"])
    # THE MIRROR OF THE CLAUSE ABOVE, and the same reason: a stretch that drew down HAS a losing day,
    # so four_numbers' Sortino denominator sqrt(mean(min(x,0)^2)) is positive and its sortino is not
    # None (measured over 400 random daily series: 0 counterexamples with dd5 > 0). Without this a
    # record reaches the scatter carrying THREE of the four numbers, and the plot cannot say so.
    if rec["dd5"] > 0 and rec["sortino"] is None:
        _refuse("sortino is null but the stretch drew down $%.2f - null is for a curve where NO day "
                "loses, and a curve that drew down has one. The four numbers travel together; three "
                "of them is not a row on the scatter" % rec["dd5"])
    if rec["cost_pt"] is not None and rec["cost_pt"] < 0:
        _refuse("cost_pt is the round-trip cost in POINTS, which is not negative, got %r" % (rec["cost_pt"],))
    if rec["win_start"] and rec["win_end"] and rec["win_end"] <= rec["win_start"]:
        _refuse("the data window ends on or before it starts (%s..%s)" % (rec["win_start"], rec["win_end"]))
    if (rec["win_start"] is None) != (rec["win_end"] is None):
        _refuse("the data window needs both ends or neither (got %s..%s)" % (rec["win_start"], rec["win_end"]))
    if None not in (rec["roc30k"], rec["net_usd"], rec["years"]) and (rec["max_dd_usd"] or 0) > 0:
        want = 30.0 * (rec["net_usd"] / rec["years"]) / rec["max_dd_usd"]
        if abs(want - rec["roc30k"]) > ROC_IDENTITY_TOL * max(1.0, abs(want)):
            _refuse("roc30k %.3f is not 30 x (net $%.2f / %.3f years) / worst drawdown $%.2f = %.3f. "
                    "Every producer in the repo uses that identity, so these figures came off "
                    "different curves - one of them is measured on rows the others are not"
                    % (rec["roc30k"], rec["net_usd"], rec["years"], rec["max_dd_usd"], want))


# ================================================================================ the append
def append_record(rec, records_dir=None, timeout=LOCK_WAIT_SECONDS):
    """Append one record as one JSONL line, under an OS lock. Returns the file it landed in.

    allow_nan=False is the backstop behind _num: json's default would write a bare NaN / Infinity,
    which no JSON reader accepts, so a line like that would be lost at sync time rather than here."""
    path = record_path(rec["lane"], rec["ts"], records_dir)
    try:
        line = json.dumps(rec, allow_nan=False)      # built BEFORE the lock: nothing fails mid-append
    except ValueError as e:
        _refuse("the record is not JSON (%s)" % e)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with _os_lock(path + ".lock", timeout) as held:
        if not held:
            _refuse("another lane held the append lock on %s for %.0f s - nothing written"
                    % (os.path.basename(path), timeout))
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())                     # a run finishing is often a box about to sleep
    return path


def write_record(lane, where, stage, *, records_dir=None, strict=False,
                 lock_timeout=LOCK_WAIT_SECONDS, **kw):
    """Build and append one record. Returns the file it landed in, or None when it was refused.

    THE FORGIVING DEFAULT IS THE POINT (rule: never raise into the caller's own save path). The
    caller is a harness tail - the line after the run's own results have been saved - so a refused
    record writes one line to stderr and returns None. strict=True re-raises instead, which is what
    the tests use; the `except Exception` is deliberately broad for the same reason the default is
    forgiving, and strict mode is how a real bug in here stays visible."""
    try:
        rec = build_record(lane, where, stage, **kw)
        return append_record(rec, records_dir=records_dir, timeout=lock_timeout)
    except RunRecordError as e:
        if strict:
            raise
        sys.stderr.write("[run-record] refused: %s\n" % e)
        return None
    except Exception as e:                           # noqa: BLE001 - a records writer never kills a run's save path
        if strict:
            raise
        sys.stderr.write("[run-record] refused: unexpected %s: %s\n" % (type(e).__name__, e))
        return None


# ================================================================================ CLI
def daily_from_csv(path):
    """(date, $) pairs from a two-column CSV, a header row skipped when its second field is not a
    number. For a lane that has its daily series on disk rather than in hand."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for n, r in enumerate(csv.reader(f), 1):
            if not r or not str(r[0]).strip():
                continue
            if len(r) < 2:
                _refuse("%s line %d has one column - the file is 'date,dollars' a day" % (path, n))
            try:
                v = float(str(r[1]).strip())
            except ValueError:
                if n == 1:
                    continue                         # a header
                _refuse("%s line %d: %r is not a dollar figure" % (path, n, r[1]))
            rows.append((str(r[0]).strip(), v))
    if not rows:
        _refuse("%s has no rows" % path)
    return rows


def _flag_one_episode(s):
    t = str(s).strip().lower()
    if t in ("true", "1", "yes", "y"):
        return True
    if t in ("false", "0", "no", "n"):
        return False
    if str(s).strip().upper() == LAB_NOT_TESTABLE:
        return LAB_NOT_TESTABLE
    raise argparse.ArgumentTypeError("one-episode is true / false / %r" % LAB_NOT_TESTABLE)


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lane", required=True, help="the chat-inbox lane name, verbatim")
    ap.add_argument("--where", required=True, choices=list(WHERE))
    ap.add_argument("--stage", required=True, choices=list(STAGES))
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--family", required=True)
    ap.add_argument("--instrument", required=True)
    ap.add_argument("--timeframe", required=True)
    ap.add_argument("--daily-csv", help="'date,dollars' a day, EVERY day of the stretch (zero days "
                                        "included): the four numbers are measured from it")
    ap.add_argument("--roc30k", type=float, help="handed-in instead of --daily-csv: ROC %%/yr at a $30k drawdown")
    ap.add_argument("--dd5", type=float, help="DOLLARS: the average of the 5 deepest episodes")
    ap.add_argument("--ddpct", type=float, help="percent from the equity HIGH (13.09 means 13.09%%)")
    ap.add_argument("--sortino", type=float, help="DAILY, zero days counted - never per trade")
    ap.add_argument("--one-episode", type=_flag_one_episode,
                    help="the worst episode is more than 1.3x DD5: true / false / %r" % LAB_NOT_TESTABLE)
    ap.add_argument("--trades", type=int, required=True)
    ap.add_argument("--gross-pt", type=float, help="points per round trip")
    ap.add_argument("--cost-pt", type=float, help="points per round trip")
    ap.add_argument("--net-usd", type=float)
    ap.add_argument("--max-dd-usd", type=float)
    ap.add_argument("--years", type=float)
    ap.add_argument("--win-start", help="the DATA window start, YYYY-MM-DD")
    ap.add_argument("--win-end")
    ap.add_argument("--start-usd", type=float, default=None,
                    help="the account the DD %% was measured on (default %s). Left out beside "
                         "handed-in numbers it is an ASSUMPTION about someone else's run, so a DD %% "
                         "that the assumed account would make impossible asks for this flag instead"
                         % DEFAULT_START_USD)
    ap.add_argument("--run-id", help="the engine run number, when the run has one")
    ap.add_argument("--ledger-row", help="e.g. 2.195")
    ap.add_argument("--sha", help="the CODE commit sha (default: this checkout's HEAD)")
    ap.add_argument("--note", default="")
    ap.add_argument("--verdict", help="PASS / FAIL / HOLDS / DEAD / crown ... - needs --prereg (board C8)")
    ap.add_argument("--prereg", help='a LOCKED prereg id (tools/prereg_lock.py lock <file>), or "none - exploratory"')
    ap.add_argument("--run-start", help="when the run started, 'YYYY-MM-DD HH:MM' local or ISO (default: --ts)")
    ap.add_argument("--ts", help="'YYYY-MM-DD HH:MM' local (default: now)")
    ap.add_argument("--host", help="default: EDGELOG_HOST_ID else this hostname")
    ap.add_argument("--records-dir", help="default: EDGELOG_RUN_RECORDS else <EDGELOG_HOME>/run_records")
    ap.add_argument("--dry", action="store_true", help="print the record, write nothing")
    ap.add_argument("--strict", action="store_true",
                    help="exit 2 on a refusal. WITHOUT it a refusal prints to stderr and still exits "
                         "0, so a lane tail calling this from a shell cannot die of a records write")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    handed = dict(roc30k=a.roc30k, dd5=a.dd5, ddpct=a.ddpct, sortino=a.sortino,
                  one_episode=a.one_episode, net_usd=a.net_usd, max_dd_usd=a.max_dd_usd,
                  years=a.years, win_start=a.win_start, win_end=a.win_end)
    kw = dict(strategy=a.strategy, family=a.family, instrument=a.instrument, timeframe=a.timeframe,
              trades=a.trades, gross_pt=a.gross_pt, cost_pt=a.cost_pt, start_usd=a.start_usd,
              run_id=a.run_id, ledger_row=a.ledger_row, sha=a.sha, note=a.note, ts=a.ts, host=a.host,
              verdict=a.verdict, prereg=a.prereg, run_start=a.run_start)
    try:
        if a.daily_csv:
            if any(v is not None for k, v in handed.items() if k in REQUIRED_NUMBERS):
                _refuse("--daily-csv measures the four numbers; do not hand them in as well")
            kw["daily"] = daily_from_csv(a.daily_csv)
            kw["years"] = a.years
        else:
            kw["numbers"] = {k: v for k, v in handed.items() if v is not None}
        if a.dry:
            rec = build_record(a.lane, a.where, a.stage, **kw)
            print(json.dumps(rec, allow_nan=False, indent=1))
            print("[run-record] DRY - would append to %s" % record_path(rec["lane"], rec["ts"], a.records_dir))
            return 0
        # strict=True: a human (or a test) at a prompt wants to be told. The lane tail's protection is
        # the exit code below, not a swallowed refusal - the reason always reaches stderr.
        print("[run-record] appended to %s"
              % write_record(a.lane, a.where, a.stage, records_dir=a.records_dir, strict=True, **kw))
        return 0
    except RunRecordError as e:
        sys.stderr.write("[run-record] refused: %s\n" % e)
        return 2 if a.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
