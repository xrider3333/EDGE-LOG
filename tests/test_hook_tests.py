r"""tools/hook_tests.py: the pre-push test tiers run BEFORE the push lock, re-checked under it.

THE PROBLEM (2026-10-08). The pre-push hook ran the engine tier - the whole suite bar two files,
20-40 minutes - with the machine-wide push lock held, for every ship touching augur_engine/, api/
or tests/ (a research tool that adds its own test counts). ~25 ships queued = a 7-13 hour queue.

WHAT CHANGED. ship runs the same tiers before the lock and stamps the test files that really
passed on that tree; under the lock the hook re-runs only what the final tree's difference from
that tree can reach, plus an always-run smoke set.

THE INVARIANT these tests pin, end to end where it matters:
  nothing reaches main unless the final tree passed every needed test whose inputs changed since
  that test last really passed.
In particular:
  * a change landed by ANOTHER lane while this one queued, which breaks one of this ship's tests,
    is caught under the lock and the push is refused (test_another_lanes_breaking_change_...);
  * the selector's holes found while building this are closed, each by a case that fails when
    its fix is reverted: relative imports, renamed modules, a data file a module reads by name,
    a directory a test lists, importlib.import_module("X");
  * every doubt runs the tier in full with the hook's old command: no stamp, a dirty worktree,
    another Python environment, a stale or unknown tree, conftest changed, the deciding code
    itself changed, a pushed commit that is not the tree on disk;
  * ship stops before taking a ticket or the lock when a pre-lock test fails.
Nothing here touches this repository, C:\EdgeLog or the real push lock: every repo is a throwaway
under tmp_path and EDGELOG_HOME points into it.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import affected_tests as at  # noqa: E402
import hook_tests as ht  # noqa: E402


@pytest.fixture(autouse=True)
def _no_git_env(monkeypatch, tmp_path):
    """This suite also runs from the pre-push hook, whose environment can carry GIT_DIR and
    friends; a sandbox git call that inherited one would act on THIS repository. And every
    in-process call keeps its parse cache and slots under tmp_path, never C:\\EdgeLog."""
    for k in list(os.environ):
        if k.upper().startswith('GIT_'):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('EDGELOG_HOME', str(tmp_path / 'home'))


def _env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update({
        'GIT_AUTHOR_NAME': 'hook test', 'GIT_AUTHOR_EMAIL': 'hook-test@example.invalid',
        'GIT_COMMITTER_NAME': 'hook test', 'GIT_COMMITTER_EMAIL': 'hook-test@example.invalid',
        'PYTHONDONTWRITEBYTECODE': '1',
        'EDGELOG_HOME': str(tmp_path / 'home'),                   # never C:\EdgeLog
        'EDGELOG_WT_ROOT': str(tmp_path / 'worktrees'),
        'EDGELOG_WT_BACKUP_ROOT': str(tmp_path / 'wt_backup'),
        'HOOKLOG': str(tmp_path / 'ran.log'),
    })
    env.pop('PYTEST_ADDOPTS', None)
    env.update(extra)
    return env


def _git(env, cwd, *args, ok=True):
    p = subprocess.run(['git', '-C', str(cwd)] + list(args), env=env, capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if ok:
        assert p.returncode == 0, 'git %s failed:\n%s%s' % (' '.join(args), p.stdout, p.stderr)
    return p.stdout.strip() if ok else p


def _write(base, rel, text):
    path = os.path.join(str(base), *rel.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


# A sandbox test file: logs its own name to $HOOKLOG when it runs, then asserts `body`.
_TEST = '''import os
{imports}

def _held_path(path):
    import sys
    sys.path.insert(0, os.environ["FAKE_TOOLS"])
    import push_lock
    if not os.path.exists(path):
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            push_lock._lock_fd(fd)
        except OSError:
            return True
        push_lock._unlock_fd(fd)
        return False
    finally:
        os.close(fd)


def _lock_held():
    return _held_path(os.path.join(os.environ["EDGELOG_HOME"], "state", "push.lock"))


def _slots():
    d = os.path.join(os.environ["EDGELOG_HOME"], "state", "gate_slots")
    names = sorted(os.listdir(d)) if os.path.isdir(d) else []
    held = [n[:-5] for n in names if n.endswith(".lock") and _held_path(os.path.join(d, n))]
    return ",".join(held) or "-"


def test_it():
    with open(os.environ["HOOKLOG"], "a") as f:
        f.write("{name}\\n")
    if os.environ.get("LOCKLOG"):
        with open(os.environ["LOCKLOG"], "a") as f:
            f.write("{name} %s %s\\n" % ("locked" if _lock_held() else "unlocked", _slots()))
{body}
'''


def _test_src(name, imports='', body='    pass'):
    return _TEST.format(name=name, imports=imports, body=body)


# The sandbox repo. Every dependency below is reachable by exactly ONE selector rule, and the
# names are chosen so no test mentions the file it depends on (the old by-name rule matches bare
# stems as substrings - a one-letter module name would be "found" in every source and hide a
# missing rule):
#   test_beta    -> pkg.bridge -> pkg.base_value      a RELATIVE import (`from .base_value`)
#   test_dyn     -> pkg.dyn    -> pkg.cee_module      importlib.import_module("pkg.cee_module")
#   test_loader  -> pkg.loader -> docs/lookup_rows.csv   a data file named in a MODULE
#   test_plug    -> pkg.plug   -> plugins/*           the module names its own directory
#   test_listing -> os.listdir(.../"tools")           a test that LISTS a generic directory
#   test_alpha   -> pkg.cee_module                    a plain import
SANDBOX = {
    'pytest.ini': '[pytest]\npythonpath = .\naddopts = -p no:cacheprovider\n',
    'tools/preflight_boot.py': 'print("PREFLIGHT: PASS")\n',
    'pkg/__init__.py': '',
    'pkg/base_value.py': 'VALUE = 1\n',
    'pkg/bridge.py': 'from .base_value import VALUE as _V\nVALUE = 2\n',
    'pkg/cee_module.py': 'VALUE = 3\n',
    'pkg/loader.py': ('import os\nHERE = os.path.dirname(os.path.abspath(__file__))\n'
                      'def rows():\n'
                      '    return open(os.path.join(HERE, "..", "docs", "lookup_rows.csv")).read()\n'),
    'pkg/dyn.py': 'import importlib\nC = importlib.import_module("pkg.cee_module")\n',
    'pkg/plug.py': ('import os\nHERE = os.path.dirname(os.path.abspath(__file__))\n'
                    'NAME = "zeta" + "_plug" + "in"\n'
                    'def load():\n'
                    '    return open(os.path.join(HERE, "..", "plugins", NAME + ".py")).read()\n'),
    'docs/lookup_rows.csv': 'x\n1\n',
    'plugins/zeta_plugin.py': 'X = 1\n',
    'tests/test_strategy_contract.py': _test_src('test_strategy_contract'),
    'tests/test_alpha.py': _test_src('test_alpha', 'import pkg.cee_module',
                                     '    assert pkg.cee_module.VALUE == 3'),
    'tests/test_beta.py': _test_src('test_beta', 'import pkg.bridge\nimport time\n'
                                    'import subprocess\nimport sys',
                                    '    assert pkg.bridge._V == 1\n'
                                    '    time.sleep(float(os.environ.get("BETA_SLEEP", "0")))\n'
                                    '    if os.environ.get("BETA_LAND"):\n'
                                    '        subprocess.run([sys.executable,'
                                    ' os.environ["BETA_LAND"]], check=True)'),
    'tests/test_loader.py': _test_src('test_loader', 'import pkg.loader',
                                      '    assert pkg.loader.rows().startswith("x")'),
    'tests/test_dyn.py': _test_src('test_dyn', 'import pkg.dyn',
                                   '    assert pkg.dyn.C.VALUE == 3'),
    'tests/test_plug.py': _test_src('test_plug', 'import pkg.plug',
                                    '    assert "X = 1" in pkg.plug.load()'),
    'tests/test_listing.py': _test_src(
        'test_listing', 'ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))',
        '    d = os.path.join(ROOT, "tools")\n'
        '    assert all(n.endswith(".py") or os.path.isdir(os.path.join(d, n))\n'
        '               for n in os.listdir(d))'),
    # one SMOKE file: always re-run when its tier is due
    'tests/test_family_vocabulary.py': _test_src('test_family_vocabulary'),
}
ALL_TESTS = {'test_alpha', 'test_beta', 'test_loader', 'test_dyn', 'test_plug', 'test_listing',
             'test_family_vocabulary'}
ENGINE_FILES = {'tests/%s.py' % n for n in ALL_TESTS}


def _seed(base, env):
    for rel, text in SANDBOX.items():
        _write(base, rel, text)
    for rel in ('tools/hook_tests.py', 'tools/affected_tests.py', 'tools/push_lock.py',
                'tools/push_queue.py', 'tools/wt.py', 'tools/githooks/pre-push'):
        src = os.path.join(ROOT, *rel.split('/'))
        dst = os.path.join(str(base), *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _repo(tmp_path):
    """origin (bare) <- lane (this ship's clone, the real pre-push hook installed) and other
    (another lane, no hook, landing straight on origin)."""
    env = _env(tmp_path)
    origin, lane, other = tmp_path / 'origin.git', tmp_path / 'lane', tmp_path / 'other'
    _git(env, tmp_path, 'init', '-q', '--bare', '-b', 'main', str(origin))
    _git(env, tmp_path, 'init', '-q', '-b', 'main', str(lane))
    _git(env, lane, 'config', 'core.autocrlf', 'false')
    _git(env, lane, 'remote', 'add', 'origin', str(origin))
    _seed(lane, env)
    _git(env, lane, 'add', '-A')
    _git(env, lane, 'commit', '-q', '-m', 'seed')
    _git(env, lane, 'push', '-q', 'origin', 'main')
    _git(env, lane, 'fetch', '-q', 'origin')
    _git(env, lane, 'config', 'core.hooksPath', 'tools/githooks')
    _git(env, tmp_path, 'clone', '-q', '-c', 'core.autocrlf=false', str(origin), str(other))
    return env, origin, lane, other


def _ran(env):
    try:
        with open(env['HOOKLOG']) as f:
            got = set(l.strip() for l in f if l.strip())
    except FileNotFoundError:
        got = set()
    open(env['HOOKLOG'], 'w').close()
    return got - {'test_strategy_contract'}, 'test_strategy_contract' in got


def _commit(env, repo, files, msg):
    for rel, text in files.items():
        _write(repo, rel, text)
    _git(env, repo, 'add', '-A')
    _git(env, repo, 'commit', '-q', '-m', msg)


def _land(env, other, files, msg):
    """Another lane's commit landing on origin/main while this ship queues."""
    _git(env, other, 'pull', '-q', '--rebase', 'origin', 'main')
    _commit(env, other, files, msg)
    _git(env, other, 'push', '-q', 'origin', 'HEAD:main')


def _prelock(env, lane):
    return subprocess.run([sys.executable, os.path.join(str(lane), 'tools', 'hook_tests.py'),
                           'prelock', '--root', str(lane)], env=env, capture_output=True,
                          text=True, encoding='utf-8', errors='replace')


def _push(env, lane):
    return subprocess.run(['git', '-C', str(lane), 'push', 'origin', 'HEAD:main'], env=env,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')


# =============================================================== the tiers are the shell's tiers
@pytest.fixture
def tier_root(tmp_path):
    env = _env(tmp_path)
    r = tmp_path / 'r'
    _git(env, tmp_path, 'init', '-q', '-b', 'main', str(r))
    for rel in ('tests/test_strategy_contract.py', 'tests/test_surrogate.py', 'tests/test_a.py',
                'tests/test_foo.py', 'tests/test_wt.py', 'tests/test_wt_ship_console.py',
                'tests/test_push_lock.py', 'tests/sub/test_deep.py', 'tests/helper.py'):
        _write(r, rel, 'x = 1\n')
    _git(env, r, 'add', '-A')
    _git(env, r, 'commit', '-q', '-m', 'seed')
    return str(r)


def _keys(tl):
    return [(t.key, sorted(t.files)) for t in tl]


def test_no_python_change_runs_no_tier(tier_root):
    assert ht.tiers(tier_root, ['index.html', 'docs/X.md', 'RESEARCH_LEDGER.md']) == []


def test_a_tool_change_runs_the_contract_and_its_own_test(tier_root):
    assert _keys(ht.tiers(tier_root, ['tools/foo.py'])) == [
        ('contract', [ht.CONTRACT]), ('tools', ['tests/test_foo.py'])]


def test_wt_brings_its_companions(tier_root):
    assert _keys(ht.tiers(tier_root, ['tools/wt.py'])) == [
        ('contract', [ht.CONTRACT]),
        ('tools', ['tests/test_push_lock.py', 'tests/test_wt.py', 'tests/test_wt_ship_console.py'])]


def test_a_tool_in_a_subfolder_runs_the_contract_tier_only(tier_root):
    """The shell's tools regex never matched tools/<dir>/<name>.py; unchanged on purpose."""
    assert _keys(ht.tiers(tier_root, ['tools/rocfrontier/r17.py'])) == [('contract', [ht.CONTRACT])]


@pytest.mark.parametrize('path', ['tests/test_a.py', 'api/x.py', 'augur_engine/data.py',
                                  'augur_mp_worker.py'])
def test_the_engine_tier_triggers_and_command_are_the_shells(tier_root, path):
    tl = ht.tiers(tier_root, [path, 'tools/foo.py'])
    assert [t.key for t in tl] == ['contract', 'engine'], 'tools tier skipped when engine runs'
    eng = tl[1]
    assert eng.full_args == ['tests', '--ignore=tests/test_strategy_contract.py',
                             '--ignore=tests/test_surrogate.py']
    assert eng.files == {'tests/test_a.py', 'tests/test_foo.py', 'tests/test_wt.py',
                         'tests/test_wt_ship_console.py', 'tests/test_push_lock.py',
                         'tests/sub/test_deep.py'}


def test_surrogate_gets_its_own_tier(tier_root):
    assert [t.key for t in ht.tiers(tier_root, ['augur_engine/surrogate.py'])] == [
        'contract', 'engine', 'surrogate']


def test_when_git_cannot_say_what_changed_the_heavy_tiers_run(tier_root):
    assert [t.key for t in ht.tiers(tier_root, None, log=lambda s: None)] == ['contract', 'engine']


def test_the_hook_delegates_to_this_module_and_no_longer_trusts_the_env_claim():
    src = open(os.path.join(ROOT, 'tools', 'githooks', 'pre-push'), encoding='utf-8').read()
    assert 'hook_tests.py" hook' in src
    assert '"$EDGELOG_GATE_PASSED_TREE"' not in src and '$EDGELOG_GATE_PASSED_TREE' not in src
    assert src.index('push_refs="$(cat)"') < src.index('preflight_boot.py"'), (
        'the refs must be read before any gate can consume stdin')
    i_missing = src.index('tools/hook_tests.py" ]')
    assert 'exit 1' in src[i_missing:i_missing + 400], 'a tree without the module fails closed'


# ===================================================================== refs, stamps, the slot
def test_refs_must_name_the_tree_on_disk(tmp_path):
    env, origin, lane, other = _repo(tmp_path)
    tree = _git(env, lane, 'rev-parse', 'HEAD^{tree}')
    head = _git(env, lane, 'rev-parse', 'HEAD')
    z = '0' * 40
    assert ht.refs_match_tree(str(lane), 'HEAD %s refs/heads/main %s\n' % (head, z), tree)
    _commit(env, lane, {'docs/x.md': 'x\n'}, 'later')
    assert not ht.refs_match_tree(str(lane), 'HEAD %s refs/heads/main %s\n' % (head, z),
                                  _git(env, lane, 'rev-parse', 'HEAD^{tree}'))
    assert not ht.refs_match_tree(str(lane), '', tree), 'no refs: nothing proves what is pushed'
    assert not ht.refs_match_tree(str(lane), '(delete) %s refs/heads/x %s\n' % (z, head), tree)


def test_stamps_round_trip_and_garbage_is_no_stamp(tmp_path):
    p = str(tmp_path / 's.json')
    assert ht.load_stamps(p) == []
    assert ht.record_pass(p, 'a' * 40, 'env1', ['tests/test_x.py'], 100.0)
    assert ht.record_pass(p, 'a' * 40, 'env1', ['tests/test_y.py'], 200.0)
    assert ht.record_pass(p, 'b' * 40, 'env1', ['tests/test_x.py'], 300.0)
    st = ht.load_stamps(p)
    assert [s['tree'] for s in st] == ['b' * 40, 'a' * 40], 'newest first'
    assert st[1]['passed'] == {'tests/test_x.py': 100.0, 'tests/test_y.py': 200.0}
    for junk in ('not json', json.dumps({'format': 999, 'stamps': []}), json.dumps([1, 2])):
        with open(p, 'w') as f:
            f.write(junk)
        assert ht.load_stamps(p) == []


def test_record_pass_never_records_nothing(tmp_path):
    p = str(tmp_path / 's.json')
    assert not ht.record_pass(p, 'a' * 40, 'e', [], 1.0)
    assert not os.path.exists(p)


# ============================================== plan(): what a stamp may cover, case by case
@pytest.fixture
def sb(tmp_path):
    """A committed sandbox (tree T) with every test file stamped as passed on T just now."""
    env, origin, lane, other = _repo(tmp_path)
    root = str(lane)
    t = _git(env, lane, 'rev-parse', 'HEAD^{tree}')
    now = time.time()
    stamps = [{'tree': t, 'env': 'E', 'passed': dict((f, now) for f in ENGINE_FILES)}]

    class SB(object):
        pass
    s = SB()
    s.env, s.root, s.lane, s.tree, s.stamps, s.now = env, root, lane, t, stamps, now

    def change(files, delete=(), msg='change'):
        for rel in delete:
            _git(env, lane, 'rm', '-q', rel)
        for rel, text in files.items():
            _write(lane, rel, text)
        _git(env, lane, 'add', '-A')
        _git(env, lane, 'commit', '-q', '-m', msg)
        return _git(env, lane, 'rev-parse', 'HEAD^{tree}')

    def covered(tree, stamps=None, env_fp='E', now=None):
        return set(ht.plan(root, tree, ENGINE_FILES, s.stamps if stamps is None else stamps,
                           env_fp, s.now if now is None else now))
    s.change, s.covered = change, covered
    return s


def _uncovered(sb, cov):
    return set(os.path.basename(f)[:-3] for f in ENGINE_FILES - cov)


def test_the_same_tree_covers_everything_but_the_smoke_set(sb):
    assert _uncovered(sb, sb.covered(sb.tree)) == {'test_family_vocabulary'}


def test_a_change_reaches_its_test_through_a_RELATIVE_import(sb):
    """pkg/bridge.py says `from .base_value import VALUE`; test_beta imports pkg.bridge only.
    Until 2026-10-08 the selector dropped relative imports (api/paper.py has a dozen), so this
    test would have been covered by a stale pass."""
    t = sb.change({'pkg/base_value.py': 'VALUE = 5\n'})
    assert _uncovered(sb, sb.covered(t)) == {'test_beta', 'test_family_vocabulary'}


def test_a_literal_import_module_counts_as_an_import(sb):
    t = sb.change({'pkg/cee_module.py': 'VALUE = 4\n'})
    assert _uncovered(sb, sb.covered(t)) == {'test_alpha', 'test_dyn', 'test_family_vocabulary'}


def test_a_data_file_a_module_reads_by_name_reaches_its_importers_tests(sb):
    """pkg/loader.py opens docs/lookup_rows.csv by name; test_loader never mentions the csv."""
    t = sb.change({'docs/lookup_rows.csv': 'y\n'})
    assert _uncovered(sb, sb.covered(t)) == {'test_loader', 'test_family_vocabulary'}


def _facts(literals):
    return {'literals': '\n'.join('"%s"' % x for x in literals), 'flat': frozenset(),
            'deep': frozenset(), 'blind': False}


def test_a_bare_basename_in_code_needs_evidence_it_is_this_file():
    """PRECISION, which is what keeps the hold short: a module whose code says "README.md" is not
    a reader of tools/rocfrontier/README.md unless it also names that folder or sits in it (that
    one rule put 85 test files behind every rocfrontier README edit). A full path always counts,
    and a repo-root file needs no folder."""
    srcs = dict((k, '') for k in ('api/x.py', 'api/y.py', 'tools/rocfrontier/z.py', 'api/w.py',
                                  'api/v.py'))
    fx = {'api/x.py': _facts(['README.md']),
          'api/y.py': _facts(['README.md', 'rocfrontier']),
          'tools/rocfrontier/z.py': _facts(['README.md']),
          'api/w.py': _facts(['tools/rocfrontier/README.md']),
          'api/v.py': _facts(['index.html'])}
    hit = at.reached_by_name(['tools/rocfrontier/README.md'], srcs, fx)
    assert hit == {'api/y.py', 'tools/rocfrontier/z.py', 'api/w.py'}
    assert at.reached_by_name(['index.html'], srcs, fx) == {'api/v.py'}


def test_a_file_in_a_directory_a_module_names_reaches_its_importers_tests(sb):
    """pkg/plug.py builds plugins/<computed name>.py; nothing names zeta_plugin.py itself."""
    t = sb.change({'plugins/zeta_plugin.py': 'X = 2\n'})
    assert _uncovered(sb, sb.covered(t)) == {'test_plug', 'test_family_vocabulary'}


def test_a_new_file_in_a_listed_directory_reaches_the_test_that_lists_it(sb):
    """test_listing does os.listdir(.../"tools") - a GENERIC directory, so naming it alone proves
    nothing; listing it does. A new file there is its input though no test names it."""
    t = sb.change({'tools/notes.txt': 'x\n'})
    assert 'test_listing' in _uncovered(sb, sb.covered(t))


def test_a_RENAMED_module_cannot_be_narrowed(sb):
    """With git's rename detection the diff names only the new file, so the importers of the old
    one are never asked about - test_alpha (import pkg.cee_module) would be covered and then fail
    on main. --no-renames lists the deleted pkg/cee_module.py, which the tree no longer has:
    nothing is covered."""
    t = sb.change({'pkg/cee2.py': 'VALUE = 3\n'}, delete=('pkg/cee_module.py',))
    assert sb.covered(t) == set()


@pytest.mark.parametrize('rel', ['conftest.py', 'tests/conftest.py', 'pytest.ini'])
def test_a_change_to_how_the_suite_runs_covers_nothing(sb, rel):
    text = '[pytest]\npythonpath = .\naddopts = -p no:cacheprovider -ra\n' if rel == 'pytest.ini' \
        else '# changed\n'
    assert sb.covered(sb.change({rel: text})) == set()


@pytest.mark.parametrize('rel', ht.SELF)
def test_a_change_to_the_deciding_code_covers_nothing(sb, rel):
    with open(os.path.join(sb.root, *rel.split('/')), encoding='utf-8') as f:
        text = f.read()
    assert sb.covered(sb.change({rel: text + '\n# changed\n'})) == set()


def test_another_python_environment_covers_nothing(sb):
    assert sb.covered(sb.tree, env_fp='OTHER') == set()


def test_a_stale_or_future_pass_covers_nothing(sb):
    assert sb.covered(sb.tree, now=sb.now + ht.STAMP_MAX_AGE + 1) == set()
    assert sb.covered(sb.tree, now=sb.now - 3600) == set(), 'a pass from the future is not one'


def test_a_tree_git_does_not_have_covers_nothing(sb):
    fake = [{'tree': 'f' * 40, 'env': 'E', 'passed': sb.stamps[0]['passed']}]
    assert sb.covered(sb.tree, stamps=fake) == set()


def test_only_files_that_really_passed_are_covered(sb):
    part = [{'tree': sb.tree, 'env': 'E', 'passed': {'tests/test_alpha.py': sb.now}}]
    assert sb.covered(sb.tree, stamps=part) == {'tests/test_alpha.py'}


def test_the_newest_stamp_that_can_vouch_is_used(sb):
    """An older stamp whose diff cannot be narrowed does not block a newer one that can."""
    t1 = sb.change({'tests/conftest.py': '# c\n'})
    newer = [{'tree': t1, 'env': 'E', 'passed': dict((f, sb.now) for f in ENGINE_FILES)}]
    t2 = sb.change({'docs/n.md': 'n\n'})
    assert _uncovered(sb, sb.covered(t2, stamps=newer + sb.stamps)) == {'test_family_vocabulary'}


# ============================================= the parse cache answers only for the same bytes
def _fresh_graphs():
    at._GRAPH_CACHE.clear()
    at._SOURCES.clear()
    at._FACTS.clear()


def test_the_parse_cache_never_answers_for_changed_bytes(sb, tmp_path):
    """The cache keys each file by its git blob: a module that GAINED an import since the cache
    was written must be re-parsed, or its new importers' tests would be skipped."""
    cp = str(tmp_path / 'cache.json')
    sb.change({'pkg/plain.py': 'VALUE = 7\n',
               'tests/test_gamma.py': _test_src('test_gamma', 'import pkg.plain')})
    _fresh_graphs()
    assert 'tests/test_gamma.py' not in at.tests_for(['pkg/base_value.py'], sb.root,
                                                     max_share=None, cache_path=cp)
    sb.change({'pkg/plain.py': 'from .base_value import VALUE\n'})
    _fresh_graphs()
    assert 'tests/test_gamma.py' in at.tests_for(['pkg/base_value.py'], sb.root,
                                                 max_share=None, cache_path=cp)


def test_the_parse_cache_never_answers_for_an_uncommitted_edit(sb, tmp_path):
    """The index still holds the old blob of a file edited on disk; the cache must not answer for
    it (the hook only narrows on a clean tree, but the cache must be right on its own)."""
    cp = str(tmp_path / 'cache.json')
    sb.change({'pkg/plain.py': 'VALUE = 7\n',
               'tests/test_gamma.py': _test_src('test_gamma', 'import pkg.plain')})
    _fresh_graphs()
    assert 'tests/test_gamma.py' not in at.tests_for(['pkg/base_value.py'], sb.root,
                                                     max_share=None, cache_path=cp)
    _write(sb.lane, 'pkg/plain.py', 'from .base_value import VALUE\n')       # not committed
    _fresh_graphs()
    assert 'tests/test_gamma.py' in at.tests_for(['pkg/base_value.py'], sb.root,
                                                 max_share=None, cache_path=cp)


def test_a_cache_written_by_other_selector_code_is_ignored(sb, tmp_path):
    cp = str(tmp_path / 'cache.json')
    sb.change({'pkg/plain.py': 'from .base_value import VALUE\n',
               'tests/test_gamma.py': _test_src('test_gamma', 'import pkg.plain')})
    blob = _git(sb.env, sb.lane, 'rev-parse', 'HEAD:pkg/plain.py')
    lie = {'blob': blob, 'imports': [],
           'facts': {'literals': '', 'flat': [], 'deep': [], 'blind': False}}
    with open(cp, 'w') as f:
        json.dump({'key': 'some-other-selector', 'entries': {'pkg/plain.py': lie}}, f)
    _fresh_graphs()
    assert 'tests/test_gamma.py' in at.tests_for(['pkg/base_value.py'], sb.root,
                                                 max_share=None, cache_path=cp)


# ================================================================ run_tiers with a fake pytest
def test_a_failing_run_is_never_stamped_and_stops(sb, monkeypatch):
    _commit(sb.env, sb.lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '#\n'},
            'touch a test')
    log = []
    rc = ht.run_tiers(sb.root, 'T', True, log.append, runner=lambda root, args: 1)
    assert rc == 1 and any('FAILED' in l for l in log)
    assert ht.load_stamps(ht.stamp_path(sb.root)) == []


def test_a_pass_on_a_dirty_worktree_runs_in_full_and_is_not_stamped(sb):
    _commit(sb.env, sb.lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '#\n'},
            'touch a test')
    # a stamp that WOULD cover every file of this exact tree - the dirty edit must void it
    tree = _git(sb.env, sb.lane, 'rev-parse', 'HEAD^{tree}')
    spath = ht.stamp_path(sb.root)
    assert ht.record_pass(spath, tree, ht.env_fingerprint(), sorted(ENGINE_FILES | {ht.CONTRACT}),
                          time.time())
    _write(sb.lane, 'pkg/cee_module.py', 'VALUE = 3  # edited, not committed\n')
    calls = []
    rc = ht.run_tiers(sb.root, 'T', True, lambda s: None,
                      runner=lambda root, args: calls.append(list(args)) or 0)
    assert rc == 0
    assert ['tests', '--ignore=tests/test_strategy_contract.py',
            '--ignore=tests/test_surrogate.py'] in calls, 'the hook\'s own full command'
    assert [ht.CONTRACT] in calls
    before = ht.load_stamps(spath)
    assert len(before) == 1 and before[0]['tree'] == tree, 'the dirty run added no stamp'


