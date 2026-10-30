#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C19: the three-level phone alert front door (owner 10-30, MANAGER #156).

What these hold onto:
  * the three levels really differ - ring() goes out when called, batch() and morning() must NOT
    touch the network, because that is the whole point of having levels;
  * a queue drains into ONE push and is cleared ONLY once the push is away: a failed send keeps
    the lines, so a dead Wi-Fi never silently eats the evening's findings;
  * the GO/HOLD buttons publish to the answers topic and carry NO credential;
  * the action header has no stray comma in it - ntfy separates an action's fields with commas, so
    one comma in the body would split the action into nonsense and the buttons would do nothing;
  * a missing answer is None and NEVER a yes;
  * api/ntfy_push stays the only thing that knows the topic and the token: a caller may add an
    Actions header through `extra`, and may not touch Title, Priority or Authorization.
"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))


def _fresh(tmp):
    """alert.py with its queue directory pointed at a temp folder."""
    os.environ['EDGELOG_ALERT_DIR'] = tmp
    for m in ('alert',):
        sys.modules.pop(m, None)
    import alert
    alert.QUEUE_DIR = tmp
    return alert


def test_batch_and_morning_never_touch_the_network():
    """The levels are only real if the quiet ones are actually quiet."""
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        sent = []
        orig = alert.ntfy_push.push_result
        alert.ntfy_push.push_result = lambda *a, **k: sent.append((a, k)) or (True, 'HTTP 200')
        try:
            alert.batch('the ORB relay slipped a fold', area='ORB')
            alert.morning('13 papers read, nothing survived', area='MISC')
        finally:
            alert.ntfy_push.push_result = orig
        assert sent == [], 'batch and morning must queue, not push'
        assert len(alert.read_queue('batch')) == 1
        assert len(alert.read_queue('morning')) == 1


def test_ring_pushes_at_once_with_a_high_priority():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        got = {}

        def fake(message, title=None, priority=None, timeout=8, log=None, extra=None):
            got.update(message=message, title=title, priority=priority, extra=extra)
            return True, 'HTTP 200'

        orig = alert.ntfy_push.push_result
        alert.ntfy_push.push_result = fake
        try:
            assert alert.ring('the box stopped answering', area='Oracle') is True
        finally:
            alert.ntfy_push.push_result = orig
        assert got['priority'] == 'high'
        assert 'box stopped answering' in got['message']
        assert got['title'].startswith('Oracle')
        assert len(got['title']) <= 39, 'ntfy cuts a long title'


def test_a_queue_drains_into_one_push_newest_first():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        alert.queue('batch', 'older thing', area='ORB')
        rows = alert.read_queue('batch')
        rows[0]['at'] = 1.0
        alert.queue('batch', 'newer thing', area='NOISE')
        # rewrite the first line with the older time so the ordering is unambiguous
        p = alert._queue_path('batch')
        lines = io.open(p, encoding='utf-8').read().splitlines()
        o = json.loads(lines[0]); o['at'] = 1.0
        io.open(p, 'w', encoding='utf-8').write(json.dumps(o) + '\n' + lines[1] + '\n')

        calls = []
        orig = alert.ntfy_push.push_result
        alert.ntfy_push.push_result = (lambda message, **k: calls.append((message, k))
                                       or (True, 'HTTP 200'))
        try:
            ok, n = alert.send('batch')
        finally:
            alert.ntfy_push.push_result = orig
        assert ok is True and n == 2
        assert len(calls) == 1, 'a digest is ONE push, however many lines are in it'
        body = calls[0][0]
        assert body.index('NOISE') < body.index('ORB'), 'newest area first'
        assert '2 things from today' in body
        assert alert.read_queue('batch') == [], 'a sent queue is cleared'


def test_a_failed_send_keeps_the_queue():
    """A dead Wi-Fi must never eat the evening's findings."""
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        alert.batch('something worth knowing', area='ORB')
        orig = alert.ntfy_push.push_result
        alert.ntfy_push.push_result = lambda *a, **k: (False, 'URLError')
        try:
            ok, n = alert.send('batch')
        finally:
            alert.ntfy_push.push_result = orig
        assert ok is False and n == 1
        assert len(alert.read_queue('batch')) == 1, 'a failed push must keep the lines'


def test_sending_an_empty_queue_is_silence_not_an_empty_push():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        calls = []
        orig = alert.ntfy_push.push_result
        alert.ntfy_push.push_result = lambda *a, **k: calls.append(1) or (True, 'HTTP 200')
        try:
            assert alert.send('morning') == (None, 0)
        finally:
            alert.ntfy_push.push_result = orig
        assert calls == []


