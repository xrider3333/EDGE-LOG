# -*- coding: utf-8 -*-
"""THE RUN RECORDS SYNC (owner ask 2026-10-18, W47): tools/run_records_sync.py.

The lanes append one JSON object per finished run to <EDGELOG_HOME>/run_records/<lane>_YYYYMM.jsonl and this tool
uploads the new lines to users/{uid}/research_runs. Everything that matters about it is a rule about not writing
twice and not writing rubbish, so that is what this file tests.

Nothing here touches the network, a credential or the real records directory: the Firestore client is an in-memory
fake that records every set() and every commit, and both the records files and the marker live in tmp_path
(conftest.py's live-system guard would fail a test that wrote under the real EDGELOG_HOME, which is exactly where
the tool's own default directory is).

THE CONTRACT THIS FILE PINS WAS CORRECTED ON 2026-10-19 (parent, W47): AN ABSENT FIGURE COSTS ONE AXIS, A WRONG
FIGURE COSTS THE CHART. The first pass required thirteen fields with a value and, over the seven lanes' 1,199
real records, refused 1,164 of them - 86% of the month - almost every one for a null the page would have dashed.
So the tests below pin BOTH halves of the new rule, and the second half is what keeps the first honest:

  * a SPARSE record - ts, lane, where, stage, family and one figure - uploads, and every other frozen key is in
    the document as null, so the page can tell NOT MEASURED from zero
  * every timestamp shape a lane really writes NORMALISES to the stored "YYYY-MM-DD HH:MM" instead of refusing
  * every WRONG-number refusal still refuses, each one beside the invariant it comes from
  * a pair rule whose own input is absent DOES NOT REFUSE: an invariant between a number and a null is an
    unasked question, and that mistake alone threw away honest runs over an axis the page would have dashed
"""
import copy
import datetime
import hashlib
import json
import os
import random
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.run_records_sync as rs  # noqa: E402
import tools.runboard_watch as rw  # noqa: E402

NOW = datetime.datetime(2026, 10, 18, 16, 5, tzinfo=datetime.timezone.utc)   # a fixed sync_at, so docs compare


def rec(**kw):
    """One valid record, the shape MANAGER #127 froze and tools/run_record.py writes. Overrides go in as keyword
    arguments; a key the schema does not have is how the unknown-field refusal is exercised."""
    r = {"ts": "2026-10-17 14:35", "lane": "STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y", "host": "EDGELOG-PC",
         "where": "lane", "stage": "WF", "strategy": "NOISE_4_2.py", "family": "NOISE", "instrument": "NQ",
         "timeframe": "5m", "roc30k": 41.7, "dd5": 18450.0, "ddpct": 13.09, "sortino": 1.42, "trades": 318,
         "gross_pt": 3.41, "cost_pt": 0.533, "one_episode": False, "ledger_row": "2.195", "run_id": None,
         "sha": "0a102780", "note": "pre-WF screen, 24 cells | numbers: computed", "start_usd": 100000,
         "net_usd": 61240.0, "max_dd_usd": 21100.0, "years": 4.2, "win_start": "2022-06-01",
         "win_end": "2026-08-29", "schema_v": 1}
    r.update(kw)
    return r


def write_records(folder, name, rows, newline_at_end=True):
    """Append-style write of a records file. A row may be a dict (dumped) or raw text (a malformed line)."""
    body = "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows)
    with open(os.path.join(str(folder), name), "w", encoding="utf-8") as f:
        f.write(body + ("\n" if newline_at_end else ""))


def marker_of(folder):
    with open(os.path.join(str(folder), rs.MARKER_NAME), encoding="utf-8") as f:
        return json.load(f)


def doc_id_of(record):
    return rs.doc_id_for(rs.content_hash(rs.validate(record)))


# ── the fake Firestore client (tests/test_runboard_watch.py's FakeClient, plus a batch) ──────
class _Snap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return _Coll(self.db, self.path + (name,))

    def get(self, transaction=None):
        self.db.reads.append(self.path)
        return _Snap(self.db.store.get(self.path))


class _Coll:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, doc_id):
        return _Doc(self.db, self.path + (str(doc_id),))


class _Batch:
    def __init__(self, db):
        self.db, self.ops = db, []

    def set(self, ref, data, merge=False):
        self.ops.append((ref.path, copy.deepcopy(data), merge))

    def commit(self):
        """Atomic, like the real one: a commit that raises lands NOTHING."""
        self.db.commits += 1
        if self.db.fail_on_commit == self.db.commits:
            raise RuntimeError("firestore said no")
        for path, data, merge in self.ops:
            if merge and path in self.db.store:
                cur = dict(self.db.store[path])
                cur.update(data)
                self.db.store[path] = cur
            else:
                self.db.store[path] = data
            self.db.sets.append((path, data, merge))
        self.db.committed.append(list(self.ops))
        self.ops = []


class FakeDb:
    """In-memory Firestore stand-in. `fail_on_commit=N` makes the Nth commit blow up, which is how the
    crash-between-batches rule is tested."""
    def __init__(self, fail_on_commit=None):
        self.store, self.sets, self.reads, self.committed = {}, [], [], []
        self.batches = self.commits = 0
        self.fail_on_commit = fail_on_commit

    def collection(self, name):
        return _Coll(self, (name,))

    def batch(self):
        self.batches += 1
        return _Batch(self)

    @property
    def batch_sizes(self):
        return [len(ops) for ops in self.committed]


class Pass:
    """What one run of the tool did: its exit code, its reports, the text it printed and the client it opened."""
    def __init__(self, code, reports, ids, text, db, opened):
        self.code, self.reports, self.ids, self.text, self.db, self.opened = code, reports, ids, text, db, opened


def go(folder, *argv, db=None):
    db = FakeDb() if db is None else db
    opened, lines = [], []

    def open_db():
        opened.append(db)
        return db

    args = rs.build_parser().parse_args(["--dir", str(folder)] + list(argv))
    code, reports, ids = rs.run(args, open_db, out=lines.append, now=NOW)
    return Pass(code, reports, ids, "\n".join(lines), db, opened)


# ── uploading, once ──────────────────────────────────────────────────────────────────────────
def test_a_new_record_uploads_once_and_its_document_id_is_its_content(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    p = go(tmp_path, "--write")
    assert p.code == 0
    (path, data, merge), = p.db.sets
    assert merge is True                                       # merge preserves only keys absent from the payload
    assert path == ("users", rw.UID, "research_runs", doc_id_of(rec()))
    assert p.db.reads == []                                    # the collection is never read back
    assert data["roc30k"] == 41.7 and data["ddpct"] == 13.09 and data["sortino"] == 1.42
    assert data["one_episode"] is False and data["trades"] == 318 and data["schema_v"] == 1
    assert data["ledger_row"] == "2.195" and data["run_id"] is None
    assert data["start_usd"] == 100000.0                        # the default, as a number
    assert data["sync_file"] == "NOISE_202610.jsonl" and data["sync_at"] == NOW.isoformat()
    assert all(not isinstance(v, (dict, list)) for v in data.values())   # flat: no array inside an array
    assert marker_of(tmp_path)["written"] == {doc_id_of(rec()): rs.content_hash(rs.validate(rec()))}
    assert "1 new" in p.text and "ROC@30k" in p.text and "wrote 1 doc(s) in 1 batch(es)" in p.text


def test_a_second_pass_uploads_nothing_and_opens_no_firestore_client(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec(ts="2026-10-17 15:00")])
    first = go(tmp_path, "--write")
    assert len(first.db.sets) == 2 and len(first.opened) == 1
    again = go(tmp_path, "--write")
    assert again.code == 0
    assert again.opened == [] and again.db.sets == [] and again.db.batches == 0   # no client, no credential, no quota
    assert "2 already uploaded" in again.text and "every line is already in the marker" in again.text


