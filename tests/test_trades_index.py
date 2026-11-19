"""THE TRADES INDEX (MANAGER 2026-11-19, owner: "why database limit dry. fix it").

The website used to listen to users/{uid}/trades - 108 documents, 108 billed reads, on every page
open and every listener re-attach. api/trades_index.py keeps meta/trades_index (head: revision,
which shard holds which trade, the last two dozen changes inline) plus shard documents, so the
page reads three. These tests hold the WRITER's half:

  * a trade write never streams the collection - only an explicit rebuild does, and it backs up
  * the index carries the WHOLE trade, because the view must render exactly what it rendered
  * a batch of changes costs one shard read and one shard write per shard, not per trade
  * a deletion leaves the index, or a purged paper trade would sit on the owner's journal for good
  * the inline list stays bounded and holds each trade once, at its latest version
  * a broken index NEVER fails a trade write, and never raises into a sync
  * every path that writes a trade tells the index
"""
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import trades_index as T  # noqa: E402

UID = 'probe-uid'


class FakeDoc(object):
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, c):
        return FakeCol(self.store, self.path + '/' + c)

    def set(self, body):
        self.store['writes'].append(self.path)
        self.store['docs'][self.path] = json.loads(json.dumps(body, default=str))

    def get(self):
        self.store['reads'].append(self.path)
        body = self.store['docs'].get(self.path)
        return type('S', (), {'exists': body is not None,
                              'to_dict': staticmethod(lambda: dict(body or {}))})()


class FakeCol(object):
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, d):
        return FakeDoc(self.store, self.path + '/' + d)

    def stream(self):
        self.store['streams'] += 1
        pre = self.path + '/'
        for k, v in sorted(self.store['docs'].items()):
            if k.startswith(pre) and '/' not in k[len(pre):]:
                self.store['reads'].append(k)
                yield type('S', (), {'id': k[len(pre):],
                                     'to_dict': staticmethod(lambda v=v: dict(v))})()


class FakeDb(object):
    def __init__(self):
        self.store = {'docs': {}, 'reads': [], 'writes': [], 'streams': 0}

    def collection(self, c):
        return FakeCol(self.store, c)


def tpath(tid):
    return 'users/%s/trades/%s' % (UID, tid)


def head(db):
    return db.store['docs'].get('users/%s/meta/trades_index' % UID)


def shard(db, i):
    return db.store['docs'].get('users/%s/meta/trades_index_%d' % (UID, i))


def seed(db, n=5, **kw):
    for i in range(1, n + 1):
        db.store['docs'][tpath('t%d' % i)] = dict(
            {'date': '2026-11-%02d' % i, 'symbol': 'MNQ', 'pnl': i * 10.0,
             'pointScore': {'total': i, 'max': 10}}, **kw)
    T.rebuild(db, UID)
    db.store.update(reads=[], writes=[], streams=0)


def test_a_trade_write_never_streams_the_collection():
    d = FakeDb()
    seed(d, 5)
    T.note(d, UID, ['t3'])
    assert d.store['streams'] == 0


def test_a_batch_costs_one_read_and_one_write_per_shard_not_per_trade(monkeypatch):
    d = FakeDb()
    monkeypatch.setattr(T, 'SHARD_TRADES', 100)
    seed(d, 8)
    T.note(d, UID, ['t1', 't2', 't3', 't4'])
    shard_writes = [w for w in d.store['writes'] if 'trades_index_' in w]
    shard_reads = [r for r in d.store['reads'] if 'trades_index_' in r]
    assert len(shard_writes) == 1 and len(shard_reads) == 1, (shard_reads, shard_writes)
    # one read per changed trade, because every writer upstream uses merge and holds only part
    assert len([r for r in d.store['reads'] if '/trades/' in r]) == 4


def test_the_index_carries_the_whole_trade():
    """No slim/heavy split: the ledger must render exactly what it rendered before."""
    d = FakeDb()
    seed(d, 3)
    row = [r for r in shard(d, 0)['trades'] if r['_id'] == 't2'][0]
    assert row['pointScore'] == {'total': 2, 'max': 10}
    assert row['pnl'] == 20.0 and row['symbol'] == 'MNQ' and row['date'] == '2026-11-02'


def test_a_deleted_trade_leaves_the_index_and_the_map():
    d = FakeDb()
    seed(d, 4)
    del d.store['docs'][tpath('t2')]
    T.note(d, UID, [], deleted=['t2'])
    assert [r['_id'] for r in shard(d, 0)['trades']] == ['t1', 't3', 't4']
    assert 't2' not in head(d)['map']
    assert head(d)['recent'][-1] == {'rev': head(d)['rev'], 'id': 't2', 'deleted': True}


def test_a_trade_that_vanished_between_the_write_and_here_is_treated_as_deleted():
    d = FakeDb()
    seed(d, 3)
    del d.store['docs'][tpath('t1')]
    T.note(d, UID, ['t1'])
    assert [r['_id'] for r in shard(d, 0)['trades']] == ['t2', 't3']


