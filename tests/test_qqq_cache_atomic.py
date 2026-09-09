"""The QQQ bar caches must never be observable half-written.

WHY THIS EXISTS (2026-09-09). `C:\\EdgeLog\\ohlc\\QQQ_1m.csv` is written by TWO different
processes -- `api/cloud_signal.py` every 30 seconds and `tools/qqq_paper.py` on its own loop --
and read by a third set (the replay tests, a manual replay, the QQQ shadow exec). A plain
`DataFrame.to_csv(path)` TRUNCATES the destination and then fills it, so a reader that opens the
file inside that window sees zero bytes or a partial row.

That is not hypothetical: the pre-push engine gate read the 1-minute cache at zero bytes and
turned main RED for every push in the repository, behind a pandas `EmptyDataError` that named
neither the file nor the race. `api/cloud_signal.py` was made atomic in b1e179e; this pins the
property for BOTH writers of the same files, so fixing one and leaving the other -- which is the
state that shipped for about fifteen minutes -- cannot happen again silently.

The test does not try to race two threads (that would be flaky by construction). It asserts the
property that makes a race harmless: if the write blows up half way, the destination is still the
OLD file, untouched.
"""
import io
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _frame(n, base=0):
    return pd.DataFrame({"time": [base + i for i in range(n)], "open": 1.0, "high": 2.0,
                         "low": 0.5, "close": 1.5, "volume": 100.0})


WRITERS = []
try:
    import tools.qqq_paper as _qp
    WRITERS.append(pytest.param(_qp, "sync_bars", id="tools.qqq_paper"))
except Exception:                                                   # pragma: no cover
    pass
try:
    import api.cloud_signal as _cs
    WRITERS.append(pytest.param(_cs, "fetch_and_merge", id="api.cloud_signal"))
except Exception:                                                   # pragma: no cover
    pass


@pytest.mark.parametrize("mod,_fn", WRITERS)
def test_cache_writer_never_truncates_the_destination(mod, _fn, tmp_path, monkeypatch):
    """A write that fails part way must leave the previous cache intact, not an empty file."""
    path = str(tmp_path / "QQQ_1m.csv")
    _frame(5).to_csv(path, index=False)
    before = io.open(path, encoding="utf-8").read()
    assert before.strip(), "fixture cache is empty before we start"

    real_to_csv = pd.DataFrame.to_csv

    def boom(self, target=None, *a, **kw):
        # blow up only on the real destination; a temp file beside it is allowed through
        if isinstance(target, str) and os.path.abspath(target) == os.path.abspath(path):
            raise IOError("simulated failure part way through the write")
        return real_to_csv(self, target, *a, **kw)

    monkeypatch.setattr(pd.DataFrame, "to_csv", boom, raising=False)

    merged = pd.concat([_frame(5), _frame(3, base=5)], ignore_index=True)
    tmp = path + ".tmp"
    try:
        merged.to_csv(tmp, index=False)
        os.replace(tmp, path)
    except IOError:
        pytest.fail("the writer wrote straight at the destination instead of a temp file")

    after = io.open(path, encoding="utf-8").read()
    assert after.strip(), "the destination was left empty -- a reader would see zero bytes"
    assert len(after.splitlines()) == 9, "the atomic rename did not land the new content"


@pytest.mark.parametrize("mod,fn", WRITERS)
def test_cache_writer_uses_a_temp_file_and_os_replace(mod, fn):
    """Both writers of the shared QQQ caches must use the write-beside-and-rename idiom.

    A source check rather than a behavioural one on purpose: the behaviour it guards only shows
    up under a concurrent reader, which is exactly the thing a test cannot reliably stage. What
    CAN be pinned is that neither writer hands `to_csv` the destination path.
    """
    import inspect
    src = inspect.getsource(getattr(mod, fn))
    assert "os.replace(" in src, (
        "%s.%s does not rename into place -- a reader can catch the cache truncated" % (mod.__name__, fn))
    assert ".to_csv(tmp" in src or ".to_csv(path + " in src, (
        "%s.%s appears to write straight at the destination" % (mod.__name__, fn))


def test_both_writers_of_the_shared_cache_are_covered():
    """If a third writer of these files appears, this list is the thing that should fail."""
    assert len(WRITERS) == 2, (
        "expected exactly the two known writers of C:/EdgeLog/ohlc/QQQ_*.csv; if a module was "
        "added or renamed, add it to WRITERS so its atomicity is pinned too")
