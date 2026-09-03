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
                                     (gates: boot, STUDIES, PAPER, run REPORT, row numbers)
  python tools/wt.py list            show every session worktree
  python tools/wt.py drop <name>     remove a worktree (refuses if it has uncommitted work)

`ship` run from inside a worktree needs no name.

After a successful push, `ship` also FAST-FORWARDS the shared checkout to the main it
just pushed (fast-forward only; skipped if that checkout is dirty or carries commits of
its own). The runner executes the shared checkout, so leaving it behind meant the code
that shipped was not the code that ran.

IMPORTANT: always invoke ship via the SHARED checkout's script path, e.g.
  python C:\\...\\EDGE-LOG\\tools\\wt.py ship
from inside (or naming) your worktree. Running the worktree's OWN tools/wt.py
resolves the repo root to the worktree itself, self-detects as "the shared
checkout", and refuses to ship.

Stdlib only. Safe to re-run: `new` on an existing name just prints its path.
"""
import argparse
import io
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

    # THIRD GATE: the PAPER boards (2026-08-26). Same argument as the studies gate, and the
    # same lesson learned the same way: a change to the PAPER branch of renderApp shipped a
    # mismatched paren that preflight_boot.py reported as PASS. paper_render_probe.py seeds a
    # real captured board and renders PAPER and PAPER * under 28 control combinations, and
    # asserts the two honesty rules that view has to keep - an archived leg must not leave
    # trades behind it, and NinjaTrader must never be shown refusing a trade on a leg it does
    # not run. Only runs when index.html changed. INCONCLUSIVE never blocks.
    pp = os.path.join(wt, 'tools', 'paper_render_probe.py')
    if touched_index.strip() and os.path.isfile(pp):
        r = subprocess.run([sys.executable, pp], cwd=wt, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        print(out.strip().splitlines()[0] if out.strip() else '(paper probe produced no output)')
        if r.returncode == 1:
            sys.stderr.write(out)
            raise SystemExit('paper render gate FAILED - not pushing')

    # REPORT GATE (2026-09-02): the RESULTS run report. The boot gate never opens a report,
    # and the report has shipped broken behind a green boot gate THREE times in a week
    # (v73.367 _reXNm undefined; v73.442 an _hRow without its heat getter; v73.443 the hotfix's
    # own EV R row outside the row list). Each blanked every run report on the live site until
    # a hotfix. report_render_probe.py injects one real captured validate run
    # (tools/fixtures/run_report.json, gate_validate with candidates / tilts / hybrids) into
    # runHistory, renders the report through renderApp exactly as a PAST RUNS click does, and
    # fails on any "runDetail failed" console.error, any uncaught exception, or the "couldn't
    # render" fallback card. Only runs when index.html changed. INCONCLUSIVE never blocks.
    rp = os.path.join(wt, 'tools', 'report_render_probe.py')
    if touched_index.strip() and os.path.isfile(rp):
        r = subprocess.run([sys.executable, rp], cwd=wt, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        print(out.strip().splitlines()[0] if out.strip() else '(report probe produced no output)')
        if r.returncode == 1:
            sys.stderr.write(out)
            raise SystemExit('run-report render gate FAILED - not pushing')

    # REPORT GATE SELF-TEST (2026-09-02): a gate that watches for one log line can go blind
    # without anyone noticing and keep printing PASS. Whenever the report probe or its fixture
    # changes, prove the gate still catches every build it was written for (KNOWN_BAD inside
    # report_render_probe.py: v73.367, v73.442, v73.443, each pulled from git history) and still
    # passes the current index.html. ~10 s, and only when the gate itself moved.
    touched_gate = run(['git', '-C', wt, 'diff', '--name-only', 'origin/main', '--',
                        'tools/report_render_probe.py', 'tools/fixtures/run_report.json'],
                       check=False)
    if touched_gate.strip() and os.path.isfile(rp):
        r = subprocess.run([sys.executable, rp, '--selftest'], cwd=wt, capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        last = [l for l in out.strip().splitlines() if l.startswith('SELFTEST:')]
        print(last[-1] if last else '(report probe self-test produced no output)')
        if r.returncode == 1:
            sys.stderr.write(out)
            raise SystemExit('run-report gate SELF-TEST FAILED - the gate no longer catches a '
                             'known-bad build - not pushing')

    # FOURTH GATE: STUDIES row numbers must stay unique (2026-08-26). The render probe proves
    # the board DRAWS; it says nothing about the registry contract. Two sessions numbering rows
    # at the same time silently produced 27 collisions, and a row number is the board's permanent
    # identifier - docs and memory refer to studies by number, so a duplicate makes those
    # references ambiguous forever. studies_registry_check.py already asserted uniqueness; it was
    # simply never wired into a gate.
    #
    # KNOWN_DUP_ROWS is the mess that already exists on main (the TTM Squeeze rounds and the ORB
    # travel/exits rounds landed on the same numbers). Renumbering those is an OWNER call, not a
    # side effect of someone else's push, so they are baselined: this gate blocks a push that adds
    # a NEW collision and lets the existing ones through. Shrink this set as they get resolved;
    # never grow it to get a push through.
    # 592-616: the TTM Squeeze rounds vs the ORB travel/exits rounds.
    # 697-736: a second cross-session overlap found 2026-08-26, same cause.
    # Both belong to other work and are referenced elsewhere BY NUMBER, so renumbering
    # them is an owner call. Shrink this set as they get resolved; never grow it to
    # get a push through - pick a free number instead.
    KNOWN_DUP_ROWS = set(range(592, 617)) | set(range(697, 737))
    rc = os.path.join(wt, 'tools', 'studies_registry_check.py')
    if touched_index.strip() and os.path.isfile(rc):
        r = subprocess.run([sys.executable, rc], cwd=wt, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        dups = set(int(m) for m in re.findall(r'row (\d+) duplicated', out))
        fresh = sorted(dups - KNOWN_DUP_ROWS)
        if fresh:
            sys.stderr.write(out)
            raise SystemExit('STUDIES row-number gate FAILED - not pushing. New duplicate row '
                             'number(s): ' + ', '.join(str(x) for x in fresh) +
                             '. Pick numbers above the current maximum and re-run.')
        print('STUDIES ROW NUMBERS: OK' +
              (' (%d known duplicate row(s) baselined)' % len(dups & KNOWN_DUP_ROWS) if dups else ''))

    run(['git', '-C', wt, 'push', '-q', 'origin', 'HEAD:main'])
    print('pushed: ' + run(['git', '-C', wt, 'log', '--oneline', '-1']))
    warn_pages_budget(wt)
    sync_shared(root)


def warn_pages_budget(wt):
    """Say something when we are about to out-run GitHub Pages' build limit.

    WHY (2026-08-26). A branch-sourced Pages site builds on every push to main and
    GitHub soft-limits that to roughly TEN BUILDS PER HOUR. Several Claude sessions ship
    independently, and none of them can see the others' pace, so nobody notices the line
    being crossed. That day main took 15 pushes inside the 07:00 hour; the site stopped
    publishing at v73.284 and sat there while main went to v73.287. Everything looked
    fine from every session's point of view - each push succeeded, the gates passed, git
    was clean - and the owner was the one who found out, by not being able to see his own
    feature.

    Nothing here can raise the limit. What it can do is make the invisible thing visible
    at the only moment anyone is looking: right after a push. Purely advisory - it never
    fails a push and never blocks one.
    """
    try:
        out = run(['git', '-C', wt, 'log', 'origin/main', '--since=1 hour ago',
                   '--format=%H'], check=False, quiet=True)
        n = len([l for l in (out or '').splitlines() if l.strip()])
        if n >= 10:
            print('  \u26a0 %d pushes to main in the last hour. GitHub Pages builds a '
                  'branch-sourced site about 10 times an hour, so the LIVE SITE MAY NOW '
                  'LAG BEHIND main.' % n)
            print('    Check: curl -s https://xrider3333.github.io/EDGE-LOG/index.html '
                  '| grep -o "const VERSION=.[0-9.]*."')
            print('    If it is behind, one more push once the hour rolls over '
                  'republishes it.')
        elif n >= 7:
            print('  note: %d pushes to main in the last hour (Pages builds ~10/hour).' % n)
    except Exception:
        pass          # advisory only - never let this affect a push that worked


def sync_shared(root):
    """Fast-forward the SHARED checkout to the main we just pushed.

    WHY THIS EXISTS (owner 2026-08-20: "fix the 66 commits behind issue. this keeps
    happening"). Every session works in its own worktree and pushes straight to
    origin/main, so nothing ever moved the shared checkout's own `main` -- it only
    advanced when a human remembered to pull, and nobody did. Measured that day it was
    66 commits behind, and the drift is not cosmetic: the RUNNER executes the shared
    checkout, so shipped code was sitting unshipped-in-practice for weeks (see memory
    `edgelog-shipped-vs-running`). Worse, the stale files still LOOKED like local edits,
    so a session could mistake a 147-line-behind copy for work in progress.

    Deliberately conservative -- this is a shared working directory on a live trading
    machine:
      * fast-forward ONLY. Never rebase, never merge a divergence, never reset.
      * skipped entirely if the shared checkout has uncommitted changes or commits of
        its own; that is somebody's work, so this prints how to look at it instead.
      * never fatal. A push that succeeded must not report failure because the shared
        checkout could not be tidied afterwards.
    """
    try:
        if run(['git', '-C', root, 'rev-parse', '--abbrev-ref', 'HEAD'], check=False) != 'main':
            print('shared checkout: not on main - left alone')
            return
        dirty = run(['git', '-C', root, 'status', '--porcelain', '--untracked-files=no'],
                    check=False, quiet=True)
        if dirty:
            # Most of what stalls this is not somebody's work at all - see
            #   _clear_lossless_modified. Try to clear it, then re-read.
            run(['git', '-C', root, 'fetch', '-q', 'origin'], check=False)
            _clear_lossless_modified(root)
            dirty = run(['git', '-C', root, 'status', '--porcelain',
                         '--untracked-files=no'], check=False, quiet=True)
        if dirty:
            print('shared checkout: %d file(s) modified - NOT fast-forwarded. '
                  'Review with: git -C "%s" status' % (len(dirty.splitlines()), root))
            return
        run(['git', '-C', root, 'fetch', '-q', 'origin'], check=False)
        counts = run(['git', '-C', root, 'rev-list', '--left-right', '--count',
                      'origin/main...HEAD'], check=False)
        parts = counts.split() + ['0', '0']
        behind, ahead = parts[0], parts[1]
        if ahead != '0':
            print('shared checkout: %s unpushed commit(s) of its own - NOT fast-forwarded. '
                  'Review with: git -C "%s" log origin/main..HEAD' % (ahead, root))
            return
        if behind == '0':
            print('shared checkout: already current')
            return
        _clear_identical_untracked(root)
        run(['git', '-C', root, 'merge', '--ff-only', '-q', 'origin/main'])
        print('shared checkout: fast-forwarded %s commit(s) -> %s'
              % (behind, run(['git', '-C', root, 'log', '--oneline', '-1'])))
    except Exception as e:                                    # never fail a good push
        print('shared checkout: could not fast-forward (%s: %s) - the push itself was fine'
              % (type(e).__name__, e))


def _clear_lossless_modified(root):
    """Discard TRACKED modifications that provably carry no unshipped work.

    WHY. _clear_identical_untracked (below) already solves this for UNTRACKED files:
    a session drops a file in the shared checkout, ships the same file properly from a
    worktree, and the fast-forward then stalls on a duplicate of what it was about to
    write. The identical thing happens to TRACKED files and was not covered, so the
    shared checkout sat 25 commits behind for days on five files that held nothing.
    Measured 2026-08-28: four TTM strategy files whose working copies were BYTE-
    IDENTICAL to origin/main, and an index.html whose entire uncommitted delta was a
    CRLF/LF flip on two lines. Nothing to lose in any of the five, and the runner was
    meanwhile executing engine code 25 commits old.

    TWO conditions, either of which proves the discard is lossless:
      (a) the working copy already equals the INCOMING version, so the merge was going
          to write exactly these bytes anyway; or
      (b) the working copy equals its own HEAD version once line endings are
          normalised, so the uncommitted delta is whitespace and nothing else.

    A file can be dirty with NOTHING uncommitted in it at all: if the blob at HEAD
    carries a stray CR that .gitattributes normalisation strips on the way back in,
    every checkout of that file is instantly dirty again and no amount of
    `git checkout --` clears it. That is why the discard writes the origin/main
    version rather than re-materialising the index one.

    Anything failing BOTH is somebody's unshipped work. It is left alone and named,
    and the caller then declines to fast-forward exactly as before - a human decides.
    That asymmetry is deliberate: the cost of a stalled fast-forward is a stale runner,
    and the cost of a wrong discard is lost work. Only the provable case is automated.
    """
    norm = lambda t: (t or "").replace("\r\n", "\n").strip()
    try:
        rows = run(["git", "-C", root, "status", "--porcelain",
                    "--untracked-files=no"], check=False, quiet=True)
    except Exception:
        return
    cleared, kept = [], []
    for line in (rows or "").splitlines():
        code, _, rel = line.partition(" ")[0], None, line[3:].strip().strip('"')
        if not rel or "->" in rel:          # a rename is never auto-discarded
            kept.append(rel or line.strip())
            continue
        full = os.path.join(root, rel.replace("/", os.sep))
        try:
            with io.open(full, encoding="utf-8", errors="replace") as fh:
                local = fh.read()
            incoming = run(["git", "-C", root, "show", "origin/main:" + rel],
                           check=False, quiet=True)
            head = run(["git", "-C", root, "show", "HEAD:" + rel],
                       check=False, quiet=True)
            n = norm(local)
            if n == norm(incoming) or n == norm(head):
                # CHECK OUT FROM origin/main, NOT from the index. Measured 2026-08-28:
                #   the blob at the stale HEAD held two stray CR bytes, so `checkout --`
                #   re-materialised the same dirt and the guard would have looped for
                #   ever. origin/main is what the fast-forward is about to write anyway,
                #   so writing it now is the same outcome one step early.
                run(["git", "-C", root, "checkout", "origin/main", "--", rel],
                    check=False, quiet=True)
                cleared.append(rel)
            else:
                kept.append(rel)
        except Exception:
            kept.append(rel)
    if cleared:
        print("shared checkout: discarded %d modification(s) that carried no unshipped "
              "work - already identical to what was incoming, or whitespace only (%s)"
              % (len(cleared), ", ".join(cleared[:4])
                 + (", ..." if len(cleared) > 4 else "")))
    if kept:
        print("shared checkout: left %d modified file(s) alone - they hold real "
              "unshipped changes (%s)" % (len(kept), ", ".join(kept[:4])
                                          + (", ..." if len(kept) > 4 else "")))


def _clear_identical_untracked(root):
    """Remove untracked files that are BYTE-IDENTICAL to the incoming commit.

    WHY (hit three times in four days, 2026-08-20 / 24). A session researching in the
    shared checkout drops a new strategy or tool file there, then ships the same file
    properly from a worktree. Now the shared checkout holds an untracked copy of a file
    that main tracks, and `merge --ff-only` refuses outright:

        error: The following untracked working tree files would be overwritten by merge

    So the whole auto-fast-forward stalls on files whose content is already what the
    merge wants to write. Every collision found so far has been an exact duplicate:
    ONDRIFT_1_0.py, r18/r18b/r19 triage tools, the TTM squeeze files, eleven more on
    2026-08-20 -- 0 differing lines in every case.

    STRICTLY identical-only. The comparison ignores line endings (this repo mixes CRLF
    and LF and the same file legitimately differs that way), but nothing else. A file
    that differs by even one real line is somebody's unshipped work: it is left alone,
    named, and the merge is allowed to fail so a human decides. Silently deleting that
    is the one outcome worth more than the convenience.
    """
    # run() returns stdout only, and git prints this refusal on STDERR - so call the
    # dry merge directly rather than widening run()'s contract for one caller.
    try:
        pr = subprocess.run(['git', '-C', root, 'merge', '--ff-only', 'origin/main'],
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace')
        out = (pr.stdout or '') + (pr.stderr or '')
    except Exception:
        return
    if 'untracked working tree files' not in out:
        return
    names, grabbing = [], False
    for line in (out or '').splitlines():
        if 'untracked working tree files' in line:
            grabbing = True
            continue
        if grabbing:
            t = line.strip()
            if not t or t.startswith(('Please ', 'Aborting', 'error:', 'Updating')):
                if t.startswith(('Please ', 'Aborting')):
                    break
                continue
            names.append(t)
    removed, kept = [], []
    for rel in names:
        full = os.path.join(root, rel.replace('/', os.sep))
        try:
            incoming = run(['git', '-C', root, 'show', 'origin/main:' + rel],
                           check=False, quiet=True)
            with io.open(full, encoding='utf-8', errors='replace') as fh:
                local = fh.read()
            # run() already strips its side, so strip both the same way: a leading
            # blank line must not read as a real difference. CRLF vs LF is normalised
            # too - this repo legitimately holds the same file both ways.
            norm = lambda t: t.replace('\r\n', '\n').strip()
            if norm(local) == norm(incoming):
                os.remove(full)
                removed.append(rel)
            else:
                kept.append(rel)
        except Exception:
            kept.append(rel)
    if removed:
        print('shared checkout: cleared %d untracked duplicate(s) of files main already '
              'tracks (%s)' % (len(removed), ', '.join(removed[:4])
                               + (', ...' if len(removed) > 4 else '')))
    if kept:
        print('shared checkout: %d untracked file(s) DIFFER from main and were left alone '
              '- fast-forward will stop here on purpose: %s'
              % (len(kept), ', '.join(kept)))


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
