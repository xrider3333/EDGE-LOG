r"""tools/wt.py ship: which gates need the push lock, and which do not (2026-10-07).

THE PROBLEM. ship took the machine-wide push lock and then ran every gate under it, including the
probes' --selftest mutant runs (HOME ~61-75 broken copies of index.html, WEBULL ~221-231: 47
minutes to 2 hours each). On 2026-10-07 one probe-changing ship held the lock from 17:45 while
ten lanes waited, so the machine landed about one ship per one to two hours.

WHAT SHIP DOES NOW. It runs every gate BEFORE the lock and stamps each pass with the tree it
passed on. Under the lock it rebases onto the newest main and re-runs only what that final tree
needs: the fast gates (unless the tree is byte-identical), and a selftest only when a file it
reads changed since it passed - and then it gives the lock back, re-runs it outside, and queues
again (at most 3 rounds, then under the lock).

THE INVARIANTS, each pinned by an end-to-end ship below:
  (a) nothing reaches origin/main unless the final rebased tree passed the fast gates - including
      the retry after a push the remote refused (_assert_fast_gates_passed_on_what_landed);
  (b) a selftest pass is reused only when nothing in its cover changed between the tree it passed
      on and the final tree - the cover being every repo file the probe reads EXCEPT index.html
      (tools/wt.py's docstring says why; test_a_selftest_cover_lists_every_repo_file_its_probe_reads
      keeps the cover honest);
  (c) the push lock and the ticket are free for the next lane on every exit: success, a gate
      failing under the lock, Ctrl-C, a hard kill with an orphaned gate, and the one hand release
      before a re-queue (_assert_lock_and_queue_free, test_let_go_...);
  (d) the VERSION / CHANGELOG realign and the RESEARCH_LEDGER renumbering run under the lock after
      the final rebase;
  (e) a gate failing before the lock fails exactly as before - same message, nothing pushed - and
      no lock or ticket is ever taken.
Plus the adversarial cases found reviewing it: a file edited while a gate runs (the pass is not
stamped), and two ships of one worktree at once (the second is refused).

Two kinds of test here:
  - unit tests of the reuse rule and the stamp, with fake trees and a fake `changed` (no git);
  - end-to-end ships in a throwaway origin + shared checkout + worktree (the same sandbox shape
    as test_wt_ship_console.py), whose gates are FAKE scripts that log whether the push lock was
    held when they ran and which tree they ran on, and whose selftest can land "another lane's"
    commit on origin while it runs. Only a real ship in a real sandbox can say what ran under
    the lock.
Nothing here touches this repository, C:\EdgeLog or the real push lock: EDGELOG_HOME points into
tmp_path.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import wt  # noqa: E402


def _gate(key):
    return [g for g in wt.GATES if g.key == key][0]


def _never(*a):
    raise AssertionError('changed() must not be consulted here: %r' % (a,))


# =========================================================== the gate table never loses a gate
def test_every_gate_ship_has_run_is_still_in_the_table_in_the_same_order():
    """Never weaken a gate: the table is every gate cmd_ship ran inline before 2026-10-07, in the
    same order, with the same failure message - nothing was dropped in the move - plus the PAPER
    selftest (2026-10-08, TRADING-LOG #67 / MANAGER #667), the one gate added since."""
    assert [(g.key, g.fail) for g in wt.GATES] == [
        ('boot', 'boot gate FAILED - not pushing'),
        ('studies', 'studies render gate FAILED - not pushing'),
        ('paper', 'paper render gate FAILED - not pushing'),
        ('paper-selftest', 'PAPER gate SELF-TEST FAILED - the gate no longer catches a '
                           'deliberately broken build - not pushing'),
        ('report', 'run-report render gate FAILED - not pushing'),
        ('report-selftest', 'run-report gate SELF-TEST FAILED - the gate no longer catches a '
                            'known-bad build - not pushing'),
        ('axes', '1E axes / 1A funnel render gate FAILED - not pushing'),
        ('cmp2', 'COMPARE beta (cmp2) render gate FAILED - not pushing'),
        ('importtz', 'import time-zone gate FAILED - not pushing'),
        ('importtz-selftest', 'import time-zone gate SELF-TEST FAILED - the gate no longer '
                              'catches the pre-fix build - not pushing'),
        ('home', 'HOME render gate FAILED - not pushing'),
        ('home-selftest', 'HOME gate SELF-TEST FAILED - the gate no longer catches a '
                          'deliberately broken build - not pushing'),
        ('webull', 'WEBULL PAPER render gate FAILED - not pushing'),
        ('webull-selftest', 'WEBULL gate SELF-TEST FAILED - the gate no longer catches a '
                            'deliberately broken build - not pushing'),
        ('registry', 'STUDIES registry gate FAILED - not pushing.'),
    ]


def test_the_triggers_are_the_ones_ship_always_used():
    trig = dict((g.key, g.trigger) for g in wt.GATES)
    assert trig['boot'] == 'always'
    for k in ('studies', 'paper', 'report', 'axes', 'cmp2', 'importtz', 'home', 'webull',
              'registry'):
        assert trig[k] == 'index', k
    assert trig['report-selftest'] == ('tools/report_render_probe.py',
                                       'tools/fixtures/run_report.json')
    assert trig['importtz-selftest'] == ('tools/import_tz_probe.py',)
    assert trig['home-selftest'] == ('tools/home_render_probe.py',)
    assert trig['webull-selftest'] == ('tools/webull_board_probe.py',
                                       'tools/fixtures/qqq_exec_box1005.json')
    assert trig['paper-selftest'] == ('tools/paper_render_probe.py',
                                      'tools/fixtures/paper_board.json')


def test_the_paper_selftest_row_is_the_one_trading_log_specified():
    """MANAGER #667, verbatim - except that the cover also lists tools/ledger_removed.py, which
    the probe imports (the cover test caught it) - and the probe on this tree really takes those
    options."""
    g = _gate('paper-selftest')
    assert (g.label, g.script, g.prefix, g.args, g.slow) == (
        'PAPER gate SELF-TEST', 'tools/paper_render_probe.py', 'SELFTEST',
        ('--selftest', '--jobs', '3'), True)
    assert g.empty == '(paper probe self-test produced no output)'
    assert g.cover == ('tools/paper_render_probe.py', 'tools/fixtures/paper_board.json',
                       'tools/kill_on_exit.py', 'tools/ledger_removed.py')
    assert g.pick('-- mutant x: caught\nSELFTEST: PASS -- 9/9') == 'SELFTEST: PASS -- 9/9'
    assert g.pick('SELFTEST (only 2 mutants): PASS -- each') == 'SELFTEST (only 2 mutants): PASS -- each'
    assert wt.gate_command(ROOT, ROOT, g)[-3:] == ['--selftest', '--jobs', '3']


def test_a_selftest_whose_probe_lacks_its_options_does_not_apply(tmp_path):
    """An older probe without --selftest (or --jobs) would exit 2 on argparse - and an
    INCONCLUSIVE selftest stops a ship. So such a row skips, as a row whose script is missing
    always has."""
    (tmp_path / 'tools').mkdir()
    probe = tmp_path / 'tools' / 'paper_render_probe.py'
    probe.write_text("import argparse\nap = argparse.ArgumentParser()\n"
                     "ap.add_argument('--selftest', action='store_true')\n", encoding='utf-8')
    g = _gate('paper-selftest')
    assert wt.gate_command(str(tmp_path), str(tmp_path), g) is None, 'no --jobs: does not apply'
    probe.write_text(probe.read_text(encoding='utf-8') + "ap.add_argument('--jobs', type=int)\n",
                     encoding='utf-8')
    assert wt.gate_command(str(tmp_path), str(tmp_path), g)[-3:] == ['--selftest', '--jobs', '3']
    assert wt.gate_command(str(tmp_path), str(tmp_path), _gate('paper'))[-1].endswith(
        'paper_render_probe.py'), 'the plain probe takes no options and always applies'


def test_the_slow_gates_are_exactly_the_selftests():
    slow = [g for g in wt.GATES if g.slow]
    assert [g.key for g in slow] == ['paper-selftest', 'report-selftest', 'importtz-selftest',
                                     'home-selftest', 'webull-selftest']
    for g in slow:
        assert '--selftest' in g.args
        assert set(g.trigger) <= set(g.cover), 'a selftest is keyed on at least its trigger'
        assert 'index.html' not in g.cover, 'see the wt.py docstring: why not index.html'


def _repo_reads(rel, seen):
    """The repo files tools/<rel> reads: every tools/ module it imports - and, transitively,
    what THOSE import - and every tools/fixtures/ file it names."""
    src = open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8').read()
    out = set()
    for m in re.finditer(r'^\s*(?:import\s+(\w+)|from\s+(\w+)\s+import)', src, re.M):
        name = m.group(1) or m.group(2)
        path = 'tools/%s.py' % name
        if os.path.isfile(os.path.join(TOOLS, name + '.py')) and path not in seen:
            seen.add(path)
            out.add(path)
            out |= _repo_reads(path, seen)
    for m in re.finditer(r"'fixtures',\s*'([^']+)'|tools/fixtures/([\w.\-]+)", src):
        out.add('tools/fixtures/' + (m.group(1) or m.group(2)))
    return out


@pytest.mark.parametrize('key', ['paper-selftest', 'report-selftest', 'importtz-selftest',
                                 'home-selftest', 'webull-selftest'])
def test_a_selftest_cover_lists_every_repo_file_its_probe_reads(key):
    """The reuse rule is only as good as the cover. A probe that starts importing another tool
    (or a tool it imports starts importing one), or reading another fixture, without its cover
    saying so would let a selftest be reused across a change to that file - so this reads the
    probe itself and fails on anything unlisted. (2026-10-08: main wired tools/kill_on_exit.py
    into the run-report and import time-zone probes, and this caught both covers missing it.)"""
    g = _gate(key)
    reads = _repo_reads(g.script, {g.script})
    reads.discard(g.script)
    missing = sorted(reads - set(g.cover))
    assert not missing, '%s reads %s - add it to that Gate\'s cover in tools/wt.py' % (key, missing)


def test_every_chrome_selftest_cover_carries_kill_on_exit():
    """MANAGER #667: TRADING-LOG's queued ships wire tools/kill_on_exit.py into the HOME and
    WEBULL probes. Listed in every selftest cover NOW, so the cover test above does not go red
    for whichever lane runs the engine tier after those ships land."""
    for g in wt.GATES:
        if g.slow:
            assert 'tools/kill_on_exit.py' in g.cover, g.key


def test_a_gate_prints_the_line_it_always_printed():
    assert _gate('home').pick('noise\nHOMEPROBE: PASS (x)\nmore') == 'HOMEPROBE: PASS (x)'
    assert _gate('home').pick('nothing useful') == '(HOME probe produced no output)'
    assert _gate('paper').pick('PAPERPROBE: PASS\nsecond') == 'PAPERPROBE: PASS'
    assert _gate('studies').pick('first\nSTUDIES PROBE: PASS') == 'STUDIES PROBE: PASS'
    assert _gate('boot').pick('') == '(preflight produced no output)'
    assert _gate('webull-selftest').pick('SELFTEST: x\n-- m\nSELFTEST: PASS') == 'SELFTEST: PASS'


# =========================================================== the reuse rule
def _stamp(**gates):
    return {'key': wt.gates_key(), 'gates': gates}


def test_a_fast_gate_is_reused_only_on_the_exact_tree_it_passed_on():
    st = _stamp(home={'tree': 'T1', 'at': '18:00', 'line': 'HOMEPROBE: PASS'})
    assert 'exact tree' in wt.reuse_reason(_gate('home'), st, 'T1', _never)
    # a different tree means it runs again - and the cover rule is never even consulted
    assert wt.reuse_reason(_gate('home'), st, 'T2', _never) is None


def test_a_selftest_is_reused_when_nothing_it_reads_changed():
    g = _gate('webull-selftest')
    st = _stamp(**{'webull-selftest': {'tree': 'T1', 'at': '18:00', 'line': 'SELFTEST: PASS'}})
    seen = []

    def changed(a, b, paths):
        seen.append((a, b, list(paths)))
        return []
    why = wt.reuse_reason(g, st, 'T2', changed)
    assert why and 'tools/webull_board_probe.py' in why and 'tools/ledger_removed.py' in why
    assert seen == [('T1', 'T2', list(g.cover))], 'compared against the tree it really ran on'


def test_a_selftest_re_runs_when_a_file_it_reads_changed():
    g = _gate('home-selftest')
    st = _stamp(**{'home-selftest': {'tree': 'T1', 'at': '18:00', 'line': 'SELFTEST: PASS'}})
    assert wt.reuse_reason(g, st, 'T2', lambda a, b, p: ['tools/home_render_probe.py']) is None
    assert 'tools/home_render_probe.py' in wt.rerun_reason(
        g, st, 'T2', lambda a, b, p: ['tools/home_render_probe.py'])


def test_when_git_cannot_compare_the_trees_the_selftest_re_runs():
    g = _gate('home-selftest')
    st = _stamp(**{'home-selftest': {'tree': 'GONE', 'at': '18:00', 'line': 'SELFTEST: PASS'}})
    assert wt.reuse_reason(g, st, 'T2', lambda a, b, p: None) is None


def test_no_record_means_run_it():
    assert wt.reuse_reason(_gate('home-selftest'), _stamp(), 'T1', _never) is None
    assert wt.reuse_reason(_gate('home-selftest'), None, 'T1', _never) is None
    st = _stamp(**{'home-selftest': {'at': '18:00'}})                 # no tree recorded
    assert wt.reuse_reason(_gate('home-selftest'), st, 'T1', _never) is None
    assert 'no pass recorded' in wt.rerun_reason(_gate('home-selftest'), _stamp(), 'T1', _never)


def test_a_record_for_one_gate_never_vouches_for_another():
    st = _stamp(home={'tree': 'T1', 'at': '18:00', 'line': 'HOMEPROBE: PASS'})
    assert wt.reuse_reason(_gate('home-selftest'), st, 'T1', _never) is None
    assert wt.reuse_reason(_gate('webull'), st, 'T1', _never) is None


def test_only_a_slow_selftest_is_worth_giving_the_lock_back_for(monkeypatch):
    g = _gate('home-selftest')
    monkeypatch.delenv('EDGELOG_SHIP_LOCKED_RERUN_MAX', raising=False)
    assert wt.too_slow_for_the_lock(g, _stamp()) is True, 'never measured counts as slow'
    assert wt.too_slow_for_the_lock(g, _stamp(**{'home-selftest': {'tree': 'T', 'secs': None}}))
    assert wt.too_slow_for_the_lock(g, _stamp(**{'home-selftest': {'tree': 'T', 'secs': 2852.0}}))
    assert not wt.too_slow_for_the_lock(g, _stamp(**{'home-selftest': {'tree': 'T', 'secs': 12.5}}))
    monkeypatch.setenv('EDGELOG_SHIP_LOCKED_RERUN_MAX', '5')
    assert wt.too_slow_for_the_lock(g, _stamp(**{'home-selftest': {'tree': 'T', 'secs': 12.5}}))
    monkeypatch.setenv('EDGELOG_SHIP_LOCKED_RERUN_MAX', 'nonsense')
    assert wt.locked_rerun_max() == wt.LOCKED_RERUN_MAX_SECONDS


# =========================================================== the stamp
def test_the_stamp_round_trips(tmp_path):
    p = str(tmp_path / 'stamp.json')
    st = wt.load_stamp(p, wt.gates_key())
    assert st == {'key': wt.gates_key(), 'gates': {}}
    wt.record_pass(st, _gate('home'), 'T1', 'B1', 'HOMEPROBE: PASS', 'pre-lock')
    wt.save_stamp(p, st)
    back = wt.load_stamp(p, wt.gates_key())
    assert back['gates']['home']['tree'] == 'T1' and back['gates']['home']['base'] == 'B1'
    assert back['gates']['home']['line'] == 'HOMEPROBE: PASS'


def test_a_corrupt_or_foreign_stamp_only_means_re_run(tmp_path):
    p = tmp_path / 'stamp.json'
    p.write_text('{not json', encoding='utf-8')
    assert wt.load_stamp(str(p), wt.gates_key())['gates'] == {}
    p.write_text(json.dumps({'key': 'some other gate list', 'gates': {'home': {'tree': 'T1'}}}),
                 encoding='utf-8')
    assert wt.load_stamp(str(p), wt.gates_key())['gates'] == {}
    assert wt.load_stamp(str(tmp_path / 'missing.json'), wt.gates_key())['gates'] == {}


def test_a_stamp_that_cannot_be_written_never_stops_a_ship(tmp_path):
    wt.save_stamp(str(tmp_path / 'no' / 'such' / 'dir' / 'stamp.json'), _stamp())
    wt.save_stamp(None, _stamp())


def test_the_gate_list_version_changes_with_the_gate_list(monkeypatch):
    k0 = wt.gates_key()
    assert k0.startswith(wt.GATE_LIST_VERSION + '/')
    rows = list(wt.GATES)
    i = [g.key for g in rows].index('webull-selftest')
    g = rows[i]
    rows[i] = wt.Gate(g.key, g.label, g.script, g.trigger, g.fail, g.empty, prefix=g.prefix,
                      args=g.args, slow=g.slow, cover=g.cover[:1])
    monkeypatch.setattr(wt, 'GATES', rows)
    assert wt.gates_key() != k0, 'a narrower cover is a different gate list'
    monkeypatch.setattr(wt, 'GATES', list(wt.GATES))
    monkeypatch.setattr(wt, 'GATE_LIST_VERSION', 'later')
    assert wt.gates_key() != k0


# =========================================================== the one hand release
_TRY_LOCK = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
import push_lock
fd = os.open(sys.argv[2], os.O_RDWR)
try:
    push_lock._lock_fd(fd)
except OSError:
    print('held')
else:
    push_lock._unlock_fd(fd)
    print('free')
'''


def _other_process_sees(path):
    """'held' or 'free': the push lock as ANOTHER process sees it (a waiting lane)."""
    p = subprocess.run([sys.executable, '-c', _TRY_LOCK, TOOLS, str(path)], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def test_let_go_hands_the_lock_and_the_ticket_back_at_once(tmp_path, monkeypatch):
    """The one place ship releases by hand must really release - at once, not whenever Windows
    gets round to closing the handle: msvcrt unlocks the byte at the CURRENT position, and both
    holders wrote their name past byte 0 after locking it."""
    import push_lock
    import push_queue
    monkeypatch.setenv('EDGELOG_HOME', str(tmp_path / 'home'))
    quiet = lambda *a: None                                      # noqa: E731
    ticket = push_queue.hold_turn(who='lane-a', log=quiet)
    fd = push_lock.hold(who='lane-a', log=quiet)
    assert ticket[0] is not None and fd is not None
    assert _other_process_sees(push_lock.lock_path()) == 'held'
    assert len(push_queue.live_tickets()) == 1
    ticket, fd = wt._let_go(ticket, fd)
    assert ticket == (None, None) and fd is None
    assert _other_process_sees(push_lock.lock_path()) == 'free'
    assert push_queue.live_tickets() == []
    assert not [n for n in os.listdir(push_queue.queue_dir()) if n.endswith('.ticket')]
    # and a second call (or one with nothing held) is harmless
    assert wt._let_go(ticket, fd) == ((None, None), None)


# =========================================================== end to end: real ships, fake gates
FAKE_GATE = r'''# probe v1
import os, subprocess, sys, time
NAME = os.path.basename(__file__)[:-3]
MODE = 'selftest' if '--selftest' in sys.argv else 'plain'
ME = NAME + ' ' + MODE
sys.path.insert(0, os.environ['FAKE_TOOLS'])
import push_lock, push_queue
lock = os.path.join(os.environ['EDGELOG_HOME'], 'state', 'push.lock')
held = False
if os.path.exists(lock):
    fd = os.open(lock, os.O_RDWR)
    try:
        try:
            push_lock._lock_fd(fd)
        except OSError:
            held = True
        else:
            push_lock._unlock_fd(fd)
    finally:
        os.close(fd)
qdir = os.path.join(os.environ['EDGELOG_HOME'], 'state', 'push_queue')
tickets = len(push_queue.live_tickets(qdir)) if os.path.isdir(qdir) else 0
genv = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], capture_output=True, text=True,
                      env=genv).stdout.strip()
