#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/alert.py -- C19: one phone-alert front door for every lane, in three loudnesses, with
GO / HOLD buttons the owner can answer from the lock screen.

WHY ONE FILE
------------
Every lane had grown its own idea of when to push: some sent everything at once, some sent nothing
and left findings in an inbox nobody opened at 21:00. The owner asked for three levels instead, and
for one tools/alert.py that every lane calls, so loudness is a DECISION a caller declares rather
than an accident of which helper it happened to import.

THE THREE LEVELS
----------------
  ring(...)     it rings NOW. For things that are costing money or will be wrong by morning.
  batch(...)    it waits for the 21:00 post. For things worth knowing today, not worth a ring.
  morning(...)  it waits for the morning digest. For things worth reading with coffee.

ring() is the only one that touches the network when it is called; batch() and morning() append one
JSON line to a queue and return. `python tools/alert.py send batch` (21:00 task) and
`send morning` (the digest) drain their queue into ONE push, newest first, and leave the queue
empty only once the push is away - a failed send keeps the lines, so nothing is silently lost.

GO / HOLD
---------
ask(...) is a ring with two buttons. The answer does NOT need a server: the button publishes one
line to a second ntfy topic (NTFY_ANSWER_TOPIC, by default "<topic>-answers"), and answers() reads
that topic back through ntfy's own poll API. The phone therefore carries no Firestore credential
and no new secret - the ntfy token already in the environment is the only one in play.

A caller asks, then gets on with something else, and checks later:

    key = alert.ask('Ship ORB #314 to paper?', area='ORB', key='orb314-paper')
    ...
    if alert.answer_for('orb314-paper') == 'go':   # None until he taps
        ...

An answer is a FACT ABOUT WHAT HE TAPPED, nothing more. A lane may act on "go" only where it was
already allowed to act; "hold" always means stop. No lane treats a missing answer as a yes.

  python tools/alert.py ring --area ORB --text "..."        # one off, from a script or by hand
  python tools/alert.py ask --area ORB --text "..." --key k
  python tools/alert.py send batch|morning                  # drain a queue into one push
  python tools/alert.py answers [--since 24h]               # what he has tapped
  python tools/alert.py queue batch|morning                 # what is waiting, without sending
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import ntfy_push                                        # noqa: E402

QUEUE_DIR = os.environ.get('EDGELOG_ALERT_DIR') or r'C:\EdgeLog\alerts'
LEVELS = ('ring', 'batch', 'morning')
# the queues hold at most this many lines; past it the OLDEST go, and the digest says how many
MAX_QUEUED = 200


def _queue_path(level):
    return os.path.join(QUEUE_DIR, 'queue_%s.jsonl' % level)


def _answers_topic():
    t = (os.environ.get('NTFY_ANSWER_TOPIC') or '').strip()
    if t:
        return t
    base = (os.environ.get('NTFY_TOPIC') or '').strip()
    return (base + '-answers') if base else ''


def _server():
    return ((os.environ.get('NTFY_SERVER') or '').strip() or 'https://ntfy.sh').rstrip('/')


# ─────────────────────────────────────────────────────────────── the three levels
def ring(text, area='EDGE-LOG', priority='high', actions=None, log=None):
    """Push now. -> True sent, False failed, None no topic configured (same as ntfy_push)."""
    title = ('%s: now' % area) if area else 'EDGE-LOG: now'
    extra = {'Actions': actions} if actions else None
    ok, _d = ntfy_push.push_result(_one(text), title=title[:39], priority=priority,
                                   extra=extra, log=log)
    return ok


def queue(level, text, area='EDGE-LOG'):
    """Put one line in the batch or morning queue. Never touches the network."""
    if level not in ('batch', 'morning'):
        raise ValueError('queue level must be batch or morning, not %r' % (level,))
    if not os.path.isdir(QUEUE_DIR):
        os.makedirs(QUEUE_DIR)
    row = {'at': time.time(), 'area': str(area), 'text': _one(text)}
    p = _queue_path(level)
    with io.open(p, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(row, sort_keys=True) + '\n')
    _trim(p)
    return row


def batch(text, area='EDGE-LOG'):
    """Worth knowing today. Goes out in the 21:00 post."""
    return queue('batch', text, area=area)


def morning(text, area='EDGE-LOG'):
    """Worth reading with coffee. Goes out in the morning digest."""
    return queue('morning', text, area=area)


def _trim(path):
    try:
        with io.open(path, encoding='utf-8') as fh:
            lines = fh.readlines()
    except OSError:
        return
    if len(lines) <= MAX_QUEUED:
        return
    with io.open(path, 'w', encoding='utf-8') as fh:
        fh.writelines(lines[-MAX_QUEUED:])


def read_queue(level):
    """Every queued line, oldest first. A damaged line is skipped, not fatal."""
    out = []
    try:
        with io.open(_queue_path(level), encoding='utf-8') as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if isinstance(o, dict) and o.get('text'):
                    out.append(o)
    except OSError:
        pass
    return out


def digest(rows, level):
    """One note out of many queued lines, NEWEST FIRST, grouped by the area that raised it."""
    if not rows:
        return None
    by = {}
    for r in rows:
        by.setdefault(str(r.get('area') or 'EDGE-LOG'), []).append(r)
    order = sorted(by, key=lambda k: max(float(x.get('at') or 0) for x in by[k]), reverse=True)
    lines = []
    for area in order:
        items = sorted(by[area], key=lambda x: float(x.get('at') or 0), reverse=True)
        lines.append('%s:' % area)
        for it in items:
            lines.append('  %s' % it['text'])
    head = ('%d thing%s from today' if level == 'batch' else '%d thing%s overnight')
    n = len(rows)
    return {'title': ('EDGE-LOG: %s' % ('tonight' if level == 'batch' else 'this morning'))[:39],
            'message': (head % (n, '' if n == 1 else 's')) + '\n' + '\n'.join(lines),
            'priority': 'low'}


