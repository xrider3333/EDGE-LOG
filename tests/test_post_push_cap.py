"""OWNER HARD RULE 11-25: no check over 5 min - shards, a 5-min kill, no stacking per lane."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import post_push_tests as P  # noqa: E402


def test_shards_stay_under_target_and_cover_every_file():
    secs = {'a': 150, 'b': 120, 'c': 90, 'd': 30, 'e': 30}
    files = list(secs) + ['new']                       # 'new' untimed -> median
    sh = P.make_shards(files, secs, target=200)
    assert sorted(f for s in sh for f in s) == sorted(files)
    for s in sh:
        assert sum(secs.get(f, 90) for f in s) <= 200 or len(s) == 1


def test_one_huge_file_gets_its_own_shard():
    sh = P.make_shards(['big', 'x'], {'big': 900, 'x': 1}, target=200)
    assert ['big'] in sh


class _Proc:
    def __init__(self, rc_after, clock, pid):
        self.rc_after, self.clock, self.pid, self.t0 = rc_after, clock, pid, clock[0]

    def poll(self):
        if self.rc_after is None:
            return None
        return self.rc_after[1] if self.clock[0] - self.t0 >= self.rc_after[0] else None


def test_shard_over_cap_is_killed_and_reported_slow():
    clock = [0.0]
    plan = {'ok.py': (10, 0), 'bad.py': (10, 1), 'hang.py': None}
    killed = []

    def popen(cmd, **kw):
        return _Proc(plan[cmd[-1]], clock, pid=len(killed) + 100)

    def sleep(s):
        clock[0] += 5
    res = P.run_shards('.', [['ok.py'], ['bad.py'], ['hang.py']], {}, par=3, cap=300, popen=popen,
                       clock=lambda: clock[0], sleep=sleep, kill=killed.append)
    st = {s[0][0]: s[1] for s in res}
    assert st == {'ok.py': 'pass', 'bad.py': 'fail', 'hang.py': 'SLOW'}
    assert len(killed) == 1 and clock[0] <= 310


def test_new_push_cancels_older_run_for_same_lane(tmp_path):
    pf = str(tmp_path / 'lane.pid')
    open(pf, 'w').write('999999 oldsha')
    killed = []
    P.take_lane('wbcalm', 'newsha', pf=pf, kill=killed.append)
    assert killed == [999999]
    assert P.still_mine(pf)
    open(pf, 'w').write('424242 newer')
    assert not P.still_mine(pf)