def test_a_cosmetic_rewrite_of_the_same_line_is_not_a_new_run(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    go(tmp_path, "--write")
    # the same readings, re-dumped with the keys in another order, a float spelled as an int and the note padded
    other = dict(reversed(list(rec(roc30k=41.70, trades=318,
                                   note=" pre-WF screen, 24 cells | numbers: computed ").items())))
    write_records(tmp_path, "NOISE_202610.jsonl", [other])
    p = go(tmp_path, "--write")
    assert p.db.sets == [] and "1 already uploaded" in p.text


def test_a_changed_line_uploads_as_a_new_document_and_leaves_the_old_row_alone(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    first = go(tmp_path, "--write")
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(roc30k=44.0)])   # the lane re-read the run, new number
    p = go(tmp_path, "--write")
    (path, _data, _m), = p.db.sets
    assert path[-1] == doc_id_of(rec(roc30k=44.0)) != first.db.sets[0][0][-1]
    assert len(marker_of(tmp_path)["written"]) == 2                 # both rows are known; neither overwrote the other
    assert "1 new, 0 already uploaded" in p.text


def test_the_same_record_twice_is_one_document(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec()])   # a lane that appended again after a restart
    write_records(tmp_path, "ZZ-LAB_202610.jsonl", [rec()])         # and the same run copied into a second file
    p = go(tmp_path, "--write")
    assert len(p.db.sets) == 1
    assert "the same record as NOISE_202610.jsonl:1" in p.text and "1 duplicate(s)" in p.text


# ── a null is a figure that does not exist ───────────────────────────────────────────────────
def test_the_nulls_the_lane_side_writer_really_writes_are_uploaded_not_refused(tmp_path):
    # tools/run_record.py writes null for a figure the tail did not hold, for a window it has no dates for, and
    # for the lab's NOT TESTABLE one_episode - all of that beside a real dollar drawdown is still an honest row
    lab = rec(ts="2026-10-18 09:00", where="lab", one_episode=None, gross_pt=None, cost_pt=None, net_usd=None,
              max_dd_usd=None, years=None, win_start=None, win_end=None, ledger_row=None, run_id=None)
    # roc30k and sortino are null for ONE shape: a curve that never drew down. four_numbers returns None for both
    # there (nothing fell, so there is no ROC @ $30k; no day lost, so the Sortino denominator is zero) and dd5 and
    # ddpct are 0 beside them - which is what makes those two nulls a reading rather than a hole in the row.
    flat = rec(ts="2026-10-18 10:00", roc30k=None, sortino=None, dd5=0.0, ddpct=0.0, one_episode=False,
               max_dd_usd=0.0, net_usd=3200.0, years=1.1, note="never drew down")
    write_records(tmp_path, "QWEN-LAB_202610.jsonl", [lab, flat])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 2
    data = p.db.sets[0][1]
    assert data["one_episode"] is None and data["max_dd_usd"] is None and data["win_start"] is None
    assert data["dd5"] == 18450.0 and data["ddpct"] == 13.09      # the figures that ARE there still go up
    assert p.db.sets[1][1]["roc30k"] is None and p.db.sets[1][1]["sortino"] is None
    assert "ROC@30k       -" in p.text and "Sortino      -" in p.text   # a null prints as a dash, never a zero


@pytest.mark.parametrize("patch, fragment", [
    ({"ddpct": 0.0}, "ddpct is 0 but the stretch drew down $18,450.00 on a $100,000.00 account"),
    ({"dd5": 13.09}, "dd5 $13.09 is less than a fifth of max_dd_usd $21,100.00 ($4,220.00)"),
])
def test_a_wrong_figure_beside_the_one_it_contradicts_is_refused(tmp_path, patch, fragment):
    """THE PAIR RULES, and these are the ones where BOTH figures are in hand and cannot both be true.

    MEASURED over 400 random daily series straight through augur_engine.drawdowns.four_numbers (re-run in
    test_the_pair_rules_are_the_engines_own_invariants_measured_over_400_series below): a stretch that drew down
    in dollars fell from a high in percent too, so a ZERO ddpct beside a real dd5 means the percent was taken
    from the dollars - and dd5 averages at most 5 depths one of which IS max_dd, so a dd5 below max_dd / 5 means
    a PERCENT was written into the dollars field. 13.09 is this record's own DD %, dropped one line up into the
    dd5 column, and no floor of zero can catch it: a percent is a perfectly good small positive number.

    NOTE WHAT IS NOT IN THIS LIST ANY MORE. {"roc30k": None} and {"sortino": None} were refusals here until
    2026-10-19, on the ground that a curve which drew down has both figures. True of the ENGINE, and beside the
    point: the record is not the engine, it is what a lane wrote down, and a lane that did not write the Sortino
    has not claimed a false one. See test_a_pair_rule_whose_own_input_is_missing_does_not_refuse.
    """
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec(ts="2026-10-17 15:00", **patch)])
    p = go(tmp_path, "--write")
    assert p.code == 2 and len(p.db.sets) == 1                     # the good line on line 1 still went up
    assert "REFUSED line 2" in p.text and fragment in p.text


@pytest.mark.parametrize("patch, kept", [
    ({"roc30k": None}, "net_usd"),                     # the row still has the money axis to sit on
    ({"sortino": None}, "roc30k"),
    ({"dd5": None, "ddpct": None}, "roc30k"),          # 200 of the 1,199 real records are exactly this shape
    ({"trades": None}, "roc30k"),
    ({"sha": None}, "roc30k"),
    ({"max_dd_usd": None, "net_usd": None, "years": None}, "roc30k"),
    ({"one_episode": None}, "roc30k"),
])
def test_a_pair_rule_whose_own_input_is_missing_does_not_refuse(tmp_path, patch, kept):
    """THE RULE THAT COST THE MOST LINES, pinned so it cannot come back.

    A check that compares two readings of the same curve needs BOTH of them. Where one is absent the rule does
    not apply - an invariant between a number and a null is not a violated invariant, it is an unasked question -
    and the answer to an unasked question is never "throw the run away". Every patch here removes one side of a
    real pair rule: a null roc30k or sortino beside a $18,450 drawdown (the two refusals this round deleted), a
    null dd5 and ddpct where the dd5-deeper-than-max_dd and dd5-below-max_dd/5 and zero-percent rules all read
    dd5, a null max_dd_usd where the ddpct ceiling and the one_episode cross-check both read it, a null
    one_episode where the 1.3x test reads the flag.

    Every one of them UPLOADS, with the absent figure stored as null and dashed on the board.
    """
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(ts="2026-10-18 09:00", **patch)])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1, p.text
    d = p.db.sets[0][1]
    for k in patch:
        assert d[k] is None, k                                     # stored as null, not dropped and not zeroed
    assert d[kept] is not None                                     # and the figure it kept is still a figure


def test_a_sub_cent_drawdown_whose_percent_rounds_to_zero_is_not_refused(tmp_path):
    """The one exception the writer carries and this half has to carry too: dd_pct_peak rounds to 4 dp while DD5
    rounds to the CENT, so a $0.01 fall on $100k measures 0.00001% and reads as a flat 0.0 beside dd5 0.01. That
    is four_numbers' own output, and the measured path must never refuse it - so the zero-percent rule fires only
    above DDPCT_ROUNDING_FLOOR, which is the writer's own figure."""
    assert rs.DDPCT_ROUNDING_FLOOR == 0.00005
    rounded = rec(dd5=0.01, ddpct=0.0, max_dd_usd=0.01, roc30k=12.5, sortino=0.9, one_episode=False)
    write_records(tmp_path, "NOISE_202610.jsonl", [rounded])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1 and p.db.sets[0][1]["ddpct"] == 0.0


def test_the_two_halves_of_this_pipeline_refuse_the_same_lines():
    """One ceiling and one floor, not two opinions. The lane-side writer tools/run_record.py validates the record
    as it is written and this tool validates it again as it goes up - the second gate is the last one before the
    page plots the row, and a line can reach it from a lane that never ran the writer, so the two have to agree
    figure for figure."""
    rr = pytest.importorskip("tools.run_record")
    assert rs.MAX_RUN_ID == rr.MAX_RUN_ID == 100_000
    assert rs.DDPCT_ABSURD == rr.DDPCT_ABSURD == 1000.0
    assert rs.DDPCT_BOUND_SLACK == rr.DDPCT_BOUND_SLACK == 0.01
    assert rs.DDPCT_ROUNDING_FLOOR == rr.DDPCT_ROUNDING_FLOOR == 0.00005


