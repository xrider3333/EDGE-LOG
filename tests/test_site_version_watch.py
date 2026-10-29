#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""w34: the website check that catches a failed update (owner, MANAGER GO 2026-10-29).

What these tests hold onto:
  * the check is about the DEPLOYED page, not the repository - a push landing on main is not proof
    that GitHub Pages built it or that an edge stopped serving the old file;
  * a disagreement does NOT reach the phone immediately, because a deploy honestly takes a few
    minutes - it has to last the grace period first, and the first-seen time has to survive
    between runs for that to mean anything;
  * the alert says which version each side is on, so the owner can tell "behind" from "broken";
  * a different stale pair is a NEW problem, not a repeat of the old one.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import site_version_watch as W   # noqa: E402


NOW = 1_800_000_000.0


def test_versions_agree_is_silence():
    agree, mins, msg, since = W.decide('73.1300', '73.1300', {}, NOW)
    assert agree is True
    assert mins == 0
    assert msg is None
    assert since is None            # nothing to remember


def test_a_fresh_disagreement_is_remembered_not_pushed():
    """A deploy takes a few minutes. The first sighting only starts the clock."""
    agree, mins, msg, since = W.decide('73.1299', '73.1300', {}, NOW)
    assert agree is False
    assert mins == 0
    assert msg is None, 'a brand new disagreement must not reach the phone'
    assert since == NOW, 'the first-seen time has to be handed back so the next run can use it'


def test_the_clock_runs_from_the_first_sighting_not_this_run():
    st = {'since': NOW - 11 * 60}
    agree, mins, msg, since = W.decide('73.1299', '73.1300', st, NOW, grace_min=12)
    assert (agree, mins, msg) == (False, 11, None)
    assert since == NOW - 11 * 60, 'the first-seen time must not be reset on every run'


def test_a_disagreement_that_outlasts_the_grace_period_is_pushed():
    st = {'since': NOW - 13 * 60}
    agree, mins, msg, _ = W.decide('73.1299', '73.1300', st, NOW, grace_min=12)
    assert agree is False and mins == 13
    assert msg, 'past the grace period it has to reach the phone'
    # it says which side is on which version - "behind" and "broken" are different problems
    assert '73.1299' in msg and '73.1300' in msg
    assert '13 minutes' in msg
    assert len(msg.splitlines()) == 3, 'the phone note is three short lines'


def test_recovery_clears_the_clock():
    st = {'since': NOW - 60 * 60}
    agree, mins, msg, since = W.decide('73.1300', '73.1300', st, NOW)
    assert (agree, mins, msg, since) == (True, 0, None, None)


def test_an_unreadable_live_page_is_not_reported_as_a_stale_deploy():
    """None means the page could not be read, which is a different fault from being behind - and
    the note has to say so rather than inventing a version."""
    agree, mins, msg, _ = W.decide(None, '73.1300', {'since': NOW - 30 * 60}, NOW)
    assert agree is False and msg
    assert 'nothing readable' in msg
    assert 'None' not in msg


def test_the_repeat_rule_treats_a_NEW_stale_pair_as_a_new_problem():
    """Two different stale pairs must not be collapsed into one daily repeat: if the site moves
    from one old version to another it is a new fault, and the owner hears about it."""
    from api import ntfy_push
    store = {}
    a1 = ntfy_push.dedupe_in(store, 'site_version',
                             {'behind:73.1298:73.1300': ntfy_push.RANK['high']}, NOW)
    a2 = ntfy_push.dedupe_in(store, 'site_version',
                             {'behind:73.1298:73.1300': ntfy_push.RANK['high']}, NOW + 60)
    a3 = ntfy_push.dedupe_in(store, 'site_version',
                             {'behind:73.1299:73.1300': ntfy_push.RANK['high']}, NOW + 120)
    assert a1 == 'push'
    assert a2 is None, 'the same stale pair must not push again a minute later'
    assert a3 == 'push', 'a different stale pair is a new problem'
    # and when it clears, one note goes out because the episode had a high-priority push
    assert ntfy_push.dedupe_in(store, 'site_version', {}, NOW + 180) == 'clear'


def test_version_is_read_out_of_the_page_the_way_the_page_writes_it():
    """The regex has to match index.html's own line, single quotes and all."""
    m = W.VER_RE.search("window.x=1;const VERSION='73.1374';const CHANGELOG=[")
    assert m and m.group(1) == '73.1374'
    assert W.VER_RE.search('const VERSION = "73.1"') is None, \
        'double quotes are not how this repo writes it; a loose match would read a stale copy'


def test_it_reads_the_live_page_with_a_cache_buster():
    """Without one, an edge or the local cache can answer with the very file being checked for."""
    seen = {}

    class FakeResp(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=None):
            return b"const VERSION='73.1374';"

    def fake_urlopen(req, timeout=None):
        seen['url'] = req.full_url
        seen['headers'] = {k.lower(): v for k, v in req.headers.items()}
        return FakeResp()

    orig = W.urllib.request.urlopen
    W.urllib.request.urlopen = fake_urlopen
    try:
        assert W.live_version() == '73.1374'
    finally:
        W.urllib.request.urlopen = orig
    assert 'fresh=' in seen['url'], 'the live read must be cache-busted'
    assert seen['headers'].get('cache-control') == 'no-cache'


def test_the_state_file_lives_under_tools_data():
    assert W.STATE.replace('\\', '/').endswith('tools/data/site_version_watch.json')
    assert time.time() > 0   # keeps the import of time meaningful for linters
