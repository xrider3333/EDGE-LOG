"""SHIP = B (OWNER 10-29): the full test tiers, run AFTER a `wt.py ship --fast` push landed.

    python tools/post_push_tests.py <worktree> <sha> [--label NAME]

Checks <sha> out into a fresh detached worktree (so later commits in the shipped worktree cannot
change what is tested), waits while tools/quiet.py says quiet, runs the pre-push test tiers there
(tools/hook_tests.py prelock - the same tiers and stamps the hook uses), then removes it.
A failure phones the owner (api/ntfy_push, high) and posts to MANAGER's inbox, so the lane fixes
forward at once. Never raises; exit code = the tiers' (0 pass, 1 fail, 2 could not run).
Launched detached by wt.py ship --fast; log C:/EdgeLog/post_push/<label>_<sha8>.log.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))


def log(s):
    print(time.strftime('%H:%M:%S ') + s, flush=True)


def _git(*args, cwd=None):
    return subprocess.run(['git'] + list(args), cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def alert(label, sha, tail, root):
    """Phone + MANAGER inbox. Each one is best-effort and logged; neither may raise."""
    msg = ('post-push tests FAILED on %s (%s) - main has the push; fix forward now. %s'
           % (sha[:8], label, tail[-300:].replace('\n', ' | ')))
    try:
        from api import ntfy_push
        note = ntfy_push.plain('Ship tests', 'CHECK NOW', None,
                               'tests failed after push %s (%s)' % (sha[:8], label),
                               'the lane fixes forward', priority='high')
        log('phone push: %r' % (ntfy_push.send(note),))
    except Exception as e:
        log('phone push failed: %s: %s' % (type(e).__name__, e))
    try:
        r = subprocess.run([sys.executable, os.path.join(root, 'tools', 'chat_inbox.py'), 'post',
                            '--from', 'TBIS', 'MANAGER', msg], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=60)
        log('inbox: ' + (r.stdout or r.stderr or '').strip()[-200:])
    except Exception as e:
        log('inbox post failed: %s: %s' % (type(e).__name__, e))


AFTER_HOUR = 13                 # MST, market days (MANAGER #138, owner 10-29)
LOCK = os.path.join(os.environ.get('EDGELOG_HOME') or r'C:\EdgeLog', 'state', 'post_push.lock')


def wait_for_window(now=time.localtime, sleep=time.sleep):
    """Mon-Fri before 13:00 local: wait. Returns the seconds it waited (0 = none)."""
    waited = 0
    while True:
        t = now()
        if t.tm_wday >= 5 or t.tm_hour >= AFTER_HOUR:
            return waited
        if waited == 0:
            log('market day before %02d:00 - full tiers wait' % AFTER_HOUR)
        sleep(60)
        waited += 60


def hold_one_at_a_time(path=LOCK, sleep=time.sleep):
    """One post-push run on this machine at a time: an OS lock on an open handle (dropped when the
    process ends, by any route). Returns the handle to keep."""
    import msvcrt
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, 'a+')
    said = False
    while True:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return fh
        except OSError:
            if not said:
                log('another post-push run holds the slot - waiting')
                said = True
            sleep(30)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('worktree')
    ap.add_argument('sha')
    ap.add_argument('--label', default=None)
    ap.add_argument('--base', default=None,
                    help="main before the push (default <sha>~1); the tiers cover base..sha")
    a = ap.parse_args(argv)
    label = a.label or os.path.basename(os.path.abspath(a.worktree))
    root = _git('rev-parse', '--show-toplevel', cwd=a.worktree).stdout.strip() or a.worktree
    try:
        import quiet as quiet_mode
        quiet_mode.wait_while_quiet('post-push tests', log=log)
    except Exception as e:
        log('quiet check skipped: %s' % e)
    wait_for_window()
    _slot = hold_one_at_a_time()  # noqa: F841 - held until exit
    tmp = os.path.join(os.environ.get('EDGELOG_WT_ROOT') or os.path.join(
        os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'EdgeLog-worktrees'),
        '_postpush_%s' % a.sha[:8])
    if os.path.isdir(tmp):
        _git('worktree', 'remove', '--force', tmp, cwd=a.worktree)
        shutil.rmtree(tmp, ignore_errors=True)
    r = _git('worktree', 'add', '--detach', tmp, a.sha, cwd=a.worktree)
    if r.returncode != 0:
        log('could not check out %s: %s' % (a.sha[:8], (r.stderr or '').strip()))
        alert(label, a.sha, 'checkout failed: ' + (r.stderr or ''), a.worktree)
        return 2
    t0 = time.time()
    try:
        env = dict(os.environ, EDGELOG_DIFF_BASE=a.base or (a.sha + '~1'))
        log('tiers cover %s..%s' % (env['EDGELOG_DIFF_BASE'][:12], a.sha[:8]))
        p = subprocess.run([sys.executable, os.path.join(tmp, 'tools', 'hook_tests.py'),
                            'prelock', '--root', tmp], cwd=tmp, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=env)
        out = (p.stdout or '') + (p.stderr or '')
        print(out[-6000:], flush=True)
        rc = p.returncode
    except Exception as e:
        out, rc = '%s: %s' % (type(e).__name__, e), 2
    log('tiers exit %s in %.0f s' % (rc, time.time() - t0))
    if rc != 0:
        alert(label, a.sha, out, a.worktree)
    _git('worktree', 'remove', '--force', tmp, cwd=a.worktree)
    shutil.rmtree(tmp, ignore_errors=True)
    return rc


if __name__ == '__main__':
    sys.exit(main())
