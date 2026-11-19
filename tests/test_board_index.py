"""THE BOARD INDEX (MANAGER 2026-11-19, owner go: "why database limit dry. fix it").

The website used to listen to the whole users/{uid}/board collection - 324 documents, 324 billed
reads, every time a tab opened the page and again on every listener re-attach. tools/board.py now
also keeps meta/board_index (a head: revision counter, which shard holds which row, and the last
two dozen writes inline) and meta/board_index_<i> shards, so the page reads three documents.

What these tests hold is the WRITER's half of that bargain:
  * every command that changes a row updates the index, so the board the owner reads cannot go
    stale behind a row that was written;
  * a row write costs ONE read, never a stream of the collection - a rebuild is the only thing
    allowed to read every row, and it is an explicit command that backs up first;
  * the inline list stays bounded and holds the LATEST version of a row, once;
  * a broken index never fails the command, because the page can still fall back to reading the
    collection - but it is said out loud on stderr.
"""
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import board as B  # noqa: E402


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


@pytest.fixture()
def db():
    return FakeDb()


def head(db):
    return db.store['docs'].get('users/%s/meta/board_index' % B.UID)


def shard(db, i):
    return db.store['docs'].get('users/%s/meta/board_index_%d' % (B.UID, i))


def seed_index(db, n=5):
    rows = [{'_id': 'w%d' % i, 'title': 't%d' % i, 'status': 'open', 'order': i}
            for i in range(1, n + 1)]
    for r in rows:
        db.store['docs']['users/%s/board/%s' % (B.UID, r['_id'])] = {k: v for k, v in r.items()
                                                                     if k != '_id'}
    B.cmd_index(db, rebuild=True, backup=None, dry=False)
    db.store['reads'] = []
    db.store['writes'] = []
    db.store['streams'] = 0
    return rows


def test_a_row_write_costs_one_read_and_never_streams_the_collection():
    d = FakeDb()
    seed_index(d, 5)
    B.write_row(d, 'w3', {'title': 't3', 'status': 'pass', 'statusText': 'landed'})
    assert d.store['streams'] == 0, "a row write must never read every row"
    assert len(d.store['reads']) <= 2, d.store['reads']


def test_the_row_and_the_index_say_the_same_thing():
    d = FakeDb()
    seed_index(d, 5)
    B.write_row(d, 'w3', {'title': 't3', 'status': 'pass', 'statusText': 'landed'})
    rows = {r['_id']: r for r in shard(d, 0)['rows']}
    assert rows['w3']['statusText'] == 'landed'
    assert head(d)['recent'][-1]['row']['statusText'] == 'landed'
    assert head(d)['recent'][-1]['id'] == 'w3'


def test_the_revision_moves_once_per_write():
    d = FakeDb()
    seed_index(d, 3)
    r0 = head(d)['rev']
    B.write_row(d, 'w1', {'status': 'run'})
    B.write_row(d, 'w2', {'status': 'run'})
    assert head(d)['rev'] == r0 + 2


def test_the_inline_list_is_bounded_and_holds_each_row_once():
    d = FakeDb()
    seed_index(d, 3)
    for i in range(B.RECENT_KEEP + 8):
        B.write_row(d, 'w1', {'status': 'run', 'statusText': 'pass %d' % i})
    rec = head(d)['recent']
    assert len(rec) <= B.RECENT_KEEP
    assert len([e for e in rec if e['id'] == 'w1']) == 1, "one row, its latest version, once"
    assert rec[-1]['row']['statusText'] == 'pass %d' % (B.RECENT_KEEP + 7)


def test_a_new_row_is_mapped_and_a_full_shard_starts_another(monkeypatch):
    d = FakeDb()
    monkeypatch.setattr(B, 'SHARD_ROWS', 3)
    seed_index(d, 3)
    assert head(d)['shards'] == 1
    B.write_row(d, 'w9', {'status': 'open', 'title': 'new'})
    assert head(d)['shards'] == 2
    assert head(d)['map']['w9'] == 1
    assert [r['_id'] for r in shard(d, 1)['rows']] == ['w9']


def test_an_existing_row_stays_in_its_own_shard(monkeypatch):
    d = FakeDb()
    monkeypatch.setattr(B, 'SHARD_ROWS', 2)
    seed_index(d, 4)
    assert head(d)['map']['w1'] == 0 and head(d)['map']['w4'] == 1
    B.write_row(d, 'w1', {'status': 'run'})
    assert head(d)['map']['w1'] == 0
    assert len(shard(d, 0)['rows']) == 2, "no duplicate, no growth"


def test_every_command_that_changes_a_row_goes_through_the_index():
    """A path that wrote the row directly would leave the owner reading a stale board."""
    src = io.open(os.path.join(ROOT, 'tools', 'board.py'), encoding='utf-8').read()
    body = src[src.index('def cmd_set('):src.index('def main(')]
    assert 'ref.set(row)' not in body, "a write path bypasses write_row"
    assert body.count('write_row(db, rid, row)') >= 3


def test_a_broken_index_does_not_fail_the_command(capsys):
    d = FakeDb()
    seed_index(d, 3)

    def boom(*a, **k):
        raise RuntimeError('index down')
    B.index_write_row_orig = B.index_write_row
    try:
        B.index_write_row = boom
        B.write_row(d, 'w1', {'status': 'run', 'statusText': 'still written'})
    finally:
        B.index_write_row = B.index_write_row_orig
    row = d.store['docs']['users/%s/board/w1' % B.UID]
    assert row['statusText'] == 'still written', "the row is what matters"
    assert 'board index not updated' in capsys.readouterr().err


def test_no_index_yet_means_no_index_is_invented():
    """Nothing creates the index implicitly: that would cost a read per row at a random moment."""
    d = FakeDb()
    d.store['docs']['users/%s/board/w1' % B.UID] = {'status': 'open'}
    assert B.index_write_row(d, 'w1', {'status': 'open'}) is None
    assert head(d) is None


def test_a_rebuild_backs_up_first_and_refuses_an_empty_board(tmp_path):
    d = FakeDb()
    with pytest.raises(B.ToolError):
        B.cmd_index(d, rebuild=True, backup=None, dry=False)
    for i in range(1, 4):
        d.store['docs']['users/%s/board/w%d' % (B.UID, i)] = {'status': 'open', 'order': i}
    bk = str(tmp_path / 'board.json')
    B.cmd_index(d, rebuild=True, backup=bk, dry=False)
    saved = json.load(io.open(bk, encoding='utf-8'))
    assert len(saved) == 3
    assert head(d)['built_at'] and head(d)['recent'] == []


def test_a_dry_rebuild_writes_nothing():
    d = FakeDb()
    for i in range(1, 4):
        d.store['docs']['users/%s/board/w%d' % (B.UID, i)] = {'status': 'open', 'order': i}
    B.cmd_index(d, rebuild=True, backup=None, dry=True)
    assert head(d) is None and shard(d, 0) is None
