#!/usr/bin/env python3
"""
tools/wt.py -- one git worktree per Claude session, so concurrent sessions never
share a working copy of index.html.

THE PROBLEM THIS SOLVES
-----------------------
Every session used to edit the SAME checkout. `git add index.html` therefore swept in
whatever another session had half-typed into that file, and a session that wanted to be
careful had to sit and wait for the other one to commit. Both failure modes are the same
root cause: one working tree, many writers.

WITH A WORKTREE PER SESSION
---------------------------
Each session gets its own folder and its own branch off origin/main. Nobody waits, nobody
bundles. `ship` rebases onto the newest main, re-aligns the VERSION line (two sessions
racing to bump it is the one guaranteed conflict), runs the boot gate, and pushes to main.

USAGE
-----
  python tools/wt.py new  <name>     create + print the worktree path to cd into
  python tools/wt.py ship [name]     rebase onto origin/main, fix VERSION, preflight, push
  python tools/wt.py list            show every session worktree
  python tools/wt.py drop <name>     remove a worktree (refuses if it has uncommitted work)

`ship` run from inside a worktree needs no name.

IMPORTANT: always invoke ship via the SHARED checkout's script path, e.g.
  python C:\\...\\EDGE-LOG\\tools\\wt.py ship
from inside (or naming) your worktree. Running the worktree's OWN tools/wt.py
resolves the repo root to the worktree itself, self-detects as "the shared
checkout", and refuses to ship.

Stdlib only. Safe to re-run: `new` on an existing name just prints its path.
"""
import argparse
import os
import re
import subprocess
import sys
import time

BRANCH_PREFIX = 'session/'
# deliberately OFF OneDrive: a worktree churns thousands of files and the sync client
# fights git for locks. Override with EDGELOG_WT_ROOT.
DEFAULT_ROOT = os.path.join(
    os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'EdgeLog-worktrees')


def run(args, cwd=None, check=True, quiet=False):
    # encoding matters: git output (e.g. `git show origin/main:index.html`, 2 MB UTF-8)
    # decoded with the Windows default cp1252 raises UnicodeDecodeError and silently
    # skipped the VERSION realign (observed 2026-08-10: a push shipped 72.4 over 72.5).
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode != 0 and check:
        if not quiet:
            sys.stderr.write((p.stdout or '') + (p.stderr or ''))
        raise SystemExit('git failed: ' + ' '.join(args))
    return (p.stdout or '').strip()


def repo_root():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return run(['git', '-C', here, 'rev-parse', '--show-toplevel'])


def wt_root():
    return os.environ.get('EDGELOG_WT_ROOT') or DEFAULT_ROOT


def cmd_new(name):
    root = repo_root()
    path = os.path.join(wt_root(), name)
    branch = BRANCH_PREFIX + name
    if os.path.isdir(os.path.join(path, '.git')) or os.path.isfile(os.path.join(path, '.git')):
        print(path)
        return
    run(['git', '-C', root, 'fetch', '-q', 'origin'])
    os.makedirs(wt_root(), exist_ok=True)
    exists = run(['git', '-C', root, 'branch', '--list', branch])
    args = ['git', '-C', root, 'worktree', 'add']
    if exists:
        args += [path, branch]
    else:
        args += ['-b', branch, path, 'origin/main']
    run(args)
    print(path)


def read_version(text):
    m = re.search(r"const VERSION='([\d.]+)'", text)
    return m.group(1) if m else None


def bump(v):
    a, b = v.split('.')
    return '%s.%d' % (a, int(b) + 1)


