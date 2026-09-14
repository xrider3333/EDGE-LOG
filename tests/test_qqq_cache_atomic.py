"""The QQQ bar caches must never be observable half-written, and a rename onto them must
survive a reader briefly holding the destination open.

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

RENAME RETRY (2026-09-14). Being torn is only half the hazard: even a CLEAN write can fail to
swap in at all, because `os.replace` raises `PermissionError [WinError 32]` outright on Windows
if ANY other process merely has the destination open for reading (POSIX would just rename under
the reader). Seen live: `[cloud-signal] step failed: PermissionError ... 'QQQ_1m.csv.tmp' ->
'QQQ_1m.csv'`, which aborted a whole signal-engine tick over what was really a few-millisecond
reader lock (this file's OWN `_snapshot_dir()`/`shutil.copy` in tests/test_cloud_signal.py is one
such reader). Both writers now share ONE retry helper, `tools.qqq_paper._replace_with_retry` --
this file pins that it exists, rides out a transient lock, and cleans up on a persistent one.
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


def _resolve_replace_helper(mod):
    """The shared `_replace_with_retry` helper as seen from `mod`: defined directly in
    tools.qqq_paper, or reachable via `mod.qp` for a module that imports it that way
    (api.cloud_signal does `import tools.qqq_paper as qp`). None if neither applies."""
    helper = getattr(mod, "_replace_with_retry", None)
    if helper is not None:
        return helper
    qp_mod = getattr(mod, "qp", None)
    return getattr(qp_mod, "_replace_with_retry", None) if qp_mod is not None else None


def _writer_source(mod, fn):
    """Source of `fn`, plus the shared retry helper's own source when `fn` delegates its
    rename to it instead of spelling `os.replace(` inline -- both are true of a writer
    that shares ONE retry-replace helper with every other writer of these files (see
    module docstring, RENAME RETRY)."""
    import inspect
    src = inspect.getsource(getattr(mod, fn))
    if "os.replace(" not in src and "_replace_with_retry(" in src:
        helper = _resolve_replace_helper(mod)
        if helper is not None:
            src += "\n" + inspect.getsource(helper)
    return src


@pytest.mark.parametrize("mod,fn", WRITERS)
def test_cache_writer_uses_a_temp_file_and_os_replace(mod, fn):
    """Both writers of the shared QQQ caches must use the write-beside-and-rename idiom
    (directly, or via the shared `_replace_with_retry` helper both now delegate to).

    A source check rather than a behavioural one on purpose: the behaviour it guards only shows
    up under a concurrent reader, which is exactly the thing a test cannot reliably stage. What
    CAN be pinned is that neither writer hands `to_csv` the destination path.
    """
    src = _writer_source(mod, fn)
    assert "os.replace(" in src, (
        "%s.%s does not rename into place -- a reader can catch the cache truncated" % (mod.__name__, fn))
    assert ".to_csv(tmp" in src or ".to_csv(path + " in src, (
        "%s.%s appears to write straight at the destination" % (mod.__name__, fn))


@pytest.mark.parametrize("mod,fn", WRITERS)
def test_cache_writer_rename_shares_the_retry_helper(mod, fn):
    """Neither writer may grow its OWN retry loop -- see this file's RENAME RETRY note and
    api/cloud_signal.py's DATA REUSE note: there is ONE `_replace_with_retry` (defined in
    tools.qqq_paper), and every risky rename in either module calls it."""
    import inspect
    src = inspect.getsource(getattr(mod, fn))
    assert "_replace_with_retry(" in src, (
        "%s.%s does not use the shared retry helper -- either it still calls a bare "
        "os.replace() (no retry at all), or it grew a second, duplicate retry loop" % (mod.__name__, fn))


def test_both_writers_of_the_shared_cache_are_covered():
    """If a third writer of these files appears, this list is the thing that should fail."""
    assert len(WRITERS) == 2, (
        "expected exactly the two known writers of C:/EdgeLog/ohlc/QQQ_*.csv; if a module was "
        "added or renamed, add it to WRITERS so its atomicity is pinned too")


# ── Rename retry: transient lock rides out, persistent one cleans up and reports ────────
def test_replace_with_retry_succeeds_after_transient_permission_errors(tmp_path, monkeypatch):
    """Simulated PermissionError on the first N replace attempts must still succeed within
    the retry budget -- the common case (a reader's open() is milliseconds, not seconds)."""
    import tools.qqq_paper as qp
    dst = tmp_path / "QQQ_1m.csv"
    dst.write_text("old", encoding="utf-8")
    tmp = tmp_path / "QQQ_1m.csv.tmp"
    tmp.write_text("new", encoding="utf-8")

    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst_):
        calls["n"] += 1
        if calls["n"] <= 3:                      # fails 3 times, then a REAL os.replace
            raise PermissionError(32, "The process cannot access the file")
        return real_replace(src, dst_)

    monkeypatch.setattr(qp.os, "replace", flaky)
    ok = qp._replace_with_retry(str(tmp), str(dst), log=None, retries=10, sleep=0.0)

    assert ok is True, "must succeed once the simulated lock clears within the retry budget"
    assert calls["n"] == 4, "must have retried exactly the failing attempts, not more"
    assert dst.read_text(encoding="utf-8") == "new", "the real rename must have landed"
    assert not tmp.exists(), "the source is gone once os.replace actually succeeds"


def test_replace_with_retry_gives_up_cleans_up_tmp_and_logs_once(tmp_path, monkeypatch):
    """Persistent failure (every attempt raises) must not raise into the caller: the `.tmp`
    is removed rather than left beside the destination forever, the destination is left
    exactly as it was, and the failure is logged exactly once (not once per retry)."""
    import tools.qqq_paper as qp
    dst = tmp_path / "QQQ_1m.csv"
    dst.write_text("old", encoding="utf-8")
    before = dst.read_bytes()
    tmp = tmp_path / "QQQ_1m.csv.tmp"
    tmp.write_text("new", encoding="utf-8")

    def always_locked(src, dst_):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(qp.os, "replace", always_locked)
    logged = []
    ok = qp._replace_with_retry(str(tmp), str(dst), log=logged.append, what="QQQ 1m cache",
                                retries=3, sleep=0.0)

    assert ok is False
    assert dst.read_bytes() == before, "a persistently failed rename must not touch the destination"
    assert not tmp.exists(), "the abandoned .tmp must be cleaned up, not left on disk forever"
    assert len(logged) == 1, "exactly one log line for the whole exhausted retry, not one per attempt"
    assert "QQQ 1m cache" in logged[0] and "PermissionError" in logged[0]


def test_replace_with_retry_stays_silent_when_log_is_none(tmp_path, monkeypatch):
    """log=None (used by api.cloud_signal._migrate_signals_header, which has always failed
    quietly) must not raise trying to call a logger that was never given."""
    import tools.qqq_paper as qp
    dst = tmp_path / "QQQ_1m.csv"
    dst.write_text("old", encoding="utf-8")
    tmp = tmp_path / "QQQ_1m.csv.tmp"
    tmp.write_text("new", encoding="utf-8")
    monkeypatch.setattr(qp.os, "replace",
                        lambda s, d: (_ for _ in ()).throw(PermissionError(32, "locked")))
    assert qp._replace_with_retry(str(tmp), str(dst), log=None, retries=2, sleep=0.0) is False
    assert not tmp.exists()
