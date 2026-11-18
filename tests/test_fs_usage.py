import json
import os

from api import fs_usage as fu


class _Q:
    def stream(self):
        yield from (1, 2, 3)


class _Empty:
    def stream(self):
        return iter(())


class _B:
    def __init__(self, n):
        self._write_pbs = [0] * n

    def commit(self):
        return "ok"


class _D:
    def get(self):
        return "doc"


def test_counts_and_flush(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_FS_USAGE_DIR", str(tmp_path))
    before = fu.snapshot()
    assert list(fu._wrap_stream(_Q.stream)(_Q())) == [1, 2, 3]
    list(fu._wrap_stream(_Empty.stream)(_Empty()))          # empty query still bills 1 read
    fu._wrap_doc_get(_D.get)(_D())
    assert fu._wrap_commit(_B.commit)(_B(4)) == "ok"
    after = fu.snapshot()
    assert after["reads"] - before["reads"] == 5
    assert after["writes"] - before["writes"] == 4
    fu.flush()
    rows = [json.loads(x) for f in os.listdir(str(tmp_path))
            for x in open(os.path.join(str(tmp_path), f)).read().splitlines()]
    assert sum(r["reads"] for r in rows) >= 5 and sum(r["writes"] for r in rows) >= 4
    assert all(r["caller"] for r in rows)
    assert fu.flush() is None                               # nothing new -> no line


def test_listener_counts_changes(monkeypatch):
    seen = []

    class _R:
        def on_snapshot(self, cb):
            cb(["a", "b"], ["c1", "c2"], None)
            return "watch"

    before = fu.snapshot()["listen_reads"]
    assert fu._wrap_on_snapshot(_R.on_snapshot)(_R(), lambda d, c, t: seen.append(len(c))) == "watch"
    assert seen == [2] and fu.snapshot()["listen_reads"] - before == 2


def test_real_sdk_patched():
    import api  # noqa: F401
    from google.cloud.firestore_v1 import batch, query
    fu.enable()
    fu.install()
    assert hasattr(query.Query.stream, "__wrapped__") and hasattr(batch.WriteBatch.commit, "__wrapped__")