def cmd_ship(name, message):
    root = repo_root()
    wt = os.getcwd() if name is None else os.path.join(wt_root(), name)
    if not os.path.isdir(wt):
        raise SystemExit('no such worktree: ' + wt)
    inside = run(['git', '-C', wt, 'rev-parse', '--show-toplevel'])
    if os.path.abspath(inside) == os.path.abspath(root):
        raise SystemExit('refusing to ship from the SHARED checkout - run this from a worktree '
                         '(python tools/wt.py new <name>)')

    if run(['git', '-C', wt, 'status', '--porcelain']):
        if not message:
            raise SystemExit('uncommitted changes here - commit them, or pass --msg to commit now')
        run(['git', '-C', wt, 'add', '-A'])
        run(['git', '-C', wt, 'commit', '-q', '-m', message])

    run(['git', '-C', wt, 'fetch', '-q', 'origin'])
    ahead = run(['git', '-C', wt, 'rev-list', '--count', 'origin/main..HEAD'])
    if ahead == '0':
        print('nothing to ship - HEAD has no commits beyond origin/main')
        return
    p = subprocess.run(['git', '-C', wt, 'rebase', 'origin/main'], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if p.returncode != 0:
        run(['git', '-C', wt, 'rebase', '--abort'], check=False, quiet=True)
        raise SystemExit('rebase onto origin/main hit a conflict - resolve by hand in ' + wt +
                         '\n' + (p.stdout or '') + (p.stderr or ''))

    # VERSION race: two sessions bumping the same line always collides. After the rebase,
    # take whatever origin/main is on and step past it, and retag our newest changelog entry
    # so Settings > CHANGELOG still matches the version that actually ships.
    idx = os.path.join(wt, 'index.html')
    if os.path.isfile(idx):
        with open(idx, encoding='utf-8', newline='') as f:
            mine_txt = f.read()
        theirs = read_version(run(['git', '-C', wt, 'show', 'origin/main:index.html']) or '')
        mine = read_version(mine_txt)
        if mine and theirs:
            def num(v):
                a, b = v.split('.')
                return (int(a), int(b))
            if num(mine) <= num(theirs):
                want = bump(theirs)
                new_txt = mine_txt.replace("const VERSION='%s'" % mine,
                                           "const VERSION='%s'" % want, 1)
                new_txt = new_txt.replace("{v:'%s'," % mine, "{v:'%s'," % want, 1)
                # Flush to DISK, not just to the OS buffer. The boot gate below reads this
                # same file back from a SEPARATE process moments later; on a busy Windows box
                # (OneDrive/AV filter drivers in the path) that reader has been observed
                # getting a partial/empty file and reporting VERSION=None, bodyLen=0 --
                # which then blocked a perfectly valid push (2026-08-15). fsync + a
                # read-back check closes that window.
                with open(idx, 'w', encoding='utf-8', newline='') as f:
                    f.write(new_txt)
                    f.flush()
                    os.fsync(f.fileno())
                # Prove the file is readable and complete before anything downstream trusts
                # it. Cheap next to a failed ship, and it turns a silent race into a loud,
                # specific error instead of a misleading "boot gate FAILED".
                for _try in range(5):
                    try:
                        with open(idx, encoding='utf-8', newline='') as _f:
                            _back = _f.read()
                        if len(_back) == len(new_txt) and read_version(_back) == want:
                            break
                    except OSError:
                        pass
                    time.sleep(0.4)
                else:
                    raise SystemExit('version realign wrote index.html but could not read it '
                                     'back intact - aborting before the boot gate sees a '
                                     'partial file (re-run ship; nothing was pushed)')
                run(['git', '-C', wt, 'add', 'index.html'])
                run(['git', '-C', wt, 'commit', '-q', '--amend', '--no-edit'])
                print('version realigned %s -> %s (origin/main was on %s)' % (mine, want, theirs))

    # The boot gate must test the WORKTREE's index.html. preflight_boot.py resolves its
    # target from its own __file__ location (not cwd), so running the shared checkout's
    # copy validates the WRONG file (observed 2026-08-10: the gate reported the shared
    # checkout's VERSION). Prefer the worktree's own copy; fall back to the shared
    # checkout's script pointed explicitly at the worktree's index.html via --file.
    pf = os.path.join(wt, 'tools', 'preflight_boot.py')
    pf_args = [sys.executable, pf]
    if not os.path.isfile(pf):
        pf = os.path.join(root, 'tools', 'preflight_boot.py')
        pf_args = [sys.executable, pf, '--file', os.path.join(wt, 'index.html')]
    if os.path.isfile(pf):
        r = subprocess.run(pf_args, cwd=wt, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        print(out.strip().splitlines()[-1] if out.strip() else '(preflight produced no output)')
        if r.returncode == 1:
            raise SystemExit('boot gate FAILED - not pushing')

    # SECOND GATE: the STUDIES board. The boot gate only proves the app STARTS -- it never
    # enters a view, and this repo has shipped a view that crashed behind a green boot gate
    # (v64.22). studies_render_probe.py renders COMPARE > STUDIES headlessly under a dozen
    # control combinations. It only runs when index.html actually changed, so a ship that
    # touched nothing but docs or tools is not held up by it. INCONCLUSIVE never blocks.
    touched_index = run(['git', '-C', wt, 'diff', '--name-only', 'origin/main', '--', 'index.html'],
                        check=False)
    sp = os.path.join(wt, 'tools', 'studies_render_probe.py')
    if touched_index.strip() and os.path.isfile(sp):
        r = subprocess.run([sys.executable, sp], cwd=wt, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        print(out.strip().splitlines()[-1] if out.strip() else '(studies probe produced no output)')
        if r.returncode == 1:
            sys.stderr.write(out)
            raise SystemExit('studies render gate FAILED - not pushing')

    run(['git', '-C', wt, 'push', '-q', 'origin', 'HEAD:main'])
    print('pushed: ' + run(['git', '-C', wt, 'log', '--oneline', '-1']))


def cmd_list():
    root = repo_root()
    print(run(['git', '-C', root, 'worktree', 'list']))


def cmd_drop(name):
    root = repo_root()
    path = os.path.join(wt_root(), name)
    if run(['git', '-C', path, 'status', '--porcelain'], check=False, quiet=True):
        raise SystemExit('worktree has uncommitted changes - ship or discard them first')
    run(['git', '-C', root, 'worktree', 'remove', path])
    run(['git', '-C', root, 'branch', '-D', BRANCH_PREFIX + name], check=False, quiet=True)
    print('removed ' + path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('new'); n.add_argument('name')
    s = sub.add_parser('ship'); s.add_argument('name', nargs='?'); s.add_argument('--msg', default=None)
    sub.add_parser('list')
    d = sub.add_parser('drop'); d.add_argument('name')
    a = ap.parse_args()
    if a.cmd == 'new':
        cmd_new(a.name)
    elif a.cmd == 'ship':
        cmd_ship(a.name, a.msg)
    elif a.cmd == 'list':
        cmd_list()
    elif a.cmd == 'drop':
        cmd_drop(a.name)


if __name__ == '__main__':
    main()
