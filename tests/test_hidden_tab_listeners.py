"""A HIDDEN TAB STOPS LISTENING (MANAGER 2026-11-19, after the 11-18 quota night).

Every document the PC or the box writes is delivered to every live listener in every open tab,
and each delivery is a billed read whether or not a human is looking at the screen. That - not
stale code, not reloads - emptied the free read quota on 11-13 and again on 11-18.

The cut: a tab hidden for LS_HIDDEN_MS detaches every listener and re-attaches on return.
It is a JavaScript change, so these tests hold the CONTRACT of the source rather than running
it; the paused chip itself is covered by tools/header_render_probe.py (lspaused_1366, _375).

The contract matters more than the mechanism, because each rule here is a way the cut could
quietly break the app instead of saving reads:
  * ONE STABLE HANDLE. Re-attaching makes a new unsubscribe; the caller still holds the old
    one. If the handle did not survive a pause, an unsubscribe would silently miss.
  * A DEAD LISTENER STAYS DEAD. The app unsubscribes listeners of its own accord; a resume
    that resurrects one leaks a listener (and its reads) for the rest of the session.
  * NEVER PAUSE OVER WORK IN FLIGHT. A PC-runner command answers THROUGH a listener.
  * ONE PLACE. The registry wraps the prototype, so it catches the listeners nobody
    remembered to tell it about - including any a lane adds later.
"""
import os
import re

HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")


def src():
    with open(HTML, encoding="utf-8") as f:
        return f.read()


def test_the_threshold_is_ten_minutes_not_a_flicker():
    """Short thresholds are the dangerous ones: a resume re-reads ~450 documents on this
    account, so a tab flicked away and back every few minutes would COST reads, not save
    them. Ten minutes means the tab has really been left alone."""
    m = re.search(r"const LS_HIDDEN_MS\s*=\s*(\d+)\s*\*\s*60\s*\*\s*1000", src())
    assert m, "LS_HIDDEN_MS must stay a plain minutes constant"
    assert int(m.group(1)) >= 10, "below 10 minutes the resume cost outruns the saving"


def test_the_caller_gets_a_stable_handle_that_survives_a_resume():
    s = src()
    i = s.index("const wrapReg=")
    seg = s[i:i + 1400]
    assert "return function(){" in seg, "the wrapper returns its OWN handle, not the raw unsubscribe"
    assert "e.dead=true" in seg
    assert "_ls.reg.delete(e)" in seg
    assert "if(e.unsub){e.unsub();e.unsub=null;}" in seg, "it detaches whatever is attached NOW"


def test_a_resume_never_resurrects_a_listener_the_app_unsubscribed():
    s = src()
    i = s.index("function _lsResume()")
    seg = s[i:s.index("function _lsVis()")]
    assert "!e.dead" in seg, "a dead entry must be skipped on resume"
    assert "!e.unsub" in seg, "an already-attached entry must not be attached twice"


def test_a_pause_is_refused_while_a_pc_command_is_in_flight():
    s = src()
    i = s.index("function _lsPause()")
    seg = s[i:s.index("function _lsResume()")]
    assert "(window._pendingCmds|0)>0" in seg and "return" in seg


def test_becoming_visible_resumes_at_once_and_cancels_a_pending_pause():
    s = src()
    i = s.index("function _lsVis()")
    seg = s[i:i + 420]
    assert "clearTimeout(_ls.t)" in seg, "coming back must cancel the countdown"
    assert "_lsResume()" in seg
    assert "setTimeout(" in seg and "_lsPause()" in seg


def test_the_registry_wraps_the_prototype_so_no_listener_is_missed():
    s = src()
    assert "wrapReg(DR);wrapReg(Q);" in s, "document AND query listeners"
    assert s.index("wrapSnap(DR);wrapSnap(Q);") < s.index("wrapReg(DR);wrapReg(Q);"), \
        "the registry sits ON TOP of the read counter, so counted reads stay counted"


def test_nothing_in_the_cut_reloads_the_page_or_touches_the_view():
    s = src()
    i = s.index("function _lsPause()")
    seg = s[i:s.index("document.addEventListener('visibilitychange',_lsVis)")]
    for bad in ("location.reload", "location.replace", "renderApp()"):
        assert bad not in seg, "a pause must never redraw or reload - only the feed stops"


def test_the_chip_says_paused_rather_than_showing_a_number_nothing_refreshes():
    s = src()
    i = s.index("function _tbLoadHtml()")
    seg = s[i:i + 2000]
    assert "window._lsPaused" in seg and "LIVE PAUSED" in seg
    assert seg.index("window._lsPaused") < seg.index("window._pcLoad"), \
        "the paused check comes first, or a stale number wins"


def test_the_paused_chip_has_probe_cases_at_both_widths():
    p = os.path.join(os.path.dirname(HTML), "tools", "header_render_probe.py")
    with open(p, encoding="utf-8") as f:
        t = f.read()
    assert "lspaused_1366" in t and "lspaused_375" in t
    assert "window._lsPaused=true;" in t