with open(os.environ['FAKE_LOG'], 'a') as f:
    f.write('%s %s\n' % (ME, 'locked' if held else 'unlocked'))
with open(os.environ['FAKE_TREES'], 'a') as f:
    f.write('%s %s %s tickets=%d\n' % (ME, 'locked' if held else 'unlocked', tree, tickets))
if os.environ.get('FAKE_DIRTY') == ME:              # the lane edits a file while the gate runs
    with open('index.html', 'a', encoding='utf-8') as f:
        f.write('<!-- edited while the gate ran -->\n')
if MODE == 'selftest' and not held and os.environ.get('FAKE_LAND'):
    subprocess.run([sys.executable, os.environ['FAKE_LAND']], check=True)
if held and os.environ.get('FAKE_BLOCK_LOCKED') == ME:  # hang under the lock until released
    marker = os.environ['FAKE_BLOCK_MARKER']
    open(marker, 'w').close()
    t_end = time.time() + 120
    while time.time() < t_end and not os.path.exists(os.environ['FAKE_BLOCK_RELEASE']):
        time.sleep(0.1)
    open(marker + '.done', 'w').close()
if os.environ.get('FAKE_FAIL') == ME or (held and os.environ.get('FAKE_FAIL_LOCKED') == ME):
    print('SELFTEST: FAIL (fake)')
    sys.exit(1)
