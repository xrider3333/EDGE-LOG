# -*- coding: utf-8 -*-
"""THE LIVE BOARD - every lane writes its own row, the website reads it (owner 10-30, MANAGER #159).

WHY THIS EXISTS. The open board used to live in two places that could not talk to each other: the
claude.ai artifact, whose database only MANAGER can write, and a dated copy mirrored onto EDGE-LOG
by tools/board_publish.py. So the owner saw a board that did not move ("why isn't the board auto
updating", 20:45) and every lane had to ask MANAGER to change a row. This tool is the writer: a
lane sets its own row here and the EL BOARD tab shows it immediately.

WHERE THE ROWS LIVE. One Firestore collection, users/{uid}/board, one document per row, the
document id IS the row id the board already uses:

    w12   WORK          t47   RUNS (tests)      b7   AUTOMATIONS
    p03   THIS PC       q02   LOCAL AI (Qwen)

The prefix is the only thing that says which list a row belongs to, so a row cannot land in the
wrong one by a field being forgotten. Fields are the artifact's own, unchanged:

    label title status statusText why who date order        (+ tab, updated_at, updated_by)
    runs rows also carry roc dd5 ddpct sortino result

THE STATUS WORDS ARE CLOSED. Every lane writes through this tool, so a typo would quietly park a
row the owner is waiting on under a status nothing renders. An unknown status is REFUSED and the
known ones are printed. The eleven are the owner's own:

    needs-you block            he has to do something (red, and shaded on the page)
    open run wait queued park  in flight (red hollow / yellow)
    done pass fail             finished, waiting for his OK (green hollow)
    confirmed                  he said OK (green filled, collapsed on the page)

    python tools/board.py set w12 wip "landed v73.1402" --why "..." --from ELWA
    python tools/board.py set t47 fail "RUN #489" --result "chain ROC 10.1 vs bar 41" --from ENGU-Q
    python tools/board.py add c12 queued "nightly roll check" --title "..." --who ELWA --from ELWA
    python tools/board.py pushed w51 "PUSHED v73.1402 a1b2c3d4 - the live board" --from ELWA
    python tools/board.py get w12 | list [--tab WORK] [--open] | meta auto <file.md>
    python tools/board.py seed [--dir C:\\EdgeLog\\manager\\open_board\\db3] [--dry]

--dry prints the document and writes nothing. Credentials: firebase_admin + serviceAccount.json,
the same lookup as tools/runboard_watch.py; they are never printed.
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

UID = 'IO0K35JpLIcH9YK4C0pMNYUzZOM2'

# the row id's first letter decides which list it is in - nothing else does
# b and c are both AUTOMATIONS: MANAGER's board numbers them B1.. and C1.., two series of the
# same list, so the letter is kept in the id and both land in one table.
TABS = {'w': 'WORK', 't': 'RUNS', 'b': 'AUTOMATIONS', 'c': 'AUTOMATIONS', 'p': 'PC', 'q': 'QWEN'}
ID_RE = re.compile(r'^([wtbcpq])(\d{1,3})$')

# the owner's own status words. NEED = he has to act; OPEN = in flight; the rest are finished,
# and 'confirmed' is the only one he sets himself.
NEED = ('needs-you', 'block')
OPEN = ('open', 'run', 'wait', 'queued', 'park')
DONE = ('done', 'pass', 'fail')
STATUSES = NEED + OPEN + DONE + ('confirmed',)
# words lanes reach for that mean one of the above - mapped, not refused, because a lane being
# wrong about the WORD should not stop it reporting the STATE.
ALIAS = {'wip': 'run', 'running': 'run', 'needsyou': 'needs-you', 'needs you': 'needs-you',
         'blocked': 'block', 'parked': 'park', 'waiting': 'wait', 'next': 'queued',
         'new': 'queued', 'hold': 'park', 'closed': 'done', 'live': 'done', 'ok': 'confirmed'}

# fields a RUNS row may carry beyond the common ones
RUN_FIELDS = ('roc', 'dd5', 'ddpct', 'sortino', 'result', 'job')
TEXT_CAP = 600
MAX_ROWS = 600
META_KEYS = ('qwen', 'auto', 'review')
META_CAP = 400000     # a markdown page, well inside the 1 MiB document cap


class ToolError(Exception):
    """A refusal to report plainly and exit non-zero for, rather than a traceback."""


def _one(s, cap=TEXT_CAP):
    return ' '.join(str(s if s is not None else '').split())[:cap]


def parse_id(text):
    """'w12' -> ('w12', 'WORK', 12). Refuses anything the page could not place."""
    k = _one(text, 16).lower()
    m = ID_RE.match(k)
    if not m:
        raise ToolError('row id %r is not a board id: one letter then a number, '
                        'w=WORK t=RUNS b=AUTOMATIONS p=PC q=QWEN (w12, t47, b7)' % text)
    return k, TABS[m.group(1)], int(m.group(2))


def check_status(text):
    s = _one(text, 32).lower()
    s = ALIAS.get(s, s)
    if s not in STATUSES:
        raise ToolError('status %r is not one of the board words: %s' % (text, ', '.join(STATUSES)))
    return s


def is_open(status):
    """Open = not finished. An unknown status counts as OPEN: dropping a row the owner is
    waiting on is the one failure that matters, so the page shows it rather than hiding it."""
    s = str(status or '').lower()
    return s not in DONE + ('confirmed',)


# ── Firestore plumbing (real client, or a fake injected by the tests) ───────────────────────────
def real_client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, 'serviceAccount.json')
    if not os.path.exists(cred):
        cred = os.path.join(r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG', 'serviceAccount.json')
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def _user(db):
    return db.collection('users').document(UID)


def row_ref(db, rid):
    return _user(db).collection('board').document(rid)


def meta_ref(db, key):
    return _user(db).collection('meta').document('board_' + key)


def _read(ref):
    snap = ref.get()
    return snap.to_dict() if getattr(snap, 'exists', False) else None


def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _today():
    return time.strftime('%Y-%m-%d', time.localtime())


def build_row(rid, tab, order, cur, status=None, statusText=None, why=None, title=None,
              who=None, date=None, label=None, order_set=None, runs=None, frm='', tag=None):
    """The row as it will be stored: what is already there, with only the given fields changed.

    An existing row is UPDATED IN PLACE, so `set w12 run "..."` from a lane never erases the
    title or the owner's own notes that MANAGER put there.
    """
    row = dict(cur or {})
    row['tab'] = tab
    row['order'] = int(order_set if order_set is not None else row.get('order') or order)
    if label is not None:
        row['label'] = _one(label, 24)
    if tag is not None:
        # the family chip (owner 10-31): a couple of letters, upper case, so OHLC and ohlc are one
        # family and not two. An empty --tag takes the chip off the row.
        row['tag'] = _one(tag, 10).upper()
    if title is not None:
        row['title'] = _one(title, 180)
    if status is not None:
        row['status'] = check_status(status)
    if statusText is not None:
        row['statusText'] = _one(statusText, 200)
    if why is not None:
        row['why'] = _one(why)
    if who is not None:
        row['who'] = _one(who, 80)
    if date is not None:
        row['date'] = _one(date, 24)
    for k, v in (runs or {}).items():
        if v is not None:
            if k not in RUN_FIELDS:
                raise ToolError('%r is not a RUNS field: %s' % (k, ', '.join(RUN_FIELDS)))
            if tab != 'RUNS':
                raise ToolError('%s is a %s row, so it cannot carry %r - that is a RUNS field'
                                % (rid, tab, k))
            row[k] = _one(v)
    if not row.get('status'):
        raise ToolError('%s is new, so it needs a status: %s' % (rid, ', '.join(STATUSES)))
    if not row.get('title'):
        raise ToolError('%s is new, so it needs a title: pass --title "..."' % rid)
    row.setdefault('date', _today())
    row['updated_at'] = _now_iso()
    row['updated_by'] = _one(frm, 40) or 'unknown'
    return row


def cmd_set(db, rid_text, status, statusText, opts, create):
    rid, tab, order = parse_id(rid_text)
    ref = row_ref(db, rid)
    cur = _read(ref)
    if cur is None and not create:
        raise ToolError('%s is not on the board yet. Use `add %s <status> "<state>" --title "..."` '
                        'to put it there.' % (rid, rid))
    if cur is not None and create and opts.get('strict_new'):
        raise ToolError('%s is already on the board - use `set` to change it' % rid)
    runs = dict((k, opts.get(k)) for k in RUN_FIELDS)
    row = build_row(rid, tab, order, cur,
                    status=status, statusText=statusText, why=opts.get('why'),
                    title=opts.get('title'), who=opts.get('who'), date=opts.get('date'),
                    label=opts.get('label'), order_set=opts.get('order'), runs=runs,
                    frm=opts.get('frm'), tag=opts.get('tag'))
    if opts.get('dry'):
        return row, 'DRY RUN - nothing written: ' + json.dumps(row, sort_keys=True)[:900]
    ref.set(row)
    return row, 'BOARD %s %s = %s%s (%s)' % ('ADD' if cur is None else 'SET', rid, row['status'],
                                             (' - ' + row['statusText']) if row.get('statusText') else '',
                                             tab)


# THE BOARD ROW A SHIP MESSAGE NAMES, so a push can say so on the board itself.
#
# It has to be written as [w51] or board:w51 - the ROW ID, in brackets or after board:. "item 51"
# is NOT accepted even though the board calls its rows item N, because lanes number the rows of
# their own reply tables the same way: the first ship under this feature was subjected "... (item
# 29)" meaning its own row 29, while board row w29 is an NT8 alert from 10-15. One wrong stamp on
# a row the owner is waiting on is worse than every push that says nothing, so a message with no
# id in it writes nothing at all.
ROW_IN_MSG = (
    re.compile(r'[\[(]\s*([wtbcpq]\d{1,3})\s*[\])]', re.I),
    re.compile(r'\bboard:\s*([wtbcpq]\d{1,3})\b', re.I),
)


def row_in_message(text):
    """'the live board [w29]' -> 'w29'. None when the message names no row id."""
    t = str(text or '')
    for rx in ROW_IN_MSG:
        m = rx.search(t)
        if not m:
            continue
        try:
            return parse_id(m.group(1))[0]
        except ToolError:
            continue
    return None


def cmd_pushed(db, rid_text, line, frm, dry):
    """A push landed: say so on the row WITHOUT deciding its status.

    A push is not a finished row - the lane may have two more ships to go - so this only writes
    the state line and the note. Closing a row stays a deliberate `set`.
    """
    rid, tab, _ = parse_id(rid_text)
    ref = row_ref(db, rid)
    cur = _read(ref)
    if cur is None:
        raise ToolError('%s is not on the board, so a push cannot be noted on it' % rid)
    row = dict(cur)
    row['statusText'] = _one(line, 200)
    row['why'] = _one(((row.get('why') or '') + ' | ' + _one(line, 200)).strip(' |'))
    row['date'] = _today()
    row['updated_at'] = _now_iso()
    row['updated_by'] = _one(frm, 40) or 'ship'
    if dry:
        return row, 'DRY RUN - %s would read: %s' % (rid, row['statusText'])
    ref.set(row)
    return row, 'BOARD %s <- %s' % (rid, row['statusText'])


def cmd_get(db, rid_text):
    rid, tab, _ = parse_id(rid_text)
    row = _read(row_ref(db, rid))
    if row is None:
        raise ToolError('%s is not on the board' % rid)
    return row, json.dumps(row, sort_keys=True, indent=2, default=str)


def read_rows(db, tab=None, only_open=False):
    out = []
    for snap in _user(db).collection('board').stream():
        r = dict(snap.to_dict() or {})
        r['_id'] = snap.id
        if tab and str(r.get('tab') or '').upper() != tab.upper():
            continue
        if only_open and not is_open(r.get('status')):
            continue
        out.append(r)
    out.sort(key=lambda r: (str(r.get('tab') or ''), int(r.get('order') or 0), r['_id']))
    return out


def cmd_list(db, tab, only_open):
    rows = read_rows(db, tab, only_open)
    if not rows:
        return rows, 'nothing on the board matches'
    w = ['%-6s %-12s %-11s %-46s %s' % ('ID', 'TAB', 'STATUS', 'TITLE', 'STATE')]
    for r in rows:
        w.append('%-6s %-12s %-11s %-46s %s' % (r['_id'], r.get('tab') or '?',
                                                r.get('status') or '?',
                                                _one(r.get('title'), 46), _one(r.get('statusText'), 40)))
    opens = sum(1 for r in rows if is_open(r.get('status')))
    w.append('%d rows, %d open' % (len(rows), opens))
    return rows, '\n'.join(w)


def cmd_meta(db, key, path, frm, dry):
    """One of the board's three written pages (QWEN / AUTOMATIONS / WAITING ON ME) as markdown."""
    if key not in META_KEYS:
        raise ToolError('%r is not a board page: %s' % (key, ', '.join(META_KEYS)))
    if not os.path.exists(path):
        raise ToolError('no such file: %s' % path)
    md = io.open(path, encoding='utf-8', errors='replace').read()
    # MANAGER's own dump keeps each page as {"md": "..."} rather than a .md file, so either is read
    if path.lower().endswith('.json'):
        try:
            md = str((json.loads(md) or {}).get('md') or '')
        except ValueError as e:
            raise ToolError('%s is not readable JSON: %s' % (path, e))
        if not md.strip():
            raise ToolError('%s carries no "md" text' % path)
    if len(md) > META_CAP:
        raise ToolError('%s is %d characters; the page cap is %d' % (path, len(md), META_CAP))
    doc = {'md': md, 'updated': _today(), 'updated_at': _now_iso(),
           'updated_by': _one(frm, 40) or 'unknown', 'source': os.path.basename(path)}
    if dry:
        return doc, 'DRY RUN - %s page would carry %d characters from %s' % (key, len(md), path)
    meta_ref(db, key).set(doc)
    return doc, 'BOARD PAGE %s <- %s (%d characters)' % (key.upper(), os.path.basename(path), len(md))


