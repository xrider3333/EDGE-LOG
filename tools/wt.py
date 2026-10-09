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
  python tools/wt.py ship [name]     rebase onto origin/main, fix VERSION, gate, push
                                     (gates, in GATES order: boot, STUDIES, PAPER, run REPORT
                                     (+ self-test), 1E AXES / 1A funnel line procedure, CMP2,
                                     IMPORT time zones (+ self-test), HOME (+ self-test),
                                     WEBULL PAPER (+ self-test), STUDIES row numbers)
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

WHAT RUNS BEFORE THE PUSH LOCK, AND WHAT RUNS UNDER IT (2026-10-07)
-------------------------------------------------------------------
The machine-wide push lock (tools/push_lock.py, behind the FIFO ticket of tools/push_queue.py)
exists for the steps that really are serial: rebasing onto a main other lanes keep moving,
re-aligning the VERSION line and this ship's CHANGELOG entry against it, and pushing. Until
2026-10-07 ship also held it through every gate - including the probes' --selftest mutant
runs (HOME ~61-75 broken copies of index.html, WEBULL ~221-231; 47 minutes to 2 hours each) -
so a single probe-changing ship (mgr-ledger-frame-1007, from 17:45) held ten lanes for hours.
Now a ship runs in three steps:

  1. PRE-LOCK - no ticket, no lock. Fetch, rebase onto origin/main, realign VERSION, renumber
     this ship's new RESEARCH_LEDGER rows, and run EVERY gate that applies: the same set ship has always run, every --selftest included. Each
     pass is recorded in a stamp beside the worktree's git metadata
     (.git/worktrees/<name>/edgelog_ship_gates.json): the tree it passed on, the origin/main it
     was tested against, and the gate list version (GATE_LIST_VERSION + a fingerprint of GATES;
     a stamp written under any other gate list is ignored). A ship re-run on an unchanged tree
     (a killed or failed ship) reuses those passes instead of re-running them. A pass is only
     recorded when the worktree still holds that tree after the gate ran (tree_moved: no tracked
     file edited, HEAD not moved), and only one ship of a worktree runs at a time
     (hold_worktree), so a stamp never vouches for content no gate saw. A gate that fails here
     stops the ship exactly as before - no ticket, no lock, nothing pushed. Each gate run here
     first takes one of a few MACHINE-WIDE GATE SLOTS (hold_gate_slot: 1 for selftests, 2 for
     fast gates, OS locks like the push lock's), so queued lanes cannot pile their Chromes onto
     the PC that runs the trading runner; a ship waiting for one says so and whom it waits for.
     Then the PRE-PUSH TEST TIERS (2026-10-08, tools/hook_tests.py - the hook's own tiers, rule
     for rule): run on this tree, each passing test file stamped beside the worktree's git
     metadata. A heavy run (the engine tier: 20-40 minutes) takes the one TEST slot, a light one
     (timed at under LOCKED_TESTS_MAX_SECONDS) a fast slot - so the machine runs at most one heavy
     pytest and one selftest before the lock at a time. A failing test stops the ship here.
  2. LOCKED - take the ticket and the lock, fetch, rebase onto the NEWEST main, realign VERSION
     and renumber the ledger rows again against it (no-ops when main has not moved). Then each
     gate that applies to that final tree is either
       * reused - it passed on this exact tree (main did not move), or it is a SLOW gate (a
         --selftest) and every file it reads - its probe, its fixture, the helpers it imports
         (Gate.cover) - is byte-identical between the tree it passed on and this one; or
       * run, under the lock, on this tree. Those are the FAST gates (boot, the plain probes,
         the STUDIES registry): a few minutes.
     A selftest that cannot be reused does NOT run under the lock: ship gives the lock and its
     ticket back (it has pushed nothing), re-runs that selftest outside the lock and queues
     again - at most PRELOCK_ROUNDS (3) rounds, after which it runs it under the lock rather
     than loop. The exception is a QUICK selftest (its last run took under
     LOCKED_RERUN_MAX_SECONDS, 3 minutes - the run-report and import time-zone ones take
     seconds): re-running it under the lock costs less than queueing again, so it does. The
     console prints every reused gate, the verdict it carries and why it holds.
     The test tiers go the same way (2026-10-08): `hook_tests.py plan --json` estimates what the
     hook would re-run on this final tree - only what the commits that landed meanwhile can
     reach, each file at its measured time - and over LOCKED_TESTS_MAX_SECONDS (3 minutes) the
     lock and ticket go back (_let_go) and those tests run before the lock in the next round;
     after PRELOCK_ROUNDS they run under it.
  3. PUSH - the pre-push hook runs its tiers here, under the lock, on the final tree - but it
     skips every test file the pre-lock stamp vouches for and nothing since could reach
     (tools/hook_tests.py; for an engine change that was the full 20-40 minute engine tier until
     2026-10-08) - then prove the sha is on origin/main and fast-forward the shared checkout.
     The process exit releases the lock. If the remote
     refuses the push because a push from outside this machine moved main, ship rebases, realigns,
     renumbers and gates that new tree the same way under the same hold before pushing again.

No gate is weakened: every gate that ran before still runs on a tree equivalent to the one that
is pushed - the same tree, or for a selftest a tree identical in everything that selftest reads
except index.html (next paragraph).

WHY index.html IS NOT PART OF A SELFTEST'S COVER. Every ship bumps the VERSION line, so
index.html changes on main between every pre-lock run and every lock turn; keying a selftest on
it would send every probe ship round the loop three times and then run its selftest under the
lock anyway. Nor is it what a selftest has ever been keyed on: ship runs a probe's selftest only
when the PROBE or its fixture changes, and never re-runs it for a later ship that changes only
index.html - so a selftest result carried across other lanes' index.html changes is the same
assurance every later ship already relies on. The half of each selftest that does read the
final index.html ("the current file must PASS") is exactly the plain probe, which runs on the
final tree under the lock. Put another way: a reused selftest lands exactly the main the old
flow lands when this ship goes first and the lanes that moved main meanwhile go after it - none
of them would have re-run this probe's selftest either. The same holds for the few repo files the
page itself fetches at run time (PARAM_LIBRARY.md, docs/*.json - none in HOME or WEBULL). And
the one way another lane's page change can make a carried selftest meaningless - moving one of
its mutant anchors, so the broken copies could no longer even be built - is checked directly:
before a selftest pass is reused on a different tree, its MUTANTS' anchors are re-counted in
that tree's index.html (anchor_check, milliseconds); any anchor not found exactly once voids the
reuse.

Stdlib only. Safe to re-run: `new` on an existing name just prints its path.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import push_lock
except Exception:          # an older shared checkout: ship unlocked rather than not at all
    push_lock = None
try:
    import push_queue
except Exception:          # same: an unfair ship beats no ship
    push_queue = None

BRANCH_PREFIX = 'session/'
# deliberately OFF OneDrive: a worktree churns thousands of files and the sync client
# fights git for locks. Override with EDGELOG_WT_ROOT.
DEFAULT_ROOT = os.path.join(
    os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'EdgeLog-worktrees')

# Where a REAL (non-identical) fast-forward blocker gets backed up before we leave it in
# place for a human. Override with EDGELOG_WT_BACKUP_ROOT (used by the selftest so it never
# touches the real path).
BACKUP_ROOT = os.environ.get('EDGELOG_WT_BACKUP_ROOT') or r'C:\EdgeLog\_wt_backup'

# Never auto-clear these regardless of what the content-equality check says - they are
# large/binary/secret and a byte-identical read-back is not worth the risk of being wrong.
_PROTECTED_BASENAMES = {'optimizer_history.db', 'trial_cache.db', 'serviceAccount.json'}
_PROTECTED_PREFIXES = ('augur_uploads/',)


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


def utf8_console():
    """Make stdout and stderr UTF-8 before anything is printed.

    run() decodes git output as UTF-8, but printing it goes back out through the console
    encoding, and Python on Windows encodes a piped or redirected console (how Claude sessions
    run this script) as cp1252: print() raises UnicodeEncodeError on the first character
    outside it. Observed 2026-09-14: the Greek beta in the subject of 9a6ca04 ("BUILDER ...")
    killed ship on its `pushed:` line AFTER the push had landed, so sync_shared never ran and
    the shared checkout had to be fast-forwarded by hand. The same wall had been silently
    eating warn_pages_budget's warning sign. errors='replace', so nothing printed after this
    can raise on encoding.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:            # not a TextIOWrapper (None under pythonw, a test double)
            pass


def safe_print(text):
    """print() that never raises, for output after the push has landed - a report line that
    cannot be printed must not skip the post-push steps behind it. main() already made the
    console UTF-8; this backs up a stream nobody reconfigured (a caller that imported this
    module rather than running it) by printing the line with what the stream cannot encode
    escaped, e.g. \\u03b2."""
    try:
        print(text)
    except Exception:
        try:
            print(text.encode('ascii', 'backslashreplace').decode('ascii'))
        except Exception:
            pass


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


def studies_gate_verdict(out, returncode, known_dup_rows):
    """Judge one studies_registry_check.py run. Returns '' when the push may proceed, else
    the reason it may not. The check exits 1 whenever it has ANY complaint, including the
    baselined duplicates, so the exit code alone cannot be the verdict - but a non-zero
    exit with no PASS/FAIL report at all is a crash or an inconclusive run, and that must
    block too: before 2026-09-02 this gate only grepped for duplicates, so a traceback
    read as "no duplicates" and let a null slot plus six fresh collisions through."""
    m = re.search(r'^FAIL:\n((?:  .*\n?)*)', out, re.M)
    if m is None:
        if returncode == 0 and 'PASS' in out:
            return ''
        return ('studies_registry_check.py exited %d without a PASS/FAIL report (crashed '
                'or inconclusive); its output is above.' % returncode)
    fails = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    fresh = []
    for ln in fails:
        d = re.match(r'row (\d+) duplicated', ln)
        if d and int(d.group(1)) in known_dup_rows:
            continue
        fresh.append(ln)
    if not fresh:
        return ''
    dup_nums = sorted({int(re.match(r'row (\d+)', ln).group(1)) for ln in fresh
                       if re.match(r'row (\d+) duplicated', ln)})
    reason = '%d registry contract failure(s) beyond the baselined duplicates' % len(fresh)
    if dup_nums:
        reason += ('. New duplicate row number(s): ' + ', '.join(str(x) for x in dup_nums) +
                   ' - pick numbers above the current maximum')
    return reason + '. Fix the registry (or the check) and re-run.'



def changelog_entry_is_ours(diff, ver):
    """True when this ship's own diff ADDS the CHANGELOG entry tagged `ver`.

    The realign may only relabel an entry the shipping session wrote. `diff` is
    `git diff origin/main -- index.html`; an entry that is merely present on both sides
    belongs to somebody else and keeps the version it shipped under.
    """
    tag = "{v:'%s'," % ver
    return any(ln.startswith('+') and not ln.startswith('+++') and tag in ln
               for ln in (diff or '').splitlines())


def own_changelog_tag(diff):
    """The version tag of the NEWEST CHANGELOG entry this ship itself adds - the first added
    line (diff order = file order, newest first) that opens an entry - or None.

    Lanes do not have to guess the shipping version any more (2026-10-05, MANAGER go): main
    moves while a lane waits its turn, so any number typed by hand is stale by the time the
    lane gates. Whatever the entry is tagged, ship relabels it to the version that ships.
    Only a '+' line can match, so an entry that is merely present on both sides (someone
    else's work) is never relabelled - the 2026-09-03 rule below still holds.
    """
    for ln in (diff or '').splitlines():
        if ln.startswith('+') and not ln.startswith('+++'):
            m = re.match(r"^\+(?:const CHANGELOG=\[)?\{v:'([\d.]+)',", ln)
            if m:
                return m.group(1)
    return None


def resolve_version_changelog_conflict(path):
    """Resolve a rebase conflict in index.html that touches ONLY the VERSION line and the top
    of the CHANGELOG. HEAD (main) keeps its VERSION - the realign below steps past it - and
    this ship's new CHANGELOG line(s) go on top of main's. Returns True when resolved, False
    when any other hunk conflicts (that one still needs a person)."""
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read()
    nl = '\r\n' if '\r\n' in text[:5000] else '\n'
    lines = text.split(nl)
    out, i = [], 0
    while i < len(lines):
        if not lines[i].startswith('<<<<<<< '):
            out.append(lines[i]); i += 1
            continue
        try:
            j = lines.index('=======', i)
            k = next(x for x in range(j, len(lines)) if lines[x].startswith('>>>>>>> '))
        except (ValueError, StopIteration):
            return False
        head, mine = lines[i + 1:j], lines[j + 1:k]
        if head and all(re.match(r"^const VERSION='[\d.]+';$", x) for x in head + mine):
            out.extend(head)
        elif head and mine and head[0].startswith('const CHANGELOG=[{') \
                and mine[0].startswith('const CHANGELOG=[{'):
            seen = set(x.replace('const CHANGELOG=[', '', 1) for x in head)
            new = [x.replace('const CHANGELOG=[', '', 1) for x in mine
                   if x.replace('const CHANGELOG=[', '', 1) not in seen]
            if not new:
                return False
            out.append('const CHANGELOG=[' + new[0])
            out.extend(new[1:])
            out.append(head[0].replace('const CHANGELOG=[', '', 1))
            out.extend(head[1:])
        else:
            return False
        i = k + 1
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(nl.join(out))
    return True


LEDGER_FILE = 'RESEARCH_LEDGER.md'
_LEDGER_ROW = re.compile(r'^\| (\d+)\.(\d+) \|')


def resolve_ledger_row_conflict(path):
    """RESEARCH_LEDGER.md rows race between lanes (2026-10-06: 2.84 / 2.86 went to TTM while two other
    lanes' rows queued, and each had to rebuild by hand). A conflict made ONLY of table rows - each
    lane appended its own row(s) at the end of a section - is settled by keeping main's rows and
    putting this ship's rows after them; renumber_ledger_rows() then gives them free numbers.
    Returns True when resolved, False when any hunk holds anything but table rows."""
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read()
    nl = '\r\n' if '\r\n' in text[:5000] else '\n'
    lines = text.split(nl)
    out, i = [], 0
    while i < len(lines):
        if not lines[i].startswith('<<<<<<< '):
            out.append(lines[i]); i += 1
            continue
        try:
            j = lines.index('=======', i)
            k = next(x for x in range(j, len(lines)) if lines[x].startswith('>>>>>>> '))
        except (ValueError, StopIteration):
            return False
        head, mine = lines[i + 1:j], lines[j + 1:k]
        rows = [x for x in head + mine if x.strip()]
        if not rows or not all(_LEDGER_ROW.match(x) for x in rows):
            return False
        out.extend(head)
        out.extend(x for x in mine if x not in head)
        i = k + 1
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(nl.join(out))
    return True


def renumber_ledger_rows(wt):
    """Give this ship's NEW RESEARCH_LEDGER rows numbers nobody on main holds. A row is this ship's
    when its line is a + line in the ship own diff; when its number now appears TWICE in the file (another
    lane took it while this one waited), it moves to the next free number in its section. Rows that
    are main's are never touched. Returns [(old, new)] and amends the commit when anything moved."""
    path = os.path.join(wt, LEDGER_FILE)
    if not os.path.isfile(path):
        return []
    diff = run(['git', '-C', wt, 'diff', 'origin/main', '--', LEDGER_FILE], check=False, quiet=True)
    added = set(ln[1:] for ln in (diff or '').splitlines()
                if ln.startswith('+') and not ln.startswith('+++') and _LEDGER_ROW.match(ln[1:]))
    if not added:
        return []
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read()
    nl = '\r\n' if '\r\n' in text[:5000] else '\n'
    lines = text.split(nl)
    # NEW rows are this ship's added lines whose number main does not hold, or holds AND this file now
    # holds twice (another lane took it first - a CLASH). A row this ship only EDITED keeps its number:
    # main holds it and it appears once. When a section has a clash, all of this ship's new rows in that
    # section are renumbered in file order from main's highest number + 1, so they stay consecutive.
    theirs = run(['git', '-C', wt, 'show', 'origin/main:' + LEDGER_FILE], check=False, quiet=True) or ''
    on_main = set()
    for ln in theirs.splitlines():
        m = _LEDGER_ROW.match(ln)
        if m:
            on_main.add((int(m.group(1)), int(m.group(2))))
    count = {}
    for ln in lines:
        m = _LEDGER_ROW.match(ln)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            count[key] = count.get(key, 0) + 1
    new_rows, clash_secs = [], set()
    for n, ln in enumerate(lines):
        m = _LEDGER_ROW.match(ln)
        if not m or ln not in added:
            continue
        key = (int(m.group(1)), int(m.group(2)))
        if key in on_main and count[key] < 2:
            continue                                    # an edit of main's own row
        new_rows.append((n, key, m.end()))
        if key in on_main:
            clash_secs.add(key[0])
    moved, nxt = [], {}
    for n, key, end in new_rows:
        sec = key[0]
        if sec not in clash_secs:
            continue
        if sec not in nxt:
            nxt[sec] = max([b for a, b in on_main if a == sec] + [0]) + 1
        new = (sec, nxt[sec])
        nxt[sec] += 1
        if new != key:
            lines[n] = '| %d.%d |' % new + lines[n][end:]
            moved.append(('%d.%d' % key, '%d.%d' % new))
    if not moved:
        return []
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(nl.join(lines))
    run(['git', '-C', wt, 'add', LEDGER_FILE])
    run(['git', '-C', wt, 'commit', '-q', '--amend', '--no-edit'])
    # the lane may have quoted its row number elsewhere in this ship (a README line, BOOK.md, a doc)
    names = run(['git', '-C', wt, 'diff', '--name-only', 'origin/main'], check=False, quiet=True).split()
    for old, new in moved:
        hits = []
        for nm in names:
            if nm == LEDGER_FILE:
                continue
            body = run(['git', '-C', wt, 'diff', 'origin/main', '--', nm], check=False, quiet=True) or ''
            if any(ln.startswith('+') and re.search(r'(?<![\d.])' + re.escape(old) + r'(?![\d])', ln)
                   for ln in body.splitlines()):
                hits.append(nm)
        safe_print('RESEARCH_LEDGER row %s is now %s (another lane numbered its rows first)%s'
                   % (old, new, ('; this ship also quotes %s in: %s - check those' % (old, ', '.join(hits)))
                      if hits else ''))
    return moved


def rebase_onto_main(wt, cmd):
    """git rebase origin/main, settling VERSION / CHANGELOG-only conflicts on the way (a lane's
    own entry against another lane's, the one collision every lane hits). Returns the failed
    CompletedProcess when a real conflict stops it (the rebase is aborted), else None. `cmd` is
    the rebase command itself, written out at the call site so the lock-before-rebase order stays
    readable there (tests/test_push_lock.py checks it)."""
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    for _ in range(50):                       # one pass per replayed commit at most
        if p.returncode == 0:
            return None
        unmerged = run(['git', '-C', wt, 'diff', '--name-only', '--diff-filter=U'],
                       check=False, quiet=True).split()
        settled = []
        for nm in unmerged:
            fn = {'index.html': resolve_version_changelog_conflict,
                  LEDGER_FILE: resolve_ledger_row_conflict}.get(nm)
            if not fn or not fn(os.path.join(wt, nm)):
                run(['git', '-C', wt, 'rebase', '--abort'], check=False, quiet=True)
                return p
            settled.append(nm)
        if not settled:
            run(['git', '-C', wt, 'rebase', '--abort'], check=False, quiet=True)
            return p
        safe_print('rebase: settled %s (main keeps its version / rows, this ship goes on top)'
                   % ' + '.join(settled))
        run(['git', '-C', wt, 'add'] + settled)
        p = subprocess.run(['git', '-C', wt, 'rebase', '--continue'], capture_output=True,
                           text=True, encoding='utf-8', errors='replace',
                           env=dict(os.environ, GIT_EDITOR='true'))
    run(['git', '-C', wt, 'rebase', '--abort'], check=False, quiet=True)
    return p


# ==================================================================================== the gates
# WHICH GATES NEED THE PUSH LOCK (2026-10-07). Every gate ship runs, in the order it runs them,
# as one table - so the pre-lock run and the run under the lock can never drift apart, and so a
# stamp can say exactly which gate list it was written under. See the module docstring.

# Bump when a gate's MEANING changes without its row below changing (a new verdict rule, a probe
# re-purposed). A row change already changes gates_key() on its own, through the fingerprint.
GATE_LIST_VERSION = '2026-10-08.1'

# How many times a ship goes back outside the lock to re-run a selftest that main invalidated
# while it queued. Past this it runs it under the lock: rare, and better than never landing.
PRELOCK_ROUNDS = 3

# ...but only for a selftest that is SLOW. One that took less than this the last time it ran is
# cheaper to re-run under the lock than to give the lock back and queue again: the run-report and
# import time-zone selftests take seconds, HOME and WEBULL most of an hour. Measured per run and
# kept in the stamp; a selftest with no measured time counts as slow. Override (seconds) with
# EDGELOG_SHIP_LOCKED_RERUN_MAX.
LOCKED_RERUN_MAX_SECONDS = 180

# The pre-push test tiers' equivalent (2026-10-08): a re-run the hook would make under the lock,
# estimated over this, goes back outside the lock instead (another round), and a pre-lock run
# estimated over it is HEAVY - it takes the one test slot rather than a fast one. Override
# (seconds) with EDGELOG_SHIP_LOCKED_TESTS_MAX.
LOCKED_TESTS_MAX_SECONDS = 180

STAMP_FILE = 'edgelog_ship_gates.json'

# FOURTH GATE's baseline: STUDIES row numbers must stay unique (2026-08-26). The render probe
# proves the board DRAWS; it says nothing about the registry contract. Two sessions numbering
# rows at the same time silently produced 27 collisions, and a row number is the board's
# permanent identifier - docs and memory refer to studies by number, so a duplicate makes those
# references ambiguous forever. studies_registry_check.py already asserted uniqueness; it was
# simply never wired into a gate.
#
# KNOWN_DUP_ROWS baselines collisions that ALREADY exist on main, so this gate blocks a push
# that adds a NEW one while letting the known mess through. It is EMPTY, and should stay that
# way: the 65 rows that used to sit here (592-616, the TTM Squeeze rounds 2 and 4 against the
# ORB travel/exits rounds, and 697-736, TTM round 5 against MISC rounds 20-23) were resolved
# on 2026-09-09 in web v73.647. The rule was the study discovered first keeps the number: the
# TTM rounds carry disc 2026-08-22/23, the other six 2026-08-24/25, so those six moved to
# 1485-1549. See STUDIES_BOARD.md section 9. Never grow this set to get a push through -
# pick a free number above the board's current maximum instead.
KNOWN_DUP_ROWS = set()


class Gate(object):
    """One ship gate: a tools/ script run in the worktree.

    trigger  'always', 'index' (index.html differs from origin/main) or a tuple of paths (any of
             them differs from origin/main) - exactly when ship has always run it. A gate whose
             script the worktree does not have does not apply, as before.
    prefix   the gate prints its LAST output line starting with this; without one it prints the
             last line, or the first with first=True - each the line ship has always printed.
    slow     the probes' --selftest mutant runs. They run BEFORE the lock, and under it they are
             reused when nothing in `cover` changed. Everything else re-runs under the lock on
             the final tree unless that tree is byte-identical to the one it passed on.
    cover    for a slow gate: every repo file its verdict depends on except index.html (the
             module docstring says why not index.html). tests/test_wt.py fails if a probe
             imports a tool or reads a fixture that is not listed here.
    """

    def __init__(self, key, label, script, trigger, fail, empty, prefix=None, first=False,
                 args=(), dump=True, slow=False, cover=()):
        self.key, self.label, self.script, self.trigger = key, label, script, trigger
        self.fail, self.empty, self.prefix, self.first = fail, empty, prefix, first
        self.args, self.dump, self.slow, self.cover = tuple(args), dump, slow, tuple(cover)

    def pick(self, out):
        lines = (out or '').strip().splitlines()
        if self.prefix:
            mine = [ln for ln in lines if ln.startswith(self.prefix)]
            return mine[-1] if mine else self.empty
        if not lines:
            return self.empty
        return lines[0] if self.first else lines[-1]

    def __repr__(self):
        return 'Gate(%r)' % self.key


GATES = [
    # BOOT GATE. preflight_boot.py proves the app STARTS (VERSION present, renderApp defined, no
    # loadError, real body content). It must test the WORKTREE's index.html - see gate_command.
    Gate('boot', 'boot gate', 'tools/preflight_boot.py', 'always',
         'boot gate FAILED - not pushing', '(preflight produced no output)', dump=False),

    # SECOND GATE: the STUDIES board. The boot gate only proves the app STARTS -- it never enters
    # a view, and this repo has shipped a view that crashed behind a green boot gate (v64.22).
    # studies_render_probe.py renders COMPARE > STUDIES headlessly under a dozen control
    # combinations. Only when index.html changed. INCONCLUSIVE never blocks.
    Gate('studies', 'STUDIES render gate', 'tools/studies_render_probe.py', 'index',
         'studies render gate FAILED - not pushing', '(studies probe produced no output)'),

    # THIRD GATE: the PAPER boards (2026-08-26). A change to the PAPER branch of renderApp shipped
    # a mismatched paren that preflight_boot.py reported as PASS. paper_render_probe.py seeds a
    # real captured board and renders PAPER and PAPER * under 28 control combinations, and asserts
    # the view's two honesty rules - an archived leg must not leave trades behind it, and
    # NinjaTrader must never be shown refusing a trade on a leg it does not run.
    Gate('paper', 'PAPER render gate', 'tools/paper_render_probe.py', 'index',
         'paper render gate FAILED - not pushing', '(paper probe produced no output)', first=True),
    # ... and its SELF-TEST (2026-10-08, TRADING-LOG #67 / MANAGER #667): deliberately broken
    # copies of the current index.html (MUTANTS) must each FAIL for the reason they name, and the
    # real file must PASS - whenever the probe or its fixture changed. Three broken builds render
    # side by side (--jobs 3). Its last line starts 'SELFTEST:' or 'SELFTEST (only N mutants):'.
    # The cover adds tools/ledger_removed.py to the one #667 gave: the probe lints with it (the
    # cover test in tests/test_wt.py caught that), and a cover may only ever be a superset.
    Gate('paper-selftest', 'PAPER gate SELF-TEST', 'tools/paper_render_probe.py',
         ('tools/paper_render_probe.py', 'tools/fixtures/paper_board.json'),
         fail='PAPER gate SELF-TEST FAILED - the gate no longer catches a deliberately broken '
              'build - not pushing',
         empty='(paper probe self-test produced no output)',
         prefix='SELFTEST', args=('--selftest', '--jobs', '3'), slow=True,
         cover=('tools/paper_render_probe.py', 'tools/fixtures/paper_board.json',
                'tools/kill_on_exit.py', 'tools/ledger_removed.py')),

    # REPORT GATE (2026-09-02): the RESULTS run report, which shipped broken behind a green boot
    # gate THREE times in a week (v73.367 _reXNm undefined; v73.442 an _hRow without its heat
    # getter; v73.443 the hotfix's own EV R row outside the row list), each blanking every run
    # report on the live site. report_render_probe.py injects one real captured validate run
    # (tools/fixtures/run_report.json) and renders the report exactly as a PAST RUNS click does.
    Gate('report', 'run-report render gate', 'tools/report_render_probe.py', 'index',
         'run-report render gate FAILED - not pushing', '(report probe produced no output)',
         first=True),
    # ... and its SELF-TEST: a gate that watches for one log line can go blind and keep printing
    # PASS. Whenever the probe or its fixture changes, prove it still FAILS every build it was
    # written for (KNOWN_BAD: v73.367, v73.442, v73.443, pulled from git history) and still
    # passes the current index.html. Its entry point imports tools/kill_on_exit.py (MANAGER #69).
    Gate('report-selftest', 'run-report gate SELF-TEST', 'tools/report_render_probe.py',
         ('tools/report_render_probe.py', 'tools/fixtures/run_report.json'),
         'run-report gate SELF-TEST FAILED - the gate no longer catches a known-bad build - '
         'not pushing', '(report probe self-test produced no output)',
         prefix='SELFTEST:', args=('--selftest',), slow=True,
         cover=('tools/report_render_probe.py', 'tools/fixtures/run_report.json',
                'tools/kill_on_exit.py')),

    # AXES GATE (2026-09-07): the 1E ALL-CONFIGS axis set and the 1A CONFIG FUNNEL's line
    # procedure. matrix_axes_render_probe.py had caught a real regression (045de82, v73.520) - the
    # funnel's crowned line lost its walk-forward dash for a full day of shipped versions - but was
    # never wired into ship, so nobody was told. Also covers the EV R / SORTINO axes on the 1E
    # PARALLEL/SCATTER/TABLE views and the ML family tables.
    Gate('axes', '1E axes / 1A funnel render gate', 'tools/matrix_axes_render_probe.py', 'index',
         '1E axes / 1A funnel render gate FAILED - not pushing', '(axes probe produced no output)',
         prefix='1E AXES PROBE:'),

    # CMP2 GATE (2026-09-08): the COMPARE beta LEADERBOARD (augurSub==='cmp2'), its
    # expand-a-family sub-rows and the COMPARE/EXPLORE placeholder screens, rendered from the run
    # fixture plus an empty-runHistory case.
    Gate('cmp2', 'COMPARE beta (cmp2) render gate', 'tools/cmp2_render_probe.py', 'index',
         'COMPARE beta (cmp2) render gate FAILED - not pushing', '(cmp2 probe produced no output)',
         prefix='CMP2 PROBE:'),

    # IMPORT TIME-ZONE GATE (2026-09-24): TRADING LOG > IMPORT must save every trade time in
    # US/Eastern. NinjaTrader's exports print times in the platform's display zone with no label
    # and its PDF statement prints GMT; until the fix journal rows sat hours off. import_tz_probe.py
    # feeds the app's own importCSV / importPDF synthetic exports with known fill times.
    Gate('importtz', 'import time-zone gate', 'tools/import_tz_probe.py', 'index',
         'import time-zone gate FAILED - not pushing',
         '(import time-zone probe produced no output)', prefix='IMPORTTZPROBE:'),
    # ... and its SELF-TEST (does it still catch v73.885?) when the probe itself changed. Its
    # entry point imports tools/kill_on_exit.py, so that is part of what it reads.
    Gate('importtz-selftest', 'import time-zone gate SELF-TEST', 'tools/import_tz_probe.py',
         ('tools/import_tz_probe.py',),
         'import time-zone gate SELF-TEST FAILED - the gate no longer catches the pre-fix build - '
         'not pushing', '(import time-zone probe self-test produced no output)',
         prefix='SELFTEST:', args=('--selftest',), slow=True,
         cover=('tools/import_tz_probe.py', 'tools/kill_on_exit.py')),

    # HOME GATE (2026-10-02): HOME > REAL, the view the owner lands on, on a laptop and a phone.
    # home_render_probe.py seeds synthetic trades, SHOULD HAVE TRADED entries and packed trade bars
    # (no network), renders laptop / phone x glass / paper x SIMPLE / FULL / FEED and drives the
    # trade panel chart, the SHOULD HAVE TRADED panel, + ADD / SAVE and the paste box.
    Gate('home', 'HOME render gate', 'tools/home_render_probe.py', 'index',
         'HOME render gate FAILED - not pushing', '(HOME probe produced no output)',
         prefix='HOMEPROBE:'),
    # ... and its SELF-TEST (deliberately broken copies of index.html must FAIL) when the probe
    # changed. It also lints with tools/ledger_removed.py, so that is part of what it reads, and
    # its entry point is getting tools/kill_on_exit.py (TRADING-LOG's queued ship) - a cover may
    # be a superset of what the probe reads, never a subset.
    Gate('home-selftest', 'HOME gate SELF-TEST', 'tools/home_render_probe.py',
         ('tools/home_render_probe.py',),
         'HOME gate SELF-TEST FAILED - the gate no longer catches a deliberately broken build - '
         'not pushing', '(HOME probe self-test produced no output)',
         prefix='SELFTEST:', args=('--selftest',), slow=True,
         cover=('tools/home_render_probe.py', 'tools/ledger_removed.py',
                'tools/kill_on_exit.py')),

    # WEBULL GATE (2026-10-05): LEDGER > WEBULL PAPER, the same per-board render probe as HOME's.
    # webull_board_probe.py hands the board a fixed copy of the box's status doc
    # (tools/fixtures/qqq_exec_box1005.json, no network, no Firestore) and renders it on a laptop
    # and a phone in dark and MONO.
    Gate('webull', 'WEBULL PAPER render gate', 'tools/webull_board_probe.py', 'index',
         'WEBULL PAPER render gate FAILED - not pushing', '(WEBULL probe produced no output)',
         prefix='WEBULLPROBE:'),
    # ... and its SELF-TEST (the broken copies must FAIL) when the probe or its fixture changed.
    Gate('webull-selftest', 'WEBULL gate SELF-TEST', 'tools/webull_board_probe.py',
         ('tools/webull_board_probe.py', 'tools/fixtures/qqq_exec_box1005.json'),
         'WEBULL gate SELF-TEST FAILED - the gate no longer catches a deliberately broken build - '
         'not pushing', '(WEBULL probe self-test produced no output)',
         prefix='SELFTEST:', args=('--selftest',), slow=True,
         cover=('tools/webull_board_probe.py', 'tools/fixtures/qqq_exec_box1005.json',
                'tools/ledger_removed.py', 'tools/kill_on_exit.py')),

    # FOURTH GATE: STUDIES row numbers stay unique (see KNOWN_DUP_ROWS above). Judged by
    # studies_gate_verdict, not by its exit code alone.
    Gate('registry', 'STUDIES registry gate', 'tools/studies_registry_check.py', 'index',
         'STUDIES registry gate FAILED - not pushing.', ''),
]


def gates_key():
    """The gate list version a stamp is written under: GATE_LIST_VERSION plus a fingerprint of
    every GATES row (and of the registry gate's baseline), so a stamp from a different gate list
    is never trusted."""
    spec = [(g.key, g.script, g.args, g.trigger, g.cover, g.slow) for g in GATES]
    spec.append(('KNOWN_DUP_ROWS', sorted(KNOWN_DUP_ROWS)))
    return '%s/%s' % (GATE_LIST_VERSION,
                      hashlib.sha1(repr(spec).encode('utf-8')).hexdigest()[:10])


def gate_command(wt, root, g):
    """The command line for gate `g`, or None when the worktree has no such script.

    The boot gate must test the WORKTREE's index.html. preflight_boot.py resolves its target from
    its own __file__ location (not cwd), so running the shared checkout's copy validates the WRONG
    file (observed 2026-08-10: the gate reported the shared checkout's VERSION). Prefer the
    worktree's own copy; fall back to the shared checkout's script pointed explicitly at the
    worktree's index.html via --file."""
    own = os.path.join(wt, *g.script.split('/'))
    if os.path.isfile(own):
        # A selftest whose probe does not have the options it is run with yet (an older tree, a
        # probe a lane has not given --selftest / --jobs to) does not apply: argparse would exit
        # 2, and an INCONCLUSIVE selftest stops a ship (run_gate) - it must not stop one for that.
        opts = [a for a in g.args if a.startswith('--')]
        if opts:
            try:
                with open(own, encoding='utf-8', errors='replace') as f:
                    src = f.read()
            except OSError:
                return None
            if any(("'%s'" % o) not in src and ('"%s"' % o) not in src for o in opts):
                return None
        return [sys.executable, own] + list(g.args)
    if g.key == 'boot':
        shared = os.path.join(root, 'tools', 'preflight_boot.py')
        if os.path.isfile(shared):
            return [sys.executable, shared, '--file', os.path.join(wt, 'index.html')]
    return None


def applicable_gates(wt, root):
    """The gates that apply to the worktree's tree as it stands against origin/main, in order.

    index.html practically always differs, because the VERSION realign bumps it on every ship."""
    touched_index = run(['git', '-C', wt, 'diff', '--name-only', 'origin/main', '--',
                         'index.html'], check=False).strip()
    out = []
    for g in GATES:
        if gate_command(wt, root, g) is None:
            continue
        if g.trigger == 'index' and not touched_index:
            continue
        if isinstance(g.trigger, tuple) and not run(
                ['git', '-C', wt, 'diff', '--name-only', 'origin/main', '--'] + list(g.trigger),
                check=False).strip():
            continue
        out.append(g)
    return out


def run_gate(wt, root, g):
    """Run one gate and print its verdict line, exactly as ship always has. Returns (that line,
    the exit code). A failing gate raises SystemExit with the message it always had.

    INCONCLUSIVE (exit 2: no Chrome, Chrome timed out under load, a mutant anchor that moved) is
    no verdict, and since 2026-10-08 (MANAGER #667) it is never STAMPED as a pass (run_plan). A
    fast gate's INCONCLUSIVE still never blocks - as always - but it runs again on the final
    tree under the lock instead of being reused. A SELFTEST's stops the ship: carried forward it
    would vouch for a gate nobody saw catch anything, and re-running it round the pre-lock loop
    would cost an hour a time for the same answer.

    ONLY exit 2 is INCONCLUSIVE (2026-10-09, TRADING-LOG). Every gate speaks 0 PASS / 1 FAIL /
    2 INCONCLUSIVE; any other exit - a crash such as 0xC000026B (3221226091) when the PC sleeps
    mid-run, a negative signal exit, a killed process - is no verdict the gate chose, and is a
    FAIL before the lock and under it alike. Before, a fast gate that crashed under the lock was
    waved through as if INCONCLUSIVE.

    AN EXIT 0 WITHOUT ITS VERDICT LINE IS NO PASS (2026-10-09). A gate's `empty` text is the line
    ship prints when the gate printed no verdict line at all ("(... produced no output)") - by
    the table's own definition, no verdict. So exit 0 with that line counts as INCONCLUSIVE: it
    is never stamped, a selftest's stops the ship, and a fast gate's runs again on the final tree
    under the lock, exactly as an exit-2 would."""
    r = subprocess.run(gate_command(wt, root, g), cwd=wt, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    out = (r.stdout or '') + (r.stderr or '')
    if g.key == 'registry':
        verdict = studies_gate_verdict(out, r.returncode, KNOWN_DUP_ROWS)
        if verdict:
            sys.stderr.write(out)
            raise SystemExit(g.fail + ' ' + verdict)
        dups = set(int(m) for m in re.findall(r'row (\d+) duplicated', out))
        line = 'STUDIES REGISTRY: OK' + (' (%d known duplicate row(s) baselined)'
                                         % len(dups & KNOWN_DUP_ROWS) if dups else '')
        safe_print(line)
        return line, 0
    line = g.pick(out)
    safe_print(line)
    code = r.returncode
    if code not in (0, 1, 2):
        if g.dump:
            sys.stderr.write(out)
        raise SystemExit('%s (the gate exited %d - not PASS, FAIL or INCONCLUSIVE: it crashed or '
                         'was killed, e.g. the PC slept mid-run; ship again once it can finish)'
                         % (g.fail, code))
    if code == 1:
        if g.dump:
            sys.stderr.write(out)
        raise SystemExit(g.fail)
    how = 'exit %d' % code
    if code == 0 and line == g.empty:
        safe_print('  %s exited 0 without its verdict line - no verdict, so it counts as '
                   'INCONCLUSIVE, never as a pass' % g.label)
        code, how = 2, 'exit 0 with no verdict line'
    if g.slow and code != 0:
        if g.dump:
            sys.stderr.write(out)
        raise SystemExit('%s was INCONCLUSIVE (%s) - a selftest that reached no verdict is '
                         'not a pass, so it is not stamped and nothing was pushed. If Chrome '
                         'timed out under load, ship again; if a mutant anchor moved, update the '
                         'MUTANTS in %s first.' % (g.label, how, g.script))
    return line, code


# ================================================================================= the stamp
def stamp_path(wt):
    """Where this worktree's gate passes are recorded: beside its git metadata
    (.git/worktrees/<name>/), so the stamp never dirties the tree and dies with the worktree."""
    gd = run(['git', '-C', wt, 'rev-parse', '--absolute-git-dir'], check=False, quiet=True)
    return os.path.join(gd, STAMP_FILE) if gd else None


def load_stamp(path, key):
    """The stamp at `path` when it was written under gate list `key`, else an empty one. A
    missing, unreadable or foreign stamp only ever means "re-run the gates"."""
    empty = {'key': key, 'gates': {}}
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        return empty
    if not isinstance(d, dict) or d.get('key') != key or not isinstance(d.get('gates'), dict):
        return empty
    return d


def save_stamp(path, stamp):
    """Write the stamp atomically. Never raises: a stamp that cannot be written costs a re-run
    later, never a ship."""
    if not path:
        return
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(stamp, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        pass


def record_pass(stamp, g, tree, base, line, phase, secs=None):
    stamp.setdefault('gates', {})[g.key] = {
        'tree': tree, 'base': base, 'line': line, 'phase': phase, 'secs': secs,
        'at': time.strftime('%Y-%m-%d %H:%M:%S')}


def locked_rerun_max():
    try:
        return float(os.environ.get('EDGELOG_SHIP_LOCKED_RERUN_MAX', LOCKED_RERUN_MAX_SECONDS))
    except ValueError:
        return float(LOCKED_RERUN_MAX_SECONDS)


def locked_tests_max():
    try:
        return float(os.environ.get('EDGELOG_SHIP_LOCKED_TESTS_MAX', LOCKED_TESTS_MAX_SECONDS))
    except ValueError:
        return float(LOCKED_TESTS_MAX_SECONDS)


def too_slow_for_the_lock(g, stamp):
    """True when re-running selftest `g` under the lock would hold the other lanes up for longer
    than giving the lock back and queueing again costs: its last measured run took more than
    locked_rerun_max() seconds, or it has no measured run at all."""
    rec = ((stamp or {}).get('gates') or {}).get(g.key)
    secs = rec.get('secs') if isinstance(rec, dict) else None
    if isinstance(secs, bool) or not isinstance(secs, (int, float)):
        return True
    return secs > locked_rerun_max()


def tree_changes(wt):
    """changed(tree_a, tree_b, paths) -> the paths among `paths` that differ between the two
    trees, or None when git cannot say (a tree that no longer exists): None means re-run."""
    def changed(a, b, paths):
        p = subprocess.run(['git', '-C', wt, 'diff', '--name-only', a, b, '--'] + list(paths),
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        if p.returncode != 0:
            return None
        return [ln.strip() for ln in (p.stdout or '').splitlines() if ln.strip()]
    return changed


_ANCHOR_COUNT = r'''
import io, json, os, sys
tools = sys.argv[1]
sys.path.insert(0, tools)
mod = __import__(sys.argv[2])
src = io.open(os.path.join(os.path.dirname(tools), 'index.html'), encoding='utf-8',
              newline='').read()
bad = []
for m in getattr(mod, 'MUTANTS', None) or []:
    pairs = (list(zip(m[1], m[2])) if isinstance(m[1], (tuple, list)) else [(m[1], m[2])])
    built = src
    for a, r in pairs:
        n = built.count(a)
        if n != 1:
            bad.append([m[0], n])
            break
        built = built.replace(a, r)
print(json.dumps(bad))
'''


def anchor_check(wt):
    """anchors(g) -> None when every MUTANT of selftest `g` can still be built from the worktree's
    index.html - each anchor found exactly once, replaced in turn, exactly as the probe builds
    them - else plain words for why not (2026-10-08, MANAGER #667 should-fix ii).

    THE GAP IT CLOSES. index.html is in no selftest's cover (module docstring), so a selftest pass
    can be carried onto a final page where another lane has moved one of its mutant anchors - and
    there that selftest could no longer even build its broken copies. Recounting the anchors in
    the final page takes milliseconds and settles that case: the reuse is invalid and the selftest
    re-runs (and, the anchor being gone, comes back INCONCLUSIVE and stops the ship, which is the
    lane's cue to update its MUTANTS). It reads the probe's own MUTANTS by importing the probe in a
    child process (no bytecode written), so the ship never runs a probe's module code itself. A
    probe with no MUTANTS (the run-report and import time-zone selftests rebuild known-bad builds
    from git history) has nothing to recount. One that cannot be imported or counted counts as a
    problem: re-run rather than trust it."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')

    def anchors(g):
        mod = os.path.splitext(os.path.basename(g.script))[0]
        try:
            p = subprocess.run([sys.executable, '-c', _ANCHOR_COUNT, os.path.join(wt, 'tools'), mod],
                               cwd=wt, env=env, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=120)
        except Exception as e:
            return 'its mutant anchors could not be counted (%s)' % type(e).__name__
        lines = (p.stdout or '').strip().splitlines()
        try:
            bad = json.loads(lines[-1]) if p.returncode == 0 and lines else None
        except ValueError:
            bad = None
        if not isinstance(bad, list):
            tail = ((p.stderr or '').strip().splitlines() or ['no output'])[-1]
            return ('its mutant anchors could not be counted in the final index.html (%s)'
                    % tail[:160])
        if bad:
            return ('the final index.html no longer holds every mutant anchor exactly once (%s)'
                    % ', '.join('%s: found %s times' % (n, c) for n, c in bad[:5]))
        return None
    return anchors


def reuse_reason(g, stamp, tree, changed, anchors=None):
    """Why gate `g` need not run again on `tree`, or None when it must.

    Every gate is reused on the exact tree it passed on. A SLOW gate is also reused when every
    file in its cover is byte-identical between the tree it passed on and this one - which is
    what "the commits that landed meanwhile touched none of the files it reads" comes to, checked
    on the trees themselves rather than inferred from commit lists - AND, when `anchors` is given
    (anchor_check(wt); ship always gives it), every one of its mutant anchors is still in this
    tree's index.html. `changed` is tree_changes(wt) (or a fake, in tests)."""
    rec = ((stamp or {}).get('gates') or {}).get(g.key)
    if not isinstance(rec, dict) or not rec.get('tree') or not tree:
        return None
    when = rec.get('at') or '?'
    if rec['tree'] == tree:
        return 'passed on this exact tree at %s' % when
    if not g.slow or not g.cover:
        return None
    moved = changed(rec['tree'], tree, list(g.cover))
    if moved is None or moved:
        return None
    if anchors is not None:
        problem = anchors(g)
        if problem:
            return None
    return ('passed at %s on a tree that differs from this one only outside %s%s'
            % (when, ', '.join(g.cover),
               '; its mutant anchors re-counted in this index.html' if anchors else ''))


def rerun_reason(g, stamp, tree, changed, anchors=None):
    """Plain words for why a slow gate cannot be reused - for the console."""
    rec = ((stamp or {}).get('gates') or {}).get(g.key)
    if not isinstance(rec, dict) or not rec.get('tree'):
        return 'it has no pass recorded for this ship'
    moved = changed(rec['tree'], tree, list(g.cover))
    if moved is None:
        return 'the tree it passed on can no longer be compared'
    if moved:
        return 'main changed %s since it passed' % ', '.join(moved)
    problem = anchors(g) if anchors is not None else None
    return problem or 'its pass does not carry to this tree'


# ======================================================================= VERSION and phases
def realign_version(wt):
    """VERSION race: two sessions bumping the same line always collides. After a rebase, take
    whatever origin/main is on and step past it, and retag our newest changelog entry so
    Settings > CHANGELOG still matches the version that actually ships. Idempotent: run again on
    an already-realigned tree against the same main, it changes nothing."""
    idx = os.path.join(wt, 'index.html')
    if not os.path.isfile(idx):
        return
    with open(idx, encoding='utf-8', newline='') as f:
        mine_txt = f.read()
    theirs = read_version(run(['git', '-C', wt, 'show', 'origin/main:index.html']) or '')
    mine = read_version(mine_txt)
    if not (mine and theirs):
        return

    def num(v):
        a, b = v.split('.')
        return (int(a), int(b))
    entry_diff = run(['git', '-C', wt, 'diff', 'origin/main', '--', 'index.html'],
                     check=False, quiet=True)
    own_tag = own_changelog_tag(entry_diff)
    if num(mine) > num(theirs) and own_tag and own_tag != mine:
        # the lane bumped VERSION itself and tagged its entry with something else
        fixed = mine_txt.replace("{v:'%s'," % own_tag, "{v:'%s'," % mine, 1)
        with open(idx, 'w', encoding='utf-8', newline='') as f:
            f.write(fixed)
            f.flush()
            os.fsync(f.fileno())
        run(['git', '-C', wt, 'add', 'index.html'])
        run(['git', '-C', wt, 'commit', '-q', '--amend', '--no-edit'])
        print('CHANGELOG entry %s relabelled %s (the version this ship carries)'
              % (own_tag, mine))
    if num(mine) <= num(theirs):
        want = bump(theirs)
        new_txt = mine_txt.replace("const VERSION='%s'" % mine,
                                   "const VERSION='%s'" % want, 1)
        # Only re-tag a CHANGELOG entry this ship actually wrote. Retagging the top
        # entry unconditionally quietly relabels other people's work: a ship that
        # changes no index.html content (tools, docs) still bumps VERSION, and the
        # blind replace then moved the previous session's entry forward with it.
        # Observed twice on 2026-09-03 - it walked the STUDIES registry entry from
        # 73.461 to 73.462 to 73.463, so the changelog credited the wrong build.
        # A gap in the numbers is correct and already normal here: a ship with
        # nothing user-facing to say should leave the changelog alone.
        if own_tag:
            new_txt = new_txt.replace("{v:'%s'," % own_tag, "{v:'%s'," % want, 1)
            retagged = True
        else:
            retagged = False
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
        print('version realigned %s -> %s (origin/main was on %s)%s'
              % (mine, want, theirs,
                 '' if retagged else "; CHANGELOG untouched - this ship added "
                 "no entry of its own"))


def _mmss(seconds):
    s = int(max(0, seconds))
    return '%dm%02ds' % (s // 60, s % 60)


SHIP_GUARD_FILE = 'edgelog_ship.lock'


def hold_worktree(wt):
    """ONE SHIP PER WORKTREE AT A TIME (2026-10-07). Before the pre-lock phase existed the push
    lock also kept two ships of the SAME worktree apart; now each one rebases and gates before it
    queues, so two at once (a re-run in a second terminal, a lane that lost track of its first
    ship) would rebase one worktree under the other's gates - and the stamp would vouch for a
    tree no gate saw. An OS lock on a file beside the worktree's git metadata, released by the
    kernel when this process ends however it ends (the push lock's own reasoning). Returns the
    open descriptor (a plain int: nothing closes it before the process ends) or None when it
    cannot be taken for any reason but another ship (fail open, as the push lock does). Raises
    SystemExit when another ship holds it."""
    if push_lock is None:
        return None
    gd = run(['git', '-C', wt, 'rev-parse', '--absolute-git-dir'], check=False, quiet=True)
    if not gd:
        return None
    try:
        fd = os.open(os.path.join(gd, SHIP_GUARD_FILE), os.O_CREAT | os.O_RDWR)
    except Exception:
        return None
    try:
        push_lock._lock_fd(fd)
    except OSError:
        os.close(fd)
        raise SystemExit('another wt.py ship of ' + wt + ' is already running - let it finish '
                         '(two ships rebasing one worktree at once would gate one tree and '
                         'stamp another). Nothing was done.')
    except Exception:
        os.close(fd)
        return None
    return fd


def tree_moved(wt, tree):
    """Why the worktree no longer holds `tree` - a tracked file edited, or HEAD moved (a commit
    made meanwhile) - or None while it still does. A gate reads the FILES and the stamp records
    the TREE: a pass is only recorded once this says they are still the same thing, so a stamp
    can never vouch for content no gate saw, and nothing is pushed that differs from what the
    gates ran on."""
    if run(['git', '-C', wt, 'status', '--porcelain', '--untracked-files=no'],
           check=False, quiet=True):
        return 'a tracked file in %s changed while the gates ran' % wt
    now = run(['git', '-C', wt, 'rev-parse', 'HEAD^{tree}'], check=False, quiet=True)
    if now != tree:
        return 'HEAD in %s moved while the gates ran (tree %s -> %s)' % (wt, tree[:8],
                                                                         (now or '?')[:8])
    return None


# ======================================================================= the gate slots
# HOW MANY PRE-LOCK GATES RUN AT ONCE ON THIS MACHINE (2026-10-08, MANAGER #667 must-fix 1).
# Before the pre-lock phase the push lock serialized every probe and selftest machine-wide. Now
# each queued lane gates before it queues, so nine lanes could run nine sets of headless probes,
# or several 3-4-Chrome selftests, side by side - on the PC that also runs the trading runner and
# the paper boxes (100% CPU with 8 GB free last night with ONE selftest). So a pre-lock gate run
# first takes one of a few machine-wide SLOTS: an OS lock on one of these files under
# <EDGELOG_HOME>/state/gate_slots/, the push lock's own mechanism - the kernel releases it when
# the holding process ends, however it ends, so a killed ship can never wedge a slot. Selftests
# (slow gates) and fast gates draw from separate pools, so a two-hour selftest never stops the
# minute-long probes. The gates under the push lock take NO slot: one lane holds it at a time
# already, and waiting there on another lane's slot would stretch the very hold this exists to
# shorten.
GATE_SLOTS = {'slow': 1, 'fast': 2, 'tests': 1}

# A waiter stops - nothing pushed, nothing held - rather than wait for ever behind a wedged
# holder: twice the longest selftest seen (2 h) for a selftest slot, a generous multiple of the
# minutes a fast probe takes for a fast one. Override (seconds, both kinds) with
# EDGELOG_GATE_SLOT_WAIT_MAX.
GATE_SLOT_WAIT_MAX = {'slow': 4 * 3600, 'fast': 3600, 'tests': 6 * 3600}

_SLOT_WORDS = {'slow': ('selftest slot', 'selftest'), 'fast': ('gate slot', 'render gates'),
               'tests': ('test slot', 'heavy pre-push test run')}
# 'tests' (2026-10-08): the pre-push test tiers before the lock. A full engine tier is one busy
# core for 20-40 minutes, so ONE at a time machine-wide, beside at most one selftest; a light run
# (timed under LOCKED_TESTS_MAX_SECONDS - the contract tier, a tool's own tests) takes a fast
# slot instead. A test run that waits past its limit does not stop the ship: the hook still runs
# every tier under the lock, as it did before the pre-lock run existed (prelock_tests).


def gate_slot_dir():
    return os.path.join(os.environ.get('EDGELOG_HOME') or r'C:\EdgeLog', 'state', 'gate_slots')


# MORE SLOTS WHILE NINJATRADER IS CLOSED (2026-10-09, MANAGER). With ONE test slot about 14 ships
# queued for hours behind 25-30 minute test runs. The cap exists to keep the PC responsive while
# NinjaTrader trades (the 10-08 12:22 feed flap came 80 s after a Windows 'low on virtual memory'
# warning), so it stays as GATE_SLOTS while NT runs and rises to NIGHT_GATE_SLOTS while NT NIGHT
# MODE holds NinjaTrader closed (tools/nt_night.py: <EDGELOG_HOME>/nt_night_mode.json, active.until
# in the future). <gate_slot_dir>/limits.json {"tests": 2, ...} overrides both by hand (clamped
# 1..GATE_SLOT_MAX). A waiter re-reads the cap on every poll, so a rise reaches ships already waiting.
NIGHT_GATE_SLOTS = {'slow': 1, 'fast': 3, 'tests': 3}
GATE_SLOT_MAX = 4


def nt_night_active(clock=time.time):
    """True while NT night mode holds NinjaTrader closed; any problem reading it = False (the
    daytime cap - the safe side)."""
    p = os.path.join(os.environ.get('EDGELOG_HOME') or r'C:\EdgeLog', 'nt_night_mode.json')
    try:
        from datetime import datetime
        with open(p, encoding='utf-8') as f:
            until = ((json.load(f) or {}).get('active') or {}).get('until')
        return bool(until) and datetime.fromisoformat(str(until)).timestamp() > clock()
    except Exception:
        return False


def gate_slot_count(kind):
    """How many `kind` slots are open right now: limits.json by hand, else NIGHT_GATE_SLOTS
    while NT night mode is on, else GATE_SLOTS."""
    try:
        with open(os.path.join(gate_slot_dir(), 'limits.json'), encoding='utf-8') as f:
            v = (json.load(f) or {}).get(kind)
        if v is not None:
            return max(1, min(GATE_SLOT_MAX, int(v)))
    except Exception:
        pass
    if nt_night_active():
        return max(GATE_SLOTS[kind], min(GATE_SLOT_MAX, NIGHT_GATE_SLOTS.get(kind, 1)))
    return GATE_SLOTS[kind]


def gate_slot_paths(kind, count=None):
    n = gate_slot_count(kind) if count is None else count
    return [os.path.join(gate_slot_dir(), '%s-%d.lock' % (kind, i))
            for i in range(1, n + 1)]


def _slot_wait_max(kind):
    try:
        return float(os.environ['EDGELOG_GATE_SLOT_WAIT_MAX'])
    except (KeyError, ValueError):
        return float(GATE_SLOT_WAIT_MAX[kind])


def hold_gate_slot(kind, who, sleep=time.sleep, now=time.time):
    """Take one `kind` ('slow' or 'fast') gate slot for this process, waiting - and saying so,
    once, with who holds them - while every one is taken. Returns the open descriptor (hand it to
    release_gate_slot when the gate is done; the process exit releases it otherwise), or None when
    the slots cannot be used at all (no push_lock module, no state directory): a missing cap must
    not stop a ship. Raises SystemExit when none comes free within _slot_wait_max(kind)."""
    if push_lock is None:
        return None
    opened = {}                          # path -> descriptor; grows when the cap rises
    try:
        os.makedirs(gate_slot_dir(), exist_ok=True)
        paths = gate_slot_paths(kind)
        for p in paths:
            opened[p] = os.open(p, os.O_CREAT | os.O_RDWR)
    except Exception as e:
        for fd in opened.values():
            _release_fd(fd, lambda _fd: None)
        safe_print('  gate slots unavailable (%s: %s) - running this gate without one'
                   % (type(e).__name__, e))
        return None
    noun, plural = _SLOT_WORDS[kind]
    deadline = now() + _slot_wait_max(kind)
    said = False
    while True:
        try:
            paths = gate_slot_paths(kind)            # the cap is re-read on every poll
            for p in paths:
                if p not in opened:
                    opened[p] = os.open(p, os.O_CREAT | os.O_RDWR)
        except Exception:
            paths = [p for p in paths if p in opened]
        for p in paths:
            fd = opened[p]
            try:
                push_lock._lock_fd(fd)
            except OSError:
                continue
            try:
                push_lock._write_name(fd, who)
            except Exception:
                pass                     # the name is a convenience; never fail a ship over it
            for q, other in opened.items():
                if q != p:
                    _release_fd(other, lambda _fd: None)
            if said:
                safe_print('  got a %s' % noun)
            return fd
        held = ', '.join(h for h in (push_lock.holder(p) for p in paths) if h) or '?'
        if not said:
            safe_print('  waiting for a %s - at most %d %s run at a time on this machine before '
                       'the push lock (held by: %s)' % (noun, len(paths), plural, held))
            try:
                sys.stdout.flush()
            except Exception:
                pass
            said = True
        if now() >= deadline:
            for fd in opened.values():
                _release_fd(fd, lambda _fd: None)
            raise SystemExit('no %s came free in %d min (held by: %s) - stopping before the push '
                             'lock: nothing was pushed and nothing is held. Ship again later.'
                             % (noun, _slot_wait_max(kind) // 60, held))
        sleep(2.0)


def release_gate_slot(fd):
    if fd is not None:
        _release_fd(fd, push_lock._unlock_fd)


def run_plan(wt, root, plan, stamp, spath, tree, base, phase, explain=None):
    """Work through `plan` - [(gate, reuse reason or None)] in GATES order - on `tree`: print each
    reused gate with the verdict it carries and why it holds, run the rest, and record each pass
    in the stamp as it lands. `phase` is 'pre-lock' or 'locked'; `explain(g)` may return a line
    to print before a gate runs. Returns (ran, kept).

    A gate that FAILS stops the ship with the message it always had, after one line saying which
    phase it failed in (before the lock: no ticket, no lock, nothing pushed). A pass is recorded
    only when the gate exited 0 (never an INCONCLUSIVE - see run_gate) and the worktree still
    holds `tree` after it ran (tree_moved). Before the lock
    each gate run holds a machine-wide gate slot while it runs (hold_gate_slot); under the lock
    none is taken."""
    ran = kept = 0
    for g, why in plan:
        if why:
            rec = stamp['gates'][g.key]
            if phase == 'pre-lock':
                safe_print('  already passed, not re-run: %s - %s (%s)'
                           % (g.label, rec.get('line'), why))
            else:
                safe_print('reused from the %s run: %s - %s (%s)'
                           % (rec.get('phase') or 'pre-lock', g.label, rec.get('line'), why))
            kept += 1
            continue
        note = explain(g) if explain else None
        if note:
            safe_print(note)
        slot = (hold_gate_slot('slow' if g.slow else 'fast', os.path.basename(wt))
                if phase == 'pre-lock' else None)
        t_gate = time.time()
        try:
            line, code = run_gate(wt, root, g)
        except SystemExit as e:
            word = 'was INCONCLUSIVE' if ' was INCONCLUSIVE (' in str(e.code) else 'FAILED'
            if phase == 'pre-lock':
                safe_print('PRE-LOCK: %s %s before the push lock was taken - no ticket, no '
                           'lock, nothing pushed' % (g.label, word))
            else:
                safe_print('LOCKED: %s %s on the final tree - nothing was pushed; the push '
                           'lock goes with this process' % (g.label, word))
            raise
        finally:
            release_gate_slot(slot)
        moved = tree_moved(wt, tree)
        if moved:
            raise SystemExit(moved + ' - so the %s pass is NOT recorded and nothing was pushed. '
                             'Commit or discard the change and ship again.' % g.label)
        if code == 0:
            record_pass(stamp, g, tree, base, line, phase, round(time.time() - t_gate, 1))
            save_stamp(spath, stamp)
        else:
            safe_print('  %s: INCONCLUSIVE never blocks a render gate, but it is no pass either - '
                       'not stamped%s' % (g.label, ', so it runs again on the final tree under '
                                          'the lock' if phase == 'pre-lock' else ''))
        ran += 1
    moved = tree_moved(wt, tree)
    if moved:
        raise SystemExit(moved + ' - nothing was pushed. Commit or discard the change and ship '
                         'again.')
    return ran, kept


def tests_plan(wt):
    """`hook_tests.py plan --json` on the worktree's tree: {need_files, run_files, est_secs}
    - what the pre-push hook would re-run there now and its estimated seconds - or None when the
    worktree has no hook_tests.py or the plan cannot be read (then nothing is decided from it:
    the pre-lock run goes ahead, and nothing is sent back outside the lock)."""
    script = os.path.join(wt, 'tools', 'hook_tests.py')
    if not os.path.isfile(script):
        return None
    try:
        r = subprocess.run([sys.executable, script, 'plan', '--root', wt, '--json'], cwd=wt,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        got = json.loads((r.stdout or '').strip().splitlines()[-1]) if r.returncode == 0 else None
        return got if isinstance(got, dict) and 'run_files' in got else None
    except Exception:
        return None


def prelock_tests(wt):
    """THE PRE-PUSH TEST TIERS, BEFORE THE LOCK (2026-10-08) - the hook's own tiers, run here by
    tools/hook_tests.py on this tree and stamped, so under the lock the hook re-runs only what the
    commits that land meanwhile can reach. Nothing to run (no Python change, or every needed file
    already stamped on a tree nothing since could reach) takes no slot. A heavy run takes the one
    machine-wide test slot, a light one a fast slot (see GATE_SLOTS). A failing test stops the
    ship: no ticket, no lock, nothing pushed. A run that could not happen - no slot came free in
    time, an older tree without hook_tests.py - is no pass and no failure: the hook runs every
    tier under the lock, exactly as before."""
    script = os.path.join(wt, 'tools', 'hook_tests.py')
    if not os.path.isfile(script):
        return
    pl = tests_plan(wt)
    if pl is not None and not pl.get('run_files'):
        safe_print('  PRE-LOCK TESTS: nothing to run (%d needed test file(s), all already passed '
                   'here or on a tree nothing since could reach)' % pl.get('need_files', 0))
        return
    heavy = pl is None or not pl.get('timed') or pl.get('est_secs', 0) > locked_tests_max()
    kind = 'tests' if heavy else 'fast'
    try:
        slot = hold_gate_slot(kind, os.path.basename(wt))
    except SystemExit as e:
        safe_print('  PRE-LOCK TESTS: skipped - %s. The pre-push hook runs every test tier under '
                   'the lock instead, as before.' % str(e.code).split(' - ')[0])
        return
    t0 = time.time()
    try:
        safe_print('  PRE-LOCK TESTS: %s - the pre-push test tiers, before the lock (%s run%s)'
                   % ('running' if pl is None else '%d test file(s), ~%s'
                      % (pl['run_files'], _mmss(pl.get('est_secs', 0))),
                      'heavy' if heavy else 'light', '' if slot is None else ', %s slot' % kind))
        try:
            sys.stdout.flush()
        except Exception:
            pass
        r = subprocess.run([sys.executable, '-u', script, 'prelock', '--root', wt], cwd=wt)
    finally:
        release_gate_slot(slot)
    if r.returncode == 1:
        raise SystemExit('PRE-LOCK TESTS FAILED before the push lock was taken - no ticket, no '
                         'lock, nothing pushed. Fix it and ship again.')
    safe_print('  PRE-LOCK TESTS: done in %s%s' % (_mmss(time.time() - t0), '' if r.returncode == 0
               else ' - NOT run (exit %d), so the hook runs them under the lock' % r.returncode))


def gate_before_lock(wt, root, rnd, spath, key, changed, anchors=None):
    """Step 1, with no ticket and no lock: rebase onto origin/main, realign VERSION, renumber
    this ship's RESEARCH_LEDGER rows, and run every gate that applies - selftests included -
    recording each pass in the stamp. Gates that already passed (this exact tree, or a selftest
    whose cover is unchanged) are not re-run. Returns the stamp, or None when there is nothing
    to ship. Pushes nothing."""
    safe_print('PRE-LOCK (round %d of %d): rebasing onto origin/main and running the gates '
               'BEFORE taking the push lock - other lanes keep pushing meanwhile'
               % (rnd, PRELOCK_ROUNDS))
    run(['git', '-C', wt, 'fetch', '-q', 'origin'])
    if run(['git', '-C', wt, 'rev-list', '--count', 'origin/main..HEAD']) == '0':
        return None
    p = rebase_onto_main(wt, ['git', '-C', wt, 'rebase', 'origin/main'])
    if p is not None:
        raise SystemExit('rebase onto origin/main hit a conflict - resolve by hand in ' + wt +
                         '\n' + (p.stdout or '') + (p.stderr or ''))
    # The same steps the lock phase repeats after its final rebase, so that when main does not
    # move meanwhile the tree gated here IS the tree that ships and nothing re-runs under the lock.
    realign_version(wt)
    renumber_ledger_rows(wt)
    tree = run(['git', '-C', wt, 'rev-parse', 'HEAD^{tree}'])
    base = run(['git', '-C', wt, 'rev-parse', 'origin/main'])
    stamp = load_stamp(spath, key)
    t0 = time.time()
    plan = [(g, reuse_reason(g, stamp, tree, changed, anchors))
            for g in applicable_gates(wt, root)]
    ran, kept = run_plan(wt, root, plan, stamp, spath, tree, base, 'pre-lock')
    stamp['tree'], stamp['base'] = tree, base
    save_stamp(spath, stamp)
    # After the gates (minutes), the test tiers (up to 40 minutes) on the same tree. The tree
    # may not move while they run: hook_tests only stamps a pass when the worktree still holds
    # the tree it ran on, and tree_moved below stops the ship if it did not.
    prelock_tests(wt)
    moved = tree_moved(wt, tree)
    if moved:
        raise SystemExit(moved + ' - nothing was pushed. Commit or discard the change and ship '
                         'again.')
    safe_print('PRE-LOCK: %d gate(s) run, %d already passed, on tree %s against origin/main %s '
               '(%s) - now queueing for the push lock'
               % (ran, kept, tree[:8], base[:8], _mmss(time.time() - t0)))
    return stamp


def _release_fd(fd, unlock):
    """Unlock and close one held handle; never raises. msvcrt locks and unlocks the byte at the
    CURRENT file position, and both holders write their name after locking byte 0 - so seek back
    to 0 first, or the unlock misses its byte and only the close (whenever Windows gets to it)
    lets go."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
    except Exception:
        pass
    try:
        unlock(fd)
    except Exception:
        pass
    try:
        os.close(fd)
    except Exception:
        pass


def _let_go(ticket, lock_fd):
    """Hand the push lock and the queue ticket back BEFORE this ship has pushed anything, so the
    next lane goes while this one re-runs a selftest outside the lock. This is the ONLY place
    ship gives either back by hand; every other route (each SystemExit, a kill, the end of the
    run) still leaves it to the process exit - see push_lock.hold."""
    if lock_fd is not None:
        _release_fd(lock_fd, push_lock._unlock_fd)
    n, tfd = ticket if ticket else (None, None)
    if tfd is not None:
        _release_fd(tfd, push_queue._unlock_fd)
        if n is not None:
            try:
                os.remove(os.path.join(push_queue.queue_dir(),
                                       '%d-%d.ticket' % (n, os.getpid())))
            except Exception:
                pass                     # a dead ticket is swept by the next lane that looks
    return (None, None), None


def cmd_ship(name, message):
    root = repo_root()
    wt = os.getcwd() if name is None else os.path.join(wt_root(), name)
    if not os.path.isdir(wt):
        raise SystemExit('no such worktree: ' + wt)
    inside = run(['git', '-C', wt, 'rev-parse', '--show-toplevel'])
    if os.path.abspath(inside) == os.path.abspath(root):
        raise SystemExit('refusing to ship from the SHARED checkout - run this from a worktree '
                         '(python tools/wt.py new <name>)')

    # One ship of this worktree at a time - see hold_worktree. Taken before anything here touches
    # the worktree (the commit below included); the process exit releases it. Its handle is a raw
    # os.open() descriptor, which nothing closes until this process ends.
    hold_worktree(wt)

    if run(['git', '-C', wt, 'status', '--porcelain']):
        if not message:
            raise SystemExit('uncommitted changes here - commit them, or pass --msg to commit now')
        run(['git', '-C', wt, 'add', '-A'])
        run(['git', '-C', wt, 'commit', '-q', '-m', message])

    who = os.path.basename(wt)
    spath, key, changed = stamp_path(wt), gates_key(), tree_changes(wt)
    anchors = anchor_check(wt)
    t_start = time.time()
    for rnd in range(1, PRELOCK_ROUNDS + 1):
        stamp = gate_before_lock(wt, root, rnd, spath, key, changed, anchors)
        if stamp is None:
            print('nothing to ship - HEAD has no commits beyond origin/main')
            return

        # ONE LANE AT A TIME FROM HERE TO THE PUSH (2026-10-02). The engine tier runs for any
        # change under augur_engine/, api/ or tests/ and takes ~23 minutes; with ten sessions
        # shipping, main moves inside that window and the push is rejected on a stale ref. This
        # session ran three 23m38s gates in a row and was overtaken every time - nothing was
        # wrong with any of them. The lock is held across the final rebase, the gates that must
        # see the final tree and the push, so the lane that gates is the lane that lands. (Since
        # 2026-10-07 the slow selftests run before it - see the module docstring.)
        #
        # It is released by hand in ONE place only - _let_go below, before anything is pushed,
        # to re-run a selftest outside it. Otherwise it is an OS lock on an open handle, so the
        # kernel drops it when this process ends, by any route - every `raise SystemExit` below
        # included. That is the whole reason it is an OS lock and not a lock file with a
        # timestamp in it.
        # FIRST COME, FIRST SERVED (2026-10-05). The lock alone is not fair - a waiter takes it
        # whenever it finds it free, so arrival order meant nothing and the rocfrontier lane once
        # waited 80+ minutes while later arrivals went ahead. The ticket establishes WHOSE TURN it
        # is; the lock below still establishes who HOLDS it. Two separate things on purpose, so a
        # failure in the queue can never let two lanes gate at once - it only makes them unfair
        # again, which is where we started.
        _queue_ticket = (push_queue.hold_turn(who=who) if push_queue else (None, None))
        _lock_handle = push_lock.hold(who=who) if push_lock else None
        t_lock = time.time()

        run(['git', '-C', wt, 'fetch', '-q', 'origin'])
        ahead = run(['git', '-C', wt, 'rev-list', '--count', 'origin/main..HEAD'])
        if ahead == '0':
            print('nothing to ship - HEAD has no commits beyond origin/main')
            return
        if run(['git', '-C', wt, 'status', '--porcelain', '--untracked-files=no'],
               check=False, quiet=True):
            raise SystemExit('a tracked file in ' + wt + ' changed while this ship queued - '
                             'commit or discard it and ship again (nothing was pushed)')
        p = rebase_onto_main(wt, ['git', '-C', wt, 'rebase', 'origin/main'])
        if p is not None:
            raise SystemExit('rebase onto origin/main hit a conflict - resolve by hand in ' + wt +
                             '\n' + (p.stdout or '') + (p.stderr or ''))
        # Against the NEWEST main, under the lock, after the rebase whose result is pushed: the
        # VERSION line steps past main's and this ship's CHANGELOG entry follows it, and this
        # ship's new RESEARCH_LEDGER rows move past any number another lane took meanwhile
        # (MANAGER #69). Both are no-ops when main has not moved since the pre-lock run.
        realign_version(wt)
        renumber_ledger_rows(wt)

        tree = run(['git', '-C', wt, 'rev-parse', 'HEAD^{tree}'])
        base_now = run(['git', '-C', wt, 'rev-parse', 'origin/main'])
        base_then = stamp.get('base') or ''
        if base_then == base_now:
            safe_print('LOCKED: origin/main has not moved since the pre-lock run (%s)'
                       % base_now[:8])
        else:
            moved = run(['git', '-C', wt, 'rev-list', '--count', base_then + '..' + base_now],
                        check=False, quiet=True) or '?'
            safe_print('LOCKED: origin/main moved %s commit(s) since the pre-lock run (%s -> %s); '
                       'rebased onto it, tree %s' % (moved, base_then[:8], base_now[:8], tree[:8]))
        plan = [(g, reuse_reason(g, stamp, tree, changed, anchors))
                for g in applicable_gates(wt, root)]
        stale = [g for g, why in plan if g.slow and not why]
        too_slow = [g for g in stale if too_slow_for_the_lock(g, stamp)]
        # The pre-push test tiers the hook would re-run on this final tree (2026-10-08): only what
        # the commits that landed since the pre-lock run can reach. Too long to hold the lock
        # for, it goes back outside it like a stale slow selftest.
        tp = tests_plan(wt)
        tests_long = tp is not None and tp.get('est_secs', 0) > locked_tests_max()
        if (too_slow or tests_long) and rnd < PRELOCK_ROUNDS:
            for g in too_slow:
                safe_print('LOCK RELEASED: %s must re-run - %s. Nothing was pushed; re-running it '
                           'outside the lock, then queueing again (round %d of %d next).'
                           % (g.label, rerun_reason(g, stamp, tree, changed, anchors), rnd + 1,
                              PRELOCK_ROUNDS))
            if tests_long:
                safe_print('LOCK RELEASED: the pre-push tests would re-run %d test file(s) under the '
                           'lock (~%s, over %s) - what landed meanwhile reaches them. Nothing was '
                           'pushed; running them outside the lock, then queueing again (round %d '
                           'of %d next).' % (tp['run_files'], _mmss(tp['est_secs']),
                                             _mmss(locked_tests_max()), rnd + 1, PRELOCK_ROUNDS))
            _queue_ticket, _lock_handle = _let_go(_queue_ticket, _lock_handle)
            continue
        if tests_long:
            safe_print('LOCKED: the pre-push tests re-run %d test file(s) (~%s) under the lock - all '
                       '%d pre-lock rounds are used (rare)' % (tp['run_files'],
                                                               _mmss(tp['est_secs']),
                                                               PRELOCK_ROUNDS))
        break

    def explain(g, after_push=False):
        if not g.slow:
            return None
        why = rerun_reason(g, stamp, tree, changed, anchors)
        if after_push:
            return ('%s must re-run - %s - after the refused push, so it runs UNDER the push lock '
                    '(rare: only a push from outside this machine gets here)' % (g.label, why))
        if too_slow_for_the_lock(g, stamp):
            return ('%s must re-run - %s - and all %d pre-lock rounds are used, so it runs UNDER '
                    'the push lock (rare)' % (g.label, why, PRELOCK_ROUNDS))
        return ('%s must re-run - %s - and it took %ss last time, so it re-runs under the lock '
                '(cheaper than giving the lock back and queueing again)'
                % (g.label, why, stamp['gates'][g.key].get('secs')))

    ran, kept = run_plan(wt, root, plan, stamp, spath, tree, base_now, 'locked', explain)
    stamp['tree'], stamp['base'] = tree, base_now
    save_stamp(spath, stamp)
    safe_print('LOCKED: %d gate(s) run under the lock, %d reused from the pre-lock run'
               % (ran, kept))

    # The tree the gates above just passed on. If the push is rejected and we rebase, this is
    # what lets the retry's gate narrow to the tests the INCOMING commits could break instead of
    # re-running all 23 minutes. Read before the push, because the rebase below changes it.
    passed_tree = run(['git', '-C', wt, 'rev-parse', 'HEAD^{tree}'], check=False,
                      quiet=True).strip()

    pushed = subprocess.run(['git', '-C', wt, 'push', '-q', 'origin', 'HEAD:main'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    # A push can fail for TWO quite different reasons, and they must not be confused: the remote
    # REJECTED it (main moved), or our own pre-push hook REFUSED it (a gate failed). Only the
    # first is worth retrying. Treating every failure as a rejection cost 43 minutes the first
    # time this code ran for real: the gate failed, the retry re-ran the whole 23-minute tier on
    # code that was still broken, and the tree it claimed as "already passed" had never passed.
    out = (pushed.stdout or '') + (pushed.stderr or '')
    REJECTED = ('[remote rejected]', 'cannot lock ref', 'fetch first', 'non-fast-forward',
                'Updates were rejected')
    overtaken = pushed.returncode != 0 and any(m in out for m in REJECTED)
    if pushed.returncode != 0 and not overtaken:
        raise SystemExit('push failed, and not because main moved - so it was the gate. Nothing '
                         'was pushed and nothing is retried; fix it and ship again.' + chr(10) +
                         out.strip()[-2000:])
    if overtaken:
        # OVERTAKEN. We still hold the push lock, so no local lane did this: it was a cloud
        # session pushing straight to main from another machine, where the lock cannot reach.
        # Rebase and go again without letting go of the lock, and tell the hook which tree it has
        # already proved - which is sound only because the gate above really did pass.
        safe_print('push rejected - main moved while the gate ran (a cloud session pushes '
                   'straight to main, where the machine lock cannot reach it). Rebasing and '
                   'retrying under the same lock hold.')
        run(['git', '-C', wt, 'fetch', '-q', 'origin'], check=False, quiet=True)
        rb = rebase_onto_main(wt, ['git', '-C', wt, 'rebase', 'origin/main'])
        if rb is not None:
            raise SystemExit('push was rejected and the rebase onto the newer main hit a '
                             'conflict - resolve it by hand in ' + wt + chr(10) + out +
                             (rb.stdout or '') + (rb.stderr or ''))
        # That rebase made a NEW final tree, so it gets everything the first one got (2026-10-07;
        # before, the retry pushed it with no VERSION realign and no ship gate at all): the
        # realign and the ledger renumbering against the main that overtook us, then every gate
        # that tree needs - the fast ones on it, a selftest only if what it reads moved - all
        # under the same lock hold. Nothing reaches main that the ship gates did not pass.
        realign_version(wt)
        renumber_ledger_rows(wt)
        tree = run(['git', '-C', wt, 'rev-parse', 'HEAD^{tree}'])
        base_now = run(['git', '-C', wt, 'rev-parse', 'origin/main'])
        safe_print('LOCKED (retry): rebased onto origin/main %s, tree %s - gating it before the '
                   'second push' % (base_now[:8], tree[:8]))
        plan = [(g, reuse_reason(g, stamp, tree, changed, anchors))
                for g in applicable_gates(wt, root)]
        ran, kept = run_plan(wt, root, plan, stamp, spath, tree, base_now, 'locked',
                             lambda g: explain(g, after_push=True))
        stamp['tree'], stamp['base'] = tree, base_now
        save_stamp(spath, stamp)
        safe_print('LOCKED (retry): %d gate(s) run under the lock, %d reused' % (ran, kept))
        env = dict(os.environ, EDGELOG_GATE_PASSED_TREE=passed_tree)
        again = subprocess.run(['git', '-C', wt, 'push', 'origin', 'HEAD:main'], env=env,
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
        safe_print(((again.stdout or '') + (again.stderr or '')).strip()[-800:])
        if again.returncode != 0:
            raise SystemExit('still rejected after rebasing and re-gating. Re-run ship.')

    # PROVE IT. `git push` reporting success is not evidence that the sha is on main: piped
    # into another command it hands back the PIPE's exit code, so a rejection reads as clean
    # (this session did exactly that today, and NOISE reported 9be7e32e as landed when it
    # never was). The only answer that counts comes from a fresh fetch.
    sha = run(['git', '-C', wt, 'rev-parse', 'HEAD'], check=False, quiet=True).strip()
    run(['git', '-C', wt, 'fetch', '-q', 'origin'], check=False, quiet=True)
    on_main = subprocess.run(['git', '-C', wt, 'merge-base', '--is-ancestor', sha,
                              'origin/main'], capture_output=True)
    if on_main.returncode != 0:
        now_at = run(['git', '-C', wt, 'rev-parse', '--short', 'origin/main'],
                     check=False, quiet=True).strip()
        # Nothing of OURS landed, but another lane's work may have, so still bring the shared
        # checkout up to date before stopping - leaving it behind is the 2026-09-14 bug the
        # comment below warns about, and it does not care whose commit was the reason.
        sync_shared(root)
        raise SystemExit('the push reported success but %s is NOT on origin/main (now at '
                         '%s). Do NOT report this as landed. Re-run ship: it rebases onto '
                         'the newer main and tries again.' % (sha[:8], now_at))

    # The push has LANDED, and we have checked. Nothing from here on may stop the steps after
    # it: a print that raised on this line once skipped sync_shared and left the runner's
    # checkout behind (2026-09-14, see utf8_console). Hence check=False and safe_print.
    head = run(['git', '-C', wt, 'log', '--oneline', '-1'], check=False, quiet=True)
    safe_print('pushed (verified on main): ' + head)
    safe_print('lock phase took %s; %s before it went on the pre-lock gates and the queue'
               % (_mmss(time.time() - t_lock), _mmss(t_lock - t_start)))
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
            safe_print('  \u26a0 %d pushes to main in the last hour. GitHub Pages builds a '
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
      * skipped entirely if the shared checkout carries commits of its own; that is
        somebody's work, so this prints how to look at it instead.
      * dirty tracked/untracked files that BLOCK the merge get ONE pass of
        `_clear_ff_blockers` (below) before we retry - it only clears a blocker when the
        working copy is byte-identical to origin/main modulo line endings, and backs up
        + names anything that differs instead of touching it.
      * never fatal. A push that succeeded must not report failure because the shared
        checkout could not be tidied afterwards.
    """
    try:
        if run(['git', '-C', root, 'rev-parse', '--abbrev-ref', 'HEAD'], check=False) != 'main':
            print('shared checkout: not on main - left alone')
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

        _clear_ff_blockers(root)
        pr = subprocess.run(['git', '-C', root, 'merge', '--ff-only', 'origin/main'],
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace')
        if pr.returncode == 0:
            # safe_print: this line carries a commit subject too. A plain print that raised
            # here would land in the except below and report a fast-forward that DID happen
            # as "could not fast-forward".
            safe_print('shared checkout: fast-forwarded %s commit(s) -> %s'
                       % (behind, run(['git', '-C', root, 'log', '--oneline', '-1'],
                                      check=False, quiet=True)))
            return

        out = (pr.stdout or '') + (pr.stderr or '')
        untracked, modified = _parse_ff_blockers(out)
        blockers = sorted(set(untracked) | set(modified))
        if not blockers:
            last = out.strip().splitlines()[-1] if out.strip() else 'unknown reason'
            print('shared checkout: still %s commit(s) behind, NOT fast-forwarded (%s). '
                  'Review with: git -C "%s" status' % (behind, last, root))
            return
        print('shared checkout: still %s commit(s) behind, NOT fast-forwarded - %d real '
              'blocker(s) left in place (see backups above): %s'
              % (behind, len(blockers), ', '.join(blockers)))
    except Exception as e:                                    # never fail a good push
        print('shared checkout: could not fast-forward (%s: %s) - the push itself was fine'
              % (type(e).__name__, e))


def _is_protected(rel):
    posix = rel.replace('\\', '/')
    if posix.rsplit('/', 1)[-1] in _PROTECTED_BASENAMES:
        return True
    return any(posix.startswith(p) for p in _PROTECTED_PREFIXES)


def _parse_ff_blockers(text):
    """Parse the two shapes git prints when `merge --ff-only` refuses because local
    content is in the way. Returns (untracked_paths, modified_paths) - repo-relative
    paths, in the order git listed them. Git prints these BEFORE touching anything and
    aborts cleanly, so capturing a real (non-dry-run) merge attempt's output is safe.

        error: The following untracked working tree files would be overwritten by merge:
                path/one
        Please move or remove them before you merge.

        error: Your local changes to the following files would be overwritten by merge:
                path/two
        Please commit your changes or stash them before you merge.
    """
    untracked, modified = [], []
    mode = None
    for line in (text or '').splitlines():
        if 'untracked working tree files would be overwritten' in line:
            mode = 'untracked'
            continue
        if 'local changes to the following files would be overwritten' in line:
            mode = 'modified'
            continue
        if mode:
            t = line.strip()
            if not t:
                continue
            if t.startswith(('Please ', 'Aborting', 'error:', 'fatal:', 'Updating')):
                if t.startswith(('Please ', 'Aborting')):
                    mode = None
                continue
            (untracked if mode == 'untracked' else modified).append(t)
    return untracked, modified


def _diff_stat(root, rel, full):
    """Best-effort one-line `diff --stat` between origin/main's copy of `rel` and the
    local working copy at `full`, for the loud REAL-unshipped-work report. Never raises -
    a missing stat is not worth failing a push over."""
    tmp_dir = None
    try:
        incoming = run(['git', '-C', root, 'show', 'origin/main:' + rel], check=False, quiet=True)
        tmp_dir = tempfile.mkdtemp(prefix='wt_ff_')
        tmp_path = os.path.join(tmp_dir, os.path.basename(rel) or 'incoming')
        with io.open(tmp_path, 'w', encoding='utf-8', newline='') as f:
            f.write(incoming)
        pr = subprocess.run(['git', 'diff', '--no-index', '--stat', tmp_path, full],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
        lines = [l for l in (pr.stdout or '').strip().splitlines() if l.strip()]
        return lines[-1].strip() if lines else 'diff stat unavailable'
    except Exception:
        return 'diff stat unavailable'
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _backup_file(full, rel, ts_dir):
    dest = os.path.join(ts_dir, rel.replace('/', os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(full, dest)
    return dest


def _clear_ff_blockers(root):
    """Clear ONLY the `merge --ff-only` blockers that are provably lossless - byte-
    identical to origin/main once line endings are normalised - and back up + loudly
    name anything that genuinely differs, without touching it.

    WHY THIS EXISTS (owner, 2026-09-07: blocked the shared checkout TWICE in 24 hours -
    25 commits behind on 2026-09-05, 4 behind on 2026-09-06). Sessions write strategy/tool
    files DIRECTLY into the shared checkout AND ship the same files through a worktree, so
    the checkout ends up holding an untracked or modified copy of a file origin/main also
    carries; `merge --ff-only` refuses outright and the runner keeps executing a stale
    tree. In EVERY case measured so far the blocking copy was byte-identical to
    origin/main once CRLF/LF is normalised. This replaces the old `_clear_lossless_modified`
    (tracked-only) and `_clear_identical_untracked` (untracked-only, dry-run merge) with one
    path that handles both refusal shapes plus staged-added files, backs up anything real
    instead of silently discarding it, and never touches protected files
    (optimizer_history.db, trial_cache.db, serviceAccount.json, augur_uploads/*).

    Runs ONE real `merge --ff-only origin/main` (git aborts cleanly on either refusal
    shape without changing anything, so this is safe as the discovery step), parses both
    refusal shapes, and also folds in any `git status --porcelain` path that the incoming
    commits touch (covers staged changes, which do not always echo into the refusal text
    the same way). The caller is responsible for retrying the merge afterwards.
    """
    norm = lambda t: (t or '').replace('\r\n', '\n').strip()

    def porcelain():
        out = run(['git', '-C', root, 'status', '--porcelain'], check=False, quiet=True)
        m = {}
        for line in (out or '').splitlines():
            if len(line) < 4:
                continue
            code, rel = line[:2], line[3:].strip().strip('"')
            if '->' in rel:                  # a rename is never auto-cleared
                rel = rel.split('->', 1)[1].strip().strip('"')
            m[rel] = code
        return m

    try:
        pr = subprocess.run(['git', '-C', root, 'merge', '--ff-only', 'origin/main'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    except Exception:
        return False
    if pr.returncode == 0:
        return False                         # already fast-forwarded, nothing to clear

    out = (pr.stdout or '') + (pr.stderr or '')
    untracked, modified = _parse_ff_blockers(out)

    codes = porcelain()
    incoming_touched = set(run(['git', '-C', root, 'diff', '--name-only', 'HEAD', 'origin/main'],
                               check=False, quiet=True).splitlines())
    for rel, code in codes.items():
        if rel in untracked or rel in modified or rel not in incoming_touched:
            continue
        (untracked if code == '??' else modified).append(rel)

    seen, paths = set(), []
    for rel in untracked + modified:
        if rel and rel not in seen:
            seen.add(rel)
            paths.append(rel)
    if not paths:
        return False

    ts_dir = None
    cleared, kept = [], []
    for rel in paths:
        if _is_protected(rel):
            kept.append(rel)
            print('shared checkout: %s is protected - never auto-cleared, left alone' % rel)
            continue
        full = os.path.join(root, rel.replace('/', os.sep))
        try:
            with io.open(full, encoding='utf-8', errors='replace') as fh:
                local = fh.read()
        except OSError:
            kept.append(rel)
            continue
        incoming = run(['git', '-C', root, 'show', 'origin/main:' + rel], check=False, quiet=True)
        if norm(local) != norm(incoming):
            if ts_dir is None:
                ts_dir = os.path.join(BACKUP_ROOT, time.strftime('%Y%m%d_%H%M%S'))
            dest = _backup_file(full, rel, ts_dir)
            stat = _diff_stat(root, rel, full)
            print('REAL unshipped work - left in place, backed up to %s (%s)' % (dest, stat))
            kept.append(rel)
            continue
        code = codes.get(rel, '')
        if code[:1] == 'A':
            # staged-added file identical to origin/main: unstage first, then it is just
            # an untracked duplicate of what the merge is about to write.
            run(['git', '-C', root, 'restore', '--staged', '--', rel], check=False, quiet=True)
            os.remove(full)
        elif code == '??' or (not code and rel in untracked):
            os.remove(full)
        else:
            # CHECK OUT FROM origin/main, NOT from the index/HEAD: a stray CR baked into
            # the tracked blob would otherwise re-dirty the file every time (2026-08-28).
            run(['git', '-C', root, 'checkout', 'origin/main', '--', rel], check=False, quiet=True)
        cleared.append(rel)
        print('cleared: %s (identical to origin/main modulo line endings)' % rel)

    if cleared:
        print('shared checkout: cleared %d blocker(s) with no unshipped work (%s)'
              % (len(cleared), ', '.join(cleared[:4]) + (', ...' if len(cleared) > 4 else '')))
    if kept:
        print('shared checkout: %d blocker(s) left in place - real content differences: %s'
              % (len(kept), ', '.join(kept)))
    return bool(cleared)


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
    utf8_console()
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
