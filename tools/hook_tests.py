r"""THE PRE-PUSH TEST TIERS - RUN BEFORE THE PUSH LOCK, RE-CHECKED UNDER IT (2026-10-08)

WHY. Every ship holds the machine-wide push lock (tools/push_lock.py) from its rebase to its push,
and the pre-push hook runs inside that hold. For any change under augur_engine/, api/,
augur_mp_worker.py or tests/ the hook ran the ENGINE tier - the whole suite bar two files - which
measured 20-40 minutes on 2026-10-08 with lanes testing beside it (the holder at 12:26 was still
in it past 12:47). With ~25 ships queued that tier alone was most of a 7-13 hour queue, while the
other 24 lanes sat idle. Two things made it worse than it had to be:
  * a ship that only ADDS a test file (tests/test_my_tool.py beside tools/my_tool.py) matches
    `tests/` and pays the full engine tier, so a research tool with a test pays like an engine
    change - 35 of the 337 commits on main from 10-01 to 10-08 did exactly that;
  * tools/affected_tests.py, which can say which tests a change could break, was only consulted
    on the rare retry after a cloud session overtook a push - never on the first push.

WHAT THIS DOES. The same tiers the hook always ran (tiers(), byte-for-byte the shell rules it
replaces) are run in two places:
  1. PRE-LOCK, by `wt.py ship` (`hook_tests.py prelock`, from its pre-lock phase, after the
     rebase, the VERSION realign and the gates), on the tree it will push if main does not move -
     before the ship takes its queue ticket or the push lock, so other lanes keep landing
     meanwhile. wt.py holds one of ITS machine-wide gate slots around the run (GATE_SLOTS: the one
     'tests' slot for a heavy run, a 'fast' one for a light one - one cap design for every
     pre-lock job), so queued lanes cannot pile full suites onto the PC that runs the trading
     runner. A failing test stops the ship there: nothing queued, nothing held, nothing pushed.
  2. UNDER THE LOCK, by the pre-push hook (`hook_tests.py hook`), on the FINAL tree - which
     differs from the pre-lock one by whatever other lanes landed while this one queued, plus the
     VERSION realign. Only the tests that difference could reach are re-run.

THE STAMP. A pytest run that exits 0 on a clean worktree records, per test FILE, "passed on tree
T at time t" in <git dir>/edgelog_test_stamps.json (beside the worktree's git metadata, so it never
dirties the tree and dies with the worktree). It is written only by this module, only after its
own pytest run, only when the worktree held exactly tree T before and after that run (no tracked
file edited, HEAD not moved), and with a fingerprint of the interpreter, pytest and every
installed package (a stamp from another environment is ignored). A pass is never carried
forward: the stamp lists only files that really ran on that tree, so every skip below rests on one
real run plus one diff, never a chain of them.

THE RULE (the invariant). On the tree being pushed, a test file the tiers need is skipped only
when a stamp shows it really passed on some tree T within STAMP_MAX_AGE, and
tools/affected_tests.py, asked about `git diff --no-renames T <this tree>` - computed here, never
taken from anyone's word - says the difference cannot reach it. Everything else in the tiers runs
on this tree, and the SMOKE files always do. So nothing reaches main unless the final tree passed
every needed test whose inputs changed since that test last passed.

UNDER THE LOCK, ship first asks `plan --json` what the hook would re-run on the final tree and
how long that takes (each file at its last measured time, kept in the stamp); over 3 minutes it
gives the lock back and runs them before the lock, in another round (wt.py, at most 3 rounds).

IT FAILS SAFE, to exactly what the hook ran before: any doubt - a dirty worktree, a pushed commit
whose tree is not the one on disk, a stamp from another environment or older than STAMP_MAX_AGE,
a tree git no longer has, a difference the selector cannot narrow (a conftest.py, pytest.ini or
requirements change, a deleted or renamed module), a change to the deciding code itself (SELF),
any exception while planning - and the tier runs in full with the command the shell hook used.
When wt.py cannot run the pre-lock tests (no slot came free in time, a tree without this file),
the hook runs the tiers in full under the lock, as before - which is also exactly what a ship
started by an OLDER wt.py (no pre-lock tests, no stamps) gets from this hook: every needed tier,
the old command, nothing skipped. Exit codes: 0 passed (or nothing to run), 1 a test failed,
2 not run (prelock only).

WHAT IT SAVES, MEASURED 2026-10-08 (per-file times from a full run, 33.5 min with the contract
tier, on this PC with lanes testing beside it). Under the lock an engine ship now re-runs only
what the ships that landed while it queued can reach: an index.html-only landing ~3 min, a few
research ships ~6 min, but an api/ or augur_engine/ landing reaches most of the suite (twodefects'
api/market_calendar.py: 155 of 246 files, ~19 min) and a conftest.py landing all of it. Those
are what `plan --json` is for: it prints the files to re-run and their estimated seconds (each
file's last measured time, kept in the stamp), and wt.py ship gives the lock back and runs them
before the lock instead, as it does for a stale slow selftest.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import affected_tests as at  # noqa: E402

STAMP_FILE = 'edgelog_test_stamps.json'
STAMP_FORMAT = 1
# A pass older than this is not reused. Long enough for a ship that ran its tests and then queued
# behind a long line; short enough that a test reading the date, the live caches or the network
# (several here do) is re-run at least twice a day.
STAMP_MAX_AGE = 12 * 3600
STAMP_KEEP = 8                       # trees kept per worktree; older ones are dropped

CONTRACT = 'tests/test_strategy_contract.py'
SURROGATE = 'tests/test_surrogate.py'
ENGINE_RE = re.compile(r'^(augur_engine/|api/|augur_mp_worker\.py|tests/)')
TOOL_RE = re.compile(r'^tools/[A-Za-z0-9_]+\.py$')
# A test file whose name does not match the tool it covers (the hook's tools-tier companions).
TOOL_COMPANIONS = {'wt': ('tests/test_wt_ship_console.py', 'tests/test_push_lock.py')}

# The code that decides what may be skipped. A stamp whose tree differs from this one in any of
# these is not used: the decision would be made by code its own tests have not yet passed on.
SELF = ('tools/hook_tests.py', 'tools/affected_tests.py', 'tools/githooks/pre-push')

# Always re-run on the final tree when their tier is due, whatever the stamps say: the tests that
# LIST repo directories (every new file there is their input, named or not) - a cheap second net
# under the selector's directory rule, never the main one. ~9 s together (2026-10-08 timings:
# 0.9 + 1.4 + 6.1 + 0.4). The selector's own tests are NOT here (94 s + ~2 min): they run when
# their inputs change like any other test, and a change to the selector itself (SELF) voids
# every stamp anyway.
SMOKE = (
    'tests/test_family_vocabulary.py',
    'tests/test_master_write_guard.py',
    'tests/test_thread_wait_pattern.py',
    'tests/test_deploy_cloud_templates.py',
)


def parse_cache_path():
    """tools/affected_tests.py's per-blob parse cache: machine-local, never in a worktree."""
    return os.path.join(os.environ.get('EDGELOG_HOME') or r'C:\EdgeLog', 'state',
                        'affected_tests_cache.json')



