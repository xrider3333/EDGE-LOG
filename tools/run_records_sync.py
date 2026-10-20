# -*- coding: utf-8 -*-
"""RUN RECORDS SYNC - put the lane, lab and box runs on the COMPARE scatter (owner ask 2026-10-18, W47).

THE GAP THIS CLOSES. A run on the runner writes its own doc in users/{uid}/runs, so the board and the COMPARE
scatter find it with no help from anyone. A lane run (a research driver inside a chat session), a lab run and a box
run write nothing there - and the owner asked that every run of the past month be visible on COMPARE "wherever it
ran". So each lane appends ONE JSON object per finished run to <EDGELOG_HOME>/run_records/<lane>_YYYYMM.jsonl - a
plain append, no credentials and no Firestore in the lane, which is what tools/run_record.py does - and this tool,
on the runner host and on a timer, uploads the new lines to users/{uid}/research_runs, where the web app plots them
beside the engine runs.

    python tools/run_records_sync.py                        DRY (the default): says exactly what would go up
    python tools/run_records_sync.py --write                 upload the new lines and update the marker
    python tools/run_records_sync.py --dir D:\\records --write
    python tools/run_records_sync.py NOISE_202610.jsonl --recheck --write   repair: ignore the marker for that file
    --marker PATH  where the marker lives (default: <dir>/.run_records_sync.json, beside the records)
    exit 0 = clean, 1 = the pass could not run, 2 = the pass ran and refused at least one line.

THE RECORD SCHEMA IS FROZEN (MANAGER #127 plus the owner's addendum #1447). This tool validates and uploads it; it
never computes a number and never repairs a line. One JSON object per line:

    ts           when it ran, STORED as "YYYY-MM-DD HH:MM" LOCAL - the same shape api/runner.py:1632 stamps
                 on a run doc. Written in that shape, or as "YYYY-MM-DD HH:MM:SS", or "YYYY-MM-DD" (midnight),
                 or ISO 8601 with a T and an optional offset ("2026-09-26T11:06:38-07:00"): all four NORMALISE
                 to the stored shape rather than being refused (see _norm_ts for why the shape matters)
    lane         the chat-inbox lane name, e.g. "STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y"
    host         the lane's own EDGELOG_HOST_ID, else platform.node() (api/qqq_exec.py's host_id rule)
    where        runner | lane | lab | box
    strategy, family, instrument, timeframe    strings
    stage        IS | WF | LB | preWF | forward
    roc30k       ROC %/yr at a $30k worst drawdown (the ONE yardstick)
    dd5          DOLLARS: the average depth of the 5 deepest drawdown episodes
    ddpct        percent from the HIGH - 13.09 means 13.09%, never a dollar figure
    sortino      DAILY, zero days counted, never per trade
    trades       int
    gross_pt, cost_pt    points per round trip
    one_episode  BOOLEAN: the worst episode is more than 1.3x DD5
    ledger_row   e.g. "2.195", or null
    run_id       the engine run number when there is one, else null
    sha          the CODE commit sha - NOT a hash of the line
    note         one short free-text line
    start_usd    the account dd_pct_peak was computed on (default 100000 when the line leaves it out)
    net_usd, max_dd_usd, years, win_start, win_end    the DATA window dates are "YYYY-MM-DD"
    schema_v     1

(The addendum calls those last ones "five additive fields" and then names six; win_start / win_end are one window,
which is how that adds up. All of them are read here, nothing is invented.)

AN ABSENT FIGURE COSTS ONE AXIS; A WRONG FIGURE COSTS THE CHART. That asymmetry is the whole validation rule
here, and it is what the parent corrected on 2026-10-19 (W47): the first pass of this tool refused a line for
every figure it did not carry, and over the seven lanes' 1,199 real records that refused 1,164 of them - 86% of
the month - almost all of it for a null. THE PAGE IS BUILT FOR THE NULL. Every figure a research row puts on the
board is read through `(x!=null&&isFinite(+x))?+x:null` (index.html, the _recRows builder), the column dashes what
it does not have, and the line under the chart names what is missing. So a missing number costs the owner ONE AXIS
of ONE row, while a refused line costs him the whole run - it is not on the scatter at all, and nothing on screen
says it ever existed. Refusing for absence buys nothing and pays the worse price, every time.

So: a line must carry the few fields that PLACE it - ts, lane, where, stage, family, and at least one figure the
chart can put on an axis - and EVERYTHING ELSE may be absent or null and uploads as null. A missing `strategy`
beside a `family` is a run with a less specific name, not a run that did not happen. What stays refused is a
figure that is THERE AND WRONG: a lie the chart would draw, which no dash can take back. Each of those refusals
is an INVARIANT of augur_engine.drawdowns.four_numbers (MANAGER #170), the one producer of these figures, and
every one of them is stated below beside the two readings it compares.

AND A RULE NEVER FIRES FOR WANT OF ITS OWN INPUT. Every check that compares two figures is guarded on BOTH being
present: where one of them is absent the rule simply does not apply, because an invariant between a number and a
null is not a violated invariant - it is an unasked question. That is the mistake that cost the most lines in the
first pass: `roc30k is null but the stretch drew down` and `sortino is null but the stretch drew down` read a hole
in the row as a contradiction and threw the run away over an axis the page would have dashed.

IDEMPOTENT BY CONTENT. The document id is "rr_" plus the first 24 hex characters of the sha256 of the record's
material content, so THE CONTENT IS THE IDENTITY: a second pass over the same file computes the same id and writes
the same bytes, and a line that changed gets a new id and a new row rather than quietly overwriting the old one. A
local marker file beside the records remembers {doc_id: digest} already uploaded, so a steady state does not even
open a Firestore client - no credential read, no gRPC channel, no quota. The shape is api/nt_sync.py sync_trades's
(content hash, local marker, batched merge write); the one difference is that this tool never reads the collection
back, because a lost marker can only cost a re-upload of byte-identical content.

WHAT IT REFUSES, per line, with the line number and the reason. Every item is a WRONG value, never an absent one:

    a line that is not one JSON object               there is no record to read
    a field the frozen schema does not have          MANAGER #127; a typo'd key silently loses its figure
    an unknown `where` or `stage`                    the page BUCKETS rows by both; an unknown one is mis-bucketed
    no ts / lane / where / stage / family            nothing to place the row by
    no plotted figure at all                         no roc30k, and no net_usd with a max_dd_usd beside it
    a `ts` in no shape this tool can read            it is normalised where it can be - see _norm_ts
    a `sha` that is not a commit sha                 64 hex is a hash of the LINE, filed under no commit
    dollars in the `ddpct` percent field             ddpct <= 100 x max_dd_usd / start_usd, else the blunt bar
    a percent in the `dd5` DOLLARS field             dd5 >= max_dd_usd / 5: DD5 averages at most 5 depths and the
                                                     deepest of them IS max_dd, so it can never be a fifth of it
    a `dd5` deeper than `max_dd_usd`                 the average of the 5 worst cannot beat the worst
    a zero `ddpct` beside a real dollar drawdown     a curve that fell in dollars fell in percent too
    a `one_episode` that is not a boolean            1 / 0 / "true" tag the wrong rows downstream
    a `one_episode` that contradicts its own numbers the flag IS the max_dd > 1.3 x dd5 test, and both are here
    a `run_id` of about 1.79e9                       the runner's PROVISIONAL int(time.time()), re-saved later
    a negative `trades`, a non-finite number, a number below its floor, a backwards data window

A refused line is reported and skipped; the rest of the file still goes up. The page PLOTS these rows, so a wrong
row is worse than a missing one - and a MISSING row is worse than a dashed figure, which is the other half of the
same sentence and the half this tool got wrong first.

THE ddpct CEILING IS THE RECORD'S OWN DOLLAR DRAWDOWN (settled by the parent, W47, 2026-10-18; it was a flat
1000 while the two halves of W47 were still arguing 100 against 1000). THE INVARIANT: dd_pct_peak's high-water
mark starts at start_usd and only rises, so the worst fall it can report is the dollar fall over the smallest peak
there can be - ddpct <= 100 * max_dd_usd / start_usd. THE MEASUREMENT: over 400 random daily series straight
through augur_engine.drawdowns.four_numbers the largest excess over that bound was +0.000044, which is
dd_pct_peak's own rounding to 4 dp - hence the cent of slack (DDPCT_BOUND_SLACK, the writer's own figure).

The bound does NOT cap the reading the engine's own docstring defends. dd_pct_peak is deliberately uncapped
because an account that fell below zero really did fall more than 100% from the high before it, and a record of
THAT run is exactly the row the owner asked to be able to see: a $100k account taken $100k below its start reads
ddpct 200, and the bound there is 200 too, because the high-water mark never moved off the start. What the ceiling
refuses is the unit mistake it exists for - dollars in the percent field, which reads hundreds of times the bound -
and a percent and a dollar drawdown measured on two different curves, which a flat number let through. A record
that carries no max_dd_usd (the lab shape) has nothing to derive the bound from, so the flat DDPCT_ABSURD of
tools/run_record.py still stands there. The watch-row rule is untouched - a lane hands that figure in by hand, and
tools/runboard_watch.py's 0-100 is the right mistake-catcher there.

SAFETY. DRY by default, with an explicit --write (house rule for anything that writes to Firestore). Credentials
come from tools/runboard_watch.py's real_client() and UID - the one lookup every tool shares, which is why
tools/run_exposure.py imports it as `rw` too; nothing here hardcodes a credential path the way
tools/research_beacon.py:35 does, because that path does not exist in a git worktree. No credential value is ever
printed, logged or written.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)   # appended, not inserted: run through run_shared.py the SHARED checkout must stay first

import tools.runboard_watch as rw   # noqa: E402  (UID, real_client, ToolError - the one credential lookup)
from api.util import json_safe      # noqa: E402  (house rule: everything bound for Firestore goes through it)

ToolError = rw.ToolError
COLLECTION = "research_runs"          # users/{uid}/research_runs - the web app plots these beside users/{uid}/runs
SCHEMA_V = 1
MARKER_NAME = ".run_records_sync.json"
MARKER_RETRIES = 12                   # module level so a test can turn the Windows retry loop down to nothing
MARKER_SLEEP = 0.05


def records_root():
    """<EDGELOG_RUN_RECORDS, else EDGELOG_HOME, else C:\\EdgeLog>\\run_records - the SAME lookup the lane-side
    writer tools/run_record.py records_root() does, read at CALL time for the same reason: the two halves of this
    pipeline have to agree about where the records live even when the owner moves them with an env var.

    api/qqq_exec.py owns the EDGELOG_HOME rule; it is repeated rather than imported because importing that module
    builds a live broker order adapter and a price stream, which a records sync has no business loading."""
    override = os.environ.get("EDGELOG_RUN_RECORDS")
    if override and override.strip():
        return override.strip()
    home = os.environ.get("EDGELOG_HOME") or (r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog")
    return os.path.join(home, "run_records")


# ── the frozen line schema (MANAGER #127 + addendum #1447) ───────────────────────────────────
WHERE = ("runner", "lane", "lab", "box")
STAGES = ("IS", "WF", "LB", "preWF", "forward", "full", "preLB")
# MEASURED on the seven lanes' 1,199 real lines (2026-10-19): 58 carry stage FULL and 15 carry preLB. Both
#   name a real stretch - FULL is the whole run read as one, preLB is everything before the lockbox - so
#   refusing them kept 73 honest runs off the board over spelling. They are first-class values with their own
#   MARKS on the page (index.html _reRecMark / _reRecStageNm), never mapped onto one of the five: a shape that
#   claims the wrong stretch is worse than a new shape. The page fills no stretch COLUMN for either, so their
#   money stays the row total and is never added into a walk-forward figure.
STAGE_CANON = dict((s.lower(), s) for s in STAGES)
TS_FMT = "%Y-%m-%d %H:%M"             # what is STORED: local wall clock, as api/runner.py:1632 stamps a run doc
# the shapes a lane may WRITE, all normalised to TS_FMT. A clock finer than the minute is truncated and a bare day
#   reads as midnight, which is what the runner's own %H:%M stamp already does to its seconds.
TS_READ = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
TS_OFFSET = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")   # the tail of an ISO 8601 stamp: "...T11:06:38-07:00"
DAY_FMT = "%Y-%m-%d"
# the text fields this tool checks as text; the ones that may be blank are in MAY_BE_BLANK (sha has its own rule)
TEXT_REQUIRED = ("lane", "family")
# A LABEL THE LANE DID NOT WRITE IS A null, NOT A REFUSAL. `strategy` is the one worth spelling out: 4 of the
#   1,199 real records name only their family, and a run whose name is "BOOK" instead of "BOOK #436" is a run
#   with a less specific name - the page already falls back to the family for the row's name
#   (`d.strategy||d.family||'a lane run'`), so there is nothing here for a refusal to protect. A BLANK string
#   reads as the same null: a lane that wrote "" had nothing to write, and the page dashes what it does not have.
TEXT_OPTIONAL = ("host", "strategy", "instrument", "timeframe", "note")
TEXT = TEXT_REQUIRED + TEXT_OPTIONAL
MAY_BE_BLANK = ("note",)
# A run number is a small integer out of the runner's own counter - today's newest is 491. api/runner.py falls
#   back to int(time.time()), about 1.79e9, when the run-id counter cannot be read, and repair_provisional_run_ids
#   later re-saves that run under its real number: a row filed against the PROVISIONAL id points at a run number
#   that never exists, forever. The ceiling is the lane-side writer's own (tools/run_record.py MAX_RUN_ID) - ~200x
#   headroom over the newest real run, and still 17,000x below any provisional id.
MAX_RUN_ID = 100_000
# ddpct's ceiling comes off the record's OWN dollars - 100 x max_dd_usd / start_usd - and these three are the
#   lane-side writer's own constants (tools/run_record.py DDPCT_BOUND_SLACK / DDPCT_ABSURD /
#   DDPCT_ROUNDING_FLOOR), restated so the two halves of this pipeline refuse the same lines. A cent of slack is
#   dd_pct_peak's rounding to 4 dp (the worst measured excess over the bound was +0.000044). The flat bar is the
#   backstop for a record that hands over no max_dd_usd to derive a bound from. And under the rounding floor a
#   zero percent beside a nonzero dd5 is that same 4-dp rounding of a sub-cent fall, not an impossible pair ($0.01
#   on $100k is 0.00001%): the measured path must never refuse four_numbers' own output.
DDPCT_BOUND_SLACK = 0.01
DDPCT_ABSURD = 1000.0
DDPCT_ROUNDING_FLOOR = 0.00005
# DD5's FLOOR comes off the same record's own worst drawdown, and it is the dd5 twin of the ddpct ceiling: it
#   catches a PERCENT written into the dollars field. THE INVARIANT: dd5 averages the depths of at most 5 episodes
#   and the deepest of them IS max_dd, so dd5 >= (max_dd + 0 + 0 + 0 + 0) / 5 = max_dd / 5. MEASURED over the same
#   400 random daily series straight through augur_engine.drawdowns.four_numbers, the smallest dd5 / max_dd ratio
#   was 0.2 - the bound, reached exactly, by a curve with one episode (tests/test_run_records_sync.py). A 17.68
#   written where $22,351 belongs is 0.08% of max_dd and nowhere near a fifth of it, so it is caught; the cent of
#   slack is there because dd5 and max_dd_usd both arrive already rounded to the cent.
DD5_EPISODES = 5
DD5_FLOOR_SLACK = 0.01
# every numeric field, with the FLOOR a reading of it cannot go below (None = any finite number). No field carries
#   a flat ceiling: ddpct's is DERIVED from the record's own max_dd_usd in validate(), because 100 * max_dd_usd /
#   start_usd is the real bound (see the ddpct paragraph above) and a flat number either refuses honest rows or
#   lets a mismatched pair through.
NUMBER = {"roc30k": None, "dd5": 0.0, "ddpct": 0.0, "sortino": None, "gross_pt": None, "cost_pt": 0.0,
          "start_usd": 0.01, "net_usd": None, "max_dd_usd": 0.0, "years": 0.0}
# THE FROZEN FIELD SET, in the order the schema lists it. Every one of these keys is in the uploaded document,
#   carrying null where the lane had nothing, so the page can tell NOT MEASURED from zero - a dash and a 0.00 are
#   different readings of a run, and the board must never print one for the other.
SCHEMA = ("ts", "lane", "host", "where", "stage", "strategy", "family", "instrument", "timeframe",
          "roc30k", "dd5", "ddpct", "sortino", "trades", "gross_pt", "cost_pt", "one_episode",
          "ledger_row", "run_id", "sha", "note", "start_usd", "net_usd", "max_dd_usd", "years",
          "win_start", "win_end", "schema_v")
# WHAT A LINE MUST CARRY WITH A VALUE, and it is a SHORT list on purpose: these are the fields that PLACE a row,
#   not the fields that describe it. ts puts it in a month, where and stage put it in a bucket, lane says whose it
#   is, and family is the row's name of last resort. Take any one of them away and there is no row to draw - which
#   is the test a required field has to pass, and the test `dd5`, `ddpct`, `trades`, `sha`, `host`, `strategy`,
#   `instrument` and `timeframe` all fail: the page dashes every one of them.
REQUIRED = ("ts", "lane", "where", "stage", "family")
# ...PLUS ONE FIGURE THE CHART CAN PLACE. This is the one absence that really does cost the whole row, so it is
#   the one absence still refused: roc30k is the house's ONE YARDSTICK and the scatter's x axis, and net_usd is
#   the money axis the research rows are laid out on today (index.html: `if(net==null)return;`). A row with
#   neither has no coordinate on any axis the board draws - it would upload, occupy a document, and appear
#   nowhere. net_usd counts only WITH THE DOLLARS TO GO WITH IT: a net on its own cannot be read without the
#   drawdown it was earned against, and max_dd_usd is what the row's own dd column plots.
PLOT_ALTERNATIVES = (("roc30k",), ("net_usd", "max_dd_usd"))
# EVERYTHING ELSE may be absent or present-and-null, and uploads as null. The lane-side writer
#   tools/run_record.py really does write those nulls - roc30k and sortino have no value for a curve that never
#   draws down (its _undefined_to_none), gross_pt / cost_pt / net_usd / max_dd_usd / years are null when the tail
#   the lane handed in did not hold them, ledger_row and run_id are null for a round that has neither, and
#   one_episode is null for the lab's "NOT TESTABLE" (one episode cannot be compared with others, and that is not
#   False, which would claim the ROC was tested - MANAGER #160a, tools/qwen_lab.py) - and the seven lanes' own
#   1,199 records write far more of them than that: dd5 on 590 lines, ddpct on 411, trades on 649, sha on 798.
NULLABLE = tuple(k for k in SCHEMA if k not in REQUIRED)
DEFAULTS = {"start_usd": 100000.0,    # the $100k house account dd_pct_peak is computed on
            "note": "", "schema_v": SCHEMA_V}
KNOWN = set(SCHEMA)
# the fields the SYNC adds to the document. They are deliberately NOT in KNOWN: a line that carries one is
#   refused as an unknown field, so a lane cannot forge its own provenance. `timestamp` is the normalised ts under
#   the name the page's month query actually filters on - see payload().
SYNC_FIELDS = ("timestamp", "sync_file", "sync_at")

DOC_ID_PREFIX = "rr_"                 # as api/nt_sync.py prefixes its trade docs "nt_": recognisable in the console
DOC_ID_HEX = 24                       # see doc_id_for() for why 24
BATCH_DOCS = 400                      # Firestore's hard cap is 500 writes a batch; api/nt_sync.py commits at 400
BATCH_BYTES = 9_000_000               # Firestore's hard cap is 10 MiB a commit (a startup sync died at 11,534,336)
SIZE_REFUSE = 900_000                 # as tools/run_exposure.py: Firestore's own per-document cap is 1,048,576 B
INDEX_REFUSE = 38_000                 # Firestore's own cap is 40,000 index entries a document
PREVIEW_LINES = 20                    # how many records the report lists one by one before it just counts them


class Refusal(Exception):
    """ONE line this tool will not upload, carrying the plain reason the lane has to fix.

    A refusal is always per line: it is reported with its line number and skipped, and every other line in the file
    still goes up. It is never a crash and never a silent drop - the COMPARE page plots these rows, so a wrong row
    is worse than a missing one."""


# ── validating one record against the frozen schema ──────────────────────────────────────────
def _show(v):
    """A value as it should read inside a refusal: short, quoted, never a wall of text."""
    try:
        s = json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = repr(v)
    return s if len(s) <= 60 else s[:57] + "..."


def _number(rec, key):
    """One numeric field as a float, not below NUMBER[key]'s floor.

    A field whose ceiling depends on another reading of the same curve - ddpct, bounded by the record's own
    max_dd_usd - is checked as a PAIR RULE in validate(), where both figures are in hand.

    json.loads accepts NaN and Infinity; Firestore rejects them and a scatter cannot plot them (api/util.json_safe
    turns them into None, which would put a hole in the row instead of saying so), so a non-finite reading is a
    refusal here, where it still has a line number. A field that legitimately has no value arrives as null, which
    the caller handles before this is reached."""
    v = rec.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Refusal("%s must be a number, got %s" % (key, _show(v)))
    v = float(v)
    if v != v or v in (float("inf"), float("-inf")):
        raise Refusal("%s is not a finite number (%s) - a figure that does not exist is written as null"
                      % (key, _show(rec.get(key))))
    lo = NUMBER[key]
    if lo is not None and v < lo:
        raise Refusal("%s is %s - it cannot be below %s" % (key, _show(v), lo))
    return v


def _text(rec, key):
    """One REQUIRED text field: it has to be there, and it has to say something."""
    v = rec.get(key)
    if not isinstance(v, str):
        raise Refusal("%s must be a string, got %s" % (key, _show(v)))
    v = v.strip()
    if not v and key not in MAY_BE_BLANK:
        raise Refusal("%s is blank" % key)
    return v


def _opt_text(rec, key):
    """One OPTIONAL label: absent, null or blank all read as None, and the page dashes what it does not have.

    A BLANK IS THE SAME READING AS AN ABSENCE - a lane that wrote "" had nothing to write - so it is normalised
    to null here rather than refused. That is the same normalising the strip and the float conversion are, and it
    runs before the content hash for the same reason: a lane that wrote "" last week and left the key out this
    week recorded the same run, and must not land as a second row. A value that IS there must still be a string:
    an instrument of 5 is a lane writing a number into a name, which is a wrong value, not a missing one."""
    v = rec.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise Refusal("%s must be a string, got %s" % (key, _show(v)))
    v = v.strip()
    if not v:
        return "" if key in MAY_BE_BLANK else None
    return v


def _day(rec, key):
    v = _text(rec, key)
    try:
        datetime.datetime.strptime(v, DAY_FMT)
    except ValueError:
        raise Refusal('%s is %s - a data-window date is "YYYY-MM-DD"' % (key, _show(v))) from None
    return v


def _sha(rec):
    """The CODE commit sha, 7 to 40 hex characters, optionally marked dirty.

    The length rule also catches the one mistake the schema names outright: a sha256 of the line is 64 hex
    characters, so a lane that put the content hash here instead of `git rev-parse HEAD` is refused rather than
    quietly filed under a commit nobody can look up."""
    v = _text(rec, "sha")
    body = v[:-6] if v.lower().endswith(("-dirty", "+dirty")) else v
    ok = 7 <= len(body) <= 40 and all(c in "0123456789abcdefABCDEF" for c in body)
    if not ok:
        # IT IS A CAPTION, NOT A FIGURE, so an unusable one costs itself and not the run. MEASURED on the real
        #   lines (2026-10-19): 50 carry a 64-character content hash here instead of `git rev-parse HEAD`, 41 of
        #   them with a ROC @ $30k - refusing the record dropped 41 honest runs off the board to protect a field
        #   nobody plots. The sha is stored null, the page dashes it, and the pass REPORTS the line and the reason
        #   so the lane can fix its writer (plan_file -> FileReport.gaps).
        return None
    return v


def _norm_ts(raw):
    """The stored "YYYY-MM-DD HH:MM", NORMALISED from any shape a lane really writes, or Refusal.

    WHY THE STORED SHAPE MATTERS, and why this is a normaliser and not a refusal. The page finds a month by a
    LEXICOGRAPHIC RANGE ON THE STRING - index.html's _monQuery sends GREATER_THAN_OR_EQUAL "2026-10-01" and
    LESS_THAN "2026-11-01" as a stringValue against the timestamp field, and orderBy DESCENDING on the same
    field - exactly as it does for a run document, whose timestamp is time.strftime("%Y-%m-%d %H:%M") off the
    runner's own clock (api/runner.py:1632). A string range and a string sort are only meaningful where every
    row carries ONE shape. MEASURED, because the obvious claim is wrong: "2026-10-18T14:44:14-07:00" DOES fall
    inside a whole-month bound, because its first ten characters are the date and the bounds stop there. What it
    does not survive is the ORDER - a space is 0x20 and a T is 0x54, so "2026-10-18 09:00" sorts BEFORE
    "2026-10-18T08:00:00-07:00" and the newest-first list puts an 08:00 run above a 09:00 one - nor any bound
    tighter than a month, where the eleventh character is what the comparison reaches. The frozen schema says
    this shape, the run documents carry this shape, and the page compares a research row and a run row on the
    same string: so this is the shape that is stored. 676 of the seven lanes' 1,199 records are written as ISO
    and 275 as a bare day; the first pass of this tool refused 139 of them outright - over a T and a space.

    WHAT IS READ: the stored shape itself, "YYYY-MM-DD HH:MM:SS" (the seconds are truncated, which is what the
    runner's own %H:%M stamp does to its seconds too), "YYYY-MM-DD" (midnight - a lane that recorded the day and
    not the hour), and ISO 8601 with a T, with or without fractional seconds, with or without an offset.

    WHAT IS NOT DONE: the wall clock is never MOVED. An offset is dropped, not converted. The figure a lane
    writes with datetime.now(tz).isoformat() already IS that lane's local wall clock - which is what the stored
    shape carries, since a run document's timestamp names no zone at all - so keeping the clock and dropping the
    offset preserves the reading, while re-zoning it into the syncing host's own zone would both move a stamp
    nobody asked to move AND make the stored string, and so the content-hash document id, depend on which
    machine happened to run the pass. All 676 offsets in the real records are -07:00, the owner's own.
    """
    s = raw.strip().replace("T", " ", 1)
    m = TS_OFFSET.search(s)
    if m and ":" in s[:m.start()]:        # only strip a tail that follows a clock, so a bare day is left alone
        s = s[:m.start()].strip()
    if "." in s and ":" in s:             # ISO fractional seconds
        s = s.split(".", 1)[0].strip()
    for fmt in TS_READ:
        try:
            return datetime.datetime.strptime(s, fmt).strftime(TS_FMT)
        except ValueError:
            pass
    raise Refusal('ts is %s - a record\'s timestamp is local "YYYY-MM-DD HH:MM" (the shape the run docs carry '
                  'and the page filters a month on), or "YYYY-MM-DD HH:MM:SS", or "YYYY-MM-DD", or ISO 8601 '
                  'with an offset like "2026-09-26T11:06:38-07:00" - all of which are normalised to the stored '
                  'shape' % _show(raw))


def validate(rec):
    """The normalised record, or Refusal with the reason. Nothing is computed or repaired - only read and checked.

    Normalising (strip the strings, floats for the numbers) happens here and not at upload time because the content
    hash runs on the result: a lane writing 13 where it wrote 13.0 last week is the same reading of the same run and
    must not land as a second row."""
    if not isinstance(rec, dict):
        raise Refusal("a record is ONE JSON object per line, got %s" % _show(rec))

    sv = rec.get("schema_v", SCHEMA_V)
    if sv != SCHEMA_V or isinstance(sv, bool):
        raise Refusal("schema_v is %s - this tool only knows schema %d; a new field needs a bumped schema_v and a "
                      "matching change here, never a quiet extra key" % (_show(sv), SCHEMA_V))
    unknown = sorted(set(rec) - KNOWN)
    if unknown:
        raise Refusal("field(s) the frozen schema does not have: %s (MANAGER #127; a sync-owned field like %s is "
                      "added here, never by the lane)" % (", ".join(unknown), SYNC_FIELDS[0]))
    if rec.get("ts") is None:
        raise Refusal("ts is missing - a record with no timestamp cannot be placed on the scatter")
    missing = sorted(k for k in REQUIRED if rec.get(k) is None)
    if missing:
        raise Refusal("missing required field(s): %s - and these five are the only ones. They are what PLACES "
                      "the row (the month, the bucket, the lane, the name); every other field in the schema may "
                      "be absent or null and uploads as null, because the page dashes a figure it does not have"
                      % ", ".join(missing))
    # the fields a line is allowed to leave out, filled in BEFORE the content hash runs: a line that spells
    #   start_usd 100000 out and one that leaves it to the default are the same reading of the same run
    rec = dict(rec)
    for k, v in DEFAULTS.items():
        if rec.get(k) is None:
            rec[k] = v

    out = {}
    out["ts"] = _norm_ts(_text(rec, "ts"))
    # WHERE AND STAGE ARE BUCKETS, NOT FIGURES, so an unknown one is a WRONG value and still refuses. The page
    #   maps the stage to the stretch field it fills (`_recF`: IS and preWF are in-sample money, WF is
    #   walk-forward, LB and forward are lockbox) and falls back to 'wf' for anything it does not know - so an
    #   unrecognised stage does not go missing, it lands in the WALK-FORWARD column and reads as the house
    #   yardstick. That is the one thing worse than not plotting the run. A stage the lanes really want (preLB,
    #   FULL) is a change to STAGES and to the page's own map, made once, by MANAGER - never by letting the
    #   string through here and hoping.
    out["where"] = _text(rec, "where")
    if out["where"] not in WHERE:
        raise Refusal("where is %s - it is one of %s" % (_show(out["where"]), " | ".join(WHERE)))
    # CASE IS NOT MEANING: a lane writing "wf" or "FULL" means WF and full. The spelling is canonicalised so
    #   the page's map (which is keyed on the canonical spelling) can never miss, and an unknown stage still
    #   refuses - the page fills no stretch column for a stage it does not know, but the TABLE still reads its
    #   stage text, and a stage nobody has defined is a word the owner cannot act on.
    _stg = _text(rec, "stage")
    out["stage"] = STAGE_CANON.get(_stg.lower(), None)
    if out["stage"] is None:
        raise Refusal("stage is %s - it is one of %s (case does not matter). An unknown stage is not dashed by "
                      "the page, it is bucketed as WALK-FORWARD, so the row would read as the house yardstick "
                      "when it is not" % (_show(_stg), " | ".join(STAGES)))
    for k in TEXT_REQUIRED:
        out[k] = _text(rec, k)
    for k in TEXT_OPTIONAL:
        out[k] = _opt_text(rec, k)
    out["sha"] = _sha(rec) if rec.get("sha") is not None else None
    for k in NUMBER:
        out[k] = _number(rec, k) if rec.get(k) is not None else None

    # ONE FIGURE THE CHART CAN PLACE, and it is the only absence left that refuses a row. Everything above is
    #   where the row goes; this is whether there is anything to draw when it gets there. roc30k is the house's
    #   ONE YARDSTICK and the scatter's x axis; net_usd is the money the research rows are laid out on, and it
    #   counts only beside the max_dd_usd its own dd column plots. With neither, the document uploads, costs a
    #   write, and appears nowhere - which is not a dashed figure, it is an invisible run, and the owner would
    #   have no way to tell it from a run that was never recorded at all.
    if not any(all(out[k] is not None for k in alt) for alt in PLOT_ALTERNATIVES):
        raise Refusal("no figure the chart can place: roc30k is null, and there is no net_usd with a max_dd_usd "
                      "beside it either. Every other figure may be null - this one cannot, because a row with no "
                      "coordinate on any axis the board draws would upload and then appear nowhere. Give it the "
                      "ROC @ $30k, or the net dollars with the worst drawdown they were earned against")

    # THE DATA WINDOW. Each end is checked as a date where it is there, and ONE END ALONE NO LONGER REFUSES THE
    #   ROW: that was a refusal for an absence - the pair rule firing for want of its own input - and the window
    #   is not a plotted figure but a caption, which the page reads as a pair or not at all
    #   (`(d.win_start&&d.win_end)?{from,to}:null`), so a half-open window costs the caption and nothing else.
    #   What still refuses is a window that runs BACKWARDS, where both ends are in hand and contradict each
    #   other: that is a wrong value, and a reader would draw the run over negative time.
    for k in ("win_start", "win_end"):
        out[k] = _day(rec, k) if rec.get(k) is not None else None
    if out["win_start"] is not None and out["win_end"] is not None and out["win_start"] > out["win_end"]:
        raise Refusal("the data window runs backwards: win_start %s is after win_end %s"
                      % (out["win_start"], out["win_end"]))

    # trades is OPTIONAL now (550 of the 1,199 real records do not carry it, and the page dashes the column), so
    #   only a count that IS there is checked - and a negative one still refuses, because a trade count cannot be
    #   below zero and the row would read as a run that un-traded.
    trades = rec.get("trades")
    if trades is None:
        out["trades"] = None
    elif isinstance(trades, bool) or not isinstance(trades, int):
        raise Refusal("trades must be a whole number, got %s" % _show(trades))
    elif trades < 0:
        raise Refusal("trades is %d - a trade count cannot be negative" % trades)
    else:
        out["trades"] = trades

    # one_episode ABSENT reads as null, the same as the lab's NOT TESTABLE: a record that never mentions the flag
    #   did not compare the worst episode with the others, which is exactly what null says. The flag's own rule
    #   is unchanged - true, false or null, never 1 / 0 / "true", because the page tags rows by it.
    one = rec.get("one_episode")
    if one is not None and not isinstance(one, bool):
        # 1 / 0 / "true" all read as truthy-ish somewhere downstream and the page would tag the wrong rows
        raise Refusal("one_episode must be true, false or null, got %s - it is the flag itself, not the number "
                      "behind it" % _show(one))
    out["one_episode"] = one

    # THE RUN ID IS AN IDENTIFIER, NOT A FIGURE. 677 of the 1,199 real records carry it as a STRING - "#382" out
    #   of the BOOK ledger, "qlab-verify:20261017-1607-scalper:house" out of the lab, "DISC-bf-20260925-..." out
    #   of a backfill - because a lane run has no engine run number to give. Refusing those 677 rows would be the
    #   first pass's whole mistake in one field: nothing is PLOTTED from run_id (the page only prints " . run #N"
    #   when it reads as a number), so a label it cannot parse costs that caption and nothing more. The ONE check
    #   that has to survive is the PROVISIONAL id, and it is applied to the NUMBER a run_id reads as - whether it
    #   was written as 1760000000 or as the string "1760000000" - so quoting the figure cannot smuggle it past.
    rid = rec.get("run_id")
    if isinstance(rid, str) and not rid.strip():
        rid = None                        # a blank is an absence, as it is for every other label (_opt_text)
    num = None
    if rid is not None:
        if isinstance(rid, bool):
            raise Refusal("run_id is %s - it is the engine run number, a lane's own run id, or null" % _show(rid))
        if isinstance(rid, int):
            num = rid
        elif isinstance(rid, str):
            rid = rid.strip()
            body = rid[1:] if rid.startswith("#") else rid
            num = int(body) if re.fullmatch(r"\d+", body) else None    # None = an opaque label, nothing to bound
        else:
            raise Refusal("run_id is %s - it is the engine run number, a lane's own run id, or null" % _show(rid))
        if num is not None and num <= 0:
            raise Refusal("run_id is %s - it is the engine run number, or null when the run has none" % _show(rid))
        # rid > 0 was the only bound, so int(time.time()) uploaded as a run number. The ceiling is the writer's,
        #   in the writer's own words (tools/run_record.py _run_id): a record filed against a provisional id
        #   points at a run number the runner later replaces, and keeps pointing at it forever.
        if num is not None and num > MAX_RUN_ID:
            raise Refusal("run_id %d is not a plausible run number (1..%d; today's newest is 491). A run id of "
                          "about 1.79e9 is the runner's PROVISIONAL id, int(time.time()), handed out while "
                          "Firestore reads were failing - that run is re-saved under a different number, so a "
                          "record against this one would point at the wrong run forever. Pass the real number, "
                          "or null for a run that has none." % (num, MAX_RUN_ID))
    out["run_id"] = rid
    row = rec.get("ledger_row")
    if row is not None:
        if not isinstance(row, str):
            raise Refusal('ledger_row is %s - it is a ledger row like "2.195", or null' % _show(row))
        row = row.strip() or None         # a blank is an absence, as it is for every other label (_opt_text)
    out["ledger_row"] = row
    out["schema_v"] = SCHEMA_V

    # == THE PAIR RULES: two readings of the SAME curve that cannot both be true ============================
    # Every one of them is an invariant of augur_engine.drawdowns.four_numbers, the one producer of these figures
    #   (MANAGER #170), MEASURED over 400 random daily series straight through it (the measurement is re-run in
    #   tests/test_run_records_sync.py so the engine cannot drift out from under these rules). The lane-side
    #   writer tools/run_record.py _check_units already refuses these shapes; they are restated here because THIS
    #   is the last gate before the page plots the row, and a line can reach it from a lane that never ran the
    #   writer.
    #
    # EVERY RULE BELOW IS GUARDED ON BOTH OF ITS OWN FIGURES BEING PRESENT, and that guard is the correction of
    #   2026-10-19: a rule that fires because one side of it is NULL is not catching a contradiction, it is
    #   refusing a run for a figure the lane did not measure. An invariant between a number and a null is an
    #   unasked question, and the answer to an unasked question is not "refuse". Two refusals went entirely for
    #   that reason - a null roc30k and a null sortino beside a dollar drawdown - and between them they were a
    #   large part of the 1,164 lines the first pass threw away. A null roc30k is now dashed on the axis (and
    #   where it leaves the row with no figure at all, the PLOT_ALTERNATIVES check above is what says so, in
    #   those words); a null sortino is dashed in its column.
    if out["dd5"] is not None and out["max_dd_usd"] is not None:
        # DD5 averages the 5 deepest episodes and the deepest one IS the worst drawdown, so it can never be
        #   deeper (the same check tools/runboard_watch.py stretch_numbers makes on a research row's DD5)
        if out["dd5"] > out["max_dd_usd"] + 0.01:
            raise Refusal("dd5 $%s is deeper than max_dd_usd $%s - an average of the 5 worst episodes cannot be "
                          "deeper than the worst one, so the two came off different curves"
                          % (f"{out['dd5']:,.2f}", f"{out['max_dd_usd']:,.2f}"))
        # ...AND IT CANNOT BE A FIFTH OF IT EITHER, which is the dd5 twin of the ddpct ceiling below: dd5 averages
        #   at most 5 depths and one of them IS max_dd, so dd5 >= max_dd / 5 even when the other four are zero.
        #   What that catches is a PERCENT written into the dollars field - 17.68 where $22,351 belongs - which no
        #   floor of 0 can see, because a percent is a perfectly good small positive number. A curve with ONE
        #   episode sits exactly ON the bound (measured: the smallest dd5 / max_dd over 400 series was 0.2), so
        #   the comparison is strict and carries a cent of slack for the rounding both figures arrive with.
        floor = out["max_dd_usd"] / DD5_EPISODES
        if out["dd5"] < floor - DD5_FLOOR_SLACK:
            raise Refusal("dd5 $%s is less than a fifth of max_dd_usd $%s ($%s) - DD5 averages the depths of at "
                          "most %d episodes and the deepest of them IS the worst drawdown, so it can never be "
                          "that small. A figure this far below the dollars is a PERCENT in the dd5 dollars "
                          "field; the percent belongs in ddpct"
                          % (f"{out['dd5']:,.2f}", f"{out['max_dd_usd']:,.2f}", f"{floor:,.2f}", DD5_EPISODES))
    if out["ddpct"] is not None and out["max_dd_usd"] is not None:
        # THE CEILING COMES OFF THE RECORD'S OWN DOLLARS: dd_pct_peak's high-water mark starts AT start_usd and
        #   only rises, so every fall is measured against a peak >= start_usd and ddpct <= 100 x max_dd_usd /
        #   start_usd. An over-100% reading still gets through on its own dollars - which is why the bound is
        #   derived instead of picked - and only a figure that beats them is dollars in the percent field.
        #   start_usd is the schema's own default when the line leaves it out (the $100k house account
        #   dd_pct_peak is computed on), so the writer's "you did not pass start_usd" case has no twin here.
        bound = 100.0 * out["max_dd_usd"] / out["start_usd"]
        if out["ddpct"] > bound + DDPCT_BOUND_SLACK:
            raise Refusal("ddpct %s is impossible beside a worst drawdown of $%s on a $%s account: that is a "
                          "dollar figure in the percent field, or two figures off different curves. The equity "
                          "high starts AT the account and only rises (augur_engine.drawdowns.dd_pct_peak), so "
                          "the fall from a high is at most 100 x $%s / $%s = %.4f%% - and an account taken below "
                          "zero still gets through on its own dollars, which is the over-100%% reading"
                          % (_show(out["ddpct"]), f"{out['max_dd_usd']:,.2f}", f"{out['start_usd']:,.2f}",
                             f"{out['max_dd_usd']:,.2f}", f"{out['start_usd']:,.2f}", bound))
    elif out["ddpct"] is not None and out["ddpct"] > DDPCT_ABSURD:
        # nothing to derive a bound from (the lab shape writes no max_dd_usd), so the blunt bar is the backstop
        raise Refusal("ddpct is %s with no max_dd_usd beside it - that is a dollar figure in the percent field. "
                      "ddpct is the fall from the equity HIGH in percent (13.09 means 13.09%%); the dollars "
                      "belong in max_dd_usd, and a line that carries them is checked against its own account "
                      "instead of this %.0f bar" % (_show(out["ddpct"]), DDPCT_ABSURD))
    # A ZERO PERCENT BESIDE A REAL DOLLAR DRAWDOWN is impossible EXCEPT by rounding, and it is the one pair rule
    #   here that still fires on an absence-shaped reading - because a 0 is not an absence. It is a figure the
    #   lane WROTE, it will be drawn as "no fall from the high", and the run it describes fell. That is the whole
    #   distinction this tool now turns on: a null says not measured and is dashed, a 0 makes a claim. A ddpct
    #   the lane simply did not have arrives as null and is dashed with everything else. The dollars are not
    #   turned into a percent here (the house rule: a percentage is never derived from dollars) - they only say
    #   whether that 0 could be dd_pct_peak's 4-dp rounding of a sub-cent fall.
    if out["dd5"] is not None and out["dd5"] > 0 and out["ddpct"] is not None and out["ddpct"] <= 0 \
            and 100.0 * out["dd5"] / out["start_usd"] > DDPCT_ROUNDING_FLOOR:
        raise Refusal("ddpct is 0 but the stretch drew down $%s on a $%s account - a curve with a dollar "
                      "drawdown that size has a percent drawdown too (only a fall under %.5f%%, which is "
                      "dd_pct_peak's 4-dp rounding, reads as a flat 0; a percent the lane never measured is "
                      "written as null, which is dashed, not refused). Take it from "
                      "augur_engine.drawdowns.dd_pct_peak, never from dollars / the starting account"
                      % (f"{out['dd5']:,.2f}", f"{out['start_usd']:,.2f}", DDPCT_ROUNDING_FLOOR))
    # one_episode IS the schema's own test - the worst episode is more than 1.3x DD5 - and when all three figures
    #   are in the record a flag that contradicts them means one of the three is wrong and the row would mislead
    #   the page. Skipped when the flag is null (not testable) or when either dollar figure is absent: there is
    #   nothing to contradict then. Only a CLEAR contradiction is refused - within 1% of the 1.3x line either
    #   flag passes, because dd5 and max_dd_usd arrive already rounded to dollars.
    if out["one_episode"] is not None and out["dd5"] is not None and out["max_dd_usd"] is not None:
        line = 1.3 * out["dd5"]
        if abs(out["max_dd_usd"] - line) > 0.01 * max(1.0, line) \
                and (out["max_dd_usd"] > line) != out["one_episode"]:
            raise Refusal("one_episode is %s but max_dd_usd $%s is %s 1.3x DD5 ($%s) - the flag and its own two "
                          "numbers disagree" % (str(out["one_episode"]).lower(), f"{out['max_dd_usd']:,.0f}",
                                                "above" if out["max_dd_usd"] > line else "below", f"{line:,.0f}"))
    return out


# ── identity: the content IS the document id ─────────────────────────────────────────────────
def content_hash(rec):
    """sha256 of the record's MATERIAL CONTENT: the validated, normalised record, keys sorted, no whitespace.

    Hashing the normalised record rather than the raw line is deliberate. Re-indenting a line, reordering its keys
    or writing 13 instead of 13.0 is not a new run and must not put a second row on the scatter; changing any
    reading IS a new row. Nothing the sync adds (SYNC_FIELDS) is in here, so the same record re-synced out of a
    renamed file still lands on the same document."""
    blob = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def doc_id_for(digest):
    """The document id: "rr_" plus the first 24 hex characters of the digest, which is 96 bits.

    The board will hold thousands of these, not billions: at a million records the chance that any two share a
    truncated id is about 1e-17 (n^2 / 2^97). 16 characters (64 bits, as api/nt_sync.py's sha1[:16]) would do as
    well; 24 costs eight more characters in an id nobody ever types and takes the question off the table. The FULL
    digest goes in the marker, so if this truncation ever changes the marker's own entries stop matching and the
    next pass re-uploads instead of silently believing stale ids."""
    return DOC_ID_PREFIX + digest[:DOC_ID_HEX]


def payload(rec, src_file, now=None):
    """The Firestore document: the record, plus the three fields the SYNC owns.

    sync_file is the basename only (which lane's file it came out of - the full path says nothing a reader needs)
    and sync_at is when this pass sent it. All three are outside the content hash, so they never create a new row:
    `timestamp` is a copy of the already-normalised `ts`, so two passes over the same line always derive the same
    value and a renamed file still lands on the same document.

    WHY `timestamp` IS HERE, AND WHY IT IS THE SYNC'S FIELD AND NOT THE LANE'S. The page finds the month's rows
    with ONE query, and that query filters `timestamp` - index.html's _monQuery is shared by the runs read and the
    research_runs read, and sends a lexicographic string range against that exact field path; the row builder then
    reads `d.timestamp` for the row's DATE RAN. A run document carries that name because api/runner.py:1632 wrote
    it; the frozen record schema (MANAGER #127) calls the same reading `ts`, and a record uploaded under `ts`
    alone matches no month filter and shows no date - it is in the collection and invisible on the board, which
    is the one outcome W47 exists to prevent. So the sync writes the normalised stamp under BOTH names: `ts` is
    the schema's field and is hashed, `timestamp` is the page's and is not. It stays a SYNC field, so a lane that
    writes `timestamp` itself is still refused as an unknown field and cannot forge its own stamp."""
    doc = dict(rec)
    doc["timestamp"] = rec["ts"]
    doc["sync_file"] = os.path.basename(src_file)
    doc["sync_at"] = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()
    return json_safe(doc)


# ── the pre-write size discipline (tools/run_exposure.py's rules, on one small document) ─────
def fs_size(v):
    """Firestore's storage size of one value (api/runner.py _fs_value_size's rules, as tools/run_exposure.py
    repeats them): string = UTF-8 bytes + 1, number = 8, bool / null = 1, map = key bytes + 1 + value."""
    if v is None or isinstance(v, bool):
        return 1
    if isinstance(v, (int, float)):
        return 8
    if isinstance(v, str):
        return len(v.encode("utf-8", "replace")) + 1
    if isinstance(v, dict):
        return sum(len(str(k).encode("utf-8", "replace")) + 1 + fs_size(x) for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return sum(fs_size(x) for x in v)
    return len(str(v).encode("utf-8", "replace")) + 1


def doc_bytes(doc):
    return fs_size(doc) + 32 + 200   # the document-name / per-document allowance api/runner._doc_size uses


def check_size(doc):
    """The document's size in bytes, or Refusal. Also what the batch's byte budget is spent against.

    Kept cheap on purpose: a record is a FLAT object of about thirty scalars (every schema field is a scalar and an
    unknown field was refused above), so there is no map to walk, no array to count and none of the nested-array
    trouble tools/run_exposure.py documents - the index cost is simply two entries a field. The check is still here
    because `note` is free text, and a lane that appends a logfile into it would otherwise be rejected by the
    server for the whole batch rather than for its own line."""
    size = doc_bytes(doc)
    idx = 2 * (len(doc) + 1)
    if size > SIZE_REFUSE:
        raise Refusal("the record would be %s bytes, over the %s refusal line (Firestore's own cap is 1,048,576 a "
                      "document) - the note is almost certainly carrying something that is not a note"
                      % (f"{size:,}", f"{SIZE_REFUSE:,}"))
    if idx > INDEX_REFUSE:
        raise Refusal("the record would need about %s index entries, over the %s refusal line (Firestore's own cap "
                      "is 40,000 a document)" % (f"{idx:,}", f"{INDEX_REFUSE:,}"))
    return size


# ── the marker: the local idempotency ledger ─────────────────────────────────────────────────
def marker_path_for(records_dir):
    """Beside the records, as api/nt_sync.py keeps .edgelog_sync_state.json beside fills.csv."""
    return os.path.join(records_dir, MARKER_NAME)


def read_marker(path):
    """({doc_id: digest} already uploaded, a warning line or None).

    A missing marker is the normal first run. An unreadable one reads as empty and SAYS so: the pass then re-sends
    content that is already in Firestore, which costs writes and changes nothing, because the document id IS the
    content. That is the whole reason this tool never has to read the collection back."""
    if not os.path.exists(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        written = data.get("written") if isinstance(data, dict) else None
        if not isinstance(written, dict):
            raise ValueError("no 'written' map")
        return {str(k): str(v) for k, v in written.items()}, None
    except (OSError, ValueError) as e:
        return {}, ("marker %s could not be read (%s: %s) - treating it as empty, so this pass re-sends records "
                    "that are already up. Identical content, same document ids: it costs writes, not correctness."
                    % (path, type(e).__name__, e))


def write_marker(path, written):
    """Write the marker as temp-file-then-atomic-replace, and RAISE when the replace will not land.

    This file is the idempotency ledger, so the one failure mode it must not have is a quiet one: lose it and the
    next pass re-uploads every record in the directory. The temp copy is left on disk when the swap fails, for the
    same reason api/qqq_exec.py's save_state keeps its own - a human can rename it by hand - and the retry loop is
    Windows' WinError 32: os.replace there fails outright if any other process merely has the destination open for
    reading (api/qqq_exec.py _replace_with_retry).

    The DIRECTORY IS MADE HERE, and every OSError on the way to the temp copy comes back as this tool's own
    error: by the time this is called the documents are ALREADY COMMITTED, so a --marker path into a folder nobody
    has made yet must not surface as a bare FileNotFoundError out of open(), after the write, saying nothing about
    what a lost marker costs."""
    tmp = path + ".tmp"
    body = json.dumps({"v": 1, "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "written": written}, sort_keys=True, separators=(",", ":"))
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        raise ToolError("the marker could not be written at %s (%s: %s). Whatever this pass committed is up, but "
                        "nothing recorded it, so the next pass re-uploads every record in this directory - "
                        "identical content, identical document ids, so that costs writes, not correctness."
                        % (path, type(e).__name__, e)) from None
    last = None
    for i in range(max(1, MARKER_RETRIES)):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:       # WinError 32: someone else has it open
            last = e
            time.sleep(MARKER_SLEEP * (i + 1))
        except OSError as e:
            last = e
            break
    raise ToolError("the marker could not be swapped into place at %s (%s: %s). The new copy is sitting at %s - "
                    "rename it by hand, or the next pass re-uploads every record in this directory."
                    % (path, type(last).__name__, last, tmp))


# ── reading the records files ────────────────────────────────────────────────────────────────
def read_lines(path):
    """([(line number, text)] for every line with something on it, is the last line unterminated).

    utf-8-sig because a lane appending from PowerShell can leave a byte-order mark on the first line, and that one
    invisible character would otherwise refuse a perfectly good record. Decoding errors are replaced rather than
    raised, so one bad byte costs one refused line and never the rest of the file.

    The unterminated flag matters: this tool runs on a timer while the lanes append, so it can read a line the lane
    is still in the middle of writing. A last line with no newline after it that does not parse is NOT a refusal -
    it is half a line, and the next pass will see all of it."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()
    rows = raw.split("\n")
    unterminated = bool(rows and rows[-1].strip())
    return [(i, t.strip()) for i, t in enumerate(rows, 1) if t.strip()], unterminated


class Item(object):
    """One record this pass owes Firestore."""
    __slots__ = ("doc_id", "digest", "doc", "size", "src", "lineno")

    def __init__(self, doc_id, digest, doc, size, src, lineno):
        self.doc_id, self.digest, self.doc, self.size = doc_id, digest, doc, size
        self.src, self.lineno = src, lineno

    def origin(self):
        """Which file and line this record came out of. Not the record's own `where` - that is the schema field."""
        return "%s:%d" % (os.path.basename(self.src), self.lineno)

    def line(self):
        """The four numbers the house judges a run by, so a dry run shows what would be plotted, not just a count.
        A figure the record carries as null prints as a dash, never as a zero - and EVERY figure on this line can
        be null now, dd5 and the instrument included, which is why they all go through the same formatter. A
        f"{None:,.0f}" here would be a TypeError in the middle of the report, i.e. the dry pass that is supposed
        to say what would go up instead saying nothing at all."""
        d = self.doc

        def f(key, spec=None):
            v = d.get(key)
            if v is None:
                return "-"
            return format(v, spec) if spec else str(v)

        return ("  + %s  %-22s %s  %-7s %-9s %-7s ROC@30k %7s  DD5 $%-9s DD %6s%%  Sortino %6s  %s"
                % (self.doc_id, self.origin(), d["ts"], d["family"], f("instrument"), d["stage"],
                   f("roc30k", ".2f"), f("dd5", ",.0f"), f("ddpct", ".2f"), f("sortino", ".2f"), d["lane"]))


class FileReport(object):
    """What one records file read, owes and refused. Printed per file, then summed into one line."""
    __slots__ = ("path", "lines", "already", "items", "refused", "dupes", "incomplete", "gaps")

    def __init__(self, path):
        self.path = path
        self.lines = 0
        self.already = 0
        self.items = []
        self.gaps = []          # [(line number, what was dropped and why)] - uploaded, minus one caption
        self.refused = []       # [(line number, reason)]
        self.dupes = []         # [(line number, the earlier line this one repeats)]
        self.incomplete = None  # the line number of a half-written last line, if any

    def head(self):
        bits = ["%d line(s) read" % self.lines, "%d new" % len(self.items),
                "%d already uploaded" % self.already]
        if self.dupes:
            bits.append("%d duplicate(s)" % len(self.dupes))
        if self.incomplete:
            bits.append("1 still being written")
        if self.gaps:
            bits.append("%d with a caption dropped" % len(self.gaps))
        bits.append("%d refused" % len(self.refused))
        return "[run-records] %s: %s" % (os.path.basename(self.path), ", ".join(bits))


def plan_file(path, known, seen, now=None):
    """Read one records file and work out what it owes Firestore. Writes nothing, opens no client.

    `known` is the marker's {doc_id: digest} (an empty dict under --recheck, which is what rechecking a file from
    scratch means). `seen` is shared across the whole pass: the same record written twice - a lane that appended
    again after a restart - is ONE document, so the repeat is reported and sent once."""
    rep = FileReport(path)
    rows, unterminated = read_lines(path)
    rep.lines = len(rows)
    last_no = rows[-1][0] if rows else None
    for n, text in rows:
        try:
            raw = json.loads(text)
        except ValueError as e:
            if n == last_no and unterminated:
                rep.incomplete = n          # the lane is mid-append; the next pass gets the whole line
            else:
                rep.refused.append((n, "not JSON: %s" % e))
            continue
        try:
            rec = validate(raw)
            digest = content_hash(rec)
            doc_id = doc_id_for(digest)
            doc = payload(rec, path, now)
            size = check_size(doc)
        except Refusal as e:
            rep.refused.append((n, str(e)))
            continue
        if doc_id in seen:
            rep.dupes.append((n, seen[doc_id]))
            continue
        if raw.get("sha") is not None and rec["sha"] is None:
            rep.gaps.append((n, "its sha %s is not a commit sha (7 to 40 hex, optionally -dirty) - the record "
                                "went up without it, and the page dashes it. A 64-character value here is a "
                                "content hash: the schema wants `git rev-parse HEAD`"
                             % _show(str(raw.get("sha")))))
        seen[doc_id] = "%s:%d" % (os.path.basename(path), n)
        if known.get(doc_id) == digest:     # the digest, not just the id: a marker from another hashing scheme
            rep.already += 1                #   does not match and is re-uploaded rather than trusted
            continue
        rep.items.append(Item(doc_id, digest, doc, size, path, n))
    return rep


# ── the write ────────────────────────────────────────────────────────────────────────────────
def upload(db, items, written, marker, out=print):
    """set(merge=True) every item in batches, and flush the marker after EVERY commit. Returns (ids, commits).

    merge=True preserves only the keys ABSENT from the payload and overwrites every key present. api/runner.py
    lines 207-224 is the production bug: sync_runs shipped the local starred / note / archived that way and
    clobbered 11 of the owner's own web edits. A research_runs row is machine-written - the lane's JSONL line is
    its only source and nothing in the web app edits one today - so a plain merge is right here. The day the page
    lets the owner star, note or verdict one of these rows, this write has to drop those keys from the payload the
    way api/runner.py's _WEB_OWNED_RUN_FIELDS does, or the next sync will wipe them.

    The marker is written AFTER each commit and never before: it may only ever claim what actually landed. That is
    also why a failed commit is left to propagate - the marker then holds exactly the batches that did land, and
    the next pass re-uploads only what is missing."""
    col = rw._user(db).collection(COLLECTION)
    batch = db.batch()
    pending, nbytes, commits, ids = [], 0, 0, []

    def flush():
        nonlocal batch, pending, nbytes, commits
        if not pending:
            return
        batch.commit()
        commits += 1
        for it in pending:
            written[it.doc_id] = it.digest
            ids.append(it.doc_id)
        write_marker(marker, written)
        out("[run-records] committed %d doc(s), %s bytes" % (len(pending), f"{nbytes:,}"))
        batch, pending, nbytes = db.batch(), [], 0

    for it in items:
        # commit BEFORE the doc that would push the batch past a cap, so no commit is ever over one
        if pending and (len(pending) >= BATCH_DOCS or nbytes + it.size > BATCH_BYTES):
            flush()
        batch.set(col.document(it.doc_id), it.doc, merge=True)
        pending.append(it)
        nbytes += it.size
    flush()
    return ids, commits


# ── the pass ─────────────────────────────────────────────────────────────────────────────────
def pick_files(args, out):
    """The records files this pass reads, or [] with a plain line saying there is nothing to do yet."""
    records_dir = os.path.abspath(args.dir)
    if args.files:
        files = [f if os.path.dirname(f) else os.path.join(records_dir, f) for f in args.files]
        missing = [f for f in files if not os.path.isfile(f)]
        if missing:
            raise ToolError("no such records file: %s" % ", ".join(missing))
        return files
    if not os.path.isdir(records_dir):
        out("[run-records] nothing to do: %s does not exist yet - no lane has appended a record" % records_dir)
        return []
    files = sorted(glob.glob(os.path.join(records_dir, "*.jsonl")))
    if not files:
        out("[run-records] nothing to do: no *.jsonl in %s" % records_dir)
    return files


def run(args, open_db, out=print, now=None):
    """The whole pass. Returns (exit code, [FileReport], the document ids written).

    open_db() is called ONLY when there is something to upload, so a steady state - every line already in the
    marker - opens no Firestore client at all: no credential read, no gRPC channel, no quota spent."""
    files = pick_files(args, out)
    if not files:
        return 0, [], []
    marker = os.path.abspath(args.marker) if args.marker else marker_path_for(os.path.abspath(args.dir))
    written, warning = read_marker(marker)
    if warning:
        out("[run-records] " + warning)
    if args.recheck:
        out("[run-records] --recheck: the marker is ignored for this pass, so every line is re-sent (the document "
            "id is the content, so a re-send cannot duplicate a row)")

    seen = {}
    reports = [plan_file(p, {} if args.recheck else written, seen, now) for p in files]
    items = [it for rep in reports for it in rep.items]
    refused = sum(len(rep.refused) for rep in reports)

    for rep in reports:
        out(rep.head())
        for n, why in rep.refused:
            out("    REFUSED line %d: %s" % (n, why))
        for n, why in rep.gaps:
            out("    line %d: %s" % (n, why))
        for n, earlier in rep.dupes:
            out("    line %d: the same record as %s - uploaded once" % (n, earlier))
        if rep.incomplete:
            out("    line %d: no newline yet, so the lane is still writing it - left for the next pass"
                % rep.incomplete)
    for it in items[:PREVIEW_LINES]:
        out(it.line())
    if len(items) > PREVIEW_LINES:
        out("  + ... and %d more" % (len(items) - PREVIEW_LINES))

    ids, commits = [], 0
    if args.write and items:
        ids, commits = upload(open_db(), items, written, marker, out)

    out("[run-records] %d file(s): %d line(s), %d new, %d already uploaded, %d refused, %s bytes to send"
        % (len(files), sum(r.lines for r in reports), len(items), sum(r.already for r in reports), refused,
           f"{sum(it.size for it in items):,}"))
    if not args.write:
        out("[run-records] --dry: wrote nothing - no Firestore client opened, marker untouched. Add --write to "
            "upload %d record(s)." % len(items))
    elif items:
        out("[run-records] wrote %d doc(s) in %d batch(es) to users/%s/%s; marker %s"
            % (len(ids), commits, rw.UID, COLLECTION, marker))
    else:
        # A --write pass with nothing to send has three different shapes and they must not read alike. "every
        #   line is already in the marker" is the steady state - success - and it names a file that a pass which
        #   uploaded nothing may never have written at all. A lane whose every record was REFUSED has to be told
        #   that, or it reads the last line of this output as "my rows are on the scatter".
        already = sum(r.already for r in reports)
        if refused and not already:
            out("[run-records] NOTHING WENT UP: all %d line(s) were refused, so this pass wrote no document and "
                "no marker - the reasons above have to be fixed in the lane's own records file" % refused)
        elif refused:
            out("[run-records] nothing new to upload: %d line(s) already in the marker, %d refused (the reasons "
                "above are still unfixed)" % (already, refused))
        elif already:
            out("[run-records] nothing to upload: every line is already in the marker")
        else:
            out("[run-records] nothing to upload: no finished line in %d file(s)" % len(files))
    return (2 if refused else 0), reports, ids


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="records files to read (default: every *.jsonl in --dir)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry", action="store_true",
                      help="say exactly what would be uploaded, write nothing (the default)")
    mode.add_argument("--write", action="store_true", help="upload the new lines and update the marker")
    ap.add_argument("--dir", default=records_root(),
                    help="where the lanes append their records (default: %(default)s)")
    ap.add_argument("--marker", help="the local idempotency ledger (default: <dir>/%s)" % MARKER_NAME)
    ap.add_argument("--recheck", action="store_true",
                    help="ignore the marker for this pass and re-send every line (repair)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except Exception:
            pass
    code = 1
    try:
        code, _, _ = run(args, rw.real_client)
    except ToolError as e:
        print("error: %s" % e, file=sys.stderr)
    # A Firestore client's gRPC channel holds the process open for a minute or more after the commit has returned,
    # so leave the hard way once the output is flushed (tools/run_exposure.py and tools/runboard_watch.py do the
    # same). ONLY here, in the CLI: os._exit from the library path above would take the test runner down with it.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
