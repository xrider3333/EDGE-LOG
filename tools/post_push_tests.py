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


# The test machinery itself. A queued run whose sha predates a fix to any of these on main tests
# the OLD machinery and fails for nothing (MANAGER #145: eight 30-min red runs on 10-30, all the
# same pre-fix hook test, all older than DISC's 03dc84e1).
TEST_INFRA = ('tools/githooks/', 'tools/hook_tests.py', 'tools/post_push_tests.py',
              'tests/conftest.py', 'tests/test_hook_tests.py')


def superseded_by(sha, cwd):
    """The newest main commit touching TEST_INFRA that <sha> does not contain, or None."""
    _git('fetch', '-q', 'origin', cwd=cwd)
    r = _git('log', '-1', '--format=%h %s', sha + '..origin/main', '--', *TEST_INFRA, cwd=cwd)
    return (r.stdout or '').strip() or None


# ============================================== OWNER HARD RULE 11-25: no check over 5 min, ever
CHECK_CAP_S = 300               # every shard is killed at 5:00 wall clock
SHARD_TARGET_S = 200.0          # bin-pack shards to ~200 s of measured test time (head-room)
STATE = os.path.join(os.environ.get('EDGELOG_HOME') or r'C:\EdgeLog', 'state')

_FILES_PY = """
import json, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), 'tools'))
import hook_tests as h
root = os.getcwd()
files = set()
for t in h.tiers(root, h.changed_files(root), log=lambda *a: None):
    files |= set(t.files)
secs = {}
try:
    for st in h.load_stamps(h.stamp_path(root)):
        secs.update(st.get('secs') or {})
except Exception:
    pass
print(json.dumps({'files': sorted(files), 'secs': secs}))
"""


def test_plan(tmp, env):
    """The files the tiers would run on this push, plus each file's last measured seconds."""
    import json
    r = subprocess.run([sys.executable, '-c', _FILES_PY], cwd=tmp, env=env, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=120)
    line = (r.stdout or '').strip().splitlines()[-1:] or ['']
    d = json.loads(line[0])
    return d['files'], d['secs']


def make_shards(files, secs, target=SHARD_TARGET_S):
    """Greedy bin-pack, longest file first, so each shard's measured time stays under `target`.
    A file never timed counts at the median of the timed ones. One file alone over the target
    still gets its own shard (the 5-min kill reports it SLOW, to be split)."""
    if not files:
        return []
    known = sorted(v for f, v in secs.items() if f in files)
    med = known[len(known) // 2] if known else 5.0
    cost = {f: float(secs.get(f, med)) for f in files}
    shards = []                                     # [secs, [files]]
    for f in sorted(files, key=lambda f: -cost[f]):
        best = min(shards, key=lambda b: b[0]) if shards else None
        if best is not None and best[0] + cost[f] <= target:
            best[0] += cost[f]
            best[1].append(f)
        else:
            shards.append([cost[f], [f]])
    return [sorted(b[1]) for b in shards]


def kill_tree(pid):
    try:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)], capture_output=True, timeout=30)
    except Exception:
        pass