def test_a_tree_that_moves_during_the_run_is_not_stamped(sb):
    _commit(sb.env, sb.lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '#\n'},
            'touch a test')

    calls = []

    def runner(root, args):                  # every tier's run sees HEAD move under it
        calls.append(args)
        _commit(sb.env, sb.lane, {'docs/mid%d.md' % len(calls): 'x\n'}, 'committed mid-run')
        return 0
    assert ht.run_tiers(sb.root, 'T', True, lambda s: None, runner=runner) == 0
    assert ht.load_stamps(ht.stamp_path(sb.root)) == []


# ======================================================== end to end: the real hook, real pushes
def test_no_stamp_runs_every_tier_in_full_and_stamps_it(tmp_path):
    env, origin, lane, other = _repo(tmp_path)
    _commit(env, lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '# x\n'}, 'mine')
    p = _push(env, lane)
    assert p.returncode == 0, p.stdout + p.stderr
    ran, contract = _ran(env)
    assert ran == ALL_TESTS and contract
    st = ht.load_stamps(ht.stamp_path(str(lane)))
    assert st and set(st[0]['passed']) == ENGINE_FILES | {ht.CONTRACT}


def test_prelock_then_push_reruns_only_what_the_landed_change_reaches(tmp_path):
    """THE POINT OF IT. The full tier runs before the lock; meanwhile another lane lands a change
    to pkg/base_value.py. Under the lock only test_beta (which reaches it) and the smoke file
    re-run."""
    env, origin, lane, other = _repo(tmp_path)
    _commit(env, lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '# x\n'}, 'mine')
    pre = _prelock(env, lane)
    assert pre.returncode == 0, pre.stdout + pre.stderr
    assert _ran(env) == (ALL_TESTS, True)
    _land(env, other, {'pkg/base_value.py': 'VALUE = 1  # same value, new comment\n'},
          'other lane')
    _git(env, lane, 'fetch', '-q', 'origin')
    _git(env, lane, 'rebase', '-q', 'origin/main')
    p = _push(env, lane)
    assert p.returncode == 0, p.stdout + p.stderr
    assert _ran(env) == ({'test_beta', 'test_family_vocabulary'}, False)
    assert 're-running 2 of 7' in p.stdout + p.stderr


