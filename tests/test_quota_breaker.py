"""THE QUOTA CIRCUIT BREAKER (owner, through MANAGER, 2026-11-19: "why database limit dry. fix it").

When the day's free Firestore reads are gone the server answers RESOURCE_EXHAUSTED. The SDK we
load (firebase-firestore-compat 10.14.1) does not treat that as permanent: it reconnects the
listen stream at its 60 second ceiling for as long as the tab is open, and a reconnect the
server cannot match against the client's existence filter falls back - in the SDK's own words -
to a full re-query, re-delivering and re-billing the whole result set. The refusal is therefore
not the end of the spending; it is the spending, and it holds the quota at zero by itself.

These tests hold the two rules that stop it, and the three promises around them:
  * the page must never reload and must never discard typed input to recover;
  * a listener the breaker is holding must not be revived behind its back by a resume;
  * the screen must say which of the two reasons it has stopped updating - hidden tab, or
    quota gone - and never show a stale number as if it were live.
"""
import os

HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")


def src():
    with open(HTML, encoding="utf-8") as f:
        return f.read()


def test_only_the_quota_refusal_is_intercepted():
    """An ordinary disconnect is cheap - the SDK resumes from a token and re-reads nothing.
    Stepping in front of those would cost reads instead of saving them."""
    s = src()
    i = s.index("function _lsErr(e,ent)")
    seg = s[i:s.index("function _lsHold(")]
    assert "if(!_lsIsQuota(c))return;" in seg
    j = s.index("function _lsIsQuota(")
    assert "resource-exhausted" in s[j:j + 160]


def test_rule_one_detaches_that_listener_and_retries_in_minutes_not_seconds():
    s = src()
    i = s.index("function _lsHold(ent)")
    seg = s[i:s.index("function _lsMsToReset(")]
    assert "if(ent.unsub){ent.unsub();ent.unsub=null;}" in seg, "the refusing listener comes off"
    assert "mins*60000" in seg, "the ladder is in minutes"
    k = s.index("const LS_BACKOFF_MIN=")
    ladder = s[k:k + 80]
    assert "[5,10,20,30]" in ladder
    # every rung must be longer than the SDK's own 60 second retry, or we have saved nothing
    for rung in (5, 10, 20, 30):
        assert rung >= 2


def test_rule_two_stops_the_whole_page_after_a_proposed_count():
    s = src()
    assert "const LS_QUOTA_N=3;" in s
    i = s.index("function _lsErr(e,ent)")
    seg = s[i:s.index("function _lsHold(")]
    assert "_lsQuota.hits>=LS_QUOTA_N" in seg and "_lsQuotaStop()" in seg
    j = s.index("function _lsQuotaStop()")
    stop = s[j:s.index("function _lsQuotaGo(")]
    assert "_ls.reg.forEach" in stop and "e.unsub();e.unsub=null;" in stop, "every listener comes off"
    assert "clearTimeout(e.timer)" in stop, "and its pending retry with it"


def test_it_never_reloads_and_never_touches_typed_input():
    """The whole point of detaching instead of reloading. A reload would lose the view, the
    scroll position and anything half-typed, which is worse than a stale chip."""
    s = src()
    i = s.index("function _lsErr(e,ent)")
    seg = s[i:s.index("function _fsuInstall()")]
    for bad in ("location.reload", "location.href", "renderApp(", ".value=''", 'value=""'):
        assert bad not in seg, "the breaker must not " + bad


def test_a_held_listener_is_not_revived_by_looking_at_the_tab():
    """The hidden-tab resume walks the same registry. Without the guard, showing the window
    would re-attach a listener the breaker had just backed off - straight back into the 429."""
    s = src()
    i = s.index("function _lsResume()")
    seg = s[i:s.index("function _lsVis()")]
    assert "if(!_lsQuota.dead)" in seg
    assert "!e.held" in seg


def test_a_stopped_page_does_not_attach_new_listeners_either():
    s = src()
    assert "if(_ls.paused||_lsQuota.dead){_ls.reg.add(e);}" in s


def test_the_way_back_is_a_click_or_the_pacific_reset():
    s = src()
    j = s.index("function _lsQuotaStop()")
    stop = s[j:s.index("function _lsQuotaGo(")]
    assert "setTimeout(_lsQuotaGo" in stop, "comes back by itself at the reset"
    b = s.index("function _lsQuotaBar()")
    bar = s[b:b + 1400]
    assert "b.onclick" in bar and "_lsQuotaGo()" in bar, "and on a click"
    i = s.index("function _lsMsToReset()")
    reset = s[i:i + 420]
    assert "America/Los_Angeles" in reset, "the allowance resets on Pacific midnight, not local"


def test_the_one_plain_line_says_what_happened_and_when_it_comes_back():
    s = src()
    b = s.index("function _lsQuotaBar()")
    bar = s[b:b + 1400]
    assert "allowance for today is used up" in bar
    assert "live updates paused" in bar
    assert "_lsResetClock()" in bar, "the time must be the viewer's own clock"
    assert "textContent" in bar, "built as text, never interpolated into innerHTML"


def test_the_line_exists_only_when_it_has_something_to_say():
    """No element when the quota is fine means no layout change at all, and a one-commit revert."""
    s = src()
    b = s.index("function _lsQuotaBar()")
    bar = s[b:b + 1400]
    assert "document.createElement" in bar and "appendChild" in bar
    go = s[s.index("function _lsQuotaGo()"):s.index("// ONE PLAIN LINE")]
    assert "removeChild(b)" in go, "and it is taken away again when the feed returns"


def test_the_chip_distinguishes_quota_from_hidden_tab():
    s = src()
    i = s.index("function _tbLoadHtml()")
    seg = s[i:i + 1600]
    assert seg.index("window._fsQuotaOut") < seg.index("window._lsPaused"), \
        "quota is the more important of the two reasons, so it is tested first"
    assert "LIVE OFF" in seg


def test_tomorrows_readout_shows_the_breaker_firing():
    s = src()
    i = s.index("function _lsReadout()")
    seg = s[i:i + 700]
    for k in ("quota_holds", "quota_stops", "quota_off"):
        assert k in seg, k


def test_the_header_probe_covers_the_quota_state():
    p = os.path.join(os.path.dirname(HTML), "tools", "header_render_probe.py")
    with open(p, encoding="utf-8") as f:
        t = f.read()
    assert "quotaout_1366" in t and "quotaout_375" in t