def test_the_pair_rules_are_the_engines_own_invariants_measured_over_400_series():
    """THE MEASUREMENT behind those refusals, re-run here so the engine cannot drift out from under them.

    400 random daily series straight through augur_engine.drawdowns.four_numbers - the one producer of these
    figures (MANAGER #170) - seeded, so it is the same 400 every time:

      * ddpct <= 100 * max_dd_usd / start_usd    worst excess +0.000044, dd_pct_peak's own rounding to 4 dp
      * dd5 >= max_dd / 5                        dd5 averages at most 5 depths and one of them IS the worst
      * a stretch that drew down has a losing day, so neither its Sortino nor its ROC @ $30k is ever null

    And every one of those 400 readings, written out as a record, VALIDATES: these rules refuse what
    four_numbers cannot produce, and nothing it can.
    """
    dd = pytest.importorskip("augur_engine.drawdowns")
    random.seed(47)
    drew_down, worst_excess, min_ratio = 0, -1.0, 1.0
    for _ in range(400):
        n = random.randint(40, 600)
        drift, vol = random.uniform(-400, 400), random.uniform(50, 3000)
        vals = [random.gauss(drift, vol) for _ in range(n)]
        start = random.choice([100000.0, 30000.0, 250000.0])
        dates = [datetime.date(2022, 1, 3) + datetime.timedelta(days=i) for i in range(n)]
        f = dd.four_numbers(vals, dates=dates, start=start)
        worst_excess = max(worst_excess, f["dd_pct_peak"] - 100.0 * f["max_dd"] / start)
        if f["dd5_usd"] > 0:
            drew_down += 1
            min_ratio = min(min_ratio, f["dd5_usd"] / f["max_dd"])
            assert f["sortino"] is not None and f["roc30"] is not None, "a stretch that drew down has a losing day"
        out = rs.validate(rec(roc30k=f["roc30"], dd5=f["dd5_usd"], ddpct=f["dd_pct_peak"], sortino=f["sortino"],
                              one_episode=f["one_episode"], net_usd=f["net"], years=f["years"],
                              max_dd_usd=f["max_dd"], start_usd=start, win_start=f["from"], win_end=f["to"],
                              trades=n))
        assert out["ddpct"] == f["dd_pct_peak"]                    # the honest reading, uncapped, goes through
    assert drew_down >= 390, "a random walk draws down: %d of 400" % drew_down
    assert worst_excess < rs.DDPCT_BOUND_SLACK, "ddpct over 100 x max_dd / start by %r" % worst_excess
    assert min_ratio >= 1.0 / rs.DD5_EPISODES, \
        "dd5 is the mean of at most %d depths, one of them the worst: %r" % (rs.DD5_EPISODES, min_ratio)
    # AND THE FLOOR IS TIGHT, which is what makes it a bound and not a safety margin: the smallest ratio these
    #   400 series produced is 0.2087, so a floor of max_dd / 4 would already refuse output four_numbers really
    #   produces. The divisor is the number of episodes DD5 averages, and there is no room to round it up.
    assert rs.DD5_EPISODES == 5 and min_ratio < 1.0 / (rs.DD5_EPISODES - 1), \
        "the dd5 floor has room above it, so it is not the engine's own bound: %r" % min_ratio


def test_a_record_the_lane_side_writer_produced_goes_straight_through(tmp_path):
    """The two halves of this pipeline have to agree about the frozen schema, so the writer's own output is the
    test. These are the three shapes tools/run_record.py really produces: a full record, a lab row whose
    NOT TESTABLE flag it writes as null (MANAGER #160a), and a curve that never drew down, which has no ROC @ $30k
    and no Sortino. Every one of them must upload - a refusal here would keep honest runs off the scatter."""
    rr = pytest.importorskip("tools.run_record")        # the lane-side half, shipped alongside this one
    full = {"roc30k": 20.731, "dd5": 18450.0, "ddpct": 13.09, "sortino": 1.42, "one_episode": False,
            "net_usd": 61240.0, "max_dd_usd": 21100.0, "years": 4.2, "from": "2022-06-01", "to": "2026-08-29",
            "trades": 318, "gross_pt": 3.41, "cost_pt": 0.533}
    lab = {"roc30k": 9.4, "dd5": 18450.0, "ddpct": 13.09, "sortino": 0.81, "one_episode": "NOT TESTABLE",
           "trades": 12}
    # A CURVE THAT NEVER DREW DOWN has no ROC @ $30k - there is no $30k drawdown to scale to - and no Sortino,
    #   because no day lost. It still MADE money, so the net is the figure that places it, and that is the row
    #   the board draws for it.
    flat = {"roc30k": None, "dd5": 0.0, "ddpct": 0.0, "sortino": None, "one_episode": "NOT TESTABLE",
            "trades": 3, "net_usd": 3200.0, "max_dd_usd": 0.0, "years": 1.1}
    rows = [rr.build_record("NOISE", "lane", "WF", strategy="NOISE_4_2.py", family="NOISE", instrument="NQ",
                            timeframe="5m", numbers=full, ledger_row="2.195", sha="0a102780",
                            note="interop", ts="2026-10-17 14:35"),
            rr.build_record("QWEN-LAB", "lab", "preWF", strategy="Q48.py", family="MISC", instrument="NQ",
                            timeframe="5m", numbers=lab, sha="0a102780", ts="2026-10-18 09:00"),
            rr.build_record("ORB", "lane", "IS", strategy="ORB_3_0.py", family="ORB", instrument="NQ",
                            timeframe="5m", numbers=flat, sha="0a102780", ts="2026-10-18 10:00")]
    write_records(tmp_path, "INTEROP_202610.jsonl", rows)
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 3
    assert [d["one_episode"] for _p, d, _m in p.db.sets] == [False, None, None]
    assert set(rows[0]) == set(rs.KNOWN)                # the writer's field set IS the schema this tool knows
    # AND THE ONE WRITER SHAPE THIS TOOL STILL REFUSES, so the cost of the plotted-figure rule is on the record:
    #   a run with no ROC and no net has no coordinate on any axis the board draws. It would upload, cost a
    #   write, and appear nowhere - and the owner could not tell it from a run never recorded at all. 231 of the
    #   seven lanes' 1,199 real lines are this shape, most of them carrying their money in the NOTE text instead
    #   of in net_usd, which is a one-line fix in the lane and not something this tool may guess at.
    #   The WRITER cannot produce this shape - tools/run_record.py refuses "dd5 is required" before it gets
    #   here - so it is written the way the real DISC lines were: by hand, by a lane that never ran the writer,
    #   which is exactly why this tool validates again at all.
    silent = {"ts": "2026-09-25", "lane": "DISC", "host": "RyansRazer", "where": "lane", "stage": "IS",
              "strategy": "CBDQ_1M_1_0 r1 ES best cell", "family": "CBU-Q", "instrument": "ES",
              "timeframe": "1m ETH no-adj", "roc30k": None, "dd5": None, "ddpct": None, "sortino": None,
              "trades": 580, "cost_pt": 0.363, "sha": "a7a070b1",
              "note": "backfill: -$4,465, PF 0.93, max DD $13,727 - the money is in the note, not in net_usd"}
    write_records(tmp_path, "INTEROP_202610.jsonl", [silent])
    q = go(tmp_path, "--write")
    assert q.code == 2 and q.db.sets == []
    assert "no figure the chart can place" in q.text and "appear nowhere" in q.text