def send(level, log=None):
    """Drain a queue into ONE push. The queue is only cleared once the push is away."""
    rows = read_queue(level)
    note = digest(rows, level)
    if not note:
        return None, 0
    ok, _d = ntfy_push.push_result(note['message'], title=note['title'],
                                   priority=note['priority'], log=log)
    if ok:
        try:
            os.remove(_queue_path(level))
        except OSError:
            pass
    return ok, len(rows)


# ─────────────────────────────────────────────────────────────── GO / HOLD
def actions_for(key):
    """ntfy's Actions header for a GO/HOLD pair.

    Each button PUBLISHES one line to the answers topic - that is the whole mechanism. The body is
    two plain words, "<key> go" / "<key> hold", deliberately WITHOUT commas: ntfy separates the
    fields of an action with commas, so a JSON body would have to be quoted and one stray comma
    would silently split the action into nonsense.
    """
    topic = _answers_topic()
    if not topic:
        return None
    url = '%s/%s' % (_server(), topic)
    k = str(key).replace(',', '-').replace(' ', '-')
    return ('http, GO, %s, method=POST, body=%s go, clear=true; '
            'http, HOLD, %s, method=POST, body=%s hold, clear=true' % (url, k, url, k))


def ask(text, key, area='EDGE-LOG', priority='high', log=None):
    """A ring with GO and HOLD on it. -> the same tri-state as ring()."""
    return ring(text, area=area, priority=priority, actions=actions_for(key), log=log)


def answers(since='24h', timeout=10):
    """Every answer the phone has published -> [{'key','answer','at'}], oldest first.

    Read through ntfy's own poll API, so nothing has to be running to collect them.
    """
    topic = _answers_topic()
    if not topic:
        return []
    url = '%s/%s/json?poll=1&since=%s' % (_server(), topic, since)
    req = urllib.request.Request(url, headers={'User-Agent': 'edgelog-alert'})
    token = (os.environ.get('NTFY_TOKEN') or '').strip()
    if token and 'CHANGE-ME' not in token:
        req.add_header('Authorization', 'Bearer ' + token)
    out = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode('utf-8', 'replace')
    except Exception:
        return []
    for ln in body.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        out.append(o)
    return parse_answers(out)


def parse_answers(messages):
    """The ntfy messages -> answers. Anything that is not '<key> go|hold' is ignored."""
    out = []
    for o in messages:
        if not isinstance(o, dict) or o.get('event') not in (None, 'message'):
            continue
        parts = str(o.get('message') or '').split()
        if len(parts) != 2:
            continue
        key, ans = parts[0], parts[1].lower()
        if ans not in ('go', 'hold'):
            continue
        out.append({'key': key, 'answer': ans, 'at': float(o.get('time') or 0)})
    out.sort(key=lambda x: x['at'])
    return out


def answer_for(key, since='24h'):
    """The LATEST answer for one key, or None if he has not tapped. None is never a yes."""
    k = str(key).replace(',', '-').replace(' ', '-')
    hit = [a for a in answers(since=since) if a['key'] == k]
    return hit[-1]['answer'] if hit else None


def _one(text):
    return ' '.join(str(text or '').split())


def main():
    ap = argparse.ArgumentParser(description='EDGE-LOG phone alerts, in three loudnesses')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('ring', 'ask', 'batch', 'morning'):
        p = sub.add_parser(name)
        p.add_argument('--area', default='EDGE-LOG')
        p.add_argument('--text', required=True)
        if name == 'ask':
            p.add_argument('--key', required=True)
    p = sub.add_parser('send')
    p.add_argument('level', choices=('batch', 'morning'))
    p = sub.add_parser('queue')
    p.add_argument('level', choices=('batch', 'morning'))
    p = sub.add_parser('answers')
    p.add_argument('--since', default='24h')
    a = ap.parse_args()

    if a.cmd == 'ring':
        ok = ring(a.text, area=a.area, log=print)
        print('ALERT ring: %s' % ('sent' if ok else ('no topic configured' if ok is None else 'FAILED')))
        return 0 if ok is not False else 1
    if a.cmd == 'ask':
        ok = ask(a.text, a.key, area=a.area, log=print)
        print('ALERT ask: %s (key %s)' % ('sent' if ok else ('no topic configured' if ok is None
                                                             else 'FAILED'), a.key))
        return 0 if ok is not False else 1
    if a.cmd in ('batch', 'morning'):
        queue(a.cmd, a.text, area=a.area)
        print('ALERT %s: queued (%d waiting)' % (a.cmd, len(read_queue(a.cmd))))
        return 0
    if a.cmd == 'send':
        ok, n = send(a.level, log=print)
        if not n:
            print('ALERT send %s: nothing queued' % a.level)
            return 0
        print('ALERT send %s: %d line(s) %s' % (a.level, n,
                                                'sent' if ok else ('skipped, no topic' if ok is None
                                                                   else 'FAILED - kept in the queue')))
        return 0 if ok is not False else 1
    if a.cmd == 'queue':
        rows = read_queue(a.level)
        print('ALERT queue %s: %d waiting' % (a.level, len(rows)))
        for r in rows:
            print('  [%s] %s' % (r.get('area'), r.get('text')))
        return 0
    if a.cmd == 'answers':
        for x in answers(since=a.since):
            print('%s -> %s' % (x['key'], x['answer']))
        return 0
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())
