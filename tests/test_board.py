#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The live board's writer (owner 10-30, MANAGER #159).

Every lane writes the owner's to-do list through this tool, so the failures that matter are the
quiet ones: a row landing in the wrong list, a status nothing renders, and a lane's one-field
update wiping the title or the note MANAGER wrote. Each is held here.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import board as B   # noqa: E402


# ── the smallest Firestore that behaves like the real one for this tool ─────────────────────────
class FakeSnap(object):
    def __init__(self, i, d):
        self.id = i
        self._d = d
        self.exists = d is not None

    def to_dict(self):
        return dict(self._d or {})


class FakeDoc(object):
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def collection(self, c):
        return FakeColl(self.store, self.path + '/' + c)

    def get(self):
        return FakeSnap(self.path.rsplit('/', 1)[-1], self.store.get(self.path))

    def set(self, d):
        self.store[self.path] = dict(d)


class FakeColl(object):
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def document(self, d):
        return FakeDoc(self.store, self.path + '/' + d)

    def stream(self):
        out = []
        for k, v in sorted(self.store.items()):
            head, _, tail = k.rpartition('/')
            if head == self.path:
                out.append(FakeSnap(tail, v))
        return out


class FakeDb(object):
    def __init__(self):
        self.store = {}

    def collection(self, c):
        return FakeColl(self.store, c)


BOARD = 'users/%s/board' % B.UID


@pytest.fixture
def db():
    return FakeDb()


def opts(**kw):
    o = {'why': None, 'title': None, 'who': None, 'date': None, 'label': None, 'order': None,
         'frm': 'ELWA', 'dry': False, 'strict_new': False}
    for k in B.RUN_FIELDS:
        o[k] = None
    o.update(kw)
    return o


def add(db, rid, status='queued', state='', **kw):
    kw.setdefault('title', 'a thing')
    return B.cmd_set(db, rid, status, state, opts(**kw), create=True)[0]


# ── the row id is the only thing that places a row ──────────────────────────────────────────────
def test_the_id_prefix_decides_the_list():
    assert B.parse_id('w12') == ('w12', 'WORK', 12)
    assert B.parse_id('T47')[1] == 'RUNS'
    assert B.parse_id('b7')[1] == 'AUTOMATIONS'
    assert B.parse_id('c12')[1] == 'AUTOMATIONS', 'the board numbers automations B1.. and C1..'
    assert B.parse_id('p03')[1] == 'PC'
    assert B.parse_id('q2')[1] == 'QWEN'


@pytest.mark.parametrize('bad', ['12', 'x4', 'w', 'item 12', 'w1234', 'w-1', ''])
def test_an_id_the_page_could_not_place_is_refused(bad):
    with pytest.raises(B.ToolError):
        B.parse_id(bad)


# ── the status words are closed, and the near-misses map rather than fail ───────────────────────
def test_every_owner_status_is_accepted():
    for s in B.STATUSES:
        assert B.check_status(s) == s


def test_the_words_lanes_actually_type_are_mapped():
    assert B.check_status('wip') == 'run'
    assert B.check_status('NeedsYou') == 'needs-you'
    assert B.check_status('blocked') == 'block'
    assert B.check_status('hold') == 'park'


def test_an_invented_status_is_refused_and_names_the_real_ones():
    with pytest.raises(B.ToolError) as e:
        B.check_status('sideways')
    assert 'needs-you' in str(e.value) and 'confirmed' in str(e.value)


def test_only_the_three_finished_words_and_confirmed_close_a_row():
    for s in ('done', 'pass', 'fail', 'confirmed'):
        assert not B.is_open(s)
    for s in B.NEED + B.OPEN:
        assert B.is_open(s)
    assert B.is_open('sideways'), 'a status nobody classified still has to show as open'