def test_plan_json_estimates_the_re_run_from_the_stamped_times(tmp_path):
    """What ship needs to decide whether a re-run is worth holding the lock for: after the
    pre-lock run every file has a measured time; on the same tree only the smoke file would
    run, and its estimate is its own measured time."""
    env, origin, lane, other = _repo(tmp_path)
    _commit(env, lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '# x\n'}, 'mine')
    assert _prelock(env, lane).returncode == 0
    st = ht.load_stamps(ht.stamp_path(str(lane)))
    assert set(st[0]['secs']) == ENGINE_FILES | {ht.CONTRACT}, 'every file timed (junit xunit1)'
    p = subprocess.run([sys.executable, os.path.join(str(lane), 'tools', 'hook_tests.py'), 'plan',
                        '--root', str(lane), '--json'], env=env, capture_output=True, text=True)
    got = json.loads(p.stdout.strip().splitlines()[-1])
    assert (got['need_files'], got['run_files']) == (len(ENGINE_FILES) + 1, 1)
    assert got['est_secs'] == round(st[0]['secs']['tests/test_family_vocabulary.py'], 1)


def test_estimate_counts_an_untimed_file_at_the_median():
    st = [{'secs': {'a': 1.0, 'b': 3.0, 'c': 100.0}}, {'secs': {'a': 50.0}}]
    assert ht.estimate_secs(st, ['a', 'c']) == 101.0, 'the newest stamp that timed it'
    assert ht.estimate_secs(st, ['a', 'zz']) == 4.0, 'untimed: the median (3.0)'
    assert ht.estimate_secs([], ['x', 'y']) == 2.0


