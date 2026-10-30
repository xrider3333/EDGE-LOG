#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The open-board mirror (owner 10-30, MANAGER #156).

The board is the owner's to-do list, so the one failure that matters here is DROPPING a row he is
waiting on. These tests hold the parser to the board's real shape and make the unknown-status path
explicit: a status this tool has never seen counts as OPEN and is named in the document, never
quietly discarded.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import board_publish as B   # noqa: E402

SAMPLE = """# EDGE-LOG Open Board (copy for Qwen/Cline - read-only; live board: https://x)

## WORK
- **item 1** [done] KEEL: match its backtest | who: Custom ML + Webull | date: 2026-10-12
  - what: Per-trade KEEL live on Webull since Mon
  - statusText: LIVE 10-12
- **item 3** [block] RESMOM real data pull | who: You | date: 2026-10-11
  - what: Sat 10-31 07:00 MST, about 3 h. Leave the PC on
  - statusText: NEEDS YOU 10-31
- **item 9** [wip] column filters | who: ELWA | date: 2026-10-30
  - what: per-column header filter, sort and range

## TESTS
- **test 4** [confirmed] paper parity | who: PAPER-WB | date: 2026-10-20
  - what: fills match the logged trades
- **test 7** [sideways] something nobody has classified | who: MANAGER | date: 2026-10-30
  - what: a status this tool has never seen
"""


def test_the_real_board_shape_is_parsed():
    rows = B.parse_board(SAMPLE)
    assert [r['n'] for r in rows] == ['item 1', 'item 3', 'item 9', 'test 4', 'test 7']
    r = rows[1]
    assert r['status'] == 'block'
    assert r['title'] == 'RESMOM real data pull'
    assert r['who'] == 'You'
    assert r['date'] == '2026-10-11'
    assert 'Leave the PC on' in r['what']
    assert r['statusText'] == 'NEEDS YOU 10-31'
    assert r['section'] == 'WORK'
    assert rows[3]['section'] == 'TESTS', 'the section header has to follow the rows under it'


def test_finished_rows_are_left_out_and_open_ones_kept():
    doc = B.build_doc(B.parse_board(SAMPLE), now=1.0)
    ns = [r['n'] for r in doc['rows']]
    assert 'item 1' not in ns, 'done is finished'
    assert 'test 4' not in ns, "confirmed is the owner's own last step, so it is finished too"
    assert ns == ['item 3', 'item 9', 'test 7']
    assert doc['total'] == 5 and doc['open'] == 3


def test_an_unrecognised_status_counts_as_OPEN_and_is_named():
    """Dropping a row the owner is waiting on is the only failure that really matters here."""
    doc = B.build_doc(B.parse_board(SAMPLE), now=1.0)
    assert 'test 7' in [r['n'] for r in doc['rows']], 'an unknown status must still be shown'
    assert doc['unknown'] == ['sideways'], 'and it has to be named so someone classifies it'


def test_the_statuses_the_real_board_uses_are_all_classified():
    """Measured on the board 2026-10-30: these four were unclassified on the first run."""
    rows = [{'n': 'r%d' % i, 'title': 't', 'status': s, 'statusText': '', 'who': '', 'date': '',
             'what': '', 'section': 'WORK'}
            for i, s in enumerate(('needs-you', 'park', 'wait', 'confirmed'))]
    doc = B.build_doc(rows, now=1.0)
    assert doc['unknown'] == [], 'all four are known now'
    assert [r['status'] for r in doc['rows']] == ['needs-you', 'park', 'wait'], \
        'three are open, confirmed is finished'


def test_the_counts_say_what_the_board_holds():
    doc = B.build_doc(B.parse_board(SAMPLE), now=1.0)
    assert doc['kinds'] == {'done': 1, 'block': 1, 'wip': 1, 'confirmed': 1, 'sideways': 1}
    assert doc['source'] and doc['at'] == 1.0


def test_a_long_board_is_capped_and_says_so():
    rows = [{'n': 'item %d' % i, 'title': 't', 'status': 'open', 'statusText': '', 'who': '',
             'date': '', 'what': '', 'section': 'WORK'} for i in range(B.MAX_ROWS + 25)]
    doc = B.build_doc(rows, now=1.0)
    assert len(doc['rows']) == B.MAX_ROWS
    assert doc['open'] == B.MAX_ROWS + 25, 'the COUNT is honest even when the list is cut'
    assert doc['cut'] is True


def test_text_is_flattened_and_bounded_so_one_row_cannot_blow_the_document():
    big = 'x' * 5000
    rows = B.parse_board('## WORK\n- **item 1** [open] t | who: W | date: D\n  - what: %s\n' % big)
    assert len(rows) == 1
    assert len(rows[0]['what']) <= B.MAX_TEXT
    multi = B.parse_board('## WORK\n- **item 1** [open] t\n  - what: one   two\n')
    assert multi[0]['what'] == 'one two', 'runs of whitespace collapse'


def test_junk_between_rows_is_ignored_rather_than_fatal():
    rows = B.parse_board('## WORK\nsome prose\n\n- **item 1** [open] t\n  - notes: ignored\n'
                         '  - what: kept\n> quote\n')
    assert len(rows) == 1 and rows[0]['what'] == 'kept'


def test_an_empty_board_publishes_nothing_rather_than_an_empty_mirror():
    doc = B.build_doc(B.parse_board('# nothing here\n'), now=1.0)
    assert doc['total'] == 0 and doc['rows'] == []
