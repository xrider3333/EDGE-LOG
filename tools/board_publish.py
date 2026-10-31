#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/board_publish.py -- SUPERSEDED 2026-10-30 by tools/board.py (MANAGER #159).

The EL BOARD tab no longer reads the document this writes: the board is LIVE now, one row per
document in users/{uid}/board, written by whichever lane owns the row with `board.py set`. This
tool still parses board.md and still writes meta/open_board, so nothing that depended on that
document breaks, but NOTHING ON THE WEBSITE READS IT - publishing here will not move the board.

Put the open board's OPEN rows where the website can read them.

OWNER 10-30 (MANAGER #156): "Open Board on EL: mirror the artifact board's open rows on an EL page
(read-only) so the owner has it next to the trading tabs."

WHY A PUBLISH STEP AT ALL. The board lives on this machine as
C:/EdgeLog/manager/open_board/board.md, and EDGE-LOG is a static page served by GitHub Pages - it
cannot read a local file. So one Firestore document carries the open rows, exactly the way
tools/runboard_watch.py already feeds COMPARE > RUNBOARD, and the page reads that. No new backend,
no commit per board edit.

WHAT COUNTS AS OPEN. Everything that is NOT finished: the board's own statuses are [done] / [block]
/ [wip] / [new] / [hold] / [pass] / [fail] and friends, and only done, pass, fail and closed are
finished. A row whose status this tool does not recognise is treated as OPEN and SAID SO in the
document, because quietly dropping a row the owner is waiting on is the one failure that matters
here - the board is his to-do list, not a report.

THE DOCUMENT (users/{uid}/meta/open_board), small on purpose - the board is ~400 lines and the
Firestore cap is 1 MiB:
  {at, source, total, open, kinds: {status: n}, unknown: [status...],
   rows: [{n, title, status, statusText, who, date, what, section}]}

  python tools/board_publish.py              # read, publish, print one line
  python tools/board_publish.py --dry-run    # read and print, write nothing
  python tools/board_publish.py --json       # the document, to stdout
"""
import argparse
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BOARD = os.environ.get('EDGELOG_BOARD_MD') or r'C:\EdgeLog\manager\open_board\board.md'
UID = 'IO0K35JpLIcH9YK4C0pMNYUzZOM2'

# the statuses that mean the row is FINISHED. Anything else is open - including a status this tool
# has never seen, which is reported rather than silently dropped.
# MEASURED against the real board 2026-10-30: it also uses 'confirmed', which is the owner's
# own last step (his status circles run needs-you / open / run / done / CONFIRMED), so it is
# finished; and needs-you, park and wait, which are all still open.
DONE = ('done', 'closed', 'pass', 'fail', 'dead', 'live', 'confirmed')
OPEN_KNOWN = ('block', 'wip', 'new', 'hold', 'next', 'open', 'queued', 'draft', 'ask',
              'run', 'running', 'needs-you', 'needsyou', 'park', 'parked', 'wait')

ROW_RE = re.compile(r'^\s*-\s+\*\*(?P<id>[^*]+)\*\*\s*\[(?P<status>[^\]]*)\]\s*(?P<rest>.*)$')
SUB_RE = re.compile(r'^\s+-\s+(?P<key>what|statusText|status|who|date)\s*:\s*(?P<val>.*)$')
SEC_RE = re.compile(r'^##\s+(?P<name>.+?)\s*$')
MAX_ROWS = 300
MAX_TEXT = 400


def _one(s, cap=MAX_TEXT):
    return ' '.join(str(s or '').split())[:cap]


def parse_board(text):
    """board.md -> [{n,title,status,statusText,who,date,what,section}], in board order."""
    rows, section, cur = [], '', None
    for line in str(text or '').splitlines():
        m = SEC_RE.match(line)
        if m:
            section = _one(m.group('name'), 80)
            continue
        m = ROW_RE.match(line)
        if m:
            rest = m.group('rest')
            bits = [b.strip() for b in rest.split('|')]
            title = _one(bits[0] if bits else '', 180)
            who = date = ''
            for b in bits[1:]:
                low = b.lower()
                if low.startswith('who:'):
                    who = _one(b.split(':', 1)[1], 80)
                elif low.startswith('date:'):
                    date = _one(b.split(':', 1)[1], 40)
            cur = {'n': _one(m.group('id'), 40), 'title': title,
                   'status': _one(m.group('status'), 40).lower(),
                   'statusText': '', 'who': who, 'date': date, 'what': '', 'section': section}
            rows.append(cur)
            continue
        m = SUB_RE.match(line)
        if m and cur is not None:
            k, v = m.group('key'), _one(m.group('val'))
            if k == 'what':
                cur['what'] = v
            elif k in ('statusText', 'status'):
                cur['statusText'] = v
    return rows


def build_doc(rows, source=BOARD, now=None):
    """The rows that are not finished, plus what was counted - including statuses not recognised."""
    now = now if now is not None else time.time()
    kinds, unknown, open_rows = {}, [], []
    for r in rows:
        st = r.get('status') or ''
        kinds[st or '(none)'] = kinds.get(st or '(none)', 0) + 1
        if st in DONE:
            continue
        # an unrecognised status is OPEN, and named: dropping a row he is waiting on is the one
        #   failure that matters on a to-do list
        if st and st not in DONE and st not in OPEN_KNOWN:
            if st not in unknown:
                unknown.append(st)
        open_rows.append(r)
    cut = len(open_rows) > MAX_ROWS
    return {'at': now, 'source': str(source), 'total': len(rows), 'open': len(open_rows),
            'kinds': kinds, 'unknown': unknown, 'cut': bool(cut),
            'rows': open_rows[:MAX_ROWS]}


def read_board(path=None):
    p = path or BOARD
    with io.open(p, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def publish(doc):
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, 'serviceAccount.json')
    if not os.path.exists(cred):
        cred = os.path.join(r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG', 'serviceAccount.json')
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    db = firestore.client()
    db.collection('users').document(UID).collection('meta').document('open_board').set(doc)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--board', default=None)
    a = ap.parse_args()
    try:
        text = read_board(a.board)
    except OSError as e:
        print('BOARD PUBLISH: cannot read the board (%s: %s)' % (type(e).__name__, e))
        return 2
    rows = parse_board(text)
    doc = build_doc(rows, source=(a.board or BOARD))
    if a.json:
        print(json.dumps(doc, indent=1, sort_keys=True)[:200000])
        return 0
    if not rows:
        print('BOARD PUBLISH: no rows parsed from %s - nothing published' % (a.board or BOARD))
        return 2
    if a.dry_run:
        print('BOARD PUBLISH (dry run): %d open of %d rows%s%s'
              % (doc['open'], doc['total'],
                 ('; statuses not recognised: ' + ', '.join(doc['unknown'])) if doc['unknown'] else '',
                 ' (capped)' if doc['cut'] else ''))
        return 0
    try:
        publish(doc)
    except Exception as e:
        print('BOARD PUBLISH: FAILED to write the document (%s: %s)' % (type(e).__name__, e))
        return 1
    print('BOARD PUBLISH: %d open of %d rows -> users/%s/meta/open_board%s'
          % (doc['open'], doc['total'], UID,
             ('; statuses not recognised: ' + ', '.join(doc['unknown'])) if doc['unknown'] else ''))
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())