# ── a lane's one-field update must not erase the row ────────────────────────────────────────────
def test_setting_the_status_keeps_the_title_and_the_note(db):
    add(db, 'w12', 'queued', 'QUEUED', title='column filters', who='ELWA',
        why='per-column header filter, sort and range')
    row, msg = B.cmd_set(db, 'w12', 'wip', 'landed v73.1402', opts(), create=False)
    assert row['status'] == 'run' and row['statusText'] == 'landed v73.1402'
    assert row['title'] == 'column filters', "a status change must not wipe MANAGER's title"
    assert row['why'].startswith('per-column'), 'nor the note behind the row'
    assert row['who'] == 'ELWA'
    assert 'w12' in msg


def test_a_row_that_is_not_there_yet_is_not_invented_by_set(db):
    with pytest.raises(B.ToolError) as e:
        B.cmd_set(db, 'w99', 'queued', '', opts(), create=False)
    assert 'add w99' in str(e.value), 'the refusal has to say how to put it on the board'


def test_a_new_row_needs_a_title_and_a_status(db):
    with pytest.raises(B.ToolError):
        B.cmd_set(db, 'w13', 'queued', '', opts(), create=True)   # no title


def test_add_refuses_to_walk_over_a_row_that_exists(db):
    add(db, 'w12')
    with pytest.raises(B.ToolError) as e:
        B.cmd_set(db, 'w12', 'queued', '', opts(strict_new=True, title='x'), create=True)
    assert 'already on the board' in str(e.value)


def test_a_dry_run_writes_nothing(db):
    add(db, 'w12', 'queued', 'QUEUED')
    before = json.dumps(db.store, sort_keys=True)
    row, msg = B.cmd_set(db, 'w12', 'fail', 'broke', opts(dry=True), create=False)
    assert row['status'] == 'fail'
    assert msg.startswith('DRY RUN')
    assert json.dumps(db.store, sort_keys=True) == before


def test_every_write_stamps_who_wrote_it_and_when(db):
    row = add(db, 'w12', frm='ENGU-Q')
    assert row['updated_by'] == 'ENGU-Q'
    assert row['updated_at'].endswith('Z') and len(row['updated_at']) == 20
    assert row['date'], 'a row with no date would sort as the oldest thing on the board'


# ── run numbers belong to RUNS rows only ────────────────────────────────────────────────────────
def test_a_runs_row_carries_its_four_numbers(db):
    row = add(db, 't47', 'fail', 'RUN #489', roc='10.1 (chain)', dd5='- / $39.4k',
              ddpct='- / 17.0%', sortino='1.21 / 6.06', result='fails 3 of 6 clauses')
    assert row['roc'] == '10.1 (chain)' and row['sortino'] == '1.21 / 6.06'


def test_a_work_row_cannot_carry_a_run_number(db):
    """Otherwise the RUNS table would print a figure for a row that never ran anything."""
    with pytest.raises(B.ToolError) as e:
        add(db, 'w12', 'queued', '', roc='10.1')
    assert 'RUNS field' in str(e.value)


# ── reading back ────────────────────────────────────────────────────────────────────────────────
def test_list_is_grouped_by_list_then_board_order(db):
    add(db, 'w12', 'queued', title='b', order=12)
    add(db, 'w03', 'queued', title='a', order=3)
    add(db, 't47', 'fail', title='run', order=47)
    assert [r['_id'] for r in B.read_rows(db)] == ['t47', 'w03', 'w12']
    assert [r['_id'] for r in B.read_rows(db, tab='WORK')] == ['w03', 'w12']


def test_the_open_filter_leaves_the_finished_rows_out(db):
    add(db, 'w01', 'done', 'LIVE 10-12')
    add(db, 'w02', 'needs-you', 'NEEDS YOU 10-31')
    assert [r['_id'] for r in B.read_rows(db, only_open=True)] == ['w02']
    _, msg = B.cmd_list(db, None, False)
    assert '2 rows, 1 open' in msg


def test_get_says_so_plainly_when_the_row_is_not_there(db):
    with pytest.raises(B.ToolError) as e:
        B.cmd_get(db, 'w77')
    assert 'not on the board' in str(e.value)


# ── the one-time seed from MANAGER's dump ───────────────────────────────────────────────────────
def _dump(tmp_path, sub, name, doc):
    d = tmp_path / sub
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps(doc), encoding='utf-8')


