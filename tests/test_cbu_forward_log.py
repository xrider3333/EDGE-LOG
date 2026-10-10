"""CBU ALERT forward log (tools/cbu_forward_log.py): the owner's plan (stop under the candle, breakeven at +1R, ride
to 15:59) is walked bar by bar inside the session, and only closed sessions are logged."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import cbu_forward_log as F  # noqa: E402
import point_score as P  # noqa: E402

TICK = 0.25


def _session(rows, start_mod=600):
    """rows = (open, high, low, close) per one-minute bar from start_mod (minute of day) in one session."""
    a = np.array(rows, dtype='float64')
    n = len(a)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], np.zeros(n, dtype='int64'), start_mod + np.arange(n)


def test_stopped_out_is_minus_one_r():
    # signal bar 0 (low 99), entry 100.25 at bar 1's open, stop 98.75, R = 1.5; bar 2 trades through the stop
    po, ph, pl, pc, d, m = _session([(99.5, 100.5, 99.0, 100.2), (100.25, 100.6, 100.0, 100.4), (100.4, 100.5, 98.5, 98.6)])
    w = F.walk(po, ph, pl, pc, d, m, 0, TICK)
    assert w['stop'] == 98.75 and w['risk_pts'] == 1.5
    assert not w['reached_1R'] and w['exit'] == 98.75 and w['R'] == -1.0


def test_plus_one_r_then_back_is_breakeven():
    # entry 100.25, R 1.5: bar 1 reaches 101.75 (+1R), bar 2 comes back to the entry
    po, ph, pl, pc, d, m = _session([(99.5, 100.5, 99.0, 100.2), (100.25, 101.8, 100.1, 101.5), (101.5, 101.6, 100.2, 100.3)])
    w = F.walk(po, ph, pl, pc, d, m, 0, TICK)
    assert w['reached_1R'] and w['exit'] == 100.25 and w['R'] == 0.0


def test_ride_to_the_last_regular_bar():
    # +1R reached and never back to the entry: out at the close of the 15:59 bar, nothing after 16:00 is read
    rows = [(99.5, 100.5, 99.0, 100.2), (100.25, 101.8, 100.1, 101.5), (101.5, 103.0, 101.0, 102.5), (102.5, 110, 50, 60)]
    po, ph, pl, pc, d, m = _session(rows, start_mod=P.RTH_CLOSE - 3)
    w = F.walk(po, ph, pl, pc, d, m, 0, TICK)
    assert w['reached_1R'] and w['exit'] == 102.5
    assert abs(w['R'] - (102.5 - 100.25) / 1.5) < 1e-12


def test_a_bar_touching_stop_and_target_counts_as_stopped():
    po, ph, pl, pc, d, m = _session([(99.5, 100.5, 99.0, 100.2), (100.25, 102.0, 98.5, 101.0)])
    w = F.walk(po, ph, pl, pc, d, m, 0, TICK)
    assert not w['reached_1R'] and w['R'] == -1.0


def test_no_next_bar_in_the_session_gives_none():
    po, ph, pl, pc, d, m = _session([(99.5, 100.5, 99.0, 100.2), (100.25, 100.6, 100.0, 100.4)])
    d[1] = 1                                    # the next bar belongs to another session
    assert F.walk(po, ph, pl, pc, d, m, 0, TICK) is None
    po, ph, pl, pc, d, m = _session([(99.5, 100.5, 99.0, 100.2)], start_mod=P.RTH_CLOSE - 1)
    assert F.walk(po, ph, pl, pc, d, m, 0, TICK) is None


def test_missed_entries_mark_only_cbu_longs(tmp_path):
    import json
    p = tmp_path / 'missed.json'
    p.write_text(json.dumps({'entries': {
        'a': dict(id='a', setup='CBU', type='LONG', symbol='MNQ', date='2026-09-30', signal_candle='09:59'),
        'b': dict(id='b', setup='ENGU', type='LONG', symbol='MNQ', date='2026-09-30', signal_candle='10:05'),
        'c': dict(id='c', setup='CBU', type='SHORT', symbol='MES', date='2026-09-30', signal_candle='10:07')}}))
    assert F.missed_cbu(str(p)) == [('NQ', P._epoch('2026-09-30 09:59'))]


def _log(rs, per_session):
    """A fake alerts frame: R values rs, per_session alerts on each session."""
    import pandas as pd
    return pd.DataFrame({'R': rs, 'session': ['2026-10-%02d' % (1 + k // per_session) for k in range(len(rs))]})


def test_read_status_before_fifty_alerts_makes_no_read():
    s = F.read_status(_log([-1.0] * 49, 5))
    assert s.startswith('READ: none yet') and '49/50' in s


def test_harm_read_flags_a_real_loser():
    # 50 alerts, mostly stopped: mean well below -0.3R, spread across 25 sessions -> clustered t far below -2
    rs = ([-1.0] * 4 + [0.0]) * 10
    s = F.read_status(_log(rs, 2))
    assert s.startswith('HARM READ: HARM') and 'edge read waits' in s


def test_harm_read_needs_both_mean_and_t():
    # mean -0.4R but driven by one bad session: the clustered t stays above -2, so no harm is called
    rs = [-1.0] * 25 + [0.2] * 25
    s = F.read_status(_log(rs, 25))
    assert F.clustered_t(_log(rs, 25)) is None or 'no harm shown' in s
    rs = [-1.0, 0.5] * 25            # mean -0.25R: above the -0.3R bar
    assert 'no harm shown' in F.read_status(_log(rs, 2))


def test_edge_read_waits_for_300_alerts_and_60_sessions():
    rs = [0.5, -0.2] * 150           # 300 alerts
    assert 'edge read waits' in F.read_status(_log(rs, 10))          # 30 sessions
    assert 'EDGE READ DUE: 300 alerts, 60 sessions' in F.read_status(_log(rs, 5))


def test_clustered_t_matches_iid_when_one_alert_per_session():
    import numpy as np
    rs = [0.3, -0.5, 1.2, -1.0, 0.0, 0.8, -0.2, 0.4]
    t = F.clustered_t(_log(rs, 1))
    r = np.array(rs)
    assert abs(t - r.mean() / (np.sqrt(((r - r.mean()) ** 2).sum()) / len(r))) < 1e-12


def test_open_session_is_not_logged(monkeypatch):
    """Alerts on a session that has not run to its close (today, live) never enter the log."""
    import pandas as pd
    import cbu_v1_alerts as C

    class FakeBars:
        def adjusted(self):
            o = np.array([99.5, 100.25, 100.4, 99.5, 100.25, 100.4])
            return o, o + 2, o - 2, o, None

    d = pd.DataFrame({'dord': [1, 1, 1, 2, 2, 2], 'mod': [600, 601, 602, 600, 601, 602],
                      't': [P._epoch('1970-01-02 10:00') + 60 * k for k in range(6)],
                      F.VARIANT: [True, False, False, True, False, False]})
    monkeypatch.setattr(C, 'decisions', lambda b, ma=None: d)
    monkeypatch.setattr(C, 'closed_sessions', lambda dd: {1})
    df = F.forward('1970-01-01', missed=[], bars={'NQ': FakeBars(), 'ES': FakeBars()})
    assert len(df) == 2 and set(df['session']) == {C.ord_str(1)}
