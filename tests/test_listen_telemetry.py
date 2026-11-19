"""LISTEN TELEMETRY (MANAGER 2026-11-19): tell 'many tabs' apart from 'few tabs re-reading'.

The read counter can only report reads the page makes while it is running, and it cannot say
WHY a listener delivered documents. The 11-18 burn needs that distinction, because the Firestore
SDK we load (firebase-firestore-compat 10.14.1, read on 2026-11-19) does this on a quota error:

  * resource-exhausted is NOT a permanent error to it, so a 429'd listen stream is retried;
  * on that error it goes straight to its maximum backoff - 60 seconds - and keeps retrying;
  * a reconnect the server cannot match against the client's existence filter falls back, in
    the SDK's own words, to a FULL RE-QUERY - the whole result set re-delivered and re-billed.

One such tab re-reads every listener up to 60 times an hour with nobody touching it and no
document written, which is why writes could not explain the burn. The counters below name that
shape: full resends climbing while nothing is being written.

THE RULE THESE TESTS HOLD: the telemetry must cost NO READS and NO EXTRA WRITES. An instrument
that is itself expensive is worse than none, because it burns the thing it is measuring.
"""
import os
import re

HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")


def src():
    with open(HTML, encoding="utf-8") as f:
        return f.read()


def test_the_readout_carries_what_separates_the_two_explanations():
    s = src()
    i = s.index("function _lsReadout()")
    seg = s[i:i + 600]
    for k in ("attach", "reattach", "snaps", "docs", "full_resends", "errs",
              "offline", "online", "paused", "resumes", "up_min"):
        assert k in seg, k


def test_a_full_resend_is_counted_separately_from_a_change():
    """A snapshot where EVERY document is a change is the fingerprint of a re-query. A
    one-document snapshot is not evidence of anything, so it must not count."""
    s = src()
    i = s.index("function _lsSeen(")
    seg = s[i:s.index("function _lsErr(")]
    assert "n>1" in seg, "a single-document snapshot is never a resend"
    assert "s.docChanges().length===n" in seg, "every document changed = the whole set came again"
    assert "_ls.big++" in seg


def test_listener_errors_are_counted_by_code():
    s = src()
    i = s.index("function _lsErr(")
    seg = s[i:i + 240]
    assert "e.code" in seg and "_ls.errs[c]=(_ls.errs[c]|0)+1" in seg


def test_the_counting_reads_nothing():
    """It rides snapshots the app already receives and errors the SDK already hands over."""
    s = src()
    i = s.index("function _lsSeen(")
    seg = s[i:s.index("window.addEventListener('offline'")]
    for bad in (".get(", "onSnapshot(", ".collection(", ".where(", ".stream("):
        assert bad not in seg, "the telemetry must never issue a query of its own: " + bad
    # and the readout itself only reads counters already in memory
    j = s.index("function _lsReadout()")
    assert ".get(" not in s[j:j + 600] and ".collection(" not in s[j:j + 600]


def test_it_rides_the_write_that_already_happens_and_never_double_counts_boots():
    s = src()
    i = s.index("function _clientBootRow(")
    seg = s[i:i + 900]
    assert "refresh?inc(0):inc(1)" in seg, "a refresh must not look like another boot"
    assert "listen:_lsReadout()" in seg
    j = s.index("function _fsuFlush()")
    assert "_clientBootRow(true)" in s[j:j + 1500], "refreshed on the flush that already writes"


def test_the_snapshot_hook_sits_inside_the_counter_so_nothing_is_missed():
    s = src()
    assert "_fsu.listen_reads+=_fsuSnapReads(s);_lsSeen(s);" in s, \
        "every counted snapshot is also a measured one"


def test_the_sdk_behaviour_that_justifies_this_is_written_down():
    """A future reader must not have to re-derive why these counters exist."""
    s = src()
    i = s.index("const _ls={reg:new Set()")
    note = s[max(0, i - 1800):i]
    assert "resource-exhausted" in note and "60 second" in note.replace("60 seconds", "60 second")
    assert re.search(r"full re-query", note), "say what a reconnect can cost"
