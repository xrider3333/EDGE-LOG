#!/usr/bin/env python3
"""
tools/wt_ff_selftest.py -- proves `wt.py`'s fast-forward blocker clearing (`_clear_ff_blockers`
in tools/wt.py) does the right thing on the three cases that actually happened on the shared
checkout (2026-09-07): an untracked twin of a file the incoming commit adds, a modified
tracked file identical modulo CRLF, and a genuinely different file that must NOT be touched.

Builds a throwaway bare "origin" repo plus two clones of it in a temp directory (nothing here
touches the real EDGE-LOG repo or C:\\EdgeLog\\_wt_backup - the backup root is redirected via
EDGELOG_WT_BACKUP_ROOT for the duration of this process). Never runs `git clean`.

Two clones, not one, because a fast-forward is all-or-nothing in git: a clone holding a
genuinely different blocker (scenario c) can never complete `merge --ff-only`, no matter how
correctly the clearer behaves on the other files sitting beside it. So:
  * clone "work_keep" plants ONLY the two clearable cases (a, b) and must reach a real,
    completed fast-forward (HEAD == origin/main).
  * clone "work_real" plants all three (a, b, c) and must clear a+b while leaving c's bytes
    completely untouched, backed up, and still blocking the merge on retry.

Usage: python tools/wt_ff_selftest.py
Exit 0 + "SELFTEST: PASS" on success, exit 1 + "SELFTEST: FAIL <reason>" otherwise.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wt  # noqa: E402


GIT_ENV_AUTHOR = [
    '-c', 'user.name=WT Selftest', '-c', 'user.email=wt-selftest@example.invalid',
]


def sh(args, cwd, check=True):
    p = subprocess.run(['git', '-C', cwd] + args, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError('git %s failed in %s:\n%s%s' % (args, cwd, p.stdout, p.stderr))
    return (p.stdout or '').strip()


def write(path, text, newline=''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline=newline) as f:
        f.write(text)


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def build_sandbox(tmp):
    """Central bare repo + a seed checkout two commits ahead of two fresh clones."""
    central = os.path.join(tmp, 'central.git')
    seed = os.path.join(tmp, 'seed')
    os.makedirs(central)
    sh(['init', '--bare', '-q', '-b', 'main'], central)

    os.makedirs(seed)
    sh(['init', '-q', '-b', 'main'], seed)
    sh(GIT_ENV_AUTHOR + ['remote', 'add', 'origin', central], seed)
    write(os.path.join(seed, 'README.md'), 'seed\n')
    write(os.path.join(seed, 'tracked_target.txt'), 'old content\n')
    sh(GIT_ENV_AUTHOR + ['add', '-A'], seed)
    sh(GIT_ENV_AUTHOR + ['commit', '-q', '-m', 'initial'], seed)
    sh(GIT_ENV_AUTHOR + ['push', '-q', 'origin', 'main'], seed)

    clones = {}
    for name in ('work_keep', 'work_real'):
        path = os.path.join(tmp, name)
        sh(['clone', '-q', central, path], tmp)
        sh(GIT_ENV_AUTHOR + ['checkout', '-q', 'main'], path)
        clones[name] = path

    # Advance origin past what the clones have: modify tracked_target.txt, add two new files.
    write(os.path.join(seed, 'tracked_target.txt'), 'new content\n')
    write(os.path.join(seed, 'untracked_target.txt'), 'added content\n')
    write(os.path.join(seed, 'real_diff.txt'), 'origin content\n')
    sh(GIT_ENV_AUTHOR + ['add', '-A'], seed)
    sh(GIT_ENV_AUTHOR + ['commit', '-q', '-m', 'advance'], seed)
    sh(GIT_ENV_AUTHOR + ['push', '-q', 'origin', 'main'], seed)

    return central, clones


def plant_clearable(work):
    """(a) untracked CRLF twin of a file the incoming commit ADDS, (b) a modified tracked
    file identical modulo CRLF."""
    write(os.path.join(work, 'untracked_target.txt'), 'added content\r\n')
    write(os.path.join(work, 'tracked_target.txt'), 'new content\r\n')


def plant_real_diff(work):
    """(c) a genuinely different untracked file colliding with a path the incoming commit
    adds - must be left completely alone."""
    write(os.path.join(work, 'real_diff.txt'), 'totally different local content\n')


def main():
    failures = []
    tmp = tempfile.mkdtemp(prefix='wt_ff_selftest_')
    backup_root = os.path.join(tmp, '_wt_backup')
    old_backup_env = os.environ.get('EDGELOG_WT_BACKUP_ROOT')
    os.environ['EDGELOG_WT_BACKUP_ROOT'] = backup_root
    wt.BACKUP_ROOT = backup_root          # module-level constant read at call time
    try:
        central, clones = build_sandbox(tmp)
        work_keep, work_real = clones['work_keep'], clones['work_real']

        # ---- scenario 1: only the clearable cases (a, b) -> full fast-forward ----
        plant_clearable(work_keep)
        sh(['fetch', '-q', 'origin'], work_keep)
        cleared = wt._clear_ff_blockers(work_keep)
        if not cleared:
            failures.append('work_keep: _clear_ff_blockers reported nothing cleared')
        pr = subprocess.run(['git', '-C', work_keep, 'merge', '--ff-only', 'origin/main'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
        if pr.returncode != 0:
            failures.append('work_keep: retry fast-forward FAILED after clearing: %s'
                            % ((pr.stdout or '') + (pr.stderr or '')))
        else:
            head = sh(['rev-parse', 'HEAD'], work_keep)
            tip = sh(['rev-parse', 'origin/main'], work_keep)
            if head != tip:
                failures.append('work_keep: HEAD (%s) did not reach origin/main tip (%s)'
                                % (head, tip))
            tt = io.open(os.path.join(work_keep, 'tracked_target.txt'), encoding='utf-8').read()
            if tt.replace('\r\n', '\n').strip() != 'new content':
                failures.append('work_keep: tracked_target.txt not at incoming content: %r' % tt)
            ut = io.open(os.path.join(work_keep, 'untracked_target.txt'), encoding='utf-8').read()
            if ut.replace('\r\n', '\n').strip() != 'added content':
                failures.append('work_keep: untracked_target.txt not at incoming content: %r' % ut)

        # ---- scenario 2: a + b + a genuinely different c -> c must survive untouched ----
        plant_clearable(work_real)
        plant_real_diff(work_real)
        original_c = read_bytes(os.path.join(work_real, 'real_diff.txt'))
        sh(['fetch', '-q', 'origin'], work_real)
        wt._clear_ff_blockers(work_real)

        c_path = os.path.join(work_real, 'real_diff.txt')
        if not os.path.isfile(c_path):
            failures.append('work_real: real_diff.txt was DELETED - must be left in place')
        else:
            now_c = read_bytes(c_path)
            if now_c != original_c:
                failures.append('work_real: real_diff.txt content CHANGED (was %r, now %r)'
                                % (original_c, now_c))

        backups = []
        if os.path.isdir(backup_root):
            for dirpath, _, files in os.walk(backup_root):
                for fn in files:
                    if fn == 'real_diff.txt':
                        backups.append(os.path.join(dirpath, fn))
        if not backups:
            failures.append('work_real: no backup of real_diff.txt found under %s' % backup_root)
        elif read_bytes(backups[0]) != original_c:
            failures.append('work_real: backup of real_diff.txt does not match original content')

        # tracked_target.txt is a TRACKED file: clearing it runs `checkout origin/main --`,
        # which writes the incoming content immediately - no full fast-forward required.
        tt2 = io.open(os.path.join(work_real, 'tracked_target.txt'), encoding='utf-8').read()
        if tt2.replace('\r\n', '\n').strip() != 'new content':
            failures.append('work_real: tracked_target.txt was not cleared: %r' % tt2)
        # untracked_target.txt is UNTRACKED: clearing it just deletes the identical local
        # duplicate so a future successful fast-forward can (re)materialise it from the
        # commit. Because real_diff.txt still blocks THIS merge, that full fast-forward
        # never runs in this scenario, so the file staying deleted (not present) is the
        # correct, expected outcome here - not data loss, since its content was proven
        # byte-identical to what main was going to write anyway.
        ut2_path = os.path.join(work_real, 'untracked_target.txt')
        if os.path.isfile(ut2_path):
            failures.append('work_real: untracked_target.txt should have been cleared '
                            '(deleted, pending a future successful fast-forward) but still '
                            'exists locally')

        pr2 = subprocess.run(['git', '-C', work_real, 'merge', '--ff-only', 'origin/main'],
                             capture_output=True, text=True, encoding='utf-8', errors='replace')
        if pr2.returncode == 0:
            failures.append('work_real: fast-forward SUCCEEDED despite real_diff.txt still '
                            'differing - it should still be blocked')
        else:
            out2 = (pr2.stdout or '') + (pr2.stderr or '')
            untracked2, modified2 = wt._parse_ff_blockers(out2)
            remaining = set(untracked2) | set(modified2)
            if remaining - {'real_diff.txt'}:
                failures.append('work_real: retry still blocked on unexpected path(s): %s - '
                                'expected only real_diff.txt' % sorted(remaining))
            if 'real_diff.txt' not in remaining:
                failures.append('work_real: retry no longer lists real_diff.txt as a blocker '
                                '(expected it to still block)')
    finally:
        if old_backup_env is None:
            os.environ.pop('EDGELOG_WT_BACKUP_ROOT', None)
        else:
            os.environ['EDGELOG_WT_BACKUP_ROOT'] = old_backup_env
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print('SELFTEST: FAIL (%d issue(s))' % len(failures))
        for f in failures:
            print('  - ' + f)
        return 1
    print('SELFTEST: PASS - clearable blockers (untracked twin + CRLF-only modified tracked '
          'file) cleared and fast-forwarded cleanly; a genuinely different file was left '
          'byte-unchanged, backed up, and still blocks the retry.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
