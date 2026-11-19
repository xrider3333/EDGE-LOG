#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/index_doctor.py -- is either read index behind its collection? Rebuild it if so.

WHY THIS EXISTS (MANAGER 2026-11-19, the hour after v91.06)
----------------------------------------------------------
The website reads the journal from meta/trades_index and the open board from meta/board_index -
three documents each instead of 108 and 324. Those indexes are maintained by the code that writes
the rows: api/trades_index.py is told by nt_sync, webull_sync, trade_bars and the purge tool, and
tools/board.py writes the board index itself. The moment a WRITER RUNS OLD CODE - the shared
checkout the PC runner runs from was sixteen commits behind main when this was written - it writes
a real document and tells no index, and a page that trusted the index would not show the owner his
new trade. The page itself now audits for that and falls back to reading the collection, which is
safe but dear; this tool is the other half: it finds the drift and FIXES it.

WHAT IT DOES
------------
For each index: counts the collection, compares it with what the index holds, lists the ids each
side has that the other does not, and compares the newest row stamp with when the index was last
written. With --fix (or when the page has left a `stale` mark on the head) it rebuilds. Reading
every row costs one read per row, which is why this is a command and not a loop - run it after a
sync that may have been on old code, or nightly.

    python tools/index_doctor.py                 # report only, both indexes
    python tools/index_doctor.py --fix           # rebuild whichever is behind
    python tools/index_doctor.py --which trades  # one of them
    python tools/index_doctor.py --fix --quiet   # for a scheduled job

Exit code 0 = both indexes agree with their collection (or were fixed), 1 = drift left unfixed,
2 = could not tell (no credentials, no index yet).
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

UID = 'IO0K35JpLIcH9YK4C0pMNYUzZOM2'