if NAME == 'preflight_boot':
    print('PREFLIGHT: PASS (fake)')
elif MODE == 'selftest':
    print('-- mutant m1: expect FAIL')
    print('SELFTEST: PASS -- gate caught 1/1 broken builds (fake)')
else:
    print('HOMEPROBE: PASS (fake)')
# filler, so another lane's change at the bottom of this file never touches this lane's change
# at the top of it
#
#
#
#
#
#
#
'''

# "Another lane" landing on origin while a gate runs, the way a real ship lands: it bumps VERSION
# (FAKE_LAND_BUMPS times, one commit each), appends a line to FAKE_LAND_FILE when one is named,
# and with FAKE_LAND_LEDGER_ROW adds that RESEARCH_LEDGER row where this lane added its own.
LAND = r'''
import os, re, subprocess, sys
count_file = os.environ['FAKE_LAND_COUNT']
n = int(open(count_file).read()) if os.path.exists(count_file) else 0
if n >= int(os.environ.get('FAKE_LAND_TIMES', '1')):
    sys.exit(0)
open(count_file, 'w').write(str(n + 1))
other = os.environ['FAKE_OTHER']
# run from a gate OR a git hook: no GIT_* variable from either may point this at another repo
env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
env.update(GIT_AUTHOR_NAME='other lane', GIT_AUTHOR_EMAIL='other@example.invalid',
           GIT_COMMITTER_NAME='other lane', GIT_COMMITTER_EMAIL='other@example.invalid')