def test_a_window_with_one_end_is_a_missing_caption_not_a_refusal(tmp_path):
    """The data window is a CAPTION, not a plotted figure, and the page reads it as a pair or not at all
    (`(d.win_start&&d.win_end)?{from,to}:null`), so one end alone costs the caption and nothing else. This was a
    refusal until 2026-10-19, and it was the plainest case of a pair rule firing for want of its own input. No
    line in the seven lanes' 1,199 records has a half-open window - 21 carry both ends and 1,178 neither - so
    this costs nothing today and makes the rule consistent for the day a lane writes one."""
    write_records(tmp_path, "LAB_202610.jsonl", [rec(win_end=None)])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1
    d = p.db.sets[0][1]
    assert d["win_start"] == "2022-06-01" and d["win_end"] is None
    # ...and a window that runs BACKWARDS is both ends in hand, contradicting each other, so it still refuses
    write_records(tmp_path, "LAB_202610.jsonl", [rec(win_start="2026-09-01")])
    back = go(tmp_path, "--write")
    assert back.code == 2 and "the data window runs backwards" in back.text


# ── bad lines ────────────────────────────────────────────────────────────────────────────────
def test_a_malformed_line_is_reported_with_its_line_number_and_the_good_lines_still_go(tmp_path):
    write_records(tmp_path, "LAB_202610.jsonl", [rec(), "{oh dear", rec(ts="2026-10-17 15:00"), "[1, 2, 3]"])
    p = go(tmp_path, "--write")
    assert p.code == 2                                             # the pass ran, and says a line was refused
    assert "REFUSED line 2" in p.text and "not JSON" in p.text
    assert "REFUSED line 4" in p.text and "ONE JSON object per line" in p.text
    assert len(p.db.sets) == 2                                     # neither bad line stopped the file
    assert "4 line(s), 2 new" in p.text and "2 refused" in p.text


@pytest.mark.parametrize("patch, fragment", [
    ({"where": "cloud"}, 'where is "cloud" - it is one of runner | lane | lab | box'),
    ({"stage": "OOS"}, 'stage is "OOS" - it is one of IS | WF | LB | preWF | forward'),
    ({"one_episode": 1}, "one_episode must be true, false or null, got 1"),
    ({"one_episode": "true"}, 'one_episode must be true, false or null, got "true"'),
    ({"ts": None}, "ts is missing"),
    ({"ts": "17/10/2026 14:35"}, 'local "YYYY-MM-DD HH:MM"'),
    ({"ts": "2026-10-17 14:35 MST"}, 'local "YYYY-MM-DD HH:MM"'),
    ({"ts": "2026-13-01 14:35"}, 'local "YYYY-MM-DD HH:MM"'),          # a month that does not exist
    ({"ddpct": 13090.0}, "dollar figure in the percent field"),
    ({"ddpct": -2.0}, "ddpct is -2.0 - it cannot be below"),
    ({"lane": None}, "missing required field(s): lane"),
    ({"stage": None}, "missing required field(s): stage"),
    ({"family": None}, "missing required field(s): family"),
    ({"where": None}, "missing required field(s): where"),
    ({"roc30k": None, "net_usd": None, "max_dd_usd": None}, "no figure the chart can place"),
    ({"roc30k": None, "max_dd_usd": None}, "no figure the chart can place"),   # a net with no dollars beside it
    ({"instrument": 5}, "instrument must be a string, got 5"),
    ({"trades": -2}, "trades is -2 - a trade count cannot be negative"),
    ({"sortino": "1.42"}, 'sortino must be a number, got "1.42"'),
    ({"roc30k": float("nan")}, "roc30k is not a finite number"),
    ({"trades": 3.5}, "trades must be a whole number, got 3.5"),
    ({"trades": True}, "trades must be a whole number, got true"),
    ({"cost_pt": -0.5}, "cost_pt is -0.5 - it cannot be below"),
    ({"lane": "   "}, "lane is blank"),
    ({"dd5": 30000.0}, "deeper than max_dd_usd"),
    ({"dd5": 4000.0}, "is less than a fifth of max_dd_usd"),
    ({"one_episode": True}, "the flag and its own two numbers disagree"),
    ({"win_start": "2026-09-01"}, "the data window runs backwards"),
    ({"win_end": "2026/08/29"}, 'win_end is "2026/08/29" - a data-window date is "YYYY-MM-DD"'),
    ({"run_id": 0}, "run_id is 0 - it is the engine run number"),
    ({"run_id": "1760000000"}, "PROVISIONAL id, int(time.time())"),    # quoting it does not get it past
    ({"run_id": 3.5}, "a lane's own run id"),
    ({"ledger_row": 2.195}, "ledger_row is 2.195"),
    ({"schema_v": 2}, "this tool only knows schema 1"),
    ({"roc_30k": 41.7}, "field(s) the frozen schema does not have: roc_30k"),
    ({"sync_file": "NOISE.jsonl"}, "field(s) the frozen schema does not have: sync_file"),
])
def test_each_schema_refusal_names_the_line_and_the_reason(tmp_path, patch, fragment):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec(**patch)])
    p = go(tmp_path, "--write")
    assert p.code == 2
    assert "REFUSED line 2" in p.text and fragment in p.text
    assert len(p.db.sets) == 1                                     # the good line on line 1 still went up
    assert len(marker_of(tmp_path)["written"]) == 1                 # and only it is marked as uploaded


def test_a_provisional_runner_run_id_is_refused_in_the_writers_own_words(tmp_path):
    """A run number is a small integer out of the runner's own counter - today's newest is 491. api/runner.py
    falls back to int(time.time()), about 1.79e9, when the run-id counter cannot be read, and
    repair_provisional_run_ids later re-saves that run under its real number, so a row filed against the
    provisional id points at a run number that never exists, forever. rid > 0 was the only bound here, so
    int(time.time()) uploaded as a run number; the ceiling is the lane-side writer's own, not a second opinion."""
    write_records(tmp_path, "NOISE_202610.jsonl",
                  [rec(run_id=int(time.time())), rec(ts="2026-10-17 15:00", run_id=491)])
    p = go(tmp_path, "--write")
    assert p.code == 2 and len(p.db.sets) == 1
    assert p.db.sets[0][1]["run_id"] == 491                        # today's newest real run still goes up
    assert "REFUSED line 1" in p.text and "PROVISIONAL id, int(time.time())" in p.text
    assert "not a plausible run number (1..100000" in p.text
    assert rs.validate(rec(run_id=rs.MAX_RUN_ID))["run_id"] == rs.MAX_RUN_ID      # the ceiling itself passes


def test_a_record_with_no_one_episode_field_at_all_uploads_it_as_null(tmp_path):
    """An ABSENT flag says exactly what the lab's NOT TESTABLE null says - the worst episode was not compared
    with the others - so it is stored as null and the page tags no row by it. It was a refusal until 2026-10-19,
    which is the same mistake in its smallest form: a run thrown off the board for a field nobody measured.
    What the flag may still not be is 1, 0 or "true" (see the refusal table above): the page tags rows by it, so
    a value that is not the flag itself tags the wrong ones."""
    no_flag = rec()
    no_flag.pop("one_episode")
    write_records(tmp_path, "NOISE_202610.jsonl", [no_flag])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1 and p.db.sets[0][1]["one_episode"] is None
    # and leaving it out is the same reading as writing null, so it is the same row, not a second one
    assert doc_id_of(no_flag) == doc_id_of(rec(one_episode=None))


def test_a_note_the_size_of_a_logfile_is_refused_before_it_can_sink_the_batch(tmp_path):
    write_records(tmp_path, "LAB_202610.jsonl", [rec(), rec(ts="2026-10-17 15:00", note="x" * 950_000)])
    p = go(tmp_path, "--write")
    assert p.code == 2 and len(p.db.sets) == 1
    assert "REFUSED line 2" in p.text and "Firestore's own cap is 1,048,576" in p.text


def test_a_half_written_last_line_is_left_for_the_next_pass_not_refused(tmp_path):
    # the tool runs on a timer while the lanes append, so it can read a line mid-write
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), json.dumps(rec(ts="2026-10-17 15:00"))[:60]],
                  newline_at_end=False)
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1
    assert "still being written" in p.text and "no newline yet" in p.text
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec(ts="2026-10-17 15:00")])   # the lane finished it
    done = go(tmp_path, "--write")
    assert len(done.db.sets) == 1 and "1 already uploaded" in done.text


