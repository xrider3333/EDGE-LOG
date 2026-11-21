from tools.ownbar_shadow_report import check_decision, run
from tools.ownbar_shadow import fold_own


def row(rule, level, **bar):
    r = {"dec_rule": rule, "dec_level": "" if level is None else str(level)}
    base = {"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10}
    base.update(bar)
    for k, v in base.items():
        r["dec_" + k] = str(v)
    return r


OWN = [100, 101, 99, 100.5, 10]


def test_same_when_own_still_crosses():
    assert check_decision(row("close>upper", 100.2), OWN)[0] == "same"


def test_flip_when_own_close_misses_level():
    st, d = check_decision(row("close>upper", 100.2), [100, 101, 99, 100.1, 10])
    assert st == "flip" and d["own_margin"] < 0


def test_flip_below_rule_and_low_stop():
    assert check_decision(row("close<lower", 100.6), [100, 101, 99, 100.7, 10])[0] == "flip"
    assert check_decision(row("low<=stop", 99.0), [100, 101, 99.01, 100, 10])[0] == "flip"
    assert check_decision(row("low<=stop", 99.0), [100, 101, 99.0, 100, 10])[0] == "same"


def test_equality_boundary_strict():
    assert check_decision(row("close>upper", 100.2), [100, 101, 99, 100.2, 10])[0] == "flip"


def test_level_from_band_column_when_dec_level_blank():
    r = row("close<vwap", None)
    r["dec_vwap"] = "100.7"
    assert check_decision(r, OWN)[0] == "same"


def test_not_checkable_cases():
    assert check_decision(row("", None), OWN)[0] == "not_checkable"
    assert check_decision(row("orb_break", 1.0), OWN)[0] == "not_checkable"
    assert check_decision(row("close>upper", None), OWN)[0] == "not_checkable"
    # inconsistent: rule false on the logged bar itself
    assert check_decision(row("close>upper", 200), OWN)[0] == "not_checkable"


def test_time_rule_and_missing_own():
    assert check_decision(row("session_last_bar", None), None)[0] == "time_rule"
    assert check_decision(row("close>upper", 100.2), None)[0] == "no_own_bar"


def test_run_joins_on_bar_start_and_counts():
    start = 1763571600  # 2025-11-19 12:00 ET
    shadow = {start: {"bar_start": start, "own_1_0": {"bar": [100, 101, 99, 100.1, 10]},
                      "rest_final": [100, 101, 99, 100.5, 10], "seconds_to_final": 7.0}}
    r = row("close>upper", 100.2)
    r["dec_bar_start"] = "2025-11-19T12:00:00-05:00"
    summary, res = run(shadow, [r, {"dec_bar_start": ""}])
    assert summary["flips"] == 1 and summary["decisions_checked"] == 1
    assert summary["bars_compared"] == 1 and summary["pct_identical"] == 0.0
    assert summary["worst_close_diff"] == 0.4 and summary["seconds_saved_median"] == 6.0


def test_fold_own_needs_all_five_minutes():
    rows = {60 * k: [10 + k, 20 + k, 5 - k, 11 + k, 1] for k in range(5)}
    assert fold_own(rows, 0)["bar"] == [10, 24, 1, 15, 5]
    rows.pop(240)
    assert fold_own(rows, 0) == {"bar": None, "minutes": 4}