# ── the one-time seed from MANAGER's dump ───────────────────────────────────────────────────────
SEED_DIRS = (('work', 'w'), ('tests', 't'), ('auto', 'bc'), ('pc', 'p'), ('qwen', 'q'))
SEED_META = {'qwen': 'meta_qwen.json', 'auto': 'meta_auto.json', 'review': 'meta_review.json'}


def seed_rows(dump_dir):
    """Read MANAGER's dump into board rows. The dump's own file name carries the row id."""
    rows = []
    for sub, pre in SEED_DIRS:
        d = os.path.join(dump_dir, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith('.json'):
                continue
            stem = os.path.splitext(fn)[0].lower()
            if not stem[:1] in pre:
                raise ToolError('%s is under %s/, so its id has to start with %s'
                                % (fn, sub, ' or '.join(repr(c) for c in pre)))
            # the id is the dump's own file name, and it has to round-trip through parse_id or
            # the page could not place the row
            rid, tab, order = parse_id(stem)
            o = json.load(io.open(os.path.join(d, fn), encoding='utf-8'))
            status = str(o.get('status') or '').lower()
            status = ALIAS.get(status, status)
            if status not in STATUSES:
                raise ToolError('%s carries status %r, which the board does not know: %s'
                                % (fn, o.get('status'), ', '.join(STATUSES)))
            row = {'_id': rid, 'tab': tab, 'status': status,
                   'order': int(o.get('order') or order),
                   'title': _one(o.get('title'), 180),
                   'statusText': _one(o.get('statusText'), 200),
                   'who': _one(o.get('who'), 80), 'date': _one(o.get('date'), 24),
                   'label': _one(o.get('label'), 24)}
            # 'what' is the artifact's long note and 'why' is the page's click-through, so the
            # dump's what (plus its two appended edits) becomes the why.
            what = ' '.join(x for x in (o.get('what'), o.get('what_append_1018'),
                                        o.get('what_append_1019')) if x)
            row['why'] = _one(what)
            for k in RUN_FIELDS:
                if o.get(k) is not None and tab == 'RUNS':
                    row[k] = _one(o.get(k))
            if o.get('confirmedAt'):
                row['confirmedAt'] = _one(o.get('confirmedAt'), 40)
            rows.append(row)
    if len(rows) > MAX_ROWS:
        raise ToolError('the dump holds %d rows; the cap is %d' % (len(rows), MAX_ROWS))
    return rows


def cmd_seed(db, dump_dir, frm, dry, force=False):
    rows = seed_rows(dump_dir)
    if not rows:
        raise ToolError('no rows found under %s' % dump_dir)
    have = read_rows(db) if not dry else []
    if have and not force:
        raise ToolError('the board already holds %d rows - seeding would overwrite them. '
                        'Pass --force if that is what you mean.' % len(have))
    at, by = _now_iso(), (_one(frm, 40) or 'seed')
    if dry:
        kinds = {}
        for r in rows:
            kinds[r['status']] = kinds.get(r['status'], 0) + 1
        opens = sum(1 for r in rows if is_open(r['status']))
        return rows, ('DRY RUN - %d rows (%d open) would be written: %s'
                      % (len(rows), opens, json.dumps(kinds, sort_keys=True)))
    n = 0
    for r in rows:
        doc = dict(r)
        rid = doc.pop('_id')
        doc['updated_at'] = at
        doc['updated_by'] = by
        row_ref(db, rid).set(doc)
        n += 1
    return rows, 'BOARD SEEDED: %d rows -> users/%s/board' % (n, UID)


def main(argv=None):
    # the board carries the owner's own emoji, and a Windows console is cp1252 - without this a
    # row with a status circle in it kills the whole listing
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    p = argparse.ArgumentParser(prog='board.py', description='the live open board')
    sub = p.add_subparsers(dest='cmd')

    def common(q):
        q.add_argument('--from', dest='frm', default='', help='the lane writing the row')
        q.add_argument('--dry', action='store_true', help='print, write nothing')

    for name in ('set', 'add'):
        q = sub.add_parser(name)
        q.add_argument('id')
        q.add_argument('status')
        q.add_argument('state', nargs='?', default=None, help='the short state line')
        q.add_argument('--why', default=None)
        q.add_argument('--title', default=None)
        q.add_argument('--who', default=None)
        q.add_argument('--date', default=None)
        q.add_argument('--label', default=None)
        q.add_argument('--tag', default=None,
                       help='short family label shown as a chip before the title, e.g. OHLC or AI')
        q.add_argument('--order', type=int, default=None)
        for k in RUN_FIELDS:
            q.add_argument('--' + k, default=None)
        common(q)

    q = sub.add_parser('pushed')
    q.add_argument('id')
    q.add_argument('line', help='what landed, e.g. "PUSHED v73.1402 a1b2c3d4 - the live board"')
    common(q)
    q = sub.add_parser('get')
    q.add_argument('id')
    q = sub.add_parser('list')
    q.add_argument('--tab', default=None)
    q.add_argument('--open', dest='only_open', action='store_true')
    q = sub.add_parser('meta')
    q.add_argument('key')
    q.add_argument('path')
    common(q)
    q = sub.add_parser('seed')
    q.add_argument('--dir', dest='dump', default=r'C:\EdgeLog\manager\open_board\db3')
    q.add_argument('--force', action='store_true')
    common(q)

    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 2
    try:
        # a dry run still READS, so it can show what would change - it only never writes
        db = real_client()
        if a.cmd in ('set', 'add'):
            opts = {'why': a.why, 'title': a.title, 'who': a.who, 'date': a.date,
                    'label': a.label, 'order': a.order, 'frm': a.frm, 'dry': a.dry,
                    'strict_new': (a.cmd == 'add')}
            for k in RUN_FIELDS:
                opts[k] = getattr(a, k)
            _, msg = cmd_set(db, a.id, a.status, a.state, opts, create=(a.cmd == 'add'))
        elif a.cmd == 'pushed':
            _, msg = cmd_pushed(db, a.id, a.line, a.frm, a.dry)
        elif a.cmd == 'get':
            _, msg = cmd_get(db, a.id)
        elif a.cmd == 'list':
            _, msg = cmd_list(db, a.tab, a.only_open)
        elif a.cmd == 'meta':
            _, msg = cmd_meta(db, a.key, a.path, a.frm, a.dry)
        else:
            _, msg = cmd_seed(db, a.dump, a.frm, a.dry, a.force)
    except ToolError as e:
        sys.stderr.write('REFUSED: %s\n' % e)
        return 1
    print(msg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