def test_the_dump_file_name_is_the_row_id(tmp_path):
    _dump(tmp_path, 'work', 'w01.json',
          {'order': 1, 'status': 'done', 'statusText': 'LIVE 10-12', 'title': 'KEEL',
           'what': 'Per-trade KEEL live', 'who': 'Custom ML', 'date': '2026-10-12'})
    _dump(tmp_path, 'auto', 'b1.json',
          {'order': 1, 'label': 'B1', 'status': 'queued', 'statusText': 'LIVE on the box',
           'title': 'Daily check', 'what': 'Runs as the Qwen runner', 'who': 'Custom ML',
           'date': '2026-10-30'})
    rows = B.seed_rows(str(tmp_path))
    ids = dict((r['_id'], r) for r in rows)
    assert sorted(ids) == ['b1', 'w01']
    assert ids['w01']['tab'] == 'WORK' and ids['b1']['tab'] == 'AUTOMATIONS'
    assert ids['b1']['label'] == 'B1'
    assert ids['w01']['why'] == 'Per-trade KEEL live', "the dump's long note becomes the why"


def test_the_dumps_appended_edits_are_kept_not_dropped(tmp_path):
    _dump(tmp_path, 'work', 'w09.json',
          {'order': 9, 'status': 'run', 'title': 't', 'what': 'first',
           'what_append_1018': 'then this', 'what_append_1019': 'and this'})
    r = B.seed_rows(str(tmp_path))[0]
    assert r['why'] == 'first then this and this'


def test_a_dump_row_in_the_wrong_folder_is_refused(tmp_path):
    _dump(tmp_path, 'work', 't47.json', {'order': 47, 'status': 'fail', 'title': 't'})
    with pytest.raises(B.ToolError) as e:
        B.seed_rows(str(tmp_path))
    assert "start with 'w'" in str(e.value)


def test_a_dump_status_the_board_does_not_know_stops_the_seed(tmp_path):
    """The seed is one shot, so a status nothing renders must be seen now, not on the page."""
    _dump(tmp_path, 'work', 'w05.json', {'order': 5, 'status': 'sideways', 'title': 't'})
    with pytest.raises(B.ToolError) as e:
        B.seed_rows(str(tmp_path))
    assert 'sideways' in str(e.value)


def test_the_real_dump_seeds_cleanly_if_it_is_on_this_machine():
    """Measured 2026-10-30: 184 rows across work/tests/auto/pc."""
    d = r'C:\EdgeLog\manager\open_board\db3'
    if not os.path.isdir(d):
        pytest.skip('the dump is only on the owner PC')
    rows = B.seed_rows(d)
    assert len(rows) >= 150
    assert set(r['tab'] for r in rows) <= {'WORK', 'RUNS', 'AUTOMATIONS', 'PC', 'QWEN'}
    assert all(r.get('title') for r in rows), 'a row with no title reads as an empty line'


def test_seeding_over_a_board_that_already_has_rows_is_refused(db, tmp_path):
    add(db, 'w12')
    _dump(tmp_path, 'work', 'w01.json', {'order': 1, 'status': 'done', 'title': 't'})
    with pytest.raises(B.ToolError) as e:
        B.cmd_seed(db, str(tmp_path), 'ELWA', dry=False)
    assert '--force' in str(e.value)
    rows, msg = B.cmd_seed(db, str(tmp_path), 'ELWA', dry=False, force=True)
    assert 'SEEDED: 1' in msg
    assert db.store[BOARD + '/w01']['status'] == 'done'


def test_an_empty_dump_is_an_error_rather_than_an_emptied_board(db, tmp_path):
    with pytest.raises(B.ToolError):
        B.cmd_seed(db, str(tmp_path), 'ELWA', dry=False)


# ── the written pages ───────────────────────────────────────────────────────────────────────────
def test_a_board_page_is_markdown_with_the_day_it_was_taken(db, tmp_path):
    f = tmp_path / 'auto.md'
    f.write_text('# AUTOMATIONS\n\n- B1 runs nightly\n', encoding='utf-8')
    doc, msg = B.cmd_meta(db, 'auto', str(f), 'ELWA', dry=False)
    assert doc['md'].startswith('# AUTOMATIONS')
    assert doc['updated'] and doc['updated_by'] == 'ELWA'
    assert db.store['users/%s/meta/board_auto' % B.UID]['md'] == doc['md']
    assert 'AUTO' in msg