def run_shards(tmp, shards, env, par, cap=CHECK_CAP_S, popen=subprocess.Popen, clock=time.time,
               sleep=time.sleep, kill=None):
    """Run the shards `par` at a time, each its own pytest process killed (whole tree) at `cap`
    seconds. Returns [(shard, status, tail)] with status 'pass' | 'fail' | 'SLOW'."""
    import tempfile
    kill = kill or kill_tree
    todo, live, out = list(shards), [], []
    while todo or live:
        while todo and len(live) < par:
            sh = todo.pop(0)
            fh = tempfile.TemporaryFile(mode='w+', encoding='utf-8', errors='replace')
            pr = popen([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'] + sh,
                       cwd=tmp, env=env, stdout=fh, stderr=subprocess.STDOUT)
            live.append((sh, pr, fh, clock()))
        sleep(2)
        for item in list(live):
            sh, pr, fh, t0 = item
            rc = pr.poll()
            if rc is None and clock() - t0 < cap:
                continue
            if rc is None:
                kill(pr.pid)
                status = 'SLOW'
            else:
                status = 'pass' if rc in (0, 5) else 'fail'      # 5 = no tests collected
            try:
                fh.seek(0)
                tail = fh.read()[-2500:]
                fh.close()
            except Exception:
                tail = ''
            live.remove(item)
            out.append((sh, status, tail))
            log('shard of %d file(s): %s in %.0f s%s' % (len(sh), status, clock() - t0,
                ': ' + ' '.join(sh) if status != 'pass' else ''))
    return out


def lane_file(label):
    return os.path.join(STATE, 'post_push_lane_%s.pid'
                        % ''.join(c if c.isalnum() else '_' for c in label))


def take_lane(label, sha, pf=None, kill=None):
    """NO STACKING: a new push cancels the older post-push run for the same lane. Kills the
    process tree recorded for this lane (if alive) and records this one."""
    pf = pf or lane_file(label)
    kill = kill or kill_tree
    os.makedirs(os.path.dirname(pf), exist_ok=True)
    try:
        old = int(open(pf).read().split()[0])
        if old != os.getpid():
            log('cancelling the older post-push run for lane %s (pid %d)' % (label, old))
            kill(old)
    except Exception:
        pass
    with open(pf, 'w') as fh:
        fh.write('%d %s' % (os.getpid(), sha))
    return pf


def still_mine(pf):
    try:
        return int(open(pf).read().split()[0]) == os.getpid()
    except Exception:
        return True


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
    pf = take_lane(label, a.sha)
    wait_for_window()
    _slot = hold_one_at_a_time()  # noqa: F841 - held until exit; max 1 suite machine-wide
    if not still_mine(pf):
        log('SKIP: a newer push for lane %s took over while this one waited' % label)
        return 0
    newer = superseded_by(a.sha, a.worktree)
    if newer:
        log('SKIP: %s predates a test-machinery fix on main (%s) - its tiers would test the old '
            'machinery; the next push runs on the fixed one' % (a.sha[:8], newer))
        return 0
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
        files, secs = test_plan(tmp, env)
        par = max(1, min(6, (os.cpu_count() or 4) // 3))
        shards = make_shards(files, secs)
        log('%d test file(s) in %d shard(s), %d at a time, %d s cap each'
            % (len(files), len(shards), par, CHECK_CAP_S))
        res = run_shards(tmp, shards, env, par)
        bad = [r for r in res if r[1] == 'fail']
        slow = [r for r in res if r[1] == 'SLOW']
        out = ''.join('\n[%s] %s\n%s' % (st, ' '.join(sh), tail[-800:]) for sh, st, tail in bad)
        if slow:
            note = ('post-push SLOW on %s (%s): %d shard(s) killed at %d s - split these tests: %s'
                    % (a.sha[:8], label, len(slow), CHECK_CAP_S,
                       ' | '.join(' '.join(sh) for sh, _, _ in slow)))
            log(note)
            try:
                subprocess.run([sys.executable, os.path.join(a.worktree, 'tools', 'chat_inbox.py'),
                                'post', '--from', 'TBIS', 'MANAGER', note[:1500]],
                               capture_output=True, timeout=60)
            except Exception:
                pass
        rc = 1 if bad else 0
    except Exception as e:
        out, rc = '%s: %s' % (type(e).__name__, e), 2
    log('shards exit %s in %.0f s' % (rc, time.time() - t0))
    if rc != 0:
        alert(label, a.sha, out, a.worktree)
    _git('worktree', 'remove', '--force', tmp, cwd=a.worktree)
    shutil.rmtree(tmp, ignore_errors=True)
    return rc


if __name__ == '__main__':
    sys.exit(main())