def git(*a):
    subprocess.run(['git', '-C', other] + list(a), check=True, capture_output=True, env=env)
git('fetch', '-q', 'origin')
git('reset', '-q', '--hard', 'origin/main')
for b in range(int(os.environ.get('FAKE_LAND_BUMPS', '1'))):
    p = os.path.join(other, 'index.html')
    txt = open(p, encoding='utf-8', newline='').read()
    m = re.search(r"const VERSION='(\d+)\.(\d+)'", txt)
    txt = txt.replace(m.group(0), "const VERSION='%s.%d'" % (m.group(1), int(m.group(2)) + 1), 1)
    open(p, 'w', encoding='utf-8', newline='').write(txt)
    if os.environ.get('FAKE_LAND_FILE'):
        with open(os.path.join(other, os.environ['FAKE_LAND_FILE']), 'a', encoding='utf-8') as f:
            f.write('# another lane, landing %d.%d\n' % (n + 1, b))
    row = os.environ.get('FAKE_LAND_LEDGER_ROW')
    if row and b == 0:
        lp = os.path.join(other, 'RESEARCH_LEDGER.md')
        txt = open(lp, encoding='utf-8', newline='').read()
        nl = '\r\n' if '\r\n' in txt else '\n'
        anchor = '| 2.2 | seed |' + nl
        assert anchor in txt, txt
        open(lp, 'w', encoding='utf-8', newline='').write(txt.replace(anchor, anchor + row + nl, 1))
    git('add', '-A')
    git('commit', '-q', '-m', 'another lane %d.%d' % (n + 1, b))
