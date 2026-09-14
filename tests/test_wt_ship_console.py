"""Pins `tools/wt.py ship` finishing its post-push steps when a commit subject is not ASCII.

2026-09-14, shipping 9a6ca04 ("BUILDER" plus a Greek beta): every gate passed and the push
landed, then the `pushed:` report line raised UnicodeEncodeError - Python on Windows encodes a
piped console as cp1252, which has no beta. The exception skipped warn_pages_budget and
sync_shared, so the shared checkout (the tree the runner executes) was left behind and had to
be fast-forwarded by hand.

Each case builds a throwaway origin, a "shared checkout" clone carrying the wt.py under test,
and a session worktree holding one commit with a beta in its subject, then really ships it
(fetch, rebase, push, fast-forward - all inside tmp_path, never this repository) with the
child's console forced to cp1252:
  cli     `python tools/wt.py ship`, the way every session runs it.
  direct  cmd_ship() called on an import, so main() never widened the console and only the
          guarded post-push prints stand between that subject and a skipped sync.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBJECT = 'BUILDER \u03b2: a subject cp1252 cannot encode'


def _env(tmp_path):
    # This suite also runs from the pre-push hook, and a hook's environment can carry
    # GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE. A sandbox git call that inherited one would
    # act on THIS repository instead of the throwaway one, so no GIT_* variable gets through.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update({
        'GIT_AUTHOR_NAME': 'wt test', 'GIT_AUTHOR_EMAIL': 'wt-test@example.invalid',
        'GIT_COMMITTER_NAME': 'wt test', 'GIT_COMMITTER_EMAIL': 'wt-test@example.invalid',
        'PYTHONIOENCODING': 'cp1252',        # what a piped console gets on Windows
        'PYTHONDONTWRITEBYTECODE': '1',
        'EDGELOG_WT_BACKUP_ROOT': str(tmp_path / 'wt_backup'),   # never C:\EdgeLog\_wt_backup
    })
    return env


def _git(env, cwd, *args):
    p = subprocess.run(['git', '-C', str(cwd)] + list(args), env=env, capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    assert p.returncode == 0, 'git %s failed:\n%s%s' % (' '.join(args), p.stdout, p.stderr)
    return p.stdout.strip()


def _sandbox(tmp_path, env):
    """origin (bare) <- shared checkout on main holding tools/wt.py <- session worktree with one
    unshipped commit whose subject carries a beta. Origin already has ten commits inside the
    hour, so warn_pages_budget prints its warning-sign line after the push too."""
    origin, shared, session = tmp_path / 'origin.git', tmp_path / 'shared', tmp_path / 'session'
    _git(env, tmp_path, 'init', '-q', '--bare', '-b', 'main', str(origin))
    _git(env, tmp_path, 'init', '-q', '-b', 'main', str(shared))
    _git(env, shared, 'remote', 'add', 'origin', str(origin))
    (shared / 'tools').mkdir()
    shutil.copy2(os.path.join(ROOT, 'tools', 'wt.py'), str(shared / 'tools' / 'wt.py'))
    _git(env, shared, 'add', '-A')
    _git(env, shared, 'commit', '-q', '-m', 'seed')
    for i in range(9):
        _git(env, shared, 'commit', '-q', '--allow-empty', '-m', 'earlier push %d' % i)
    _git(env, shared, 'push', '-q', 'origin', 'main')
    _git(env, shared, 'worktree', 'add', '-q', '-b', 'session/beta', str(session), 'origin/main')
    (session / 'feature.txt').write_text('beta\n')
    _git(env, session, 'add', 'feature.txt')
    _git(env, session, 'commit', '-q', '-m', SUBJECT)
    return origin, shared, session


def test_sandbox_console_really_is_cp1252(tmp_path):
    """Without this, the ship tests below could pass on a console that never needed the fix."""
    p = subprocess.run([sys.executable, '-c', 'print("\\u03b2")'], env=_env(tmp_path),
                       capture_output=True)
    assert p.returncode != 0 and b'UnicodeEncodeError' in p.stderr, p.stderr


@pytest.mark.parametrize('how', ['cli', 'direct'])
def test_ship_finishes_post_push_steps_on_non_ascii_subject(tmp_path, how):
    env = _env(tmp_path)
    origin, shared, session = _sandbox(tmp_path, env)
    tools = str(shared / 'tools')
    if how == 'cli':
        cmd = [sys.executable, os.path.join(tools, 'wt.py'), 'ship']
    else:
        cmd = [sys.executable, '-c',
               'import sys; sys.path.insert(0, sys.argv[1]); import wt; wt.cmd_ship(None, None)',
               tools]
    p = subprocess.run(cmd, cwd=str(session), env=env, capture_output=True)
    out = p.stdout.decode('utf-8', 'replace')
    err = p.stderr.decode('utf-8', 'replace')
    assert p.returncode == 0 and 'Traceback' not in err, out + err

    pushed = _git(env, session, 'rev-parse', 'HEAD')
    assert _git(env, origin, 'rev-parse', 'main') == pushed, 'the push did not land'
    assert _git(env, shared, 'rev-parse', 'HEAD') == pushed, (
        'the push landed but the shared checkout was NOT fast-forwarded:\n' + out + err)

    lines = out.splitlines()
    report = [ln for ln in lines if ln.startswith('pushed: ')]
    synced = [ln for ln in lines if ln.startswith('shared checkout: fast-forwarded 1 commit(s)')]
    budget = [ln for ln in lines if 'pushes to main in the last hour' in ln]
    assert len(report) == 1 and 'BUILDER ' in report[0], out
    assert len(synced) == 1 and 'BUILDER ' in synced[0], out
    assert len(budget) == 1, out
    if how == 'cli':        # main() made the console UTF-8, so nothing had to be escaped
        assert report[0].endswith(SUBJECT), report[0]
        assert synced[0].endswith(SUBJECT), synced[0]
        assert budget[0].lstrip().startswith('\u26a0 11 pushes'), budget[0]