def test_another_lanes_breaking_change_is_caught_under_the_lock(tmp_path):
    """THE INVARIANT. test_beta passed before the lock; the change another lane lands while this
    ship queues breaks it (pkg.base_value, reached only through pkg.bridge's relative import). The final
    tree must re-run it, fail, and refuse the push - main stays where the other lane left it."""
    env, origin, lane, other = _repo(tmp_path)
    _commit(env, lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '# x\n'}, 'mine')
    assert _prelock(env, lane).returncode == 0
    _ran(env)
    _land(env, other, {'pkg/base_value.py': 'VALUE = 5\n'}, 'other lane breaks test_beta')
    landed = _git(env, other, 'rev-parse', 'HEAD')
    _git(env, lane, 'fetch', '-q', 'origin')
    _git(env, lane, 'rebase', '-q', 'origin/main')
    p = _push(env, lane)
    assert p.returncode != 0, 'the push must be refused'
    assert 'test_beta' in _ran(env)[0]
    assert _git(env, origin, 'rev-parse', 'main') == landed


def test_a_pushed_commit_that_is_not_the_tree_on_disk_runs_everything(tmp_path):
    env, origin, lane, other = _repo(tmp_path)
    _commit(env, lane, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '# x\n'}, 'mine')
    assert _prelock(env, lane).returncode == 0
    _ran(env)
    first = _git(env, lane, 'rev-parse', 'HEAD')
    _commit(env, lane, {'docs/later.md': 'x\n'}, 'a later commit, not pushed')
    p = subprocess.run(['git', '-C', str(lane), 'push', 'origin', first + ':refs/heads/main'],
                       env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert p.returncode == 0, p.stdout + p.stderr
    assert _ran(env) == (ALL_TESTS, True)


# ============================================================= end to end: wt.py ship, sandboxed
# "Another lane" landing a change that reaches test_beta (a comment in pkg/base_value.py) while
# this ship's tests run - at most BETA_LAND_TIMES times in all.
LAND_BETA = r"""
import os, subprocess, sys
cf = os.environ['BETA_LAND_COUNT']
n = int(open(cf).read()) if os.path.exists(cf) else 0
if n >= int(os.environ.get('BETA_LAND_TIMES', '1')):
    sys.exit(0)
open(cf, 'w').write(str(n + 1))
other = os.environ['BETA_OTHER']
env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
env.update(GIT_AUTHOR_NAME='other lane', GIT_AUTHOR_EMAIL='other@example.invalid',
           GIT_COMMITTER_NAME='other lane', GIT_COMMITTER_EMAIL='other@example.invalid')
def git(*a):
    subprocess.run(['git', '-C', other] + list(a), check=True, capture_output=True, env=env)
git('fetch', '-q', 'origin')
git('reset', '-q', '--hard', 'origin/main')
with open(os.path.join(other, 'pkg', 'base_value.py'), 'a') as f:
    f.write('# another lane, landing %d\n' % (n + 1))
git('add', '-A')
git('commit', '-q', '-m', 'another lane %d' % (n + 1))
git('push', '-q', 'origin', 'HEAD:main')
"""


def _ship_sandbox(tmp_path, test_body=None, wt_source=None):
    """origin <- shared checkout (tools/wt.py, or `wt_source` text, on main; the real pre-push
    hook installed) <- session worktree with one commit that changes a test file (so the
    engine tier is due)."""
    env, origin, shared, other = _repo(tmp_path)
    if wt_source is not None:
        _write(shared, 'tools/wt.py', wt_source)
        _git(env, shared, 'commit', '-q', '-am', 'this ship runs another wt.py')
        _git(env, shared, 'push', '-q', '--no-verify', 'origin', 'HEAD:main')   # setup only
    session = tmp_path / 'worktrees' / 'lane1'
    _git(env, shared, 'worktree', 'add', '-q', '-b', 'session/lane1', str(session), 'origin/main')
    body = test_body or SANDBOX['tests/test_alpha.py'] + '# mine\n'
    _commit(env, session, {'tests/test_alpha.py': body}, 'lane1 change')
    (tmp_path / 'land_beta.py').write_text(LAND_BETA, encoding='utf-8')
    env.update({'FAKE_TOOLS': str(shared / 'tools'), 'LOCKLOG': str(tmp_path / 'lock.log'),
                'BETA_OTHER': str(other), 'BETA_LAND_COUNT': str(tmp_path / 'beta_land.count')})
    return env, origin, shared, other, session


def _ship(env, shared):
    return subprocess.run([sys.executable, os.path.join(str(shared), 'tools', 'wt.py'), 'ship',
                           'lane1'], cwd=str(shared), env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=900)


def _counts(env):
    with open(env['HOOKLOG']) as f:
        lines = [l.strip() for l in f if l.strip()]
    return dict((n, lines.count(n)) for n in set(lines))


def _slot_rows(env):
    """[(test, 'locked'|'unlocked', gate slots held machine-wide while it ran)]."""
    try:
        with open(env['LOCKLOG']) as f:
            return [tuple(l.split()) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def _lock_rows(env):
    return [r[:2] for r in _slot_rows(env)]


def _assert_free(tmp_path):
    """Once the ship is gone the push lock and every gate slot can be taken and no ticket is
    live - nothing leaked, whatever round it ended in."""
    sys.path.insert(0, TOOLS)
    import push_lock
    import push_queue
    state = tmp_path / 'home' / 'state'
    paths = [state / 'push.lock']
    if (state / 'gate_slots').is_dir():
        paths += [state / 'gate_slots' / n for n in os.listdir(str(state / 'gate_slots'))]
    for path in paths:
        if path.exists():
            fd = os.open(str(path), os.O_RDWR)
            try:
                push_lock._lock_fd(fd)              # raises OSError if anything still holds it
                push_lock._unlock_fd(fd)
            finally:
                os.close(fd)
    q = state / 'push_queue'
    assert not (q.exists() and push_queue.live_tickets(str(q))), 'a ticket outlived its ship'


def test_ship_runs_the_tests_before_the_lock_and_the_hook_rechecks_only_the_difference(tmp_path):
    env, origin, shared, other, session = _ship_sandbox(tmp_path)
    p = _ship(env, shared)
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert 'PRE-LOCK (round 1 of 3)' in out
    assert out.index('  PRE-LOCK TESTS: ') < out.index('  PRE-LOCK TESTS: done')
    assert out.index('  PRE-LOCK TESTS: done') < out.index('push lock held by this lane')
    assert 'LOCK RELEASED' not in out
    assert 'pushed (verified on main)' in out
    # ship swallows a successful push's output, so read what ran from the log: every file once
    # before the lock, and under it (main did not move) only the smoke file again
    assert _counts(env) == dict([(n, 1) for n in ALL_TESTS | {'test_strategy_contract'}],
                                test_family_vocabulary=2), _counts(env)
    assert ('test_family_vocabulary', 'locked') in _lock_rows(env)
    assert [r for r in _lock_rows(env) if r[1] == 'locked'] == [
        ('test_family_vocabulary', 'locked')], 'nothing else ran under the lock'
    # THE CAP: the heavy first run held the ONE machine-wide test slot (and nothing else); under
    # the lock no slot is taken
    rows = _slot_rows(env)
    assert all(r[2] == 'tests-1' for r in rows if r[1] == 'unlocked'), rows
    assert all(r[2] == '-' for r in rows if r[1] == 'locked'), rows
    _assert_free(tmp_path)


def test_a_long_re_run_goes_back_outside_the_lock_and_queues_again(tmp_path):
    """THE GIVE-BACK. Another lane lands a change reaching test_beta (timed at ~1 s, over the
    0.5 s limit set here) while this ship's pre-lock tests run. Under the lock the plan says
    test_beta must re-run: ship hands the lock and the ticket back, re-runs it in round 2 BEFORE
    the lock, and queues again; under the second hold only the smoke file runs."""
    env, origin, shared, other, session = _ship_sandbox(tmp_path)
    env.update(BETA_SLEEP='1.0', BETA_LAND=str(tmp_path / 'land_beta.py'), BETA_LAND_TIMES='1',
               EDGELOG_SHIP_LOCKED_TESTS_MAX='0.5')
    p = _ship(env, shared)
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert out.count('LOCK RELEASED: the pre-push tests would re-run') == 1, out
    assert 'PRE-LOCK (round 2 of 3)' in out and 'PRE-LOCK (round 3 of 3)' not in out
    rows = _lock_rows(env)
    assert [r for r in rows if r[0] == 'test_beta'] == [('test_beta', 'unlocked')] * 2, rows
    assert [r for r in rows if r[1] == 'locked'] == [('test_family_vocabulary', 'locked')], rows
    assert _landed_tree_has(env, origin, '# another lane, landing 1')
    # both pre-lock runs were HEAVY (round 1 untimed; round 2 ~1 s, over the 0.5 s set here): the
    # one test slot each time
    assert [r[2] for r in _slot_rows(env) if r[0] == 'test_beta'] == ['tests-1', 'tests-1']
    _assert_free(tmp_path)
    # THE LIGHT RUN. Next ship of the same lane, with the limit at 30 s: its re-run (the changed
    # test file + smoke, all timed far under it) takes a FAST slot, so a two-second re-run never
    # queues behind another lane's 40-minute engine tier for the one test slot.
    env2 = dict(env, EDGELOG_SHIP_LOCKED_TESTS_MAX='30')
    _commit(env2, session, {'tests/test_alpha.py': SANDBOX['tests/test_alpha.py'] + '# two\n'},
            'lane1 again')
    open(env['LOCKLOG'], 'w').close()
    p = _ship(env2, shared)
    assert p.returncode == 0, p.stdout + p.stderr
    assert ('test_alpha', 'unlocked', 'fast-1') in _slot_rows(env2), _slot_rows(env2)
    _assert_free(tmp_path)


def test_after_three_rounds_the_re_run_happens_under_the_lock_rather_than_loop(tmp_path):
    env, origin, shared, other, session = _ship_sandbox(tmp_path)
    env.update(BETA_SLEEP='1.0', BETA_LAND=str(tmp_path / 'land_beta.py'), BETA_LAND_TIMES='3',
               EDGELOG_SHIP_LOCKED_TESTS_MAX='0.5')
    p = _ship(env, shared)
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert out.count('LOCK RELEASED: the pre-push tests would re-run') == 2, out
    assert 'LOCKED: the pre-push tests re-run 2 test file(s)' in out, out
    rows = _lock_rows(env)
    assert [r for r in rows if r[0] == 'test_beta'] == [('test_beta', 'unlocked')] * 3 + [
        ('test_beta', 'locked')], rows
    assert _landed_tree_has(env, origin, '# another lane, landing 3')
    _assert_free(tmp_path)


def _landed_tree_has(env, origin, text):
    return text in _git(env, origin, 'show', 'main:pkg/base_value.py')


def test_ship_stops_before_the_ticket_when_a_pre_lock_test_fails(tmp_path):
    env, origin, shared, other, session = _ship_sandbox(
        tmp_path, test_body=_test_src('test_alpha', body='    assert False, "broken"'))
    before = _git(env, origin, 'rev-parse', 'main')
    p = _ship(env, shared)
    out = p.stdout + p.stderr
    assert p.returncode != 0
    assert 'PRE-LOCK TESTS FAILED before the push lock was taken' in out
    assert 'queued for the push gate' not in out
    qdir = tmp_path / 'home' / 'state' / 'push_queue'
    assert not qdir.exists() or not [n for n in os.listdir(str(qdir)) if n.endswith('.ticket')]
    assert not (tmp_path / 'home' / 'state' / 'push.lock').exists(), 'no lock was ever taken'
    assert _git(env, origin, 'rev-parse', 'main') == before, 'nothing pushed'
    _assert_free(tmp_path)


# Every ship queued on 2026-10-08 runs THIS wt.py (main's since 64bccc16, unchanged through
# 9fb7fd1f): no pre-lock phase, no test stamps. Once this change lands, those ships rebase onto
# it and push through the NEW pre-push hook.
OLD_WT_COMMIT = '64bccc16'


def test_an_already_queued_ship_on_the_OLD_wt_py_gets_the_full_old_tiers_from_the_new_hook(
        tmp_path):
    """COMPATIBILITY. No stamp exists for an old-wt.py ship, so the new hook must run exactly what
    the old one did: the contract tier and the engine tier in full, every test file, nothing
    skipped - and it lands."""
    p = subprocess.run(['git', '-C', ROOT, 'show', OLD_WT_COMMIT + ':tools/wt.py'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.returncode != 0:
        pytest.skip('history without %s (a shallow clone): %s' % (OLD_WT_COMMIT, p.stderr[:80]))
    old = p.stdout
    assert 'def gate_before_lock' not in old and 'hook_tests' not in old, 'really the old one'
    env, origin, shared, other, session = _ship_sandbox(tmp_path, wt_source=old)
    r = _ship(env, shared)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert 'PRE-LOCK' not in out
    assert 'pushed (verified on main)' in out
    assert _counts(env) == dict((n, 1) for n in ALL_TESTS | {'test_strategy_contract'}), (
        'every needed test file ran exactly once, under the lock', _counts(env))
    assert all(r[1] == 'locked' for r in _lock_rows(env)), _lock_rows(env)
    _assert_free(tmp_path)


def test_ship_calls_the_pre_lock_tests_in_its_pre_lock_phase():
    src = open(os.path.join(ROOT, 'tools', 'wt.py'), encoding='utf-8').read()
    body = src[src.index('def gate_before_lock'):src.index('def _release_fd')]
    assert body.index('realign_version(wt)') < body.index('prelock_tests(wt)'), (
        'the tests run on the realigned tree that would ship')
    ship = src[src.index('def cmd_ship'):src.index('def warn_pages_budget')]
    assert ship.index('gate_before_lock(') < ship.index('push_queue.hold_turn(') < ship.index(
        'push_lock.hold(') < ship.index('tests_plan(wt)') < ship.index('_let_go(')