def test_the_revision_moves_once_per_changed_trade():
    d = FakeDb()
    seed(d, 4)
    r0 = head(d)['rev']
    T.note(d, UID, ['t1', 't2'])
    assert head(d)['rev'] == r0 + 2


def test_the_inline_list_is_bounded_and_holds_each_trade_once():
    d = FakeDb()
    seed(d, 3)
    for i in range(T.RECENT_KEEP + 6):
        d.store['docs'][tpath('t1')]['notes'] = 'n%d' % i
        T.note(d, UID, ['t1'])
    rec = head(d)['recent']
    assert len(rec) <= T.RECENT_KEEP
    assert len([e for e in rec if e['id'] == 't1']) == 1
    assert rec[-1]['trade']['notes'] == 'n%d' % (T.RECENT_KEEP + 5)


def test_a_new_trade_is_mapped_and_a_full_shard_starts_another(monkeypatch):
    d = FakeDb()
    monkeypatch.setattr(T, 'SHARD_TRADES', 3)
    seed(d, 3)
    assert head(d)['shards'] == 1
    d.store['docs'][tpath('t9')] = {'date': '2026-11-09', 'symbol': 'ES'}
    T.note(d, UID, ['t9'])
    assert head(d)['shards'] == 2 and head(d)['map']['t9'] == 1
    assert [r['_id'] for r in shard(d, 1)['trades']] == ['t9']


def test_a_broken_index_never_raises_into_a_sync(capsys, monkeypatch):
    d = FakeDb()
    seed(d, 3)

    def boom(ref):
        raise RuntimeError('firestore down')
    monkeypatch.setattr(T, '_read', boom)
    assert T.note(d, UID, ['t1']) is None          # swallowed, not raised
    assert 'trades index' in capsys.readouterr().err


def test_no_index_yet_means_no_index_is_invented():
    d = FakeDb()
    d.store['docs'][tpath('t1')] = {'date': '2026-11-01'}
    assert T.note(d, UID, ['t1']) is None
    assert head(d) is None


def test_a_rebuild_backs_up_first_refuses_an_empty_journal_and_sorts_by_date(tmp_path):
    d = FakeDb()
    with pytest.raises(RuntimeError):
        T.rebuild(d, UID)
    for i, day in enumerate(['2026-11-05', '2026-11-01', '2026-11-03']):
        d.store['docs'][tpath('t%d' % i)] = {'date': day}
    bk = str(tmp_path / 'trades.json')
    out = T.rebuild(d, UID, backup=bk)
    assert out['trades'] == 3
    saved = json.load(io.open(bk, encoding='utf-8'))
    assert [r['date'] for r in saved] == ['2026-11-01', '2026-11-03', '2026-11-05']
    assert head(d)['recent'] == [] and head(d)['built_at']


def test_a_dry_rebuild_writes_nothing():
    d = FakeDb()
    d.store['docs'][tpath('t1')] = {'date': '2026-11-01'}
    T.rebuild(d, UID, dry=True)
    assert head(d) is None and shard(d, 0) is None


@pytest.mark.parametrize('rel,needle', [
    ('api/nt_sync.py', 'trades_index'),
    ('api/webull_sync.py', 'trades_index'),
    ('api/trade_bars.py', 'trades_index'),
    ('tools/purge_sim_trades.py', 'trades_index'),
])
def test_every_path_that_writes_a_trade_tells_the_index(rel, needle):
    src = io.open(os.path.join(ROOT, rel), encoding='utf-8').read()
    assert needle in src, rel
    assert '_tix.note(' in src, rel


def test_the_point_score_sweep_tells_the_index_once_for_the_whole_pass():
    """One note per publish(), not one per trade: a sweep touches many trades at once."""
    src = io.open(os.path.join(ROOT, 'api', 'trade_bars.py'), encoding='utf-8').read()
    body = src[src.index('def publish('):]
    assert body.count('_tix.note(') == 1
    assert '_touched.append(tid)' in body and 'if coll == "trades"' in body


def test_the_page_falls_back_and_the_gate_exists():
    html = io.open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    i = html.index('function _tixAttach(')
    seg = html[i:i + 1800]
    assert "colRef.orderBy('date','asc').onSnapshot" in seg, "the old listener is still the fallback"
    assert '_fsQuotaNote(err)' in seg, "a refused read must still not hold the splash"
    probe = io.open(os.path.join(ROOT, 'tools', 'trades_index_probe.py'), encoding='utf-8').read()
    assert 'idxHash' in probe and 'refHash' in probe, "the gate compares the two rendered ledgers"
    wt = io.open(os.path.join(ROOT, 'tools', 'wt.py'), encoding='utf-8').read()
    assert 'trades_index_probe.py' in wt, "a gate nobody runs is not a gate"