git('push', '-q', 'origin', 'HEAD:main')
'''

INDEX = ("<!doctype html>\n<script>\nconst VERSION='1.1';\n" + "// filler\n" * 12 +
         "const CHANGELOG=[{v:'1.1',date:'2026-10-07',notes:['seed']}];\n</script>\n")

LEDGER = ("# RESEARCH LEDGER\n\n## 2. Round two\n\n| # | what |\n|---|---|\n| 2.1 | seed |\n"
          "| 2.2 | seed |\n\n## 3. Round three\n\n| # | what |\n|---|---|\n| 3.1 | seed |\n")


def _env(tmp_path, **extra):
    # No GIT_* variable from a hook's environment may reach the sandbox (see
    # test_wt_ship_console.py): it would make sandbox git act on THIS repository.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update({
        'GIT_AUTHOR_NAME': 'wt test', 'GIT_AUTHOR_EMAIL': 'wt-test@example.invalid',
        'GIT_COMMITTER_NAME': 'wt test', 'GIT_COMMITTER_EMAIL': 'wt-test@example.invalid',
        'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1',
        'EDGELOG_WT_BACKUP_ROOT': str(tmp_path / 'wt_backup'),
        'EDGELOG_HOME': str(tmp_path / 'home'),          # the push lock + queue live here
        'FAKE_LOG': str(tmp_path / 'gates.log'),
        'FAKE_TREES': str(tmp_path / 'trees.log'),
        'FAKE_TOOLS': str(tmp_path / 'shared' / 'tools'),
        'FAKE_OTHER': str(tmp_path / 'other'),
        'FAKE_LAND_COUNT': str(tmp_path / 'land.count'),
    })
    for k in ('EDGELOG_SHIP_LOCKED_RERUN_MAX', 'EDGELOG_GATE_PASSED_TREE', 'FAKE_LAND',
              'FAKE_FAIL', 'FAKE_FAIL_LOCKED', 'FAKE_DIRTY', 'FAKE_HOOK_FAIL', 'FAKE_HOOK_LAND',
              'FAKE_BLOCK_LOCKED', 'FAKE_BLOCK_MARKER', 'FAKE_BLOCK_RELEASE',
              'FAKE_LAND_FILE', 'FAKE_LAND_BUMPS', 'FAKE_LAND_TIMES', 'FAKE_LAND_LEDGER_ROW'):
        env.pop(k, None)                  # only what a test asks for, never the caller's
    env.update(extra)
    return env


def _git(env, cwd, *args):
    p = subprocess.run(['git', '-C', str(cwd)] + list(args), env=env, capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    assert p.returncode == 0, 'git %s failed:\n%s%s' % (' '.join(args), p.stdout, p.stderr)
    return p.stdout.strip()


def _sandbox(tmp_path, env, ledger=False, changelog=False):
    """origin (bare) <- shared checkout on main holding the real wt.py / push_lock / push_queue and
    two fake gates (boot + HOME, so HOME's selftest exists) <- a session worktree with one commit
    that changes the HOME probe (so its selftest applies) - and a second clone, 'other', that
    plays the other lanes. ledger=True seeds a RESEARCH_LEDGER.md and has the session add row
    2.3; changelog=True has the session add its own CHANGELOG entry (tagged 9.9, a guess the
    realign must correct)."""
    origin, shared, session = tmp_path / 'origin.git', tmp_path / 'shared', tmp_path / 'session'
    _git(env, tmp_path, 'init', '-q', '--bare', '-b', 'main', str(origin))
    _git(env, tmp_path, 'init', '-q', '-b', 'main', str(shared))
    _git(env, shared, 'remote', 'add', 'origin', str(origin))
    (shared / 'tools').mkdir()
    for f in ('wt.py', 'push_lock.py', 'push_queue.py'):
        shutil.copy2(os.path.join(TOOLS, f), str(shared / 'tools' / f))
    (shared / 'tools' / 'preflight_boot.py').write_text(FAKE_GATE, encoding='utf-8')
    (shared / 'tools' / 'home_render_probe.py').write_text(FAKE_GATE, encoding='utf-8')
    (shared / 'index.html').write_text(INDEX, encoding='utf-8')
    if ledger:
        (shared / 'RESEARCH_LEDGER.md').write_text(LEDGER, encoding='utf-8')
    _git(env, shared, 'add', '-A')
    _git(env, shared, 'commit', '-q', '-m', 'seed')
    _git(env, shared, 'push', '-q', 'origin', 'main')
    _git(env, shared, 'worktree', 'add', '-q', '-b', 'session/prelock', str(session),
         'origin/main')
    probe = session / 'tools' / 'home_render_probe.py'
    probe.write_text(probe.read_text(encoding='utf-8').replace('# probe v1', '# probe v2 (lane)', 1),
                     encoding='utf-8')
    if ledger:
        lp = session / 'RESEARCH_LEDGER.md'
        lp.write_text(lp.read_text(encoding='utf-8').replace(
            '| 2.2 | seed |\n', '| 2.2 | seed |\n| 2.3 | lane row |\n', 1), encoding='utf-8')
    if changelog:
        ip = session / 'index.html'
        ip.write_text(ip.read_text(encoding='utf-8').replace(
            "const CHANGELOG=[{v:'1.1',",
            "const CHANGELOG=[{v:'9.9',date:'2026-10-08',notes:['lane']},\n{v:'1.1',", 1),
            encoding='utf-8')
    _git(env, session, 'add', '-A')
    _git(env, session, 'commit', '-q', '-m', 'HOME probe: a new mutant')
    _git(env, tmp_path, 'clone', '-q', str(origin), str(tmp_path / 'other'))
    (tmp_path / 'land.py').write_text(LAND, encoding='utf-8')
    return origin, shared, session


def _ship(env, shared, session):
    p = subprocess.run([sys.executable, str(shared / 'tools' / 'wt.py'), 'ship'], cwd=str(session),
                       env=env, capture_output=True, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')


def _log(tmp_path):
    p = tmp_path / 'gates.log'
    return p.read_text(encoding='utf-8').split('\n')[:-1] if p.exists() else []


def _trees(tmp_path):
    """[(gate, mode, 'locked'|'unlocked', tree it ran on, live tickets)] in the order they ran."""
    p = tmp_path / 'trees.log'
    rows = p.read_text(encoding='utf-8').split('\n')[:-1] if p.exists() else []
    return [tuple(r.split()[:4]) + (int(r.split()[4].split('=')[1]),) for r in rows]


def _landed(env, origin, session):
    head = _git(env, session, 'rev-parse', 'HEAD')
    return _git(env, origin, 'rev-parse', 'main') == head


def _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path):
    """INVARIANT (a): the tree on origin/main is the tree the LAST run of every fast gate saw."""
    landed = _git(env, origin, 'rev-parse', 'main^{tree}')
    for gate in ('preflight_boot', 'home_render_probe'):
        runs = [r for r in _trees(tmp_path) if r[0] == gate and r[1] == 'plain']
        assert runs and runs[-1][3] == landed, (gate, runs, landed)


def _assert_lock_and_queue_free(tmp_path):
    """INVARIANT (c), as the next lane sees it once this ship's process is gone: the push lock
    can be taken and no ticket is live. (A lock file that was never created is free too.)"""
    import push_queue
    state = tmp_path / 'home' / 'state'
    path = state / 'push.lock'
    if path.exists():
        deadline = time.time() + 10
        while _other_process_sees(path) != 'free':
            assert time.time() < deadline, 'the push lock outlived the ship that held it'
            time.sleep(0.2)
    qdir = state / 'push_queue'
    assert not (qdir.exists() and push_queue.live_tickets(str(qdir))), 'a ticket outlived its ship'


def test_quiet_main_every_gate_runs_before_the_lock_and_nothing_runs_under_it(tmp_path):
    env = _env(tmp_path)
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    assert sorted(_log(tmp_path)) == ['home_render_probe plain unlocked',
                                      'home_render_probe selftest unlocked',
                                      'preflight_boot plain unlocked'], out
    assert 'PRE-LOCK (round 1 of 3)' in out
    assert 'LOCKED: origin/main has not moved since the pre-lock run' in out
    assert out.count('reused from the pre-lock run: ') == 3, out
    assert 'reused from the pre-lock run: HOME gate SELF-TEST - SELFTEST: PASS' in out
    assert 'LOCKED: 0 gate(s) run under the lock, 3 reused from the pre-lock run' in out
    assert 'lock phase took ' in out
    assert 'pushed (verified on main): ' in out
    # (a) the gates ran before the lock - on exactly the tree that landed
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
    # nobody held a ticket while the gates ran, and nothing is held once the ship is done
    assert all(r[4] == 0 for r in _trees(tmp_path)), _trees(tmp_path)
    _assert_lock_and_queue_free(tmp_path)


def test_main_moved_elsewhere_the_selftest_is_reused_and_the_fast_gates_rerun_locked(tmp_path):
    """Another lane lands two commits (two VERSION bumps, so this ship's own pre-lock VERSION
    realign now CONFLICTS with main's and has to be settled on the way) touching nothing the
    HOME selftest reads. The selftest must not run again; the fast gates must, under the lock,
    on the final tree."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'), FAKE_LAND_FILE='other.txt',
               FAKE_LAND_BUMPS='2')
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    log = _log(tmp_path)
    assert log.count('home_render_probe selftest unlocked') == 1, out
    assert 'home_render_probe selftest locked' not in log, out
    assert log.count('home_render_probe plain locked') == 1, out
    assert log.count('preflight_boot plain locked') == 1, out
    assert 'LOCKED: origin/main moved 2 commit(s) since the pre-lock run' in out, out
    assert ('reused from the pre-lock run: HOME gate SELF-TEST - SELFTEST: PASS -- gate caught '
            '1/1 broken builds (fake) (passed at ') in out, out
    assert 'differs from this one only outside tools/home_render_probe.py, tools/ledger_removed.py' in out
    assert 'LOCKED: 2 gate(s) run under the lock, 1 reused from the pre-lock run' in out, out
    # the ship carries main's VERSION + 1, and both lanes' work is on main
    idx = _git(env, origin, 'show', 'main:index.html')
    assert "const VERSION='1.4';" in idx, idx
    assert 'another lane' in _git(env, origin, 'show', 'main:other.txt')
    assert '# probe v2 (lane)' in _git(env, origin, 'show', 'main:tools/home_render_probe.py')
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
    _assert_lock_and_queue_free(tmp_path)


def test_main_changed_the_probe_the_lock_is_given_back_and_the_selftest_reruns_outside(tmp_path):
    # EDGELOG_SHIP_LOCKED_RERUN_MAX=-1: the fake selftest takes no time, so without this it would
    # count as QUICK and simply re-run under the lock (the next test covers that case).
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'),
               FAKE_LAND_FILE='tools/home_render_probe.py', EDGELOG_SHIP_LOCKED_RERUN_MAX='-1')
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    log = _log(tmp_path)
    assert log.count('home_render_probe selftest unlocked') == 2, out
    assert 'home_render_probe selftest locked' not in log, out
    assert ('LOCK RELEASED: HOME gate SELF-TEST must re-run - main changed '
            'tools/home_render_probe.py since it passed. Nothing was pushed') in out, out
    assert 'PRE-LOCK (round 2 of 3)' in out and 'PRE-LOCK (round 3 of 3)' not in out
    probe = _git(env, origin, 'show', 'main:tools/home_render_probe.py')
    assert '# probe v2 (lane)' in probe and '# another lane, landing 1.0' in probe
    # (c) while the selftest re-ran outside, this lane held NEITHER the lock nor a ticket - the
    # next lane really could go - and the selftest that vouches for the push ran on a tree whose
    # probe is the one that landed (the round-2 tree; main did not move again)
    second = [r for r in _trees(tmp_path) if r[:2] == ('home_render_probe', 'selftest')][1]
    assert second[2] == 'unlocked' and second[4] == 0, second
    assert second[3] == _git(env, origin, 'rev-parse', 'main^{tree}')
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
    _assert_lock_and_queue_free(tmp_path)


def test_main_changed_a_file_the_selftest_reads_but_is_not_keyed_on_and_it_reruns(tmp_path):
    """INVARIANT (b) beyond the trigger: tools/ledger_removed.py never made ship RUN the HOME
    selftest, but the selftest reads it - so a pass from before main changed it must not vouch
    for the tree after."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'),
               FAKE_LAND_FILE='tools/ledger_removed.py', EDGELOG_SHIP_LOCKED_RERUN_MAX='-1')
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    assert ('LOCK RELEASED: HOME gate SELF-TEST must re-run - main changed '
            'tools/ledger_removed.py since it passed') in out, out
    runs = [r for r in _trees(tmp_path) if r[:2] == ('home_render_probe', 'selftest')]
    assert len(runs) == 2 and runs[-1][3] == _git(env, origin, 'rev-parse', 'main^{tree}'), runs


def test_a_quick_selftest_main_invalidated_reruns_under_the_lock_instead_of_requeueing(tmp_path):
    """The run-report and import time-zone selftests take seconds; giving the lock back for one
    of those would cost the lane a whole trip through the queue to save the others seconds."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'),
               FAKE_LAND_FILE='tools/home_render_probe.py')
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    log = _log(tmp_path)
    assert log.count('home_render_probe selftest unlocked') == 1, out
    assert log.count('home_render_probe selftest locked') == 1, out
    assert 'LOCK RELEASED' not in out and 'PRE-LOCK (round 2 of 3)' not in out, out
    assert re.search(r'HOME gate SELF-TEST must re-run - main changed tools/home_render_probe.py '
                     r'since it passed - and it took [0-9.]+s last time, so it re-runs under the '
                     r'lock', out), out


def test_after_three_rounds_the_selftest_runs_under_the_lock_rather_than_loop(tmp_path):
    """main changes the probe every time the selftest runs outside the lock - three rounds, then
    it runs under the lock (where nobody else can land) and the ship goes."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'),
               FAKE_LAND_FILE='tools/home_render_probe.py', FAKE_LAND_TIMES='99',
               EDGELOG_SHIP_LOCKED_RERUN_MAX='-1')
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    log = _log(tmp_path)
    assert log.count('home_render_probe selftest unlocked') == 3, out
    assert log.count('home_render_probe selftest locked') == 1, out
    assert out.count('LOCK RELEASED: ') == 2, out
    assert ('HOME gate SELF-TEST must re-run - main changed tools/home_render_probe.py since it '
            'passed - and all 3 pre-lock rounds are used, so it runs UNDER the push lock') in out
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
    _assert_lock_and_queue_free(tmp_path)


def test_the_realign_and_the_ledger_renumbering_happen_under_the_lock_after_the_final_rebase(
        tmp_path):
    """INVARIANT (d). While this ship's selftest runs before the lock, another lane lands two
    VERSION bumps AND takes RESEARCH_LEDGER row 2.3, the number this ship's new row carries.
    Under the lock, after the rebase onto that main: VERSION steps past main's, this ship's
    CHANGELOG entry (tagged with a guess, 9.9) follows it, row 2.3 moves to 2.4 - and the fast
    gates run on THAT tree, which is the one that lands."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'), FAKE_LAND_BUMPS='2',
               FAKE_LAND_LEDGER_ROW='| 2.3 | other lane row |')
    origin, shared, session = _sandbox(tmp_path, env, ledger=True, changelog=True)
    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    led = _git(env, origin, 'show', 'main:RESEARCH_LEDGER.md')
    assert '| 2.3 | other lane row |' in led and '| 2.4 | lane row |' in led, led
    assert '| 2.3 | lane row |' not in led, led
    idx = _git(env, origin, 'show', 'main:index.html')
    assert "const VERSION='1.4';" in idx and "{v:'1.4',date:'2026-10-08',notes:['lane']}" in idx, idx
    assert "{v:'9.9'," not in idx, idx
    # ... and all of it under the lock, after the final rebase, before the gates that saw it
    i_lock = out.index('push lock held by this lane')
    i_renumber = out.index('RESEARCH_LEDGER row 2.3 is now 2.4', i_lock)
    i_realign = out.index('version realigned 1.3 -> 1.4', i_lock)
    i_moved = out.index('LOCKED: origin/main moved 2 commit(s)', i_lock)
    assert max(i_renumber, i_realign) < i_moved < out.index('LOCKED: 2 gate(s) run under the lock')
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
    assert [r[2] for r in _trees(tmp_path) if r[1] == 'plain'][-2:] == ['locked', 'locked']


def test_a_push_refused_because_main_moved_regates_the_rebased_tree_before_pushing_again(tmp_path):
    """INVARIANT (a) on the one path that rebases AFTER the gates: a push from outside this
    machine (a cloud session; the lock cannot reach it) lands while our pre-push hook runs, so the
    remote refuses our push. Before 2026-10-07 the retry rebased and pushed that new tree with no
    ship gate and no VERSION realign - two lanes on one version. Now it realigns and gates it."""
    env = _env(tmp_path, FAKE_LAND_FILE='cloud.txt', FAKE_HOOK_LAND=str(tmp_path / 'hook.land'))
    origin, shared, session = _sandbox(tmp_path, env)
    hooks = tmp_path / 'hooks'
    hooks.mkdir()
    py = sys.executable.replace('\\', '/')
    land = str(tmp_path / 'land.py').replace('\\', '/')
    (hooks / 'pre-push').write_bytes((
        '#!/bin/sh\nif [ -f "$FAKE_HOOK_LAND" ]; then rm -f "$FAKE_HOOK_LAND"; '
        '"%s" "%s" || exit 1; fi\nexit 0\n' % (py, land)).encode('utf-8'))
    _git(env, shared, 'config', 'core.hooksPath', str(hooks).replace('\\', '/'))
    (tmp_path / 'hook.land').write_text('x', encoding='utf-8')

    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert 'push rejected - main moved while the gate ran' in out, out
    assert _landed(env, origin, session), out
    assert 'another lane' in _git(env, origin, 'show', 'main:cloud.txt')
    # the cloud lane took 1.2, the version this ship had realigned to before the lock
    assert "const VERSION='1.3';" in _git(env, origin, 'show', 'main:index.html')
    assert 'LOCKED (retry): 2 gate(s) run under the lock, 1 reused' in out, out
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
    assert 'home_render_probe selftest locked' not in _log(tmp_path), 'cover unchanged: reused'
    _assert_lock_and_queue_free(tmp_path)


def test_a_failing_selftest_stops_the_ship_before_it_ever_queues(tmp_path):
    env = _env(tmp_path, FAKE_FAIL='home_render_probe selftest')
    origin, shared, session = _sandbox(tmp_path, env)
    before = _git(env, origin, 'rev-parse', 'main')
    rc, out = _ship(env, shared, session)
    assert rc != 0
    assert 'HOME gate SELF-TEST FAILED - the gate no longer catches a deliberately broken build' in out
    assert 'push lock held by this lane' not in out and 'queued for the push gate' not in out
    assert _git(env, origin, 'rev-parse', 'main') == before, 'nothing may be pushed'
    # (e) not merely released: never taken - neither the lock file nor the queue was created
    assert not (tmp_path / 'home' / 'state').exists()


def test_a_failing_fast_gate_before_the_lock_takes_no_lock_and_says_so(tmp_path):
    """INVARIANT (e): exactly the old behaviour when a gate fails - the same message, nothing
    pushed - plus one line saying it failed before any lock or ticket was taken."""
    env = _env(tmp_path, FAKE_FAIL='preflight_boot plain')
    origin, shared, session = _sandbox(tmp_path, env)
    before = _git(env, origin, 'rev-parse', 'main')
    rc, out = _ship(env, shared, session)
    assert rc != 0
    assert 'boot gate FAILED - not pushing' in out, out
    assert ('PRE-LOCK: boot gate FAILED before the push lock was taken - no ticket, no lock, '
            'nothing pushed') in out, out
    assert _log(tmp_path) == ['preflight_boot plain unlocked'], 'it stops at the first failure'
    assert _git(env, origin, 'rev-parse', 'main') == before
    assert not (tmp_path / 'home' / 'state').exists()


def test_a_gate_failing_under_the_lock_pushes_nothing_and_lets_the_lock_go(tmp_path):
    """INVARIANT (c) on a gate failure: main moved, so the boot gate re-runs on the final tree
    under the lock - and fails there."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'), FAKE_LAND_FILE='other.txt',
               FAKE_FAIL_LOCKED='preflight_boot plain')
    origin, shared, session = _sandbox(tmp_path, env)
    rc, out = _ship(env, shared, session)
    assert rc != 0
    assert 'boot gate FAILED - not pushing' in out, out
    assert ('LOCKED: boot gate FAILED on the final tree - nothing was pushed; the push lock goes '
            'with this process') in out, out
    assert not _landed(env, origin, session)
    assert 'another lane' in _git(env, origin, 'log', '-1', '--format=%s', 'main')
    _assert_lock_and_queue_free(tmp_path)


KEYBOARD_INTERRUPT_UNDER_THE_LOCK = r'''
import sys
sys.path.insert(0, sys.argv[1])
import wt
real, calls = wt.realign_version, []
def realign(w):
    calls.append(w)
    if len(calls) == 2:                  # 1 = before the lock, 2 = under it, after the rebase
        raise KeyboardInterrupt
    return real(w)
