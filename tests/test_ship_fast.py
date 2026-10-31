"""SHIP = B (OWNER 10-29): wt.py ship --fast pieces - touched-file test pick, the hook bypass."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import hook_tests  # noqa: E402
import wt  # noqa: E402


def _mk(tmp_path, *rels):
    for r in rels:
        p = tmp_path / r
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('x')


def test_touched_tests_picks_only_what_changed(tmp_path):
    _mk(tmp_path, 'tests/test_quiet.py', 'tests/test_runner.py', 'tests/test_strategy_contract.py',
        'tests/test_wt_ship_console.py', 'tests/test_push_lock.py', 'tests/test_other.py')
    got = wt.touched_tests(str(tmp_path), ['tools/quiet.py', 'api/runner.py', 'tools/wt.py',
                                           'index.html', 'tools/nothing.py'])
    assert got == ['tests/test_push_lock.py', 'tests/test_quiet.py', 'tests/test_runner.py',
                   'tests/test_strategy_contract.py', 'tests/test_wt_ship_console.py']


def test_touched_tests_changed_test_file_runs_itself(tmp_path):
    _mk(tmp_path, 'tests/test_other.py', 'tests/test_strategy_contract.py')
    assert wt.touched_tests(str(tmp_path), ['tests/test_other.py']) == [
        'tests/test_other.py', 'tests/test_strategy_contract.py']


def test_touched_tests_no_python_no_tests(tmp_path):
    _mk(tmp_path, 'tests/test_strategy_contract.py')
    assert wt.touched_tests(str(tmp_path), ['index.html', 'CHANGELOG.md']) == []


def test_hook_skips_tiers_on_a_fast_ship(monkeypatch):
    monkeypatch.setenv('EDGELOG_FAST_SHIP', '1')
    lines = []
    monkeypatch.setattr(hook_tests, 'run_tiers', lambda *a, **k: 1 / 0)
    assert hook_tests.cmd_hook(ROOT, '', log=lines.append) == 0
    assert 'fast ship' in lines[0]


def test_hook_runs_tiers_without_the_flag(monkeypatch):
    monkeypatch.delenv('EDGELOG_FAST_SHIP', raising=False)
    monkeypatch.setattr(hook_tests, 'run_tiers', lambda *a, **k: 7)
    assert hook_tests.cmd_hook(ROOT, '', log=lambda s: None) == 7


def test_site_version_reads_index(tmp_path):
    (tmp_path / 'index.html').write_text(open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read(),
                                         encoding='utf-8')
    assert wt.site_version(str(tmp_path)) == wt.site_version(ROOT) is not None
    assert wt.site_version(str(tmp_path / 'nope')) is None


def test_post_push_waits_for_1300_on_market_days():
    import time as _t
    import post_push_tests as pp
    clock = [_t.struct_time((2026, 10, 29, 12, 58, 0, 3, 302, 0))]   # Thu 12:58

    def sleep(s):
        clock[0] = _t.struct_time((2026, 10, 29, 13, 0, 0, 3, 302, 0))
    assert pp.wait_for_window(now=lambda: clock[0], sleep=sleep) == 60
    sat = _t.struct_time((2026, 10, 31, 9, 0, 0, 5, 304, 0))
    assert pp.wait_for_window(now=lambda: sat, sleep=lambda s: 1 / 0) == 0


def test_post_push_one_at_a_time(tmp_path):
    import post_push_tests as pp
    lk = str(tmp_path / 'pp.lock')
    first = pp.hold_one_at_a_time(lk)
    calls = []

    def sleep(s):
        calls.append(s)
        first.close()
    second = pp.hold_one_at_a_time(lk, sleep=sleep)
    assert calls == [30] and second


def test_changed_files_honours_the_post_push_base(monkeypatch):
    seen = []
    monkeypatch.setattr(hook_tests, '_git', lambda root, *a: (seen.append(a), (0, 'x.py'))[1])
    monkeypatch.setenv('EDGELOG_DIFF_BASE', 'abc123')
    assert hook_tests.changed_files(ROOT) == ['x.py']
    assert seen == [('diff', '--no-renames', '--name-only', 'abc123', '--')]


def test_post_push_skips_a_sha_older_than_a_test_machinery_fix():
    import subprocess as sp
    import post_push_tests as pp
    head = sp.run(['git', '-C', ROOT, 'rev-parse', 'origin/main'], capture_output=True,
                  text=True).stdout.strip()
    old = sp.run(['git', '-C', ROOT, 'log', '-1', '--format=%H', head, '--',
                  'tools/githooks/pre-push'], capture_output=True, text=True).stdout.strip()
    assert pp.superseded_by(head, ROOT) is None
    assert pp.superseded_by(old + '~1', ROOT)
