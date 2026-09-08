"""tools/queue_guard.py's resolve_params() -- the {} TRAP fix (2026-09-08).

WHY: `tools/queue_guard.py --params '{}'` used to fall straight through to the strategy
plugin's own run_backtest() KEYWORD defaults instead of the file's DEFAULT_PARAMS[k]
['default'] values -- and on ENGUQ_1M_ETH_R2_1_0.py those are two DIFFERENT
configurations (the signature inherits its parent's frozen parity anchor; DEFAULT_PARAMS
holds the "be2.0 sibling" the owner actually chose as current). A real queued job never
hits this gap because the web Builder always fills every key from DEFAULT_PARAMS before it
ever writes a job doc -- so a bare `{}` reaching the ENGINE should behave the same way.

These tests exercise resolve_params() in isolation against a tiny synthetic strategy
module written to a temp file (an absolute path, so augur_engine.strategies._resolve()
returns it unchanged without touching augur_strategies/). No engine run (run_backtest is
never called), no Firestore, no real strategy file.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.queue_guard import resolve_params, format_resolved_report  # noqa: E402

_WITH_DEFAULTS = '''
DEFAULT_PARAMS = {
    "foo": {"default": 42, "min": 0, "max": 100, "type": "int"},
    "bar": {"default": 7, "min": 0, "max": 10, "type": "int"},
}


def run_backtest(opens, highs, lows, closes, foo=1, bar=2, return_trades=False, **_ignore):
    """Signature defaults (foo=1, bar=2) deliberately differ from DEFAULT_PARAMS's
    (foo=42, bar=7) -- the exact shape of the real ENGUQ_1M_ETH_R2_1_0.py trap."""
    return {}
'''

_NO_DEFAULTS = '''
def run_backtest(opens, highs, lows, closes, foo=1, bar=2, return_trades=False, **_ignore):
    return {}
'''


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return str(p)


def test_empty_params_resolve_to_default_params_not_signature(tmp_path):
    path = _write(tmp_path, "fake_strat_defaults.py", _WITH_DEFAULTS)
    resolved, source, has_dp = resolve_params(path, {})
    assert has_dp is True
    # THE FIX: {} must land on DEFAULT_PARAMS's values (42/7), never the function
    # signature's own keyword defaults (1/2) -- that mismatch is exactly what silently
    # re-ran run #226's parity anchor under a #323 label.
    assert resolved == {"foo": 42, "bar": 7}
    assert source == {"foo": "default", "bar": "default"}


def test_caller_supplied_keys_win_over_default_params(tmp_path):
    path = _write(tmp_path, "fake_strat_overlay.py", _WITH_DEFAULTS)
    resolved, source, has_dp = resolve_params(path, {"foo": 999})
    assert has_dp is True
    # caller's foo wins; bar (not supplied) still falls back to DEFAULT_PARAMS, not the
    # signature default of 2.
    assert resolved == {"foo": 999, "bar": 7}
    assert source == {"foo": "caller", "bar": "default"}


def test_no_default_params_falls_back_to_passthrough(tmp_path):
    path = _write(tmp_path, "fake_strat_nodefaults.py", _NO_DEFAULTS)
    resolved, source, has_dp = resolve_params(path, {"foo": 5})
    assert has_dp is False
    # nothing to resolve against: the caller's params pass through unchanged (a missing
    # key still falls back to the plugin's own signature default at call time, exactly as
    # before this fix -- resolve_params has no DEFAULT_PARAMS dict to source it from).
    assert resolved == {"foo": 5}
    assert source == {"foo": "caller"}


def test_no_default_params_with_no_caller_params_is_empty(tmp_path):
    path = _write(tmp_path, "fake_strat_nodefaults_empty.py", _NO_DEFAULTS)
    resolved, source, has_dp = resolve_params(path, {})
    assert has_dp is False
    assert resolved == {}
    assert source == {}


def test_format_resolved_report_flags_the_no_default_params_case(tmp_path):
    path = _write(tmp_path, "fake_strat_report.py", _NO_DEFAULTS)
    resolved, source, has_dp = resolve_params(path, {"foo": 5})
    lines = format_resolved_report(path, resolved, source, has_dp)
    assert any("RESOLVED PARAMS" in ln for ln in lines)
    assert any("no DEFAULT_PARAMS" in ln for ln in lines)


def test_format_resolved_report_splits_default_vs_caller(tmp_path):
    path = _write(tmp_path, "fake_strat_report2.py", _WITH_DEFAULTS)
    resolved, source, has_dp = resolve_params(path, {"foo": 999})
    lines = format_resolved_report(path, resolved, source, has_dp)
    joined = "\n".join(lines)
    assert "foo=999" in joined
    assert "bar=7" in joined
    assert "from DEFAULT_PARAMS (1): bar" in joined
    assert "from caller         (1): foo" in joined