wt.realign_version = realign
wt.cmd_ship(None, None)
'''


def test_ctrl_c_under_the_lock_pushes_nothing_and_lets_the_lock_go(tmp_path):
    """INVARIANT (c) on Ctrl-C: the interrupt arrives while this ship holds the lock and its
    ticket. Nothing is pushed, and the next lane finds both free."""
    env = _env(tmp_path)
    origin, shared, session = _sandbox(tmp_path, env)
    before = _git(env, origin, 'rev-parse', 'main')
    p = subprocess.run([sys.executable, '-c', KEYBOARD_INTERRUPT_UNDER_THE_LOCK,
                        str(shared / 'tools')], cwd=str(session), env=env, capture_output=True,
                       timeout=600)
    out = p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')
    assert p.returncode != 0 and 'KeyboardInterrupt' in out, out
    assert 'push lock held by this lane' in out, 'the interrupt must land under the lock'
    assert _git(env, origin, 'rev-parse', 'main') == before
    _assert_lock_and_queue_free(tmp_path)


def test_a_killed_ship_lets_the_lock_go_even_while_the_gate_it_started_lives_on(tmp_path):
    """INVARIANT (c), the hard way: the ship is killed outright while a gate it started runs
    under the lock - and that gate outlives it (as a probe's headless Chrome once did). The lock
    and the ticket must be free for the next lane at once: the orphan must not have inherited the
    handles."""
    env = _env(tmp_path, FAKE_LAND=str(tmp_path / 'land.py'), FAKE_LAND_FILE='other.txt',
               FAKE_BLOCK_LOCKED='preflight_boot plain',
               FAKE_BLOCK_MARKER=str(tmp_path / 'blocked'),
               FAKE_BLOCK_RELEASE=str(tmp_path / 'release'))
    origin, shared, session = _sandbox(tmp_path, env)
    marker, done = tmp_path / 'blocked', tmp_path / 'blocked.done'
    proc = subprocess.Popen([sys.executable, str(shared / 'tools' / 'wt.py'), 'ship'],
                            cwd=str(session), env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 300
        while not marker.exists():
            assert proc.poll() is None, 'the ship ended before its gate ran under the lock'
            assert time.time() < deadline, 'the gate never ran under the lock'
            time.sleep(0.1)
        assert _other_process_sees(tmp_path / 'home' / 'state' / 'push.lock') == 'held'
        proc.kill()
        proc.wait(timeout=60)
        assert not done.exists(), 'the orphaned gate must still be running for this to mean much'
        _assert_lock_and_queue_free(tmp_path)
        assert not done.exists()
        assert not _landed(env, origin, session)
    finally:
        (tmp_path / 'release').write_text('x', encoding='utf-8')
        if proc.poll() is None:
            proc.kill()
    deadline = time.time() + 60                    # let the orphan finish before tmp_path goes
    while not done.exists() and time.time() < deadline:
        time.sleep(0.1)


def test_a_file_edited_while_a_gate_runs_is_not_stamped_as_passed(tmp_path):
    """ADVERSARIAL: the lane edits a tracked file while the selftest runs (or commits, or a
    second terminal rebases). The stamp records a TREE, the gate read the FILES: recording that
    pass would let a later ship on the original tree reuse a verdict no gate gave it. The ship
    stops, pushes nothing, and the next ship runs that gate again."""
    env = _env(tmp_path, FAKE_DIRTY='home_render_probe selftest')
    origin, shared, session = _sandbox(tmp_path, env)
    before = _git(env, origin, 'rev-parse', 'main')
    rc, out = _ship(env, shared, session)
    assert rc != 0, out
    assert 'changed while the gates ran - so the HOME gate SELF-TEST pass is NOT recorded' in out
    assert _git(env, origin, 'rev-parse', 'main') == before
    assert not (tmp_path / 'home' / 'state').exists(), 'it stopped before queueing'

    _git(env, session, 'checkout', '--', 'index.html')        # the lane puts the file back
    rc, out = _ship(_env(tmp_path), shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    log = _log(tmp_path)
    assert log.count('home_render_probe selftest unlocked') == 2, 'it must run again:\n' + out
    assert out.count('already passed, not re-run: ') == 2, out    # boot + HOME, each verified
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)


def test_a_second_ship_of_the_same_worktree_is_refused_before_it_touches_anything(tmp_path):
    """ADVERSARIAL: two ships of one worktree at once would rebase it under each other's
    gates. The second refuses straight away - no gate, no lock, no ticket."""
    import push_lock
    env = _env(tmp_path)
    origin, shared, session = _sandbox(tmp_path, env)
    gd = _git(env, session, 'rev-parse', '--absolute-git-dir')
    fd = os.open(os.path.join(gd, wt.SHIP_GUARD_FILE), os.O_CREAT | os.O_RDWR)
    try:
        push_lock._lock_fd(fd)                                   # "the first ship"
        rc, out = _ship(env, shared, session)
        assert rc != 0 and 'is already running - let it finish' in out, out
        assert _log(tmp_path) == [] and not (tmp_path / 'home' / 'state').exists(), out
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        push_lock._unlock_fd(fd)
        os.close(fd)
    rc, out = _ship(env, shared, session)                        # the first one is done
    assert rc == 0, out
    assert _landed(env, origin, session), out


def test_a_re_run_ship_on_an_unchanged_tree_reuses_the_stamp(tmp_path):
    """The first ship's push is refused by its pre-push hook; the re-run must not repeat a single
    gate - every pass is in the stamp, on the same tree."""
    env = _env(tmp_path, FAKE_HOOK_FAIL=str(tmp_path / 'hook.fail'))
    origin, shared, session = _sandbox(tmp_path, env)
    hooks = tmp_path / 'hooks'
    hooks.mkdir()
    (hooks / 'pre-push').write_text(
        '#!/bin/sh\nif [ -f "$FAKE_HOOK_FAIL" ]; then rm -f "$FAKE_HOOK_FAIL"; '
        'echo "fake hook refused the push"; exit 1; fi\nexit 0\n', encoding='utf-8')
    _git(env, shared, 'config', 'core.hooksPath', str(hooks).replace('\\', '/'))
    (tmp_path / 'hook.fail').write_text('x', encoding='utf-8')

    rc, out = _ship(env, shared, session)
    assert rc != 0 and 'push failed, and not because main moved' in out, out
    assert not _landed(env, origin, session)
    assert len(_log(tmp_path)) == 3, out
    _assert_lock_and_queue_free(tmp_path)

    rc, out = _ship(env, shared, session)
    assert rc == 0, out
    assert _landed(env, origin, session), out
    assert len(_log(tmp_path)) == 3, 'the re-run repeated a gate:\n' + out
    assert out.count('already passed, not re-run: ') == 3, out
    assert 'PRE-LOCK: 0 gate(s) run, 3 already passed' in out, out
    _assert_fast_gates_passed_on_what_landed(env, origin, tmp_path)