def test_a_byte_order_mark_from_a_powershell_append_does_not_refuse_the_first_line(tmp_path):
    with open(os.path.join(str(tmp_path), "BOX_202610.jsonl"), "w", encoding="utf-8-sig") as f:
        f.write(json.dumps(rec()) + "\n")
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1


# ── dry by default ───────────────────────────────────────────────────────────────────────────
def test_dry_is_the_default_and_writes_neither_firestore_nor_the_marker(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    for argv in ([], ["--dry"]):
        p = go(tmp_path, *argv)
        assert p.code == 0 and p.opened == [] and p.db.sets == []
        assert not os.path.exists(os.path.join(str(tmp_path), rs.MARKER_NAME))
        assert "--dry: wrote nothing" in p.text and "Add --write to upload 1 record(s)" in p.text
        # it says exactly WHAT would go up: the row, where it came from and the four numbers
        assert "NOISE_202610.jsonl:1" in p.text and doc_id_of(rec()) in p.text
        assert "ROC@30k" in p.text and "DD5" in p.text and "Sortino" in p.text


def test_a_directory_with_nothing_in_it_yet_is_not_an_error(tmp_path):
    empty = go(tmp_path)
    assert empty.code == 0 and "no *.jsonl" in empty.text and empty.opened == []
    missing = go(os.path.join(str(tmp_path), "run_records"))
    assert missing.code == 0 and "does not exist yet" in missing.text


def test_a_named_file_that_is_not_there_is_a_plain_refusal(tmp_path):
    with pytest.raises(rs.ToolError) as e:
        go(tmp_path, "GONE.jsonl")
    assert "no such records file" in str(e.value)


def test_only_the_named_file_is_read(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    write_records(tmp_path, "LAB_202610.jsonl", [rec(ts="2026-10-17 15:00")])
    p = go(tmp_path, "NOISE_202610.jsonl", "--write")
    assert len(p.db.sets) == 1 and p.db.sets[0][0][-1] == doc_id_of(rec())


# ── batching ─────────────────────────────────────────────────────────────────────────────────
def test_the_batch_splits_at_the_document_cap(tmp_path):
    write_records(tmp_path, "BOX_202610.jsonl", [rec(trades=i) for i in range(rs.BATCH_DOCS + 7)])
    p = go(tmp_path, "--write")
    assert p.code == 0
    assert p.db.batch_sizes == [rs.BATCH_DOCS, 7]                  # Firestore's own cap is 500 writes a batch
    assert len(p.db.sets) == rs.BATCH_DOCS + 7 == len(set(i[0] for i in p.db.sets))
    assert len(marker_of(tmp_path)["written"]) == rs.BATCH_DOCS + 7


def test_the_batch_also_splits_on_the_byte_budget(tmp_path, monkeypatch):
    one = rs.doc_bytes(rs.payload(rs.validate(rec()), "BOX_202610.jsonl", NOW))
    monkeypatch.setattr(rs, "BATCH_BYTES", int(one * 2.5))          # the real budget is 9,000,000 of 10 MiB
    write_records(tmp_path, "BOX_202610.jsonl", [rec(trades=i) for i in range(5)])
    p = go(tmp_path, "--write")
    assert p.db.batch_sizes == [2, 2, 1]
    for ops in p.db.committed:
        assert sum(rs.doc_bytes(d) for _p, d, _m in ops) <= rs.BATCH_BYTES


def test_the_marker_survives_a_crash_between_batches_and_the_next_pass_finishes_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "BATCH_DOCS", 3)
    write_records(tmp_path, "LAB_202610.jsonl", [rec(trades=i) for i in range(7)])
    crashing = FakeDb(fail_on_commit=2)
    with pytest.raises(RuntimeError):
        go(tmp_path, "--write", db=crashing)
    assert len(crashing.sets) == 3                                 # only the first batch landed
    assert len(marker_of(tmp_path)["written"]) == 3                 # and the marker claims exactly those three
    rest = go(tmp_path, "--write")                                 # a healthy client picks up where it stopped
    assert len(rest.db.sets) == 4 and "4 new, 3 already uploaded" in rest.text
    assert len(marker_of(tmp_path)["written"]) == 7
    assert sorted(i[0][-1] for i in crashing.sets + rest.db.sets) == sorted(marker_of(tmp_path)["written"])


def test_a_write_pass_that_uploaded_nothing_says_which_kind_of_nothing_it_was(tmp_path):
    """A lane reads the LAST line of this output. "nothing to upload: every line is already in the marker" is the
    steady state - success - and it names a file that a pass which uploaded nothing may never have written. A lane
    whose every record was refused has to be told that, or it reads that line as "my rows are on the scatter"."""
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(where="cloud"), rec(ts="2026-10-17 15:00", stage="OOS")])
    refused = go(tmp_path, "--write")
    assert refused.code == 2 and refused.db.sets == [] and refused.opened == []
    assert "NOTHING WENT UP: all 2 line(s) were refused" in refused.text
    assert "already in the marker" not in refused.text
    assert not os.path.exists(os.path.join(str(tmp_path), rs.MARKER_NAME))   # the file the old line named
    # one line in the marker and one refused is a third thing again, and says both
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    go(tmp_path, "--write")
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec(ts="2026-10-17 15:00", stage="OOS")])
    mixed = go(tmp_path, "--write")
    assert mixed.code == 2 and mixed.db.sets == []
    assert "1 line(s) already in the marker, 1 refused" in mixed.text
    # and a file whose only line is still being written is not "already in the marker" either
    write_records(tmp_path, "HALF_202610.jsonl", [json.dumps(rec(ts="2026-10-17 16:00"))[:40]],
                  newline_at_end=False)
    os.remove(os.path.join(str(tmp_path), "NOISE_202610.jsonl"))
    os.remove(os.path.join(str(tmp_path), rs.MARKER_NAME))
    half = go(tmp_path, "--write")
    assert half.code == 0 and "no finished line in 1 file(s)" in half.text


def test_a_marker_in_a_directory_nobody_has_made_yet_is_still_written(tmp_path):
    """write_marker runs AFTER the documents are committed, so its one failure mode must not be a bare
    FileNotFoundError out of open(): --marker into a folder that does not exist yet (a timer's own state directory
    on a fresh box) raised exactly that, with the batch already up and nothing said about what a lost marker
    costs - the next pass re-uploads every record in the directory."""
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    marker = os.path.join(str(tmp_path), "state", "sub", "run_records_sync.json")
    p = go(tmp_path, "--write", "--marker", marker)
    assert p.code == 0 and len(p.db.sets) == 1                     # the documents landed ...
    with open(marker, encoding="utf-8") as f:
        assert list(json.load(f)["written"]) == [doc_id_of(rec())]  # ... and so did the marker that records them


def test_a_marker_that_cannot_be_written_at_all_raises_the_tools_own_error(tmp_path):
    """And when no directory can be made there - the parent of the marker is a FILE - it comes back as this
    tool's own error, carrying what a lost marker costs, not as a bare OSError out of open()."""
    blocker = os.path.join(str(tmp_path), "not-a-directory")
    with open(blocker, "w", encoding="utf-8") as f:
        f.write("a file where the marker's folder should be")
    with pytest.raises(rs.ToolError) as e:
        rs.write_marker(os.path.join(blocker, rs.MARKER_NAME), {"rr_abc": "deadbeef"})
    assert "re-uploads every record in this directory" in str(e.value)


