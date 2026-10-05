r"""THE PATTERN THAT BROKE THE GATE MUST NOT COME BACK.

A real thread joined with a short timeout, followed by an assertion that it finished, is a test
that fails when the box is busy rather than when the code is wrong. One such test in
tests/test_qqq_exec_stream_wiring.py blocked every lane's engine-tier push on 2026-10-04, because
the pre-push gate runs the full suite and the full suite is exactly the busy case.

This file scans the other test files for short numeric joins and fails naming each one. It is the
"fix the pattern once" half of the fix: converting the four sites by hand would have left nothing
stopping the fifth.

SELF-MATCHING IS A REAL TRAP AND IS HANDLED. A scanner that writes the thing it scans for into its
own source finds itself - which happened twice in this codebase on 2026-10-04, once with a doc
path and once with a fabricated path that fell into the same hole. So the pattern here is BUILT AT
RUNTIME from fragments, never written out whole, and this file is excluded by name as well.
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _threadwait  # noqa: E402

# Built from fragments so this file's own source never contains the pattern it looks for.
_JOIN = "." + "join"
_NUM = r"([0-9]+(?:\.[0-9]+)?)"
# `.join(3)` or `.join(timeout=3)`, numeric literal only - so `" ".join(parts)` never matches.
JOIN_RE = re.compile(re.escape(_JOIN) + r"\(\s*(?:timeout\s*=\s*)?" + _NUM + r"\s*\)")

# Files this scan does not apply to, each with the reason it is exempt.
EXEMPT = {
    os.path.basename(__file__): "the scanner itself",
    "_threadwait.py": "defines the constants",
}


def _test_files():
    for name in sorted(os.listdir(HERE)):
        if not name.startswith("test_") or not name.endswith(".py"):
            continue
        if name in EXEMPT:
            continue
        yield name


def _short_joins(name):
    """[(line_no, seconds, text)] for every numeric join below the floor in this file."""
    with open(os.path.join(HERE, name), encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for m in JOIN_RE.finditer(line):
            secs = float(m.group(1))
            if secs < _threadwait.MIN_JOIN_SECONDS:
                out.append((i, secs, stripped[:90]))
    return out


def test_no_test_joins_a_thread_on_a_short_fixed_deadline():
    """Every join on a real thread waits long enough that a busy box cannot fail it.

    If this fails on a test you just wrote: import tests/_threadwait.py and use
    `join_done(t)` / `wait_for(pred)` instead of a number. If your join genuinely wants to be
    short - you are asserting that a thread is STILL RUNNING - use `t.is_alive()` directly,
    which says that without a deadline at all.
    """
    offenders = []
    for name in _test_files():
        for line_no, secs, text in _short_joins(name):
            offenders.append("  tests/%s:%d  joins for %.3gs  %s" % (name, line_no, secs, text))
    assert not offenders, (
        "a thread join on a short fixed deadline fails when the box is busy, not when the code "
        "is wrong - that is what blocked every lane's push on 2026-10-04:\n"
        + "\n".join(offenders)
        + "\n\nUse tests/_threadwait.py: join_done(t) and wait_for(pred).")


# ═══════════════════════════════════════════════════ the scanner has to actually work
def test_the_scanner_catches_both_spellings(tmp_path):
    """A guard that cannot see the thing it guards against is worse than none, so prove it on
    text built here rather than trusting the regex by eye."""
    short_kw = _JOIN + "(timeout=3)"
    short_pos = _JOIN + "(5)"
    assert JOIN_RE.search(short_kw), "keyword form missed"
    assert JOIN_RE.search(short_pos), "positional form missed"
    assert float(JOIN_RE.search(short_kw).group(1)) == 3.0
    assert float(JOIN_RE.search(short_pos).group(1)) == 5.0


def test_the_scanner_ignores_string_join():
    """`" ".join(parts)` is not a thread join. Matching it would make the guard noise."""
    assert not JOIN_RE.search('" ".' + "join(parts)")
    assert not JOIN_RE.search('os.path.' + "join(a, b)")


def test_the_scanner_ignores_a_generous_join():
    assert not _below_floor(_JOIN + "(timeout=30)")
    assert not _below_floor(_JOIN + "(timeout=" + str(int(_threadwait.MIN_JOIN_SECONDS)) + ")")


def test_the_scanner_ignores_a_named_constant():
    """`join(timeout=WAIT_SECONDS)` carries no number, so it cannot be short by accident."""
    assert not JOIN_RE.search(_JOIN + "(timeout=WAIT_SECONDS)")


def _below_floor(text):
    m = JOIN_RE.search(text)
    return bool(m) and float(m.group(1)) < _threadwait.MIN_JOIN_SECONDS


def test_the_scanner_actually_reads_the_other_test_files():
    """A scan that silently covered nothing would pass for ever. There are hundreds of test
    files; if this count collapses, the walk broke."""
    assert len(list(_test_files())) > 50


def test_the_floor_is_above_the_deadline_that_failed():
    """3 seconds is what flaked, and 5 was next in line. The floor has to clear both."""
    assert _threadwait.MIN_JOIN_SECONDS > 5.0
    assert _threadwait.WAIT_SECONDS >= 2 * _threadwait.MIN_JOIN_SECONDS


# ═══════════════════════════════════════════════════ the helpers themselves
def test_wait_for_returns_as_soon_as_the_predicate_is_true():
    import time
    calls = {"n": 0}

    def pred():
        calls["n"] += 1
        return calls["n"] >= 3

    t0 = time.time()
    assert _threadwait.wait_for(pred, timeout=5.0, interval=0.001) is True
    assert time.time() - t0 < 1.0, "it must not sleep out the whole deadline on success"


def test_wait_for_gives_up_and_says_so():
    assert _threadwait.wait_for(lambda: False, timeout=0.05, interval=0.001) is False


def test_wait_for_checks_the_predicate_even_with_no_time_left():
    """With a zero deadline the loop body never runs, so the final check is the only one. A
    waiter that skipped it would report a ready condition as not ready."""
    calls = {"n": 0}

    def pred():
        calls["n"] += 1
        return True

    assert _threadwait.wait_for(pred, timeout=0.0) is True
    assert calls["n"] == 1, "the predicate must be consulted exactly once, not zero times"


def test_join_done_reports_a_finished_thread():
    import threading
    t = threading.Thread(target=lambda: None)
    t.start()
    assert _threadwait.join_done(t) is True


def test_join_done_reports_a_thread_that_is_still_running():
    import threading
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, daemon=True)
    t.start()
    try:
        assert _threadwait.join_done(t, timeout=0.05) is False
    finally:
        stop.set()
        t.join(timeout=_threadwait.WAIT_SECONDS)


@pytest.mark.parametrize("name", ["WAIT_SECONDS", "MIN_JOIN_SECONDS", "wait_for", "join_done"])
def test_the_shared_helper_exposes_what_the_tests_import(name):
    assert hasattr(_threadwait, name)
