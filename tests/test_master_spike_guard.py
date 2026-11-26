import pandas as pd

from augur_engine.master_write import first_spike


def _bars(rows):
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


def test_1030_print_is_caught():
    # 14:52, 14:53, then a 9-minute hole and the bad 15:03 open
    new = _bars([(1793386980, 29562.0, 29562.0, 28294.5, 28295.25),
                 (1793387040, 28295.25, 28310.0, 28283.25, 28307.75)])
    assert first_spike(new, prev_time=1793386380, prev_close=28234.25, bar_s=60) == 0


def test_same_jump_without_hole_or_over_a_session_break_passes():
    new = _bars([(1793386440, 29562.0, 29562.0, 28294.5, 28295.25)])
    assert first_spike(new, prev_time=1793386380, prev_close=28234.25, bar_s=60) is None
    assert first_spike(new, prev_time=1793386440 - 3 * 3600, prev_close=28234.25) is None


def test_small_move_after_hole_passes():
    new = _bars([(1793386980, 28288.0, 28312.0, 28287.0, 28294.5)])
    assert first_spike(new, prev_time=1793386380, prev_close=28234.25) is None


def test_spike_inside_new_rows():
    new = _bars([(60, 100.0, 100, 100, 100.0), (120, 100.0, 100, 100, 100.0),
                 (600, 103.0, 103, 103, 103.0)])
    assert first_spike(new, prev_time=0, prev_close=100.0, bar_s=60) == 2