def test_a_marker_that_cannot_be_swapped_into_place_raises_and_keeps_the_temp_copy(tmp_path, monkeypatch):
    # losing the idempotency ledger silently means re-uploading every record in the directory, so it must shout
    monkeypatch.setattr(rs, "MARKER_RETRIES", 2)
    monkeypatch.setattr(rs, "MARKER_SLEEP", 0.0)
    real_replace = os.replace

    def busy(src, dst):
        if str(dst).endswith(rs.MARKER_NAME):
            raise PermissionError(32, "another process has it open")   # Windows' WinError 32
        return real_replace(src, dst)

    monkeypatch.setattr(rs.os, "replace", busy)
    path = os.path.join(str(tmp_path), rs.MARKER_NAME)
    with pytest.raises(rs.ToolError) as e:
        rs.write_marker(path, {"rr_abc": "deadbeef"})
    assert "re-uploads every record" in str(e.value)
    assert os.path.exists(path + ".tmp") and not os.path.exists(path)   # left for a human to rename


def test_an_unreadable_marker_says_so_and_re_sends_the_same_document_ids(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    first = go(tmp_path, "--write")
    with open(os.path.join(str(tmp_path), rs.MARKER_NAME), "w", encoding="utf-8") as f:
        f.write("{half a mar")
    p = go(tmp_path, "--write")
    assert "could not be read" in p.text and "costs writes, not correctness" in p.text
    assert p.db.sets[0][0] == first.db.sets[0][0]                   # the content is the id: no duplicate row
    assert len(marker_of(tmp_path)["written"]) == 1                 # and the marker is rebuilt from this pass


# ── repair ───────────────────────────────────────────────────────────────────────────────────
def test_recheck_ignores_the_marker_and_re_sends_the_very_same_document(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    write_records(tmp_path, "LAB_202610.jsonl", [rec(ts="2026-10-17 15:00", where="lab")])
    first = go(tmp_path, "--write")
    assert len(first.db.sets) == 2
    p = go(tmp_path, "NOISE_202610.jsonl", "--write", "--recheck")
    assert len(p.db.sets) == 1 and p.db.sets[0][0][-1] == doc_id_of(rec())
    assert "--recheck" in p.text and "0 already uploaded" in p.text
    # rechecking one file must not forget the other file's rows: the marker is keyed by document, not by file
    assert len(marker_of(tmp_path)["written"]) == 2


def test_the_sync_provenance_is_added_here_and_never_changes_a_document_id(tmp_path):
    write_records(tmp_path, "NOISE_202610.jsonl", [rec()])
    first = go(tmp_path, "--write")
    os.rename(os.path.join(str(tmp_path), "NOISE_202610.jsonl"),
              os.path.join(str(tmp_path), "NOISE-ARCHIVE_202610.jsonl"))
    moved = go(tmp_path, "--write", "--recheck")
    assert moved.db.sets[0][0] == first.db.sets[0][0]               # the file name is not content
    assert moved.db.sets[0][1]["sync_file"] == "NOISE-ARCHIVE_202610.jsonl"


# ── where the records live ───────────────────────────────────────────────────────────────────
def test_the_records_directory_is_the_one_the_lane_side_writer_uses(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_RUN_RECORDS", str(tmp_path / "moved"))
    assert rs.records_root() == str(tmp_path / "moved")
    assert rs.build_parser().parse_args([]).dir == str(tmp_path / "moved")   # read at call time, not at import
    monkeypatch.delenv("EDGELOG_RUN_RECORDS")
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "home"))
    assert rs.records_root() == os.path.join(str(tmp_path / "home"), "run_records")


def test_the_two_stretch_names_the_lanes_already_write_are_first_class(tmp_path):
    """FULL and preLB name real stretches, so they upload and keep their own spelling.

    MEASURED on the seven lanes' 1,199 lines (2026-10-19): 58 FULL (all DISC) and 15 preLB (all FRONTIER). Until
    today both refused, which kept 73 honest runs off the board over spelling. They are NOT mapped onto one of
    the five: index.html gives each its own mark and fills no stretch column for either, so a FULL total is never
    added into a walk-forward figure. Case is not meaning either - a lane writing "full" or "PRELB" means these.
    """
    write_records(tmp_path, "LANES_202610.jsonl",
                  [rec(stage="FULL", note="the whole run as one stretch"),
                   rec(stage="preLB", note="everything before the lockbox"),
                   rec(stage="prelb", trades=319), rec(stage="wf", trades=320)])
    p = go(tmp_path, "--write")
    assert p.code == 0, p.text
    assert [d["stage"] for _p, d, _m in p.db.sets] == ["full", "preLB", "preLB", "WF"]
    # AND A STAGE NOBODY HAS DEFINED STILL REFUSES: the page has no mark for it and the table would print a word
    #   the owner cannot act on.
    write_records(tmp_path, "LANES_202610.jsonl", [rec(stage="halfway")])
    q = go(tmp_path, "--write")
    assert q.code == 2 and q.db.sets == [] and 'stage is "halfway"' in q.text


def test_a_sha_that_is_not_a_commit_costs_itself_and_not_the_run(tmp_path):
    """The sha is a CAPTION. An unusable one is stored null, the line is reported, and the run still plots.

    MEASURED: 50 of the 1,199 real lines carry a 64-character content hash here instead of `git rev-parse HEAD`,
    41 of them with a ROC @ $30k. Refusing the record dropped 41 honest runs to protect a field nobody plots -
    the asymmetry this tool is built on says an absent or unusable CAPTION costs one caption.
    """
    sha256 = hashlib.sha256(b"a line").hexdigest()
    write_records(tmp_path, "CAP_202610.jsonl", [rec(sha=sha256), rec(sha="not-a-sha", trades=319),
                                                 rec(sha="0a102780-dirty", trades=320)])
    p = go(tmp_path, "--write")
    assert p.code == 0, p.text
    assert [d["sha"] for _p, d, _m in p.db.sets] == [None, None, "0a102780-dirty"]
    assert "is not a commit sha" in p.text and "content hash" in p.text
    assert "2 with a caption dropped" in p.text        # said in the file's own head line, not only per line
    assert "REFUSED" not in p.text                     # nothing was refused over it


# ── the frozen schema itself ─────────────────────────────────────────────────────────────────
def test_the_vocabularies_and_defaults_are_the_ones_manager_127_froze():
    assert rs.WHERE == ("runner", "lane", "lab", "box")
    # THE STAGE VOCABULARY GREW ON 2026-10-19, measured on the lanes' own lines: 58 carry FULL and 15 preLB.
    #   Both are first-class, with their own marks on the page, because an unknown stage was not dashed there -
    #   it was bucketed as WALK-FORWARD, and a row reading as the house yardstick when it is not is the one
    #   outcome worse than not plotting it.
    assert rs.STAGES == ("IS", "WF", "LB", "preWF", "forward", "full", "preLB")
    assert rs.STAGE_CANON["full"] == "full" and rs.STAGE_CANON["prelb"] == "preLB"
    assert rs.SCHEMA_V == 1 and rs.DEFAULTS["start_usd"] == 100000.0 and rs.DEFAULTS["note"] == ""
    assert set(rs.KNOWN) == set(rec()) == set(rs.SCHEMA) and len(rs.KNOWN) == 28   # rec() IS the whole schema
    # THE REQUIRED LIST IS THE FIVE FIELDS THAT PLACE A ROW, plus one figure the chart can put on an axis. The
    #   test a required field has to pass is "take it away and there is no row to draw" - and dd5, ddpct, trades,
    #   sha, host, strategy, instrument and timeframe all fail it, because the page dashes every one of them.
    #   They were required until 2026-10-19 and that cost 1,164 of 1,199 real lines.
    assert rs.REQUIRED == ("ts", "lane", "where", "stage", "family")
    assert rs.PLOT_ALTERNATIVES == (("roc30k",), ("net_usd", "max_dd_usd"))
    for k in ("dd5", "ddpct", "trades", "sha", "host", "strategy", "instrument", "timeframe", "one_episode",
              "roc30k", "sortino", "win_start", "win_end", "run_id", "ledger_row"):
        assert k in rs.NULLABLE and k not in rs.REQUIRED, k
    assert set(rs.REQUIRED) | set(rs.NULLABLE) == set(rs.SCHEMA)     # every frozen key is one or the other
    assert rs.COLLECTION == "research_runs" and rs.BATCH_DOCS == 400 and rs.BATCH_BYTES == 9_000_000
    assert rs.SYNC_FIELDS == ("timestamp", "sync_file", "sync_at") and not (set(rs.SYNC_FIELDS) & rs.KNOWN)


def test_a_record_that_leaves_the_optional_fields_out_is_still_valid():
    bare = rec()
    for k in ("start_usd", "note", "schema_v"):
        bare.pop(k)
    out = rs.validate(bare)
    assert out["start_usd"] == 100000.0 and out["note"] == "" and out["schema_v"] == 1
    # leaving the three out is the same record as spelling the defaults out, so it is the same row, not a second one
    assert rs.content_hash(out) == rs.content_hash(rs.validate(rec(note="", start_usd=100000.0, schema_v=1)))
    assert rs.validate(rec(ledger_row=None, run_id=382))["run_id"] == 382


def test_a_drawdown_deeper_than_the_whole_account_is_uploaded_and_a_dollar_figure_is_not(tmp_path):
    """THE ddpct CEILING IS THE RECORD'S OWN DOLLAR DRAWDOWN: ddpct <= 100 x max_dd_usd / start_usd (settled by
    the parent, W47, 2026-10-18; it was a flat 1000 while the two halves of W47 were still arguing 100 vs 1000).

    THE INVARIANT: dd_pct_peak's high-water mark starts AT start_usd and only rises, so every fall is measured
    against a peak at least as big as the account. The bound does not cap the reading the engine's own docstring
    defends - an account that fell below zero really did fall more than 100% from the high before it, and a record
    of THAT run is exactly the row the owner asked to be able to see: a $100k account taken $100k below its start
    reads ddpct 200, and the bound there is 200 too, because the high-water mark never moved off the start. What
    the ceiling still catches is the unit mistake it exists for, and a dollar drawdown in the percent field reads
    hundreds of times the bound. Both sides of the line are pinned here, because the two halves of W47 first
    disagreed about exactly this.
    """
    below_zero = rec(ddpct=200.0, dd5=170000.0, max_dd_usd=200000.0, net_usd=-140000.0, years=4.2, roc30k=-5.0,
                     sortino=-0.42, one_episode=False, note="a $100k account taken $100k below its start")
    write_records(tmp_path, "NOISE_202610.jsonl",
                  [below_zero, rec(ts="2026-10-17 15:00", ddpct=13090.0, note="dollars in the percent field")])
    p = go(tmp_path, "--write")
    assert p.code == 2                                   # one line refused, the pass still ran
    assert [d["ddpct"] for _, d, _m in p.db.sets] == [200.0], "a 200% fall is a real reading and must go up"
    assert "REFUSED line 2" in p.text and "dollar figure in the percent field" in p.text


def test_a_percent_too_deep_for_the_records_own_dollars_is_refused(tmp_path):
    """What a flat ceiling of 1000 let through: 137.4% beside a $21,100 worst drawdown of a $100k account, where
    the bound is 21.1000% - a percent and a dollar drawdown measured on two different curves, and the page would
    plot the pair. MEASURED over 400 random daily series straight through four_numbers: the largest excess over
    the bound was +0.000044 (dd_pct_peak's rounding to 4 dp), so the cent of slack this check allows is rounding
    and nothing else, while 137.4 against 21.1000 is six times the bound."""
    write_records(tmp_path, "NOISE_202610.jsonl", [rec(), rec(ts="2026-10-17 15:00", ddpct=137.4)])
    p = go(tmp_path, "--write")
    assert p.code == 2 and len(p.db.sets) == 1
    assert "REFUSED line 2" in p.text
    assert "at most 100 x $21,100.00 / $100,000.00 = 21.1000%" in p.text
    # the same percent with the dollars to match is an honest row, and goes up
    ok = rs.validate(rec(ddpct=137.4, dd5=130000.0, max_dd_usd=137400.0, net_usd=-40000.0, years=4.2,
                         roc30k=-6.986, sortino=-0.3, one_episode=False))
    assert ok["ddpct"] == 137.4
    # and a record with no max_dd_usd to derive a bound from still has the writer's blunt bar behind it
    assert rs.DDPCT_ABSURD == 1000.0
    lab = rec(max_dd_usd=None, one_episode=None, ddpct=13090.0, note="the lab shape: no worst drawdown handed in")
    with pytest.raises(rs.Refusal) as e:
        rs.validate(lab)
    assert "no max_dd_usd beside it" in str(e.value) and "dollar figure in the percent field" in str(e.value)
    assert rs.validate(dict(lab, ddpct=137.4))["ddpct"] == 137.4


# == AN ABSENT FIGURE COSTS ONE AXIS (parent, W47, 2026-10-19) ================================
def test_a_sparse_record_with_only_the_placing_fields_and_one_figure_uploads_with_nulls(tmp_path):
    """THE NEW CONTRACT IN ONE RECORD: the five fields that place a row, one figure the chart can put on an axis,
    and nothing else at all. It uploads, and every other frozen key is in the document as NULL.

    The nulls are the point and not a side effect. A document that simply omitted what the lane did not measure
    would leave the page unable to tell NOT MEASURED from a reading of zero - and those are different facts about
    a run: a dash says nobody looked, a 0.00 says somebody looked and the answer was nothing. The board prints
    them differently, so the document has to carry the difference."""
    sparse = {"ts": "2026-10-18 11:20", "lane": "TBIS", "where": "lane", "stage": "IS", "family": "TBIS",
              "roc30k": 11.4}
    write_records(tmp_path, "TBIS_202610.jsonl", [sparse])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1, p.text
    d = p.db.sets[0][1]
    assert d["roc30k"] == 11.4 and d["ts"] == "2026-10-18 11:20" and d["where"] == "lane"
    assert set(d) == set(rs.SCHEMA) | set(rs.SYNC_FIELDS)            # every frozen key, nothing invented
    for k in ("host", "strategy", "instrument", "timeframe", "dd5", "ddpct", "sortino", "trades", "gross_pt",
              "cost_pt", "one_episode", "ledger_row", "run_id", "sha", "net_usd", "max_dd_usd", "years",
              "win_start", "win_end"):
        assert d[k] is None, k
    assert d["start_usd"] == 100000.0 and d["note"] == "" and d["schema_v"] == 1   # the three documented defaults
    # and the dry report says what it would plot, with a dash for every figure the row does not carry
    assert "ROC@30k   11.40" in p.text and "DD5 $-" in p.text and "Sortino      -" in p.text


@pytest.mark.parametrize("patch", [{"strategy": None}, {"strategy": ""}, {"strategy": "   "}, {"host": ""}])
def test_a_label_the_lane_did_not_write_is_a_null_not_a_refusal(tmp_path, patch):
    """4 of the seven lanes' 1,199 records name only their family, and 22 carry no instrument or timeframe. A run
    whose name is "BOOK" instead of "BOOK #436" is a run with a less specific name - the page already falls back
    to the family (`d.strategy||d.family||'a lane run'`) - so there is nothing here for a refusal to protect.

    A BLANK READS AS THE SAME NULL. A lane that wrote "" had nothing to write, and normalising it before the
    content hash is what makes "" last week and the key left out this week ONE row instead of two. `host` was
    a refusal for exactly this ("host is blank") until 2026-10-19."""
    write_records(tmp_path, "BOOK_202610.jsonl", [rec(**patch)])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1, p.text
    k = list(patch)[0]
    assert p.db.sets[0][1][k] is None
    assert doc_id_of(rec(**patch)) == doc_id_of(rec(**{k: None}))     # one row, however the lane spelled it


@pytest.mark.parametrize("missing", [
    ("dd5", "ddpct"),                                           # 200 of the 1,199 real lines
    ("dd5", "ddpct", "sha", "trades"),                           # 214
    ("trades",),                                                 # 138
    ("ddpct",),                                                  # 88
    ("dd5", "ddpct", "trades"),                                  # 82
    ("dd5", "ddpct", "sha"),                                     # 57
    ("sha", "trades"),                                           # 37
    ("sha",),                                                    # 36
    ("ddpct", "trades"),                                         # 24
    ("instrument", "timeframe"),                                 # 22
    ("host", "strategy", "instrument", "timeframe", "dd5", "ddpct", "sortino", "trades", "gross_pt", "cost_pt",
     "one_episode", "ledger_row", "run_id", "sha", "net_usd", "max_dd_usd", "years", "win_start", "win_end"),
])
def test_the_record_shapes_the_seven_lanes_really_wrote_are_accepted(tmp_path, missing):
    """THE MEASUREMENT THIS ROUND CAME OUT OF, as a table. Each row is a shape counted in the seven lanes' own
    1,199 records in C:/EdgeLog/run_records on 2026-10-19, with the count the dry pass refused it for. Together
    they were 1,025 of the 1,164 refusals, every one of them for a figure that was simply not measured; the other
    139 were a timestamp written as ISO. The last row is the floor of the contract: everything optional gone at
    once, one ROC left, still a row."""
    write_records(tmp_path, "LANES_202610.jsonl", [rec(**{k: None for k in missing})])
    p = go(tmp_path, "--write")
    assert p.code == 0 and len(p.db.sets) == 1, p.text
    d = p.db.sets[0][1]
    for k in missing:
        assert d[k] is None, k
    assert d["roc30k"] == 41.7                                   # the figure that places it is still there


# == THE TIMESTAMP IS NORMALISED, NEVER REFUSED ===============================================
@pytest.mark.parametrize("written, stored", [
    ("2026-09-26 11:06", "2026-09-26 11:06"),                    # the stored shape itself, unchanged
    ("2026-09-26 11:06:38", "2026-09-26 11:06"),                 # seconds truncated, as the runner's own stamp
    ("2026-09-26", "2026-09-26 00:00"),                          # a bare day reads as midnight: 275 real lines
    ("2026-09-26T11:06:38-07:00", "2026-09-26 11:06"),           # ISO with an offset: 676 real lines
    ("2026-10-18T14:44:14-07:00", "2026-10-18 14:44"),           # the one the first pass refused 139 times
    ("2026-09-26T11:06:38", "2026-09-26 11:06"),                 # ISO with no offset: 73 real lines
    ("2026-09-26T11:06:38.512-07:00", "2026-09-26 11:06"),       # fractional seconds
    ("2026-09-26T11:06:38Z", "2026-09-26 11:06"),
    ("2026-09-26T11:06+00:00", "2026-09-26 11:06"),
    ("  2026-09-26 11:06  ", "2026-09-26 11:06"),
])
def test_every_timestamp_shape_a_lane_writes_normalises_to_the_stored_shape(written, stored):
    """THE WALL CLOCK IS NEVER MOVED, only re-spelled: an offset is DROPPED, not converted. What a lane writes
    with datetime.now(tz).isoformat() already is that lane's local wall clock, which is what the stored shape
    carries - a run document's timestamp names no zone at all - so dropping the offset preserves the reading.
    Converting into the syncing host's zone would move a stamp nobody asked to move AND make the stored string,
    and so the content-hash document id, depend on which machine ran the pass. All 676 offsets in the real
    records are -07:00, the owner's own. That is why the Z and +00:00 rows above read 11:06 and not 04:06."""
    assert rs.validate(rec(ts=written))["ts"] == stored
    # re-spelling is not a new run: every shape above is the same row as the stored one
    assert doc_id_of(rec(ts=written)) == doc_id_of(rec(ts=stored))


def test_the_stored_stamp_is_the_string_the_pages_month_read_actually_uses(tmp_path):
    """WHICH FIELD, AND WHICH SHAPE. index.html's _monQuery is shared by the runs read and the research_runs
    read: it sends a lexicographic string range (GREATER_THAN_OR_EQUAL "2026-10-01", LESS_THAN "2026-11-01")
    against the field path `timestamp` and orders by the same field, and the row builder reads `d.timestamp` for
    the row's DATE RAN. A Firestore field filter does not return a document that lacks the field, so a record
    uploaded under `ts` alone is in the collection and invisible on the board - the one outcome W47 exists to
    prevent. So the sync writes the normalised stamp under BOTH names, and `timestamp` is a SYNC field: outside
    the content hash, so it can never put the same run on the board twice, and refused as an unknown field if a
    lane tries to write its own."""
    write_records(tmp_path, "FRONTIER_202610.jsonl", [rec(ts="2026-10-18T14:44:14-07:00")])
    p = go(tmp_path, "--write")
    assert p.code == 0
    d = p.db.sets[0][1]
    assert d["ts"] == d["timestamp"] == "2026-10-18 14:44"
    assert "2026-10-01" <= d["timestamp"] < "2026-11-01"             # the page's own test, on the stored string
    assert "timestamp" not in rs.validate(rec(ts="2026-10-18T14:44:14-07:00"))      # not hashed
    with pytest.raises(rs.Refusal) as e:
        rs.validate(dict(rec(), timestamp="2026-10-18 14:44"))
    assert "field(s) the frozen schema does not have: timestamp" in str(e.value)
    # MEASURED, because the obvious claim about the shape is wrong and this file does not repeat it: the ISO
    #   stamp DOES fall inside a whole-month bound, since its first ten characters are the date. What it breaks
    #   is the ORDER the page asks for - a space is 0x20 and a T is 0x54, so an 08:00 ISO row sorts above a
    #   09:00 local one in a newest-first list - and any bound tighter than a month.
    assert "2026-10-01" <= "2026-10-18T14:44:14-07:00" < "2026-11-01"
    assert "2026-10-18 09:00" < "2026-10-18T08:00:00-07:00"


def test_a_lane_run_id_that_is_no_number_is_a_label_not_a_refusal():
    """677 of the 1,199 real records carry run_id as a STRING - "#382" out of the BOOK ledger,
    "qlab-verify:20261017-1607-scalper:house" out of the lab, a DISC backfill's own slug - because a lane run has
    no engine run number to give. Nothing is PLOTTED from it (the page prints " . run #N" only when it reads as a
    number), so a label it cannot parse costs that caption and nothing else.

    THE ONE CHECK THAT HAS TO SURVIVE is the runner's PROVISIONAL int(time.time()) id, and it is applied to the
    NUMBER a run_id reads as - whether written as 1760000000, as "1760000000" or as "#1760000000" - so quoting
    the figure cannot smuggle it past."""
    for rid in ("#382", "DISC-bf-20260925-cbdq-1m-1-0-r1-es-best-cell-pm-low", 491,
                "qlab-verify:20261017-1607-scalper:house"):
        assert rs.validate(rec(run_id=rid))["run_id"] == rid
    assert rs.validate(rec(run_id="  #382  "))["run_id"] == "#382"           # stripped, like every other text
    for bad in (int(time.time()), str(int(time.time())), "#1760000000"):
        with pytest.raises(rs.Refusal) as e:
            rs.validate(rec(run_id=bad))
        assert "not a plausible run number (1..100000" in str(e.value), bad
        assert "PROVISIONAL id, int(time.time())" in str(e.value)


def test_the_dry_report_survives_a_row_whose_figures_are_all_null(tmp_path):
    """The dry pass is the whole product of a run without --write, so a figure that is null must print as a dash
    and never raise: f"{None:,.0f}" is a TypeError, and one of those in the middle of the report turns the pass
    that is supposed to say what would go up into one that says nothing at all. dd5 was formatted that way until
    2026-10-19, when it stopped being a required field."""
    bare = {"ts": "2026-10-18 11:20", "lane": "TTM", "where": "box", "stage": "forward", "family": "TTM",
            "net_usd": 1200.0, "max_dd_usd": 400.0}
    write_records(tmp_path, "TTM_202610.jsonl", [bare])
    p = go(tmp_path)                                                # dry: the report is the only output
    assert p.code == 0 and p.db.sets == [] and "1 new" in p.text
    line = [t for t in p.text.split("\n") if t.startswith("  + rr_")]
    assert len(line) == 1 and "TTM" in line[0] and "forward" in line[0]
    assert "ROC@30k       -" in line[0] and "DD5 $-" in line[0] and "DD      -%" in line[0]

