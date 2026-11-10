"""tools/nt_stranded_guard.py: the 11-04 stranded-trade loss must page within a minute and get closed."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import nt_stranded_guard as G   # noqa: E402

PHX = G.PHX
NOISE_POS = {"account": "DEMO7240108", "instrument": "MNQ 12-26", "side": "Long", "qty": 11, "avg_price": 28676}
ENGUQ_POS = {"account": "DEMO7240108", "instrument": "NQ 12-26", "side": "Long", "qty": 1, "avg_price": 28750.5}
ENGUQ_RT = {"account": "DEMO7240108", "name": "EdgeLogENGUQ1m", "state": "Realtime", "position": "Long 1"}
MIDDAY = dt.datetime(2026, 11, 4, 12, 40, tzinfo=PHX)


def test_11_04_both_legs_disabled_is_stranded():
    s, m = G.find_stranded([NOISE_POS, ENGUQ_POS], [])
    assert len(s) == 2 and m == []


def test_a_running_strategy_that_says_flat_does_not_own_the_position():
    s, m = G.find_stranded([NOISE_POS], [dict(ENGUQ_RT, name="EdgeLogNOISE", position="Flat 0")])
    assert len(s) == 1


def test_a_managed_leg_is_not_stranded_and_real_account_is_ignored():
    s, m = G.find_stranded([ENGUQ_POS, dict(NOISE_POS, account="1810769")], [ENGUQ_RT])
    assert s == [] and len(m) == 1


def test_push_after_40_s_once():
    s, _ = G.find_stranded([NOISE_POS], [])
    acts, st = G.decide(s, [], {}, 1000.0, now_mst=MIDDAY)
    assert acts == []
    acts, st = G.decide(s, [], st, 1041.0, now_mst=MIDDAY)
    assert [a[0] for a in acts] == ["push"] and "STRANDED long 11 MNQ" in acts[0][1]
    acts, st = G.decide(s, [], st, 1100.0, now_mst=MIDDAY)
    assert acts == []


def test_protective_flatten_at_100_pts_against_with_fresh_price():
    s, _ = G.find_stranded([NOISE_POS], [])
    acts, _ = G.decide(s, [], {}, 0.0, price=28576.0, price_age=20, now_mst=MIDDAY)
    assert acts[-1][0] == "flatten" and "protective stop" in acts[-1][1]
    acts, _ = G.decide(s, [], {}, 0.0, price=28600.0, price_age=20, now_mst=MIDDAY)
    assert acts == []
    acts, _ = G.decide(s, [], {}, 0.0, price=28000.0, price_age=600, now_mst=MIDDAY)     # stale price: no stop
    assert acts == []


def test_flat_at_the_close_window():
    s, _ = G.find_stranded([NOISE_POS], [])
    acts, _ = G.decide(s, [], {}, 0.0, now_mst=dt.datetime(2026, 11, 4, 13, 56, tzinfo=PHX))
    assert acts[-1] == ("flatten", "flat at the close (13:55 MST) - stranded position")
    acts, _ = G.decide(s, [], {}, 0.0, now_mst=dt.datetime(2026, 11, 7, 13, 56, tzinfo=PHX))     # Saturday
    assert acts == []


def test_never_flattens_under_a_managed_leg_pushes_instead_once():
    s, m = G.find_stranded([NOISE_POS, ENGUQ_POS], [ENGUQ_RT])
    close = dt.datetime(2026, 11, 4, 13, 56, tzinfo=PHX)
    acts, st = G.decide(s, m, {}, 0.0, now_mst=close)
    assert [a[0] for a in acts] == ["push"] and "cannot close" in acts[0][1]
    acts, st = G.decide(s, m, st, 20.0, now_mst=close)
    assert acts == []


def test_short_adverse_points():
    assert G.adverse_pts({"side": "Short", "avg_price": 100}, 150) == 50
