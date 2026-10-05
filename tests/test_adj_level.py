r"""The back-adjusted-master level warning (augur_engine/adj_level.py, 2026-10-05).

WHAT THE REAL FIXTURES ARE. MANAGER named four, and they are the whole point of the design:
NOISE_1_8_CT304H must be flagged on an ADJ_ master, and ORB_3_6_C2 / ENGUQ_1M_ETH_R2_1_0 /
TTMSQZ_3_0 must stay quiet. Those four runs need the real masters, so they live in
tools/adj_level_check.py and are exercised from the shared checkout; measured there:

    NOISE_1_8_CT304H       dependent   386 of 400 trades change at +3734 points (net -2.0%)
    ORB_3_6_C2             invariant   243 trades identical
    ENGUQ_1M_ETH_R2_1_0    invariant   283 trades identical
    TTMSQZ_3_0             invariant    94 trades identical

WHAT THIS FILE TESTS is the mechanism, on synthetic strategies whose level-dependence is known by
construction, because that is the part that has to keep working when nobody is looking:

  - a strategy reading (H-L)/C is caught and one reading only differences is not - the exact pair
    the source-scanning approach could not separate, which is why this probes behaviour instead;
  - a window too short to activate a warm-up filter returns "unknown", never "invariant". This is
    the one that would do real damage: NOISE's vol filter needs 60 reference sessions, so on a
    short window the strategy genuinely behaves level-invariantly and a guard that said "clean"
    would be confidently wrong;
  - every failure path is silent, like the push lock's (see [[edgelog-cross-process-lock]]);
  - the cache is not keyed on params, or a 900-trial validate would probe 900 times.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import adj_level  # noqa: E402


# ═══════════════════════════════════════════════════ synthetic bars and strategies
def _bars(n_sessions=300, bars_per_session=10, base=15000.0, seed=7):
    """A plain random walk with a session structure. Levels near NQ's so the real offset is a
    realistic fraction of the price rather than swamping it."""
    rng = np.random.default_rng(seed)
    n = n_sessions * bars_per_session
    close = base + np.cumsum(rng.normal(0, 5.0, n))
    high = close + np.abs(rng.normal(0, 3.0, n))
    low = close - np.abs(rng.normal(0, 3.0, n))
    open_ = close + rng.normal(0, 1.0, n)
    day_id = np.repeat(np.arange(n_sessions), bars_per_session).astype("int64")
    return {"open": open_, "high": high, "low": low, "close": close,
            "volume": np.full(n, 1000.0), "day_id": day_id, "index": None}


class LevelFree:
    """Decides on DIFFERENCES only - back-adjustment cannot move it."""
    @staticmethod
    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                     return_trades=False, **kw):
        trades = []
        for i in range(20, len(closes) - 1, 7):
            if closes[i] - closes[i - 10] > 5.0:          # a difference: offset-proof
                trades.append((i, i + 1, float(closes[i + 1] - closes[i])))
        out = {"total_pnl": sum(t[2] for t in trades), "num_trades": len(trades)}
        if return_trades:
            out["trades"] = trades
        return out


class ReadsLevels:
    """Decides on a difference divided by a LEVEL - exactly NOISE_1_0's (H-L)/C shape."""
    @staticmethod
    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                     return_trades=False, **kw):
        trades = []
        for i in range(20, len(closes) - 1, 7):
            if (highs[i] - lows[i]) / closes[i] > 0.0004:   # a ratio to the level: not offset-proof
                trades.append((i, i + 1, float(closes[i + 1] - closes[i])))
        out = {"total_pnl": sum(t[2] for t in trades), "num_trades": len(trades)}
        if return_trades:
            out["trades"] = trades
        return out


