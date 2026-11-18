"""Build the RUN INDEX: the runs list every page load needs, in a handful of documents.

WHY (owner GO 2026-11-14, board row: Firestore read cut):
  Every page load reads the runs list one DOCUMENT PER RUN - 75 by default and about 500
  after a LOAD ALL - even though the app only projects a slice of fields out of each one.
  Measured in the owner's browser on 2026-11-13: a page load cost 250 to 1,500 document
  reads, against a 50,000-a-day ceiling that was hit the same week.

  This writes the same projected fields into meta/runs_index_<n> shards with a
  meta/runs_index header, so the browser pays ONE read per shard - four or five for the
  whole list - instead of one per run.

WHAT IT IS NOT: a source of truth. It is a cache of the runs collection, and the app
  treats it as one - it reads the newest runs live on top of the index (see
  _runsIndexFetch in index.html), keeps the starred query live so a crown is never read
  out of a stale index, and falls back to the old projected query whenever the index is
  missing, short or unreadable. So a stale index can make the board SLOWER, never wrong.

THE FIELD LIST IS READ OUT OF index.html (RUNS_LITE_FIELDS), never copied here: a field
  added to the app must not need a second edit in this file to reach the index, and an
  index built on a shorter list than the app projects would quietly blank columns.

Usage:
  python tools/runs_index_build.py                 what it would write (dry run)
  python tools/runs_index_build.py --write         write the shards
  python tools/runs_index_build.py --write --limit 500
"""
import argparse
import json
import os
import re
import sys
import time

from firebase_admin import firestore
try:  # per-caller Firestore read counters (api/fs_usage.py, MANAGER 11-18)
    import os as _fsu_os, sys as _fsu_sys
    _fsu_root = _fsu_os.path.dirname(_fsu_os.path.dirname(_fsu_os.path.abspath(__file__)))
    if _fsu_root not in _fsu_sys.path:
        _fsu_sys.path.append(_fsu_root)
    import api as _fsu_api  # noqa: F401
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tools.runboard_watch as rw   # noqa: E402  (UID, real_client - the one credential lookup every tool shares)
HEADER_DOC = 'runs_index'
SHARD_PREFIX = 'runs_index_'
# Firestore caps a document at 1 MiB, and the REST encoding is far heavier than the JSON
# measured here (every value carries its own type wrapper). 350 KB of measured payload
# keeps a shard well inside the cap; the whole history was 2 shards at 600 KB, so the
# tighter figure costs a read or two and leaves no doubt.
SHARD_BYTES = 350 * 1024


# THE SLIM SET, measured 2026-11-14. The app's own projection (RUNS_LITE_FIELDS, 141 paths)
# weighs 100-400 KB A RUN - top10_results, best_params, the equity curve and the validate
# blocks - so an index of it needs a shard every two runs and saves almost nothing (80 runs
# = 42 shards against 80 document reads). These are the fields the LIST, the crowns and the
# leaderboard rows actually print; everything heavier is already fetched per run, on demand,
# by _hydrateRun / _hydrateCfg when a reader opens one.
SLIM_FIELDS = ['id', 'strategy', 'famKey', 'famSeq', 'timestamp', 'date_from', 'date_to',
               'instrument', 'timeframe', 'session', 'archived', 'starred', 'book', 'scope',
               'source_name', 'multiplier', 'cost_pts', 'commission_usd', 'slippage_pts',
               'best_pnl_usd', 'best_dd_usd', 'best_pf', 'best_trades', 'best_win_rate',
               'best_pnl_per_day', 'best_oos_pnl', 'days_in_test', 'bars', 'n_evaluated']


def lite_fields():
    """RUNS_LITE_FIELDS, read out of index.html so there is one copy of the list."""
    src = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    m = re.search(r"const RUNS_LITE_FIELDS='([^']+)'", src)
    if not m:
        raise SystemExit('RUNS_LITE_FIELDS not found in index.html - has it been renamed?')
    return [f for f in m.group(1).split(',') if f]


def top_level(fields):
    """The admin SDK selects whole top-level fields; the dotted paths (validate.x) come
    back inside their parent map, which is what the browser's projection returns too."""
    return sorted({f.split('.')[0] for f in fields})


def jsonable(v):
    """Firestore values -> plain JSON. Timestamps become ISO strings, which is the shape
    the app's own _isoTs() normalises every run to anyway."""
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true', help='write the shards (otherwise a dry run)')
    ap.add_argument('--limit', type=int, default=600, help='how many of the newest runs to index')
    ap.add_argument('--full', action='store_true',
                    help='index every projected field instead of the slim set (measured: a shard every two runs)')
    args = ap.parse_args()

    db = rw.real_client()
    uid = rw.UID

    fields = lite_fields() if args.full else SLIM_FIELDS
    sel = top_level(fields)
    runs_ref = db.collection('users').document(uid).collection('runs')
    q = runs_ref.select(sel).order_by('timestamp', direction=firestore.Query.DESCENDING)
    q = q.limit(args.limit)

    rows, read = [], 0
    for snap in q.stream():
        read += 1
        d = {k: jsonable(v) for k, v in (snap.to_dict() or {}).items()}
        d['id'] = snap.id
        rows.append(d)

    # newest first, shards filled in that order, so shard 0 alone already draws the
    # top of the list if a later one is ever missing.
    shards, cur, cur_n = [], [], 0
    for r in rows:
        n = len(json.dumps(r))
        if cur and cur_n + n > SHARD_BYTES:
            shards.append(cur)
            cur, cur_n = [], 0
        cur.append(r)
        cur_n += n
    if cur:
        shards.append(cur)

    newest = rows[0].get('timestamp') if rows else None
    head = {'built_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'n': len(rows), 'shards': len(shards), 'newest': newest,
            'fields': len(fields), 'built_by': 'tools/runs_index_build.py'}

    print('runs read      : %d (%d document reads)' % (len(rows), read))
    print('shards         : %d' % len(shards))
    for i, s in enumerate(shards):
        print('  %s%-2d %4d runs  %6.1f KB' % (SHARD_PREFIX, i, len(s), len(json.dumps(s)) / 1024.0))
    print('header         : %s' % json.dumps(head))
    if not args.write:
        print('\nDRY RUN - nothing written. Add --write.')
        return 0

    meta = db.collection('users').document(uid).collection('meta')
    for i, s in enumerate(shards):
        meta.document(SHARD_PREFIX + str(i)).set({'i': i, 'runs': s, 'built_at': head['built_at']})
    # the header LAST, so a reader never sees a header pointing at shards that are not
    # there yet; and a shard left over from a bigger build is deleted after it.
    meta.document(HEADER_DOC).set(head)
    i = len(shards)
    while True:
        old = meta.document(SHARD_PREFIX + str(i))
        if not old.get().exists:
            break
        old.delete()
        print('removed stale %s%d' % (SHARD_PREFIX, i))
        i += 1
    print('\nWRITTEN: %d shards + header' % len(shards))
    return 0


if __name__ == '__main__':
    sys.exit(main())
