"""Two readings the run report has never had: realistic cost, and stated blind spots.

BOTH COME FROM MANAGER's ziplime review (owner GO 2026-09-30), built as our own code.

(b) REALISTIC COST. Every run charges one flat cost per round trip and reports one net, which
    answers "did the rule find an edge" and not "would the edge survive being traded". The case
    that forced it: live NOISE on Webull paid about $0.30 per share each way against an edge of
    about $0.10 per share.

(c) WHAT THIS RUN DOES NOT MODEL. The assumptions are written down across ROLL_AUDIT.md,
    RESEARCH.md and a dozen memory notes, so in practice they are known by whoever read them
    most recently. The list has to be built from the RUN's settings, not printed as a fixed
    paragraph, or it will be ignored within a week.

THE TRAP THESE TESTS GUARD HARDEST: trades arrive NET - run_backtest already subtracted
cost_pts (analytics.py: "never re-subtract"). Re-costing means adding the old charge back
first. Charging a new cost straight onto a net trade list double-counts, and a double-counted
cost makes every crown look worse in a way that is very hard to spot.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import cost_readings as cr  # noqa: E402
from augur_engine import run_limits as rl  # noqa: E402


def trades(net_pnls):
    """A trade list in the engine's shape: (entry, exit, net_pnl)."""
    return [(i, i + 1, p) for i, p in enumerate(net_pnls)]


# ============================================================ (b) realistic cost

def test_the_flat_net_is_reproduced_exactly():
    """The new reading must not move the number the run already reports, or nobody can trust
    either of them."""
    t = trades([1.0, 2.0, -0.5])            # already net of a 0.5 charge
    r = cr.readings(t, cost_pts=0.5)
    assert r["net_flat_pts"] == pytest.approx(2.5)


def test_the_cost_is_added_back_before_it_is_recharged():
    """THE trap. Gross must be net + n*cost. Getting this wrong double-charges every trade."""
    t = trades([1.0, 1.0])                  # net, after 0.5 each
    assert cr.gross_pnls(t, 0.5).tolist() == [1.5, 1.5]
    r = cr.readings(t, cost_pts=0.5)
    assert r["gross_pts"] == pytest.approx(3.0)
    assert r["net_flat_pts"] == pytest.approx(2.0)
    assert r["net_double_pts"] == pytest.approx(1.0)


def test_double_cost_subtracts_exactly_one_more_charge_per_trade():
    t = trades([2.0] * 10)
    r = cr.readings(t, cost_pts=0.533)
    assert r["net_flat_pts"] - r["net_double_pts"] == pytest.approx(10 * 0.533)


def test_breakeven_is_the_cost_that_takes_net_to_zero():
    t = trades([1.0, 1.0, 1.0])             # gross 4.5 at cost 0.5
    r = cr.readings(t, cost_pts=0.5)
    be = r["breakeven_cost_pts"]
    assert be == pytest.approx(1.5)
    recheck = cr.readings(t, cost_pts=0.5)["gross_pts"] - 3 * be
    assert recheck == pytest.approx(0.0), "charging the breakeven must leave zero"


def test_headroom_says_how_many_times_its_own_cost_a_run_can_absorb():
    t = trades([1.0, 1.0, 1.0])
    r = cr.readings(t, cost_pts=0.5)
    assert r["headroom_x"] == pytest.approx(3.0)


def test_a_run_that_loses_before_any_cost_quotes_no_breakeven():
    """Quoting a negative 'breakeven cost' would read as though a rebate would save it."""
    r = cr.readings(trades([-2.0, -1.0]), cost_pts=0.5)
    assert r["breakeven_cost_pts"] is None and r["headroom_x"] is None
    assert any("loses money before any cost" in l for l in cr.summary_lines(r))


def test_money_uses_the_instrument_multiplier():
    r = cr.readings(trades([1.0, 1.0]), cost_pts=0.0, mult=20.0)
    assert r["net_flat_usd"] == pytest.approx(40.0)


def test_no_trades_is_answered_not_crashed():
    r = cr.readings([], cost_pts=0.533)
    assert r["n_trades"] == 0 and r["breakeven_cost_pts"] is None
    assert cr.summary_lines(r) == ["No trades, so there is nothing to re-cost."]


def test_the_realistic_cost_is_built_from_named_parts():
    c, b = cr.realistic_cost_pts("NQ", atr_pts=40.0, contracts=1)
    assert c == pytest.approx(b["fee_pts"] + b["spread_pts"] + b["slippage_pts"])
    assert b["fee_pts"] > 0 and b["spread_pts"] > 0 and b["slippage_pts"] > 0


def test_slippage_grows_with_volatility():
    quiet, _ = cr.realistic_cost_pts("NQ", atr_pts=10.0)
    fast, _ = cr.realistic_cost_pts("NQ", atr_pts=80.0)
    assert fast > quiet


def test_the_fee_grows_with_size_but_the_spread_does_not():
    """A fee is per contract; crossing the spread costs the same per contract whatever the
    size. Conflating them would overstate the cost of trading bigger."""
    _, one = cr.realistic_cost_pts("NQ", atr_pts=20.0, contracts=1)
    _, ten = cr.realistic_cost_pts("NQ", atr_pts=20.0, contracts=10)
    assert ten["fee_pts"] == pytest.approx(one["fee_pts"] * 10)
    assert ten["spread_pts"] == pytest.approx(one["spread_pts"])


def test_every_realistic_reading_says_it_is_not_fitted():
    """These are published figures, not measured against our fills. A reading that forgets to
    say so would be quoted as a verdict."""
    r = cr.realistic(trades([1.0] * 5), cost_pts=0.5, instrument="NQ", mult=20.0, atr_pts=30.0)
    assert r["realistic_breakdown"]["fitted"] is False
    assert r["realistic_breakdown"]["source"]
    assert any("NOT fitted" in l for l in cr.summary_lines(r))


