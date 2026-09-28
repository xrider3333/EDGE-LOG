"""The trial cache must miss when a strategy's PARENT changes, not just its own file.

WHY (TTM, 2026-09-27). The cache keyed on the SHA of the top-level strategy file alone. But a
variant in this repo is a thin wrapper that loads its parent by file path at run time:

    _sp = _u.spec_from_file_location("TTMSQZ_3_0_ES30SSOF2",
                                     os.path.join(_HERE, "TTMSQZ_3_0_ES30SSOF2.py"))
    _base = _u.module_from_spec(_sp); _sp.loader.exec_module(_base)

so a fix inside the parent left the wrapper's sha unchanged and every re-validation replayed
the OLD cached results. Silently - no error, no warning, just stale numbers presented as
fresh. TTM hit it and had to edit each wrapper by hand to force a miss. ORB, NOISE and ENGU-Q
wrappers are written the same way, so this was never TTM-only.

A second case of the same bug class, found while fixing it and covered here too: a
roll-guarded strategy reads `tools/data/rolls_<root>.csv` at run time, and that table is not
frozen - the September 2026 NQ offset changed from an estimated 295.00 to a measured 296.50
on 2026-09-28, and December's switch is appended the evening it happens.

The rule these tests pin: the cache key changes when ANYTHING the strategy actually reads
changes. A cache that returns a stale result is worse than no cache, because the number looks
real.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import strategies as S  # noqa: E402

PARENT = "PARENTSTRAT_1_0.py"
WRAPPER = "WRAPSTRAT_1_1.py"

PARENT_SRC = '''"""A stand-in for a real parent strategy file."""
STRATEGY_NAME = "Parent"
DEFAULT_PARAMS = {"k": {"type": "int", "min": 1, "max": 3, "default": 2}}
PARAM_GRID_PRESETS = {}
MAGIC = 1


def run_backtest(opens, highs, lows, closes, **kw):
    return {"total_pnl": MAGIC, "num_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "avg_pnl": 0.0, "wins": 0, "losses": 0}
'''

WRAPPER_SRC = '''"""A wrapper that loads its parent BY FILE PATH, the way the real variants do."""
import os
from importlib import util as _u

_HERE = os.path.dirname(os.path.abspath(__file__))
_sp = _u.spec_from_file_location("PARENTSTRAT_1_0", os.path.join(_HERE, "PARENTSTRAT_1_0.py"))
_base = _u.module_from_spec(_sp)
_sp.loader.exec_module(_base)

STRATEGY_NAME = "Wrapper"
DEFAULT_PARAMS = _base.DEFAULT_PARAMS
PARAM_GRID_PRESETS = {}
_AUGUR_PARENT = "PARENTSTRAT_1_0.py"

# the real roll-guarded wrappers name the table this way, with the root interpolated
_ROLLS_CSV = os.path.join(os.path.dirname(_HERE), "tools", "data", "rolls_%s.csv" % "ES")


def run_backtest(opens, highs, lows, closes, **kw):
    return _base.run_backtest(opens, highs, lows, closes, **kw)
'''


@pytest.fixture()
def strat_dir(tmp_path):
    """A throwaway augur_strategies/ with a parent, a wrapper, and a tools/data table."""
    d = tmp_path / "augur_strategies"
    d.mkdir()
    (d / PARENT).write_text(PARENT_SRC, encoding="utf-8")
    (d / WRAPPER).write_text(WRAPPER_SRC, encoding="utf-8")
    data = tmp_path / "tools" / "data"
    data.mkdir(parents=True)
    (data / "rolls_ES.csv").write_text("root,switch_sec,offset_pts\nES,1,64.00\n", encoding="utf-8")
    return d


def _sha(d, name):
    """Closure sha with BOTH module caches cleared.

    strategy_file_sha memoizes by (path, mtime); a test that rewrites a file within the
    filesystem's mtime resolution would otherwise read back the previous hash and the test
    would pass or fail for the wrong reason.
    """
    S._CACHE.clear()
    S._SHA_CACHE.clear()
    p = str(d / name)
    return S.strategy_closure_sha(p, S.load_strategy(p))


def test_editing_the_parent_changes_the_wrapper_key(strat_dir):
    """THE BUG. Before the fix this returned the same sha and the cache replayed old results."""
    before = _sha(strat_dir, WRAPPER)
    (strat_dir / PARENT).write_text(PARENT_SRC.replace("MAGIC = 1", "MAGIC = 2"), encoding="utf-8")
    after = _sha(strat_dir, WRAPPER)
    assert before != after, (
        "a change in the parent must change the wrapper's cache key, or a re-validation "
        "silently replays results computed with the old parent")


def test_editing_the_wrapper_still_changes_its_key(strat_dir):
    """The original behaviour has to survive the fix."""
    before = _sha(strat_dir, WRAPPER)
    (strat_dir / WRAPPER).write_text(WRAPPER_SRC + "\n# a real edit\n", encoding="utf-8")
    assert _sha(strat_dir, WRAPPER) != before


def test_touching_nothing_leaves_the_key_alone(strat_dir):
    """A content hash, not an mtime: re-reading unchanged files must still hit the cache,
    otherwise the cache is worthless."""
    a = _sha(strat_dir, WRAPPER)
    assert _sha(strat_dir, WRAPPER) == a


def test_the_parent_is_in_the_closure_and_so_is_the_roll_table(strat_dir):
    p = str(strat_dir / WRAPPER)
    names = [os.path.basename(f) for f in S.strategy_closure_files(p, S.load_strategy(p))]
    assert PARENT in names, "the parent it loads by path must be part of the key"
    assert WRAPPER in names
    assert "rolls_ES.csv" in names, (
        "a data table the strategy names is part of what it computes from")


def test_changing_the_roll_table_changes_the_key(strat_dir):
    """The roll table is not frozen - offsets get corrected and December's switch is appended
    the evening it happens. A trial cached against the old offsets must not be replayed."""
    before = _sha(strat_dir, WRAPPER)
    (strat_dir.parent / "tools" / "data" / "rolls_ES.csv").write_text(
        "root,switch_sec,offset_pts\nES,1,67.75\n", encoding="utf-8")
    assert _sha(strat_dir, WRAPPER) != before


def test_an_unreadable_file_disables_caching_rather_than_guessing(tmp_path):
    """The house contract: a field that cannot be sourced cleanly means do not cache. Never
    fall back to a stale or partial hash."""
    assert S.strategy_closure_sha(str(tmp_path / "does_not_exist.py")) == ""


def test_the_real_ttm_wrapper_pulls_in_its_whole_chain():
    """Against the actual repo, not a fixture: the file TTM reported is five wrappers deep."""
    p = os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2R.py")
    if not os.path.exists(p):
        pytest.skip("TTMSQZ_3_0_ES30SSOF2R.py is not in this checkout")
    names = [os.path.basename(f) for f in S.strategy_closure_files(p, S.load_strategy(p))]
    assert "TTMSQZ_3_0_ES30SSOF2.py" in names, "its immediate parent"
    assert "TTMSQZ_3_0_ES30SS.py" in names, "the file TTM edited by hand to force a miss"
    assert "rolls_ES.csv" in names, "the roll table its guard reads at run time"


def test_the_cache_context_uses_the_closure_not_the_bare_file(monkeypatch):
    """Pins the wiring: trial_cache must ask for the closure. A correct hash nothing calls
    fixes nothing."""
    src = open(os.path.join(ROOT, "augur_engine", "trial_cache.py"), encoding="utf-8").read()
    assert "strategy_closure_sha" in src
    assert "_sha_of(path, mod)" in src