class WarmsUpSlowly:
    """Level-dependent, but only after 60 sessions - NOISE's vol filter in miniature.

    Below the warm-up it takes the SAME trades whatever the price level, so a short probe window
    cannot tell it apart from LevelFree. That is the false negative MIN_SESSIONS exists for.
    """
    @staticmethod
    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                     return_trades=False, **kw):
        n_sessions = len(np.unique(day_id)) if day_id is not None else 0
        trades = []
        for i in range(20, len(closes) - 1, 7):
            if n_sessions >= 60 and (highs[i] - lows[i]) / closes[i] > 0.0004:
                continue                                   # skipped only once warmed up
            trades.append((i, i + 1, float(closes[i + 1] - closes[i])))
        out = {"total_pnl": sum(t[2] for t in trades), "num_trades": len(trades)}
        if return_trades:
            out["trades"] = trades
        return out


class NoTrades:
    @staticmethod
    def run_backtest(*a, **kw):
        return {"total_pnl": 0.0, "num_trades": 0, "trades": []}


class Explodes:
    @staticmethod
    def run_backtest(*a, **kw):
        raise RuntimeError("this strategy is broken")


@pytest.fixture(autouse=True)
def _fresh_cache():
    adj_level.clear_cache()
    yield
    adj_level.clear_cache()


# ═══════════════════════════════════════════════════ which masters are back-adjusted
@pytest.mark.parametrize("name,expected", [
    ("ADJ_NQ_5m_RTH.csv", True),
    ("FADJ_ES_30m_RTH.csv", True),
    ("adj_nq_5m_rth.csv", True),                      # case is not a contract
    (r"C:\EdgeLog\augur_uploads\ADJ_NQ_1m_ETH.csv", True),
    ("NQ_5m_RTH.csv", False),
    ("NOADJ_NQ_5m_ETH.csv", False),                   # NOT back-adjusted, despite containing ADJ
    ("", False),
    (None, False),
])
def test_only_back_adjusted_masters_are_in_scope(name, expected):
    assert adj_level.is_back_adjusted(name) is expected


def test_the_probe_shift_is_the_instruments_real_roll_offset():
    """Not a round number someone liked: the actual cumulative back-adjustment, so the question
    asked is the one that matters for this master."""
    nq = adj_level.adjustment_offset_pts("ADJ_NQ_5m_RTH.csv")
    es = adj_level.adjustment_offset_pts("ADJ_ES_5m_RTH.csv")
    assert nq > 1000.0, nq                            # measured 3733.75 on 2026-10-05
    assert es > 100.0, es                             # measured 653.00
    assert nq != es, "a per-instrument offset that is not per-instrument is a bug"


def test_an_unparseable_master_still_gets_a_usable_shift():
    assert adj_level.adjustment_offset_pts("ADJ_.csv") == adj_level.FALLBACK_OFFSET_PTS
    assert adj_level.adjustment_offset_pts("ADJ_ZZZZ_5m_RTH.csv") > 0.0