def test_the_qqq_case_that_prompted_this_shows_up_as_not_surviving():
    """About $0.30 per share round trip against a ~$0.10 per share edge: the reading has to say
    this does not survive, because that is the finding that motivated the work."""
    edge_per_share = 0.10
    t = trades([edge_per_share] * 200)                    # net at zero charged cost
    r = cr.realistic(t, cost_pts=0.0, instrument="QQQ", mult=1.0)
    assert r["net_flat_pts"] == pytest.approx(20.0)
    assert r["realistic_cost_pts"] >= 0.02
    assert r["survives"] is False, r
    assert r["net_realistic_pts"] < 0


def test_a_run_inside_its_own_costs_is_flagged_against_its_breakeven():
    t = trades([0.05] * 100)
    r = cr.realistic(t, cost_pts=0.0, instrument="QQQ", mult=1.0)
    assert r["realistic_over_breakeven"] > 1.0, "realistic cost above breakeven = under water"


# ==================================================== (c) what this run does not model

def _run(**kw):
    base = dict(instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
                date_from="2015-01-01", date_to="2026-05-01", cost_pts=0.533, n_trades=400)
    base.update(kw)
    return base


def test_a_no_adjust_run_is_warned_about_roll_steps():
    keys = [i["key"] for i in rl.not_modelled(_run())]
    assert "no_adjust_rolls" in keys


def test_a_roll_corrected_run_is_NOT_warned_about_roll_steps():
    """The whole point of building this per run: a fixed paragraph would warn about a problem
    this run does not have, and then be ignored."""
    items = rl.not_modelled(_run(source="db_adj_rth"))
    keys = [i["key"] for i in items]
    assert "no_adjust_rolls" not in keys
    assert "roll_corrected" in keys


def test_a_window_ending_before_the_feed_change_is_not_warned_about_it():
    keys = [i["key"] for i in rl.not_modelled(_run(date_to="2026-01-01"))]
    assert "secondary_feed" not in keys


def test_a_window_reaching_past_the_feed_change_IS_warned():
    keys = [i["key"] for i in rl.not_modelled(_run(date_to="2026-09-30"))]
    assert "secondary_feed" in keys


def test_the_summer_hole_is_only_mentioned_when_the_window_spans_it():
    assert "summer_hole" not in [i["key"] for i in rl.not_modelled(_run(date_to="2026-06-01"))]
    assert "summer_hole" in [i["key"] for i in rl.not_modelled(_run(date_to="2026-09-30"))]


def test_a_thin_sealed_test_is_called_material():
    items = {i["key"]: i for i in rl.not_modelled(_run(lockbox_trades=12))}
    assert items["thin_lockbox"]["severity"] == "material"
    assert "12" in items["thin_lockbox"]["text"]


def test_one_trade_carrying_the_sealed_test_is_named_with_its_share():
    items = {i["key"]: i for i in rl.not_modelled(
        _run(lockbox_trades=120, lockbox_net=100.0, lockbox_top_trade_net=103.0))}
    txt = items["one_trade_lockbox"]["text"]
    assert "103%" in txt and "NOT profitable" in txt


def test_a_sealed_test_that_survives_losing_its_best_trade_says_so():
    items = {i["key"]: i for i in rl.not_modelled(
        _run(lockbox_trades=120, lockbox_net=100.0, lockbox_top_trade_net=55.0))}
    assert "still positive" in items["one_trade_lockbox"]["text"]


def test_close_day_accounting_is_flagged_only_when_it_applies():
    assert "close_day_pnl" in [i["key"] for i in rl.not_modelled(_run(marked_daily=False))]
    assert "close_day_pnl" not in [i["key"] for i in rl.not_modelled(_run(marked_daily=True))]


def test_the_flat_cost_is_always_stated_with_its_value():
    items = {i["key"]: i for i in rl.not_modelled(_run(cost_pts=0.533))}
    assert "0.533" in items["flat_cost"]["text"]


def test_margin_and_the_absence_of_a_forward_test_are_always_stated():
    keys = [i["key"] for i in rl.not_modelled(_run())]
    assert "no_margin" in keys and "no_forward_test" in keys


def test_a_thin_run_gets_a_shorter_list_never_a_wrong_one():
    """A run dict missing most fields must not invent facts about it."""
    items = rl.not_modelled({"instrument": "NQ"})
    keys = [i["key"] for i in items]
    assert "no_margin" in keys
    for absent in ("thin_lockbox", "one_trade_lockbox", "close_day_pnl", "summer_hole",
                   "flat_cost"):
        assert absent not in keys, absent


def test_material_items_come_first():
    out = rl.lines(_run(date_to="2026-09-30", lockbox_trades=10))
    items = rl.not_modelled(_run(date_to="2026-09-30", lockbox_trades=10))
    n_mat = sum(1 for i in items if i["severity"] == "material")
    mat_texts = {i["text"] for i in items if i["severity"] == "material"}
    assert set(out[:n_mat]) == mat_texts


def test_the_lines_read_as_english_without_code_identifiers():
    for text in rl.lines(_run(date_to="2026-09-30", lockbox_trades=10, marked_daily=False)):
        for bad in ("cost_pts", "db_noadj", "lockbox_trades", "_", "()"):
            if bad == "_":
                assert "_" not in text.replace("roll-corrected", ""), text
            else:
                assert bad not in text, text


def test_counts_are_available_for_a_chip():
    c = rl.counts(_run(date_to="2026-09-30", lockbox_trades=10))
    assert c["total"] == c["material"] + c["note"] and c["material"] >= 3
