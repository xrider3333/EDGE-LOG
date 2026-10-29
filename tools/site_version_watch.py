#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/site_version_watch.py -- w34, "website check that failed updates" (owner, MANAGER GO 10-29).

THE FAULT IT WATCHES FOR
------------------------
GitHub Pages serves the site, so a push IS the deploy - but the push landing on main and the page
the owner's browser actually gets are two different things. A push can land while the Pages build
fails, or the build succeeds and a CDN edge keeps serving the old file; the repo then says one
version and the site says another, and nothing on screen admits it. This is the "shipped is not
running" trap, and the only honest way to catch it is to read the DEPLOYED page and compare it
against what main says it should be.

Under the owner's 10-29 ship rule it does double duty: every index.html push bumps VERSION and is
announced as "PUSHED v<VERSION> <hash>", so this check is also the automatic confirmation that the
announced version is the one being served.

WHAT IT DOES
------------
  1. reads VERSION out of the live page (cache-busted, so it is the edge's current answer, not the
     browser's memory)
  2. reads VERSION out of origin/main's index.html, through git, without touching the worktree
  3. agreement -> one line, no push, exit 0
  4. disagreement -> it does NOT cry at once. A deploy legitimately takes a few minutes, so the
     first disagreement is only remembered (with the time it was first seen); it pushes to the
     phone once the SAME disagreement has lasted --grace minutes, which defaults to 12.
  5. recovery -> when they agree again after a push went out, one low-priority "site caught up".

Repeats follow api.ntfy_push.dedupe_in, the same rule as every other alert in the repo: the same
problem pushes once, then at most once a day while unchanged, and a NEW or WORSE one goes at once.

  python tools/site_version_watch.py            # check, push if a stale deploy has outlasted grace
  python tools/site_version_watch.py --dry-run  # read and report, never push, never write state
  python tools/site_version_watch.py --grace 5
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SITE_URL = 'https://xrider3333.github.io/EDGE-LOG/index.html'
STATE = os.path.join(ROOT, 'tools', 'data', 'site_version_watch.json')
VER_RE = re.compile(r"const\s+VERSION\s*=\s*'([0-9][0-9.]*)'")
GRACE_MIN = 12


def _read_state():
    try:
        with io.open(STATE, encoding='utf-8') as fh:
            o = json.load(fh)
            return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def _write_state(o):
    d = os.path.dirname(STATE)
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = STATE + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(o, indent=1, sort_keys=True))
    os.replace(tmp, STATE)


def live_version(url=SITE_URL, timeout=20):
    """VERSION as the DEPLOYED page serves it right now. Cache-busted and no-cache, because the
    whole point is the edge's current answer, not a copy anything remembered."""
    u = '%s?fresh=%d' % (url, int(time.time()))
    req = urllib.request.Request(u, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
                                             'User-Agent': 'edgelog-site-version-watch'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        # VERSION sits in the first few hundred KB; the file is megabytes, so stop once it is found
        buf = r.read(900000).decode('utf-8', 'replace')
    m = VER_RE.search(buf)
    return m.group(1) if m else None


def main_version():
    """VERSION as origin/main holds it, read through git so the worktree is never touched and a
    lane's own uncommitted edit cannot be mistaken for what is deployed."""
    subprocess.run(['git', '-C', ROOT, 'fetch', '-q', 'origin'], capture_output=True, text=True,
                   timeout=120)
    sha = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', 'origin/main'],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    blob = subprocess.run(['git', '-C', ROOT, 'show', 'origin/main:index.html'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=180).stdout or ''
    m = VER_RE.search(blob)
    return (m.group(1) if m else None), sha


def note(live, want, sha, mins):
    """Three short lines, plain words - api.ntfy_push.lint is what judges the shape."""
    return ('The website is serving an older version than the one pushed.\n'
            'Site says %s, the repository says %s (%s).\n'
            'It has been behind for %d minutes - hard refresh, and check the Pages build.'
            % (live or 'nothing readable', want or 'unknown', sha or '?', mins))


def decide(live, want, state, now, grace_min=GRACE_MIN):
    """Do the deployed page and origin/main agree, and has a disagreement earned a push?

    -> (agree, minutes_behind, message_or_None, new_since)

    A deploy legitimately takes a few minutes, so a disagreement is REMEMBERED first and only
    reaches the phone once the same disagreement has lasted grace_min. `state` carries that
    first-seen time ('since'); the caller persists it.
    """
    first = (state or {}).get('since')
    if live == want:
        return True, 0, None, None
    if not first:
        first = now
    mins = int((now - float(first)) / 60)
    return False, mins, (note(live, want, None, mins) if mins >= grace_min else None), first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grace', type=int, default=GRACE_MIN,
                    help='minutes a disagreement must last before it reaches the phone')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    now = time.time()

    want, sha = main_version()
    try:
        live = live_version()
        err = None
    except Exception as e:
        live, err = None, '%s: %s' % (type(e).__name__, e)

    st = _read_state()
    if err:
        # THE SITE BEING UNREACHABLE IS NOT A STALE DEPLOY. It is said on the log line and left
        #   alone: a phone alert for every blip of the owner's Wi-Fi would train him to ignore it.
        print('SITE VERSION WATCH: could not read the live page (%s); repo says %s (%s)'
              % (err, want, sha))
        return 2
    if not want:
        print('SITE VERSION WATCH: INCONCLUSIVE - no VERSION found in origin/main index.html')
        return 2

    agree, mins, msg, since = decide(live, want, st, now, a.grace)
    st['since'] = since
    if msg:          # the real note carries the commit the repo is on; decide() has no git
        msg = note(live, want, sha, mins)

    # the shared repeat rule, so this alert behaves like every other one in the repo
    pushed = False
    if not a.dry_run:
        try:
            from api import ntfy_push
            store = st.setdefault('push', {})
            # dedupe_in wants {problem_id: rank} and returns ONE action string. The problem
            #   id carries the version pair, so a NEW stale pair counts as a new problem and
            #   goes out at once instead of waiting a day behind the previous one.
            cur = ({'behind:%s:%s' % (live, want): ntfy_push.RANK['high']} if msg else {})
            action = ntfy_push.dedupe_in(store, 'site_version', cur, now)
            if action == 'push' and msg:
                ntfy_push.push(msg, title='EDGE-LOG: site is behind', priority='high')
                pushed = True
            elif action == 'clear':
                ntfy_push.push('The website is serving the version that was pushed again.\n'
                               'Site and repository both say %s.' % want,
                               title='EDGE-LOG: site caught up', priority='low')
                pushed = True
        except Exception as e:
            print('SITE VERSION WATCH: push failed (%s: %s)' % (type(e).__name__, e))
    if not a.dry_run:
        _write_state(st)

    if agree:
        print('SITE VERSION WATCH: OK - site and repository both say %s (%s)' % (want, sha))
        return 0
    print('SITE VERSION WATCH: BEHIND - site says %s, repository says %s (%s), for %d min%s'
          % (live or 'nothing readable', want, sha, mins,
             ' - PUSHED' if pushed else (' - inside the %d min grace' % a.grace
                                         if mins < a.grace else '')))
    return 1


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())
