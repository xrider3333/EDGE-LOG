# -*- coding: utf-8 -*-
"""THE TRADES INDEX - the website reads the journal in three documents instead of 108.

WHY THIS EXISTS (MANAGER 2026-11-19, owner: "why database limit dry. fix it")
-----------------------------------------------------------------------------
Firestore bills one read per document DELIVERED, per listener, per open tab. The website
listened to the whole users/{uid}/trades collection, so every tab paid 108 reads when it opened
and another 108 every time a listener re-attached - after being hidden, or after the daily
allowance refused it. Together with the open board (324, fixed in v91.05) that was most of the
447-document bill a tab paid just to come back to life, out of 50,000 free reads a day the owner
ran dry twice this month.

The whole journal is small: 108 trades weigh 278 KB of JSON, and three quarters of that is the
pointScore block. So this index carries EVERY FIELD OF EVERY TRADE - there is no slim/heavy split
like the runs index needs - which is what lets the trades view render byte-for-byte what it
rendered before. The page is not supposed to be able to tell the difference.

WHAT IT LOOKS LIKE (the shape meta/board_index and meta/runs_index already use)
-------------------------------------------------------------------------------
    meta/trades_index         the HEAD, and the only thing the page listens to - ONE document:
                                rev       a counter, bumped once per changed trade
                                shards    how many shard documents there are
                                map       {trade id: which shard holds it}
                                recent    the last RECENT_KEEP changes, each {rev, id, trade}
                                built_at  when the shards were last rebuilt
    meta/trades_index_<i>     {trades: [the whole trade, _id included]} - read once, over REST

WHAT IT COSTS
-------------
    a tab opening the journal      3 documents, where it was 108
    a trade written on the PC      it rides inline on the head the page already listens to: the
                                   page pays NOTHING EXTRA to see a new or changed trade
    a tab that missed more than    those 3 documents again - never 108
      RECENT_KEEP changes
    the writer (box / PC)          one read per CHANGED trade, plus one read and one write per
                                   shard touched, plus one write of the head

WHAT IT MUST NEVER DO
---------------------
Break the journal. Every write path still writes the real trade document first and this index
second; `note` swallows its own failures with a warning, because the trade is what matters. And
the page falls back to listening to the collection whenever the head is missing, a shard will not
read, or the revisions do not line up. A stale index can make the journal slower to appear. It
must never make it wrong, and it must never lose a trade.

This module touches no order, fill, pairing, sizing or decision code. It is the publish path only.

    python -m api.trades_index --rebuild --backup C:\\EdgeLog\\trades_backup.json
    python -m api.trades_index                     # show the index
"""
from __future__ import annotations

import io
import json
import sys

RECENT_KEEP = 24      # changes carried inline on the head, so a page rarely re-reads the shards
SHARD_TRADES = 60     # trades per shard document - 108 fit in two, far under the 1 MiB cap

_WARNED = set()


def _warn(msg):
    """Say it once per kind - a trade sync must not spam the log with the same index trouble."""
    key = msg.split(':')[0]
    if key not in _WARNED:
        _WARNED.add(key)
        sys.stderr.write('trades index: %s\n' % msg)


def _user(db, uid):
    return db.collection('users').document(uid)


def head_ref(db, uid):
    return _user(db, uid).collection('meta').document('trades_index')


def shard_ref(db, uid, i):
    return _user(db, uid).collection('meta').document('trades_index_%d' % int(i))


def _read(ref):
    snap = ref.get()
    return snap.to_dict() if getattr(snap, 'exists', False) else None


def _now_iso():
    import time
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def read_head(db, uid):
    return _read(head_ref(db, uid))