# ================================================================================ git helpers
def _git(root, *args):
    p = subprocess.run(['git', '-C', root] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return p.returncode, (p.stdout or '').strip()


def head_tree(root):
    rc, out = _git(root, 'rev-parse', 'HEAD^{tree}')
    return out if rc == 0 and re.match(r'^[0-9a-f]{40}$', out or '') else None


def worktree_clean(root):
    """No tracked file differs from HEAD (untracked files are not what is pushed)."""
    rc, out = _git(root, 'status', '--porcelain', '--untracked-files=no')
    return rc == 0 and out == ''


def tree_exists(root, tree):
    return (bool(re.match(r'^[0-9a-f]{40}$', tree or '')) and
            _git(root, 'cat-file', '-e', tree + '^{tree}')[0] == 0)


def tree_diff(root, a, b):
    """Paths that differ between trees a and b, BOTH sides of a rename listed (--no-renames:
    with rename detection a moved module shows only its new name, and the importers of the old
    one would never be asked about). None when git cannot say."""
    if a == b:
        return []
    rc, out = _git(root, 'diff', '--no-renames', '--name-only', a, b)
    return [p for p in out.splitlines() if p.strip()] if rc == 0 else None


def changed_files(root):
    """What this push changes, exactly as the shell hook computed it - the working tree against
    its merge-base with origin/main - except that renames list both names. None when git cannot
    say (then the heavy tiers run - see tiers)."""
    rc, base = _git(root, 'merge-base', 'HEAD', 'origin/main')
    if rc != 0 or not base:
        base = 'origin/main'
    rc, out = _git(root, 'diff', '--no-renames', '--name-only', base, '--')
    if rc != 0:
        return None
    return [p.strip() for p in out.splitlines() if p.strip()]


def all_test_files(root):
    """Every tracked tests/**/test_*.py - what `pytest tests` collects, as tracked by git."""
    rc, out = _git(root, 'ls-files', 'tests')
    if rc != 0:
        return []
    return sorted(p for p in out.splitlines()
                  if p.endswith('.py') and os.path.basename(p).startswith('test_'))


# ===================================================================================== the tiers
class Tier(object):
    """One pytest run the hook makes. `files` is the set of test files it covers (for the stamp
    and for narrowing); `full_args` is the exact command the shell hook ran for it."""

    def __init__(self, key, label, files, full_args):
        self.key, self.label = key, label
        self.files = frozenset(files)
        self.full_args = list(full_args)

    def __repr__(self):
        return 'Tier(%r, %d files)' % (self.key, len(self.files))


def tiers(root, changed, log=print):
    """The tiers this push needs - the shell hook's rules (2026-08-27 / 10-02), unchanged:

      contract   any *.py changed                          tests/test_strategy_contract.py
      engine     augur_engine/, api/, augur_mp_worker.py   tests/ bar contract + surrogate
                 or tests/ changed
      surrogate  augur_engine/surrogate.py changed         tests/test_surrogate.py
      tools      tools/<name>.py changed, engine not due   tests/test_<name>.py (+ companions)

    `changed` None (git could not say) runs contract + engine: the doubt goes the safe way."""
    exists = lambda rel: os.path.isfile(os.path.join(root, rel))
    if changed is None:
        log('could not list what this push changes - running the contract and engine tiers')
        changed = ['tests/', 'x.py']
    out = []
    if not any(p.endswith('.py') for p in changed):
        return out
    out.append(Tier('contract', 'Strategy-contract', [CONTRACT], [CONTRACT]))
    engine = any(ENGINE_RE.match(p) for p in changed)
    if engine:
        files = [t for t in all_test_files(root) if t not in (CONTRACT, SURROGATE)]
        out.append(Tier('engine', 'Engine', files,
                        ['tests', '--ignore=' + CONTRACT, '--ignore=' + SURROGATE]))
    if 'augur_engine/surrogate.py' in changed:
        out.append(Tier('surrogate', 'Surrogate', [SURROGATE], [SURROGATE]))
    tool = set()
    for p in changed:
        if TOOL_RE.match(p):
            base = p[len('tools/'):-len('.py')]
            if exists('tests/test_%s.py' % base):
                tool.add('tests/test_%s.py' % base)
            for c in TOOL_COMPANIONS.get(base, ()):
                if exists(c):
                    tool.add(c)
    if tool:
        if engine:
            log('tools/ changed, but the engine tier covers it.')
        else:
            out.append(Tier('tools', 'Tools', sorted(tool), sorted(tool)))
    return out


# ===================================================================================== the stamp
def env_fingerprint():
    """The interpreter, pytest and every installed package. A pass recorded under a different one
    says nothing about this one."""
    try:
        import importlib.metadata as md
        dists = sorted('%s==%s' % ((d.metadata.get('Name') or '?').lower(), d.version)
                       for d in md.distributions())
    except Exception:
        dists = ['?']
    try:
        import pytest
        pv = pytest.__version__
    except Exception:
        pv = '?'
    # The install (prefix), not the launcher path: ship runs `python -u tools/wt.py` and the hook
    # runs `python`, but a lane that launches with `py` or the full python3.13.exe path is still
    # the same interpreter and the same packages.
    blob = '\n'.join([sys.version, os.path.normcase(sys.prefix or '?'),
                      os.path.normcase(getattr(sys, 'base_prefix', '') or '?'), pv] + dists)
    return hashlib.sha1(blob.encode('utf-8', 'replace')).hexdigest()[:16]


def stamp_path(root):
    rc, gd = _git(root, 'rev-parse', '--absolute-git-dir')
    return os.path.join(gd, STAMP_FILE) if rc == 0 and gd else None


def load_stamps(path):
    """[{tree, env, passed: {file: epoch}}], newest first. Anything unreadable is no stamp."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, dict) or data.get('format') != STAMP_FORMAT:
        return []
    out = []
    for e in data.get('stamps') or []:
        if (isinstance(e, dict) and isinstance(e.get('tree'), str)
                and isinstance(e.get('env'), str) and isinstance(e.get('passed'), dict)):
            passed = dict((k, float(v)) for k, v in e['passed'].items()
                          if isinstance(k, str) and isinstance(v, (int, float)))
            secs = e.get('secs') if isinstance(e.get('secs'), dict) else {}
            secs = dict((k, float(v)) for k, v in secs.items()
                        if isinstance(k, str) and isinstance(v, (int, float)))
            out.append({'tree': e['tree'], 'env': e['env'], 'passed': passed, 'secs': secs})
    out.sort(key=lambda e: -max(list(e['passed'].values()) or [0]))
    return out


def save_stamps(path, stamps):
    """Atomic; never raises - a stamp that cannot be written only costs a re-run."""
    try:
        tmp = '%s.%d.tmp' % (path, os.getpid())
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'format': STAMP_FORMAT, 'stamps': stamps[:STAMP_KEEP]}, f, indent=1,
                      sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def record_pass(path, tree, env, files, now, secs=None):
    """Add `files` as passed on `tree` at `now` (with their measured run times, `secs`, when
    known - only ever used to ESTIMATE a re-run, never to decide one). Only ever called right
    after this module's own pytest run on that tree exited 0 and the worktree was seen to still
    hold it."""
    if not path or not files:
        return False
    stamps = [s for s in load_stamps(path) if not (s['tree'] == tree and s['env'] == env)]
    mine = [s for s in load_stamps(path) if s['tree'] == tree and s['env'] == env]
    passed = dict(mine[0]['passed']) if mine else {}
    times = dict(mine[0].get('secs') or {}) if mine else {}
    for f in files:
        passed[f] = now
        if secs and f in secs:
            times[f] = round(float(secs[f]), 2)
    stamps.insert(0, {'tree': tree, 'env': env, 'passed': passed, 'secs': times})
    return save_stamps(path, stamps)


def junit_file_secs(path):
    """{test file: seconds} from a pytest --junitxml written with junit_family=xunit1 (which
    carries each case's file). {} on any trouble - durations only ever feed an estimate."""
    try:
        import xml.etree.ElementTree as ET
        out = {}
        for tc in ET.parse(path).getroot().iter('testcase'):
            f = (tc.get('file') or '').replace('\\', '/')
            if f:
                out[f] = out.get(f, 0.0) + float(tc.get('time') or 0)
        return out
    except Exception:
        return {}


def estimate_secs(stamps, files):
    """Seconds `files` took when they last ran (the newest stamp that timed each), a file never
    timed counted at the median of those that were. For deciding whether a re-run is worth
    holding the push lock for - see plan --json - never for deciding what runs."""
    newest = {}
    for s in reversed(stamps):              # oldest first, so the newest time wins
        newest.update(s.get('secs') or {})
    vals = sorted(newest.values())
    med = vals[len(vals) // 2] if vals else 1.0
    return round(sum(newest.get(f, med) for f in files), 1)


# ======================================================================= what the tree must run
def plan(root, tree, need, stamps, env, now, smoke=SMOKE):
    """Decide, for every test file in `need`, whether it runs on `tree` or is covered by a stamp.

    Returns {file: (stamp_tree, epoch)} for the COVERED files - everything else in `need` runs.
    A file is covered only by a pass on a tree T (same environment, within STAMP_MAX_AGE, still
    known to git) where SELF did not change between T and `tree` and tools/affected_tests.py
    selects nothing in the difference that reaches it. SMOKE files are never covered. The caller
    must have checked that the worktree holds `tree` (the selector reads the files on disk)."""
    covered = {}
    for s in stamps:
        if s['env'] != env or not tree_exists(root, s['tree']):
            continue
        fresh = dict((f, t) for f, t in s['passed'].items()
                     if f in need and f not in covered and f not in smoke
                     and 0 <= now - t <= STAMP_MAX_AGE)
        if not fresh:
            continue
        diff = tree_diff(root, s['tree'], tree)
        if diff is None or any(p in SELF for p in diff):
            continue
        reach = (at.tests_for(diff, root, max_share=None, cache_path=parse_cache_path())
                 if diff else set())
        if reach is None:
            continue
        for f, t in fresh.items():
            if f not in reach:
                covered[f] = (s['tree'], t)
    return covered


def _age(now, t):
    m = int(max(0, now - t) // 60)
    return '%d min' % m if m < 120 else '%.1f h' % (m / 60.0)


def run_pytest(root, args, junit=None):
    """The shell hook's own command: python -m pytest <args> -q, from the worktree root - plus,
    when `junit` is given, a junit report there (xunit1, which names each case's file) so the
    stamp can keep each file's run time."""
    extra = ['-o', 'junit_family=xunit1', '--junitxml=' + junit] if junit else []
    return subprocess.run([sys.executable, '-m', 'pytest'] + list(args) + ['-q'] + extra,
                          cwd=root).returncode


def run_tiers(root, phase, narrow, log=print, now=time.time, runner=None):
    """Run every tier this push needs on the worktree's tree, skipping what a stamp covers when
    `narrow` (a reason string when it may not narrow). Returns 0 or 1."""
    tree = head_tree(root)
    tl = tiers(root, changed_files(root), log)
    if not tl:
        log('%s: no Python file changed - no test tier applies' % phase)
        return 0
    env = env_fingerprint()
    spath = stamp_path(root)
    clean = worktree_clean(root) and tree is not None
    covered, why_full = {}, None
    if narrow is not True:
        why_full = narrow
    elif not clean:
        why_full = 'the worktree differs from HEAD, so a pass here would not be a pass of HEAD'
    else:
        try:
            need = set()
            for t in tl:
                need |= t.files
            covered = plan(root, tree, need, load_stamps(spath) if spath else [], env, now())
        except Exception as e:                  # every doubt: run it all
            covered, why_full = {}, 'planning failed (%s: %s)' % (type(e).__name__, e)
    if why_full:
        log('%s: every tier runs in full - %s' % (phase, why_full))
    for t in tl:
        skip = sorted(f for f in t.files if f in covered)
        run = sorted(f for f in t.files if f not in covered)
        if not run:
            trees = sorted(set(covered[f][0][:8] for f in skip))
            log('%s: %s tier - all %d test file(s) already passed on tree %s and nothing they '
                'read changed since; not re-run' % (phase, t.label, len(skip), ', '.join(trees)))
            continue
        if skip:
            newest = max(covered[f][1] for f in skip)
            trees = sorted(set(covered[f][0][:8] for f in skip))
            log('%s: %s tier - re-running %d of %d test file(s) on tree %s; the other %d passed '
                'on tree %s (latest %s ago) and nothing they read changed since'
                % (phase, t.label, len(run), len(t.files), (tree or '?')[:8], len(skip),
                   ', '.join(trees), _age(now(), newest)))
            if len(run) <= 12:
                log('  re-running: ' + ' '.join(run))
            args = run
        else:
            args = t.full_args
        t0 = now()
        junit = None
        if runner is None:
            import tempfile
            junit = os.path.join(tempfile.gettempdir(), 'edgelog_hook_tests_%d_%s.xml'
                                 % (os.getpid(), t.key))
            rc = run_pytest(root, args, junit)
        else:
            rc = runner(root, args)
        secs = junit_file_secs(junit) if junit else {}
        if junit:
            try:
                os.remove(junit)
            except Exception:
                pass
        if rc != 0:
            log('%s: %s tier FAILED on tree %s (pytest exit %d) - nothing stamped'
                % (phase, t.label, (tree or '?')[:8], rc))
            return 1
        log('%s: %s tier passed (%d file(s), %ds)' % (phase, t.label, len(run), now() - t0))
        if clean and spath and head_tree(root) == tree and worktree_clean(root):
            record_pass(spath, tree, env, run, now(), secs)
    return 0


# =============================================================================== the push refs
def refs_match_tree(root, refs_text, tree):
    """The pre-push hook's stdin: '<local ref> <local sha> <remote ref> <remote sha>' per ref.
    True only when every ref being pushed (not deleted) is a commit whose tree is `tree` - the
    tree on disk that the tests ran on. No refs at all is False: nothing to compare."""
    seen = False
    for line in (refs_text or '').splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        sha = parts[1]
        if re.match(r'^0+$', sha):
            continue                             # a delete pushes no tree
        rc, t = _git(root, 'rev-parse', sha + '^{tree}')
        if rc != 0 or t != tree:
            return False
        seen = True
    return seen


# ========================================================================================= CLI
def cmd_hook(root, refs_text, log=print):
    """Under the push lock, from tools/githooks/pre-push: the tiers on the tree being pushed."""
    tree = head_tree(root)
    narrow = True
    if not refs_match_tree(root, refs_text, tree):
        narrow = 'the commit being pushed is not the tree on disk (or git did not say)'
    return run_tiers(root, 'PRE-PUSH TESTS', narrow, log)


def cmd_prelock(root, log=print):
    """Before the push lock, from wt.py ship (which holds the machine-wide slot around it): the
    same tiers, on the same rules, stamped."""
    if not worktree_clean(root):
        log('PRE-LOCK TESTS: skipped - the worktree has uncommitted tracked changes; the hook '
            'runs every tier under the lock')
        return 2
    return run_tiers(root, 'PRE-LOCK TESTS', True, log)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('mode', choices=('hook', 'prelock', 'plan'))
    ap.add_argument('--root', default='.')
    ap.add_argument('--json', action='store_true',
                    help='plan: one JSON line - files to re-run and their estimated seconds')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    log = lambda s: print(s, flush=True)
    if a.mode == 'hook':
        refs = '' if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
        return cmd_hook(root, refs, log)
    if a.mode == 'prelock':
        return cmd_prelock(root, log)
    # plan: read-only - what would run on this tree now, what the stamps cover, and roughly how
    # long the rest takes. For wt.py ship under the lock: a re-run estimated too long for the
    # lock can be sent back outside it (give the lock back, run the pre-lock tests on this new
    # base, queue again), the way ship already treats a slow selftest.
    tree = head_tree(root)
    tl = tiers(root, changed_files(root), (lambda s: None) if a.json else log)
    need = set()
    for t in tl:
        need |= t.files
    sp = stamp_path(root)
    stamps = load_stamps(sp) if sp else []
    covered = plan(root, tree, need, stamps, env_fingerprint(),
                   time.time()) if worktree_clean(root) else {}
    run = sorted(f for f in need if f not in covered)
    if a.json:
        timed = set()
        for s in stamps:
            timed |= set(s.get('secs') or ())
        print(json.dumps({'tree': tree, 'need_files': len(need), 'run_files': len(run),
                          'est_secs': estimate_secs(stamps, run),
                          'timed': all(f in timed for f in run)}))
        return 0
    for t in tl:
        n = len([f for f in t.files if f not in covered])
        log('%s tier: %d of %d test file(s) would run' % (t.label, n, len(t.files)))
    log('estimated %ds' % estimate_secs(stamps, run))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