def _client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, 'serviceAccount.json')
    if not os.path.exists(cred):
        cred = os.path.join(r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG', 'serviceAccount.json')
    if not os.path.exists(cred):
        return None
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def _ms(v):
    """Firestore timestamp, ISO string or epoch -> milliseconds. 0 when there is nothing to read."""
    if v is None:
        return 0
    try:
        if hasattr(v, 'timestamp'):
            return int(v.timestamp() * 1000)
        if isinstance(v, (int, float)):
            return int(v * 1000) if v < 1e12 else int(v)
        s = str(v).strip().replace(' ', 'T').replace('Z', '+00:00')
        if len(s) == 10:
            s += 'T00:00:00+00:00'
        import datetime
        return int(datetime.datetime.fromisoformat(s).timestamp() * 1000)
    except Exception:
        return 0


SPECS = {
    'trades': {'col': 'trades', 'head': 'trades_index', 'rows_key': 'trades',
               'stamps': ('createdAt', 'date')},
    'board': {'col': 'board', 'head': 'board_index', 'rows_key': 'rows',
              'stamps': ('updated_at', 'date')},
}


def inspect(db, which):
    spec = SPECS[which]
    user = db.collection('users').document(UID)
    head_snap = user.collection('meta').document(spec['head']).get()
    head = head_snap.to_dict() if getattr(head_snap, 'exists', False) else None
    if head is None:
        return {'which': which, 'no_index': True}
    live = {}
    newest = 0
    for snap in user.collection(spec['col']).stream():
        row = snap.to_dict() or {}
        live[snap.id] = row
        for f in spec['stamps']:
            newest = max(newest, _ms(row.get(f)))
    indexed = set()
    for i in range(int(head.get('shards') or 0)):
        sh = user.collection('meta').document('%s_%d' % (spec['head'], i)).get()
        body = sh.to_dict() if getattr(sh, 'exists', False) else {}
        for r in (body or {}).get(spec['rows_key']) or []:
            if r and r.get('_id') is not None:
                indexed.add(str(r['_id']))
    # the head also carries the newest changes inline, which the page applies on top of the shards
    for e in head.get('recent') or []:
        if not e:
            continue
        rid = str(e.get('id') or ((e.get('trade') or e.get('row') or {}).get('_id') or ''))
        if not rid:
            continue
        if e.get('deleted'):
            indexed.discard(rid)
        else:
            indexed.add(rid)
    missing = sorted(set(live) - indexed)      # the page cannot see these at all
    ghosts = sorted(indexed - set(live))       # the page shows these although they are gone
    at = _ms(head.get('updated_at')) or _ms(head.get('built_at'))
    return {'which': which, 'live': len(live), 'indexed': len(indexed),
            'missing': missing, 'ghosts': ghosts, 'stale_mark': head.get('stale'),
            'stale_why': head.get('stale_why'), 'index_at': at, 'newest_row': newest,
            'behind_ms': max(0, newest - at) if (newest and at) else 0,
            'rev': head.get('rev'), 'shards': head.get('shards')}


def fix(db, which, backup_dir=None):
    stamp = time.strftime('%Y%m%d_%H%M%S')
    if which == 'trades':
        from api import trades_index as T
        bk = os.path.join(backup_dir, 'trades_%s.json' % stamp) if backup_dir else None
        out = T.rebuild(db, UID, backup=bk)
        db.collection('users').document(UID).collection('meta').document('trades_index') \
            .set({'stale': None, 'stale_why': None}, merge=True)
        return out
    from tools import board as B
    bk = os.path.join(backup_dir, 'board_%s.json' % stamp) if backup_dir else None
    _h, msg = B.cmd_index(db, rebuild=True, backup=bk, dry=False)
    db.collection('users').document(UID).collection('meta').document('board_index') \
        .set({'stale': None, 'stale_why': None}, merge=True)
    return {'msg': msg}


def main(argv=None):
    p = argparse.ArgumentParser(prog='index_doctor')
    p.add_argument('--which', choices=('trades', 'board', 'both'), default='both')
    p.add_argument('--fix', action='store_true', help='rebuild whichever index is behind')
    p.add_argument('--backup-dir', default=r'C:\EdgeLog', help='where a rebuild writes its backup')
    p.add_argument('--quiet', action='store_true', help='print only when something is wrong')
    a = p.parse_args(argv)
    db = _client()
    if db is None:
        print('INDEX DOCTOR: INCONCLUSIVE (no serviceAccount.json)')
        return 2
    names = ('trades', 'board') if a.which == 'both' else (a.which,)
    worst = 0
    for which in names:
        r = inspect(db, which)
        if r.get('no_index'):
            print('%-7s no index yet - nothing reads it, nothing to fix' % which)
            worst = max(worst, 2)
            continue
        drifted = bool(r['missing'] or r['ghosts'] or r['stale_mark'])
        line = ('%-7s live %-4d indexed %-4d missing %-3d ghost %-3d rev %-5s%s'
                % (which, r['live'], r['indexed'], len(r['missing']), len(r['ghosts']),
                   r['rev'], ('  STALE MARK: %s' % r['stale_why']) if r['stale_mark'] else ''))
        if drifted or not a.quiet:
            print(line)
        if r['missing']:
            print('        the page CANNOT SEE: %s' % ', '.join(r['missing'][:8])
                  + (' (+%d more)' % (len(r['missing']) - 8) if len(r['missing']) > 8 else ''))
        if r['ghosts']:
            print('        the page still shows: %s' % ', '.join(r['ghosts'][:8]))
        if not drifted:
            continue
        if not a.fix:
            worst = max(worst, 1)
            print('        run with --fix to rebuild it')
            continue
        out = fix(db, which, a.backup_dir)
        print('        REBUILT: %s' % out)
        after = inspect(db, which)
        if after['missing'] or after['ghosts']:
            print('        STILL DRIFTED after the rebuild: %s missing, %s ghost'
                  % (len(after['missing']), len(after['ghosts'])))
            worst = max(worst, 1)
    return worst


if __name__ == '__main__':
    sys.exit(main())