# ═══════════════════════════════════════════════════ the discrimination itself
def test_a_strategy_reading_a_difference_over_a_level_is_caught():
    kind, detail = adj_level.verdict(ReadsLevels, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert kind == "dependent", detail
    assert "change" in detail and "points" in detail


def test_a_strategy_reading_only_differences_is_left_alone():
    kind, detail = adj_level.verdict(LevelFree, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert kind == "invariant", detail


def test_a_ratio_of_two_DIFFERENCES_is_left_alone():
    """TTM's squeeze is a Bollinger width over a Keltner width. Both move together under an
    offset, so the ratio does not - and a source scan for "divides by a price" cannot tell this
    from NOISE's (H-L)/C, which is the reason this module probes behaviour."""
    class RatioOfWidths:
        @staticmethod
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         return_trades=False, **kw):
            trades = []
            for i in range(30, len(closes) - 1, 7):
                w = closes[i - 20:i].std()
                k = float(np.mean(highs[i - 20:i] - lows[i - 20:i]))
                if k > 0 and w / k > 0.5:
                    trades.append((i, i + 1, float(closes[i + 1] - closes[i])))
            out = {"total_pnl": sum(t[2] for t in trades), "num_trades": len(trades)}
            if return_trades:
                out["trades"] = trades
            return out

    kind, detail = adj_level.verdict(RatioOfWidths, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert kind == "invariant", detail


def test_entry_and_exit_PRICES_moving_is_not_level_dependence():
    """A level-invariant strategy's fills still move with the offset - that is arithmetic, not a
    finding. Only which trades happen and what they make in points may not move."""
    class ReportsPrices:
        @staticmethod
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         return_trades=False, **kw):
            trades = []
            for i in range(20, len(closes) - 1, 7):
                if closes[i] - closes[i - 10] > 5.0:
                    trades.append((i, i + 1, float(closes[i + 1] - closes[i]),
                                   float(closes[i]), float(closes[i + 1])))
            out = {"total_pnl": sum(t[2] for t in trades), "num_trades": len(trades)}
            if return_trades:
                out["trades"] = trades
            return out

    kind, detail = adj_level.verdict(ReportsPrices, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert kind == "invariant", detail


# ═══════════════════════════════════════════════════ THE FLOOR: never say "clean" on a short window
def test_a_window_too_short_to_judge_returns_unknown_not_invariant():
    """THE ONE THAT WOULD DO REAL DAMAGE. WarmsUpSlowly is level-dependent, but not until 60
    sessions have gone by. On a 40-session window it behaves exactly like a level-free strategy,
    so an honest guard must refuse to answer rather than report it clean."""
    kind, detail = adj_level.verdict(WarmsUpSlowly, _bars(n_sessions=40), "ADJ_NQ_5m_RTH.csv")
    assert kind == "unknown", "reported %r on a window too short to judge: %s" % (kind, detail)
    assert "sessions" in detail


def test_the_same_strategy_is_caught_once_the_window_is_long_enough():
    kind, detail = adj_level.verdict(WarmsUpSlowly, _bars(n_sessions=300), "ADJ_NQ_5m_RTH.csv")
    assert kind == "dependent", detail


def test_the_floor_is_well_clear_of_the_known_warm_up():
    """NOISE's filter needs 60 reference sessions, and at 65 sessions the real dependence showed
    up in ONE trade out of 29 - detection by a thread. The floor is set where it was measured to
    be solid (131 sessions caught 86 of 106), not where it merely becomes possible."""
    assert adj_level.MIN_SESSIONS >= 120
    assert adj_level.PROBE_SESSIONS >= 2 * adj_level.MIN_SESSIONS


def test_no_trades_is_unknown_rather_than_clean():
    kind, _ = adj_level.verdict(NoTrades, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert kind == "unknown"


def test_a_master_without_day_id_is_unknown():
    arrays = _bars()
    arrays["day_id"] = None
    kind, detail = adj_level.verdict(LevelFree, arrays, "ADJ_NQ_5m_RTH.csv")
    assert kind == "unknown" and "day_id" in detail


# ═══════════════════════════════════════════════════ it must never break a run
def test_a_strategy_that_raises_does_not_propagate():
    kind, detail = adj_level.verdict(Explodes, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert kind == "unknown"
    assert "RuntimeError" in detail


def test_warning_for_swallows_everything():
    assert adj_level.warning_for(Explodes, _bars(), "ADJ_NQ_5m_RTH.csv") is None
    assert adj_level.warning_for(LevelFree, {}, "ADJ_NQ_5m_RTH.csv") is None
    assert adj_level.warning_for(object(), _bars(), "ADJ_NQ_5m_RTH.csv") is None
    assert adj_level.warning_for(LevelFree, None, "ADJ_NQ_5m_RTH.csv") is None


def test_a_raw_master_is_never_warned_about_however_level_dependent_the_strategy():
    assert adj_level.warning_for(ReadsLevels, _bars(), "NQ_5m_RTH.csv") is None


def test_the_warning_names_the_master_and_says_what_to_do():
    msg = adj_level.warning_for(ReadsLevels, _bars(), "ADJ_NQ_5m_RTH.csv")
    assert msg
    assert "ADJ_NQ_5m_RTH.csv" in msg
    assert "raw master" in msg, "it has to say what the reader should actually check"


def test_an_invariant_strategy_produces_no_warning():
    assert adj_level.warning_for(LevelFree, _bars(), "ADJ_NQ_5m_RTH.csv") is None


def test_an_unknown_verdict_produces_no_warning():
    """"Cannot judge" is not "guilty" - it must not cry wolf on every short run."""
    assert adj_level.warning_for(WarmsUpSlowly, _bars(n_sessions=40), "ADJ_NQ_5m_RTH.csv") is None


# ═══════════════════════════════════════════════════ cost
def test_the_verdict_is_cached_so_a_long_search_probes_once():
    calls = {"n": 0}

    class Counted:
        @staticmethod
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         return_trades=False, **kw):
            calls["n"] += 1
            return ReadsLevels.run_backtest(opens, highs, lows, closes, volumes=volumes,
                                            day_id=day_id, return_trades=return_trades, **kw)

    arrays = _bars()
    for _ in range(50):
        adj_level.warning_for(Counted, arrays, "ADJ_NQ_5m_RTH.csv")
    assert calls["n"] == 2, "50 calls cost %d strategy runs, not 2" % calls["n"]


def test_the_cache_is_not_keyed_on_params():
    """A 900-trial validate changes params every trial. Keying on them would probe 900 times and
    make the warning cost more than what it warns about."""
    key_a = adj_level._cache_key(ReadsLevels, "ADJ_NQ_5m_RTH.csv")
    key_b = adj_level._cache_key(ReadsLevels, "ADJ_NQ_5m_RTH.csv")
    assert key_a == key_b
    import inspect as _i
    assert "params" not in _i.signature(adj_level._cache_key).parameters
    assert "params" not in _i.signature(adj_level.warning_for).parameters


def test_different_masters_are_judged_separately():
    a = adj_level._cache_key(ReadsLevels, "ADJ_NQ_5m_RTH.csv")
    b = adj_level._cache_key(ReadsLevels, "ADJ_ES_5m_RTH.csv")
    assert a != b


def test_a_changed_strategy_is_judged_again():
    """Keyed on the source, so an edited strategy is not answered from a stale verdict."""
    a = adj_level._cache_key(ReadsLevels, "ADJ_NQ_5m_RTH.csv")
    b = adj_level._cache_key(LevelFree, "ADJ_NQ_5m_RTH.csv")
    assert a != b


# ═══════════════════════════════════════════════════ the slice
def test_the_probe_window_is_taken_from_the_END_of_the_master():
    """The newest bars are what a current run cares about."""
    arrays = _bars(n_sessions=500)
    probe, n = adj_level._tail_sessions(arrays, 100)
    assert n == 100
    assert probe["close"][-1] == arrays["close"][-1]


def test_the_sliced_day_id_is_rebased_to_zero():
    """The day_id-aware strategies index their own session tables with it, so a slice that kept
    the original numbering would read off the end."""
    probe, _ = adj_level._tail_sessions(_bars(n_sessions=500), 100)
    assert probe["day_id"].min() == 0
    assert probe["day_id"].max() == 99
    assert np.all(np.diff(probe["day_id"]) >= 0), "sessions must stay in order"


def test_a_short_master_is_not_padded_or_wrapped():
    probe, n = adj_level._tail_sessions(_bars(n_sessions=30), 400)
    assert n == 30
    assert len(probe["close"]) == 300


# ═══════════════════════════════════════════════════ the engine hook
def test_the_engine_flag_is_off_by_default():
    """The probe runs the strategy twice; paying that on every backtest is not acceptable, so the
    callers that report a number to a person opt in."""
    import inspect as _i
    from augur_engine import engine
    p = _i.signature(engine.run_backtest).parameters
    assert "adj_warn" in p
    assert p["adj_warn"].default is False


def test_the_engine_helper_never_raises():
    from augur_engine import engine
    assert engine._adj_level_warning(Explodes, _bars(), {"filename": "ADJ_NQ_5m_RTH.csv"}) is None
    assert engine._adj_level_warning(LevelFree, None, None) is None


def test_the_engine_helper_finds_the_filename_on_the_master_row():
    from augur_engine import engine
    msg = engine._adj_level_warning(ReadsLevels, _bars(), {"filename": "ADJ_NQ_5m_RTH.csv"})
    assert msg and "ADJ_NQ_5m_RTH.csv" in msg
