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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('worktree')
    ap.add_argument('sha')
    ap.add_argument('--label', default=None)
    a = ap.parse_args(argv)
    label = a.label or os.path.basename(os.path.abspath(a.worktree))
    root = _git('rev-parse', '--show-toplevel', cwd=a.worktree).stdout.strip() or a.worktree
    try:
        import quiet as quiet_mode
        quiet_mode.wait_while_quiet('post-push tests', log=log)
    except Exception as e:
        log('quiet check skipped: %s' % e)
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
        p = subprocess.run([sys.executable, os.path.join(tmp, 'tools', 'hook_tests.py'),
                            'prelock', '--root', tmp], cwd=tmp, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
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
