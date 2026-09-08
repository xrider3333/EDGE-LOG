"""tools/queue_guard.py's --book-run: grade EVERY leg of a BOOK run doc in one command.

WHY: a BOOK job (tools/book_smoke.py / the runner's BOOK job type) pools several strategy
legs over one shared window and scores them as ONE strategy; its run doc carries
`book.legs[]` (one dict per leg, already shaped like a resolved leg -- strategy/instrument/
timeframe/session/source/cost_pts/mult/trades/net/weight, no per-leg params) plus
`book.date_from` / `book.date_to` / `book.lockbox_from` / `book.lockbox`. Before this change
every leg had to be guarded by hand with copied flags; `_grade_book()` (called by
`_book_run()` after its one Firestore doc read) now does every leg in one pass, prints a
summary table, and reports a pooled continuous lockbox line next to the doc's day-sliced
`book.lockbox`.

These tests exercise `_grade_book()` only, with the module-level `guard()` monkeypatched to
a fake that returns canned result dicts shaped exactly like a real guard() return (see
guard()'s two `return dict(...)` statements in tools/queue_guard.py). No engine call, no
Firestore -- `_grade_book()` takes a plain `book` dict and never touches either.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import tools.queue_guard as qg  # noqa: E402


def _fake_book():
    """A two-leg BOOK doc's `book` sub-dict, shaped like the module docstring's example."""
    return dict(
        date_from="2010-01-01",
        date_to="2026-01-01",
        lockbox_from="2025-01-01",
        legs=[
            dict(strategy="LEG_A.py", instrument="NQ", timeframe="5m", session="rth",
                 source="db_noadj_rth", cost_pts=0.533, mult=20.0, trades=100,
                 net=1000.0, weight=1.0),
            dict(strategy="LEG_B.py", instrument="NQ", timeframe="1m", session="eth",
                 source="db_noadj_eth", cost_pts=0.533, mult=20.0, trades=200,
                 net=2000.0, weight=1.0),
        ],
        lockbox=dict(num_trades=250, total_pnl=50000.0, profit_factor=1.3,
                    max_drawdown=10000.0),
    )


def _fake_result(strategy, verdict, lb_n=5, lb_net=2000.0):
    """A guard()-shaped result dict for `strategy` with the given verdict -- same keys as
    guard()'s real return (see tools/queue_guard.py's two `return dict(...)` statements)."""
    exit_code = {"PASS": 0, "ARTIFACT": 1, "SUSPECT": 2}[verdict]
    return dict(
        label=strategy, strategy=strategy, params={}, resolved_params={}, param_source={},
        has_default_params=True, verdict=verdict, reasons=["canned reason"],
        exit_code=exit_code,
        sel=dict(n=50, pf=1.2, wr=40.0, net=5000.0, dd=1000.0, mar=1.0, evr=0.1, ryr=5.0),
        lb=dict(n=lb_n, pf=1.1, wr=35.0, net=lb_net, dd=800.0, mar=1.2, evr=0.05, ryr=2.0),
        all=dict(n=50 + lb_n, pf=1.15, wr=38.0, net=5000.0 + lb_net, dd=1200.0, mar=1.1,
                 evr=0.08, ryr=3.5),
        sel_ex10=dict(n=40, net=2500.0), top10_share=45.0, reload_n=lb_n,
        continuous_lb_n=lb_n, longest_hold_days=3, engine_expectancy_r=0.1,
        cross_expectancy_r=0.1, date_from="2010-01-01", date_to="2026-01-01",
        split="2025-01-01",
    )


def test_leg_kwargs_built_per_leg_from_book_window(monkeypatch):
    """Every leg's guard() call must use the BOOK's own date_from/date_to/lockbox_from
    (split = lockbox_from) and params={} (a book leg carries no per-leg params today, so
    resolve_params() inside guard() falls back to the file's real DEFAULT_PARAMS)."""
    calls = []

    def fake_guard(**kw):
        calls.append(kw)
        return _fake_result(kw["strategy_file"], "PASS")

    monkeypatch.setattr(qg, "guard", fake_guard)
    book = _fake_book()

    results, worst = qg._grade_book(999, book)

    assert len(calls) == 2
    by_strategy = {kw["strategy_file"]: kw for kw in calls}
    assert set(by_strategy) == {"LEG_A.py", "LEG_B.py"}
    for kw in calls:
        assert kw["date_from"] == "2010-01-01"
        assert kw["date_to"] == "2026-01-01"
        assert kw["split"] == "2025-01-01"          # split = book.lockbox_from
        assert kw["params"] == {}                    # no per-leg params -> {}

    a_kw = by_strategy["LEG_A.py"]
    assert a_kw["instrument"] == "NQ"
    assert a_kw["timeframe"] == "5m"
    assert a_kw["session"] == "rth"
    assert a_kw["source"] == "db_noadj_rth"
    assert a_kw["cost_pts"] == 0.533
    assert a_kw["mult"] == 20.0

    assert len(results) == 2
    assert worst == 0


def test_summary_table_prints_both_legs(monkeypatch, capsys):
    def fake_guard(**kw):
        return _fake_result(kw["strategy_file"], "PASS")

    monkeypatch.setattr(qg, "guard", fake_guard)
    qg._grade_book(999, _fake_book())

    out = capsys.readouterr().out
    assert "BOOK RUN #999 SUMMARY" in out
    assert "LEG_A.py" in out
    assert "LEG_B.py" in out
    # each leg's own doc `trades` count appears next to the guard WHOLE RUN n
    assert "100" in out
    assert "200" in out


def test_pooled_line_uses_doc_book_lockbox_numbers(monkeypatch, capsys):
    def fake_guard(**kw):
        # distinct lockbox n/net per leg so the pooled sum is unambiguous
        if kw["strategy_file"] == "LEG_A.py":
            return _fake_result(kw["strategy_file"], "PASS", lb_n=3, lb_net=1000.0)
        return _fake_result(kw["strategy_file"], "PASS", lb_n=7, lb_net=3000.0)

    monkeypatch.setattr(qg, "guard", fake_guard)
    qg._grade_book(999, _fake_book())

    out = capsys.readouterr().out
    assert "POOLED continuous ENTRY-sliced lockbox" in out
    assert "n=10" in out            # 3 + 7
    assert "net=$4000" in out       # 1000 + 3000
    # the doc's own DAY-sliced book.lockbox numbers must be printed too, unflagged
    assert "book.lockbox (DAY-sliced" in out
    assert "n=250" in out
    assert "net=$50000.0" in out
    # side by side, never flagged
    assert "*** MISMATCH ***" not in out.split("POOLED continuous")[1]


@pytest.mark.parametrize("verdict_a, verdict_b, expected_exit", [
    ("ARTIFACT", "PASS", 1),
    ("SUSPECT", "PASS", 2),
    ("PASS", "PASS", 0),
])
def test_exit_code_is_worst_leg(monkeypatch, verdict_a, verdict_b, expected_exit):
    verdicts = {"LEG_A.py": verdict_a, "LEG_B.py": verdict_b}

    def fake_guard(**kw):
        return _fake_result(kw["strategy_file"], verdicts[kw["strategy_file"]])

    monkeypatch.setattr(qg, "guard", fake_guard)
    _results, worst = qg._grade_book(123, _fake_book())
    assert worst == expected_exit