def test_only_the_three_real_pages_are_accepted(db, tmp_path):
    f = tmp_path / 'x.md'
    f.write_text('x', encoding='utf-8')
    with pytest.raises(B.ToolError):
        B.cmd_meta(db, 'runs', str(f), 'ELWA', dry=False)


def test_text_is_flattened_and_bounded_so_one_row_cannot_blow_the_document(db):
    row = add(db, 'w12', 'queued', 'x' * 900, why='a' * 5000, title='one   two')
    assert len(row['statusText']) <= 200
    assert len(row['why']) <= B.TEXT_CAP
    assert row['title'] == 'one two'


# ── a push says so on the row it names (MANAGER #159: ship appends a board set) ─────────────────
@pytest.mark.parametrize('msg,rid', [
    ('The board on EDGE-LOG is the live board now [w29]', 'w29'),
    ('DD% per stretch (w51)', 'w51'),
    ('paper parity, board:t32', 't32'),
    ('nightly roll check [B7]', 'b7'),
    ('the live board [c12] wired', 'c12'),
])
def test_the_row_id_a_ship_message_names_is_found(msg, rid):
    assert B.row_in_message(msg) == rid


@pytest.mark.parametrize('msg', [
    # THE ONE THAT MATTERS: a lane numbers its OWN reply table the same way the board numbers
    # rows, and the first ship under this feature was subjected "(item 29)" meaning its own row
    # 29, while board row w29 is an NT8 alert from 10-15. One wrong stamp is worse than silence.
    'The board is the live board now, written by every lane (item 29)',
    'item 51: DD% per stretch',
    'test 32 paper parity',
    'fix the 51 runs that lost their DD%',
    'bumped to v73.1402',
    '',
    None,
])
def test_a_message_with_no_row_id_writes_nothing(msg):
    assert B.row_in_message(msg) is None


def test_a_push_writes_the_state_line_without_deciding_the_status(db):
    add(db, 'w51', 'run', 'in a worktree', title='DD% per stretch', why='owner 10-25')
    row, msg = B.cmd_pushed(db, 'w51', 'PUSHED v73.1402 a1b2c3d4 - DD% per stretch', 'ELWA', False)
    assert row['statusText'] == 'PUSHED v73.1402 a1b2c3d4 - DD% per stretch'
    assert row['status'] == 'run', 'a push is not a finished row'
    assert row['why'].startswith('owner 10-25'), 'the note it already had is kept'
    assert 'a1b2c3d4' in row['why'], 'and the push is appended to it'
    assert row['updated_by'] == 'ELWA'
    assert 'w51' in msg


def test_a_push_on_a_row_that_is_not_on_the_board_is_refused(db):
    with pytest.raises(B.ToolError) as e:
        B.cmd_pushed(db, 'w51', 'PUSHED v1 abc - x', 'ELWA', False)
    assert 'not on the board' in str(e.value)


def test_a_page_can_come_from_managers_own_json_dump(db, tmp_path):
    f = tmp_path / 'meta_auto.json'
    f.write_text(json.dumps({'md': '# AUTOMATIONS' + chr(10) + chr(10) + '- B1 runs nightly',
                             'updated': '2026-10-30'}), encoding='utf-8')
    doc, _ = B.cmd_meta(db, 'auto', str(f), 'ELWA', dry=False)
    assert doc['md'].startswith('# AUTOMATIONS')
    assert 'B1 runs nightly' in doc['md']


def test_a_json_page_with_no_text_is_refused_rather_than_blanking_the_page(db, tmp_path):
    f = tmp_path / 'meta_auto.json'
    f.write_text('{"updated": "2026-10-30"}', encoding='utf-8')
    with pytest.raises(B.ToolError):
        B.cmd_meta(db, 'auto', str(f), 'ELWA', dry=False)
