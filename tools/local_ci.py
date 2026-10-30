"""local_ci.py - the local CI runner (board C13, owner 10-30 via MANAGER #124 / #125).

Watches origin/main and runs the full pre-push test tiers on every new head, batched: one run covers
everything that landed since the last tested commit (tools/post_push_tests.py with --base = last tested).
- PAUSED 06:25-14:00 local every day (market hours + the owner's working morning); a run never STARTS inside the
  pause. post_push_tests.py's own rules still apply on top (quiet mode, its weekday window, and its OS slot lock
  C:/EdgeLog/state/post_push.lock - so this runner and wt.py ship --fast never run tiers at the same time).
- One run at a time (this loop is serial; the slot lock covers other launchers).
- State: C:/EdgeLog/state/local_ci.json {last_tested, last_rc, last_run}; log C:/EdgeLog/local_ci/local_ci.log.
- A failure is alerted by post_push_tests.py itself (phone + MANAGER inbox).

    pythonw tools/local_ci.py                 # the loop (launch via C:/EdgeLog/detach.py; autostart = owner's call)
    python  tools/local_ci.py --once          # one check, then exit
    python  tools/local_ci.py --once --dry    # say what it would run, run nothing
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOME = os.environ.get('EDGELOG_HOME') or r'C:\EdgeLog'
STATE = os.path.join(HOME, 'state', 'local_ci.json')
LOGDIR = os.path.join(HOME, 'local_ci')
PAUSE = ((6, 25), (14, 0))
POLL_S = 300


def log(s):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + s
    print(line, flush=True)
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, 'local_ci.log'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def paused(now=None):
    t = (now or dt.datetime.now()).time()
    return dt.time(*PAUSE[0]) <= t < dt.time(*PAUSE[1])


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')


def load_state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + '.tmp'
    json.dump(s, open(tmp, 'w', encoding='utf-8'), indent=1)
    os.replace(tmp, STATE)


def check(dry=False, now=None):
    """One pass. Returns 'paused' | 'idle' | 'ran:<rc>' | 'dry:<base>..<head>' | 'error'."""
    if paused(now):
        return 'paused'
    if git('fetch', '-q', 'origin', 'main').returncode != 0:
        log('fetch failed'); return 'error'
    head = git('rev-parse', 'origin/main').stdout.strip()
    st = load_state()
    last = st.get('last_tested')
    if last == head:
        return 'idle'
    if not last:                           # first run: test the head alone
        last = head + '~1'
    if dry:
        return 'dry:%s..%s' % (last[:8], head[:8])
    log('testing %s..%s' % (last[:8], head[:8]))
    rc = subprocess.run([sys.executable, os.path.join(HERE, 'post_push_tests.py'), ROOT, head,
                         '--label', 'localci', '--base', last]).returncode
    st.update(last_tested=head, last_rc=rc, last_run=time.strftime('%Y-%m-%d %H:%M'))
    save_state(st)
    log('done %s rc %s' % (head[:8], rc))
    return 'ran:%s' % rc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args(argv)
    if a.once:
        r = check(a.dry); print(r); return 0
    log('local CI runner started (pause %02d:%02d-%02d:%02d)' % (*PAUSE[0], *PAUSE[1]))
    while True:
        try:
            r = check()
            if r.startswith('ran'):
                continue                   # something may have landed while tiers ran
        except Exception as e:             # the loop never dies on one bad pass
            log('pass failed: %s: %s' % (type(e).__name__, e))
        time.sleep(POLL_S)


if __name__ == '__main__':
    sys.exit(main())