def test_the_go_hold_actions_are_wellformed_and_carry_no_secret():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        os.environ['NTFY_TOPIC'] = 'edgelog-test'
        os.environ['NTFY_TOKEN'] = 'tk_secret_value'
        os.environ.pop('NTFY_ANSWER_TOPIC', None)
        h = alert.actions_for('orb314-paper')
        assert h, 'a configured topic must produce buttons'
        assert h.count('http,') == 2, 'exactly two buttons'
        assert 'GO' in h and 'HOLD' in h
        assert 'edgelog-test-answers' in h, 'answers go to their own topic'
        assert 'tk_secret_value' not in h, 'no credential may ride on the phone'
        # ntfy splits an action's fields on commas, so EVERY field after the url has to be a
        # key=value pair - that is what proves no comma leaked into a body or a label.
        for seg in h.split(';'):
            parts = [x.strip() for x in seg.split(',')]
            assert parts[0] == 'http', parts
            assert parts[1] in ('GO', 'HOLD'), parts
            assert parts[2].startswith('http'), parts
            for extra in parts[3:]:
                assert '=' in extra, ('a field with no = means a stray comma split it', seg)
            assert any(x.startswith('body=') for x in parts[3:]), seg


def test_no_topic_means_no_buttons_rather_than_a_broken_header():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        os.environ.pop('NTFY_TOPIC', None)
        os.environ.pop('NTFY_ANSWER_TOPIC', None)
        assert alert.actions_for('k') is None


def test_answers_are_parsed_and_anything_else_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        msgs = [
            {'event': 'message', 'time': 10, 'message': 'orb314 go'},
            {'event': 'message', 'time': 20, 'message': 'orb314 hold'},
            {'event': 'message', 'time': 30, 'message': 'chatter that is not an answer at all'},
            {'event': 'keepalive', 'time': 40, 'message': 'orb314 go'},
            {'event': 'message', 'time': 50, 'message': 'orb314 maybe'},
        ]
        out = alert.parse_answers(msgs)
        assert [(a['key'], a['answer']) for a in out] == [('orb314', 'go'), ('orb314', 'hold')]
        assert out[0]['at'] < out[1]['at'], 'oldest first'


def test_the_latest_answer_wins_and_a_missing_one_is_never_a_yes():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        orig = alert.answers
        alert.answers = lambda since='24h': [{'key': 'k1', 'answer': 'go', 'at': 1},
                                             {'key': 'k1', 'answer': 'hold', 'at': 2}]
        try:
            assert alert.answer_for('k1') == 'hold', 'the last tap is the answer'
            assert alert.answer_for('never-asked') is None
        finally:
            alert.answers = orig


def test_ntfy_push_refuses_the_headers_that_are_its_own():
    """A caller that could set the token or the title through `extra` would be exactly the drift
    api/ntfy_push.py was written to stop."""
    from api import ntfy_push
    seen = {}

    class FakeResp(object):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen['headers'] = {k.lower(): v for k, v in req.headers.items()}
        return FakeResp()

    os.environ['NTFY_TOPIC'] = 'edgelog-test'
    os.environ['NTFY_TOKEN'] = 'tk_real_token'
    orig = ntfy_push.urllib.request.urlopen
    ntfy_push.urllib.request.urlopen = fake_urlopen
    try:
        ok, _ = ntfy_push.push_result('hello', title='Mine', priority='high',
                                      extra={'Actions': 'http, GO, https://x/y',
                                             'Title': 'HIJACKED',
                                             'Authorization': 'Bearer stolen'})
    finally:
        ntfy_push.urllib.request.urlopen = orig
    assert ok is True
    assert seen['headers'].get('actions', '').startswith('http, GO')
    assert seen['headers'].get('title') == 'Mine', 'the caller must not overwrite the title'
    assert seen['headers'].get('authorization') == 'Bearer tk_real_token', \
        'the token comes from the environment, never from a caller'


def test_the_queue_is_capped_so_one_runaway_lane_cannot_fill_the_disk():
    with tempfile.TemporaryDirectory() as tmp:
        alert = _fresh(tmp)
        alert.MAX_QUEUED = 5
        for i in range(12):
            alert.queue('batch', 'line %d' % i, area='LOOP')
        rows = alert.read_queue('batch')
        assert len(rows) == 5
        assert rows[-1]['text'] == 'line 11', 'the newest survive'