def note(db, uid, trade_ids, deleted=()):
    """Tell the index that these trades changed, or were deleted.

    The writers above this all use merge=True and so hold only PART of a trade; the index has to
    carry the whole one, so the changed documents are read back here. That is one read per changed
    trade - the price of the 105 a tab no longer pays every time it opens the journal.

    Returns the new revision, or None when there is no index yet (nothing is created implicitly:
    building one streams the collection, which is the cost this exists to avoid - see --rebuild).
    """
    try:
        ids = [str(i) for i in (trade_ids or [])]
        gone = [str(i) for i in (deleted or [])]
        if not ids and not gone:
            return None
        head = read_head(db, uid)
        if head is None:
            return None
        head = dict(head)
        m = dict(head.get('map') or {})
        shards = int(head.get('shards') or 0)
        col = _user(db, uid).collection('trades')

        bodies = {}
        for tid in ids:
            doc = _read(col.document(tid))
            if doc is None:
                gone.append(tid)       # written then removed between the commit and here
                continue
            body = dict(doc)
            body['_id'] = tid
            bodies[tid] = body

        # group the work by shard so each shard document is read once and written once
        plan = {}
        for tid in list(bodies) + gone:
            i = m.get(tid)
            if i is None:
                if tid in gone:
                    continue           # never indexed, nothing to remove
                i = max(0, shards - 1)
                if shards == 0:
                    i, shards = 0, 1
                else:
                    cur = _read(shard_ref(db, uid, i)) or {}
                    if len(cur.get('trades') or []) >= SHARD_TRADES:
                        i, shards = shards, shards + 1
            plan.setdefault(int(i), []).append(tid)

        for i, tids in sorted(plan.items()):
            ref = shard_ref(db, uid, i)
            cur = _read(ref) or {}
            rows = [r for r in (cur.get('trades') or []) if str(r.get('_id')) not in tids]
            for tid in tids:
                if tid in bodies:
                    rows.append(bodies[tid])
                    m[tid] = i
                else:
                    m.pop(tid, None)
            ref.set({'trades': rows})

        rev = int(head.get('rev') or 0)
        recent = [e for e in (head.get('recent') or [])
                  if str((e or {}).get('id')) not in bodies and str((e or {}).get('id')) not in gone]
        for tid, body in bodies.items():
            rev += 1
            recent.append({'rev': rev, 'id': tid, 'trade': body})
        for tid in gone:
            rev += 1
            recent.append({'rev': rev, 'id': tid, 'deleted': True})
        recent = recent[-RECENT_KEEP:]
        head_ref(db, uid).set({'rev': rev, 'shards': shards, 'map': m, 'recent': recent,
                               'built_at': head.get('built_at'), 'updated_at': _now_iso()})
        return rev
    except Exception as e:                       # never fail a trade write over the index
        _warn('not updated for %s: %s: %s' % (list(trade_ids or [])[:4], type(e).__name__, e))
        return None


def rebuild(db, uid, backup=None, dry=False):
    """Build the index from the collection. Streams every trade, so it is deliberate and rare."""
    col = _user(db, uid).collection('trades')
    rows = []
    for snap in col.stream():
        body = dict(snap.to_dict() or {})
        body['_id'] = snap.id
        rows.append(body)
    if not rows:
        raise RuntimeError('the journal has no trades - refusing to write an empty index over it')
    rows.sort(key=lambda r: (str(r.get('date') or ''), str(r.get('_id'))))
    if backup:
        with io.open(backup, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=1, sort_keys=True, default=str)
    parts, m = [], {}
    for r in rows:
        if not parts or len(parts[-1]) >= SHARD_TRADES:
            parts.append([])
        m[str(r['_id'])] = len(parts) - 1
        parts[-1].append(r)
    if dry:
        return {'trades': len(rows), 'shards': len(parts), 'dry': True}
    for i, part in enumerate(parts):
        shard_ref(db, uid, i).set({'trades': part})
    old = read_head(db, uid) or {}
    rev = int(old.get('rev') or 0) + 1
    head_ref(db, uid).set({'rev': rev, 'shards': len(parts), 'map': m, 'recent': [],
                           'built_at': _now_iso(), 'updated_at': _now_iso()})
    return {'trades': len(rows), 'shards': len(parts), 'rev': rev, 'backup': backup}


def _client():
    import os
    import firebase_admin
    from firebase_admin import credentials, firestore
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred = os.path.join(root, 'serviceAccount.json')
    if not os.path.exists(cred):
        cred = os.path.join(r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG', 'serviceAccount.json')
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog='trades_index', description='the website s trades index')
    p.add_argument('--uid', default='IO0K35JpLIcH9YK4C0pMNYUzZOM2')
    p.add_argument('--rebuild', action='store_true')
    p.add_argument('--backup', default=None, help='write every live trade to this JSON file first')
    p.add_argument('--dry', action='store_true')
    a = p.parse_args(argv)
    db = _client()
    if not a.rebuild:
        h = read_head(db, a.uid)
        if h is None:
            print('no trades index yet - run with --rebuild once to build it')
            return 0
        print('TRADES INDEX rev %s, %s shard(s), %s trade(s) mapped, %s carried inline'
              % (h.get('rev'), h.get('shards'), len(h.get('map') or {}), len(h.get('recent') or [])))
        return 0
    out = rebuild(db, a.uid, backup=a.backup, dry=a.dry)
    print(('DRY RUN - ' if a.dry else 'TRADES INDEX REBUILT: ')
          + '%(trades)d trade(s) in %(shards)d shard(s)' % out
          + (' - backup %s' % a.backup if a.backup else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
