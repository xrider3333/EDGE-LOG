"""tools/backfill_wf_oos.py - the walk-forward OOS block backfill for saved runs
(ENGINE_BRIEF.md STAGE 2, 2026-09-15).

WHY: `validate.wf_oos` is only ever written from the SAME per-trade OOS pnls a fold's own
saved oos_trades/oos_pnl/oos_pf/oos_wins already describe - so a backfilled block must be
proven to reconcile against those saved numbers before anything is written, and any run whose
data or params can no longer be pinned exactly as the run used them must be refused, not
guessed at. These tests pin, with no Firestore and no market data:
  * fold-bound reconstruction (fold_bounds_from_rows) from the doc's OWN saved rows only, for
    BOTH walk-forward schemes - and, end to end, against a REAL run_auto walk-forward result
    on synthetic data for both "rolling" and "anchored";
  * per-fold param reconstruction (fold_params) exactly as auto.py's `_wf_fold_row` passed
    them to `ev`, refusing when the strategy's DEFAULT_PARAMS no longer matches the saved row;
  * plan refusal cases (rebuild_plan) - every way a doc can fail to pin a replay;
  * per-fold match/mismatch logic (build_fold_match) against an injected evaluator, real or
    stubbed, including the tolerances and the float('inf') profit-factor edge case;
  * the block is refused (None) unless EVERY fold matched (build_block);
  * payload shape (check_payload) - only validate.wf_oos, only a well-formed block, only with
    this tool's own provenance;
  * the orchestration (dry run, write with a precondition, changed doc, conflict, a lost
    reply, --force) on a fake Firestore, exactly the shape tools/backfill_lb_tails.py's own
    tests already use;
  * --list output and the runner's own size guard.
"""
import copy
import subprocess
import sys
import types
import os

import numpy as np
import pandas as pd
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(_REPO, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import backfill_wf_oos as B  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# fold_bounds_from_rows - pure fold-bound reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def _rolling_rows(n_folds=3, init=1000, tsize=500):
    """train_bars CONSTANT across folds (rolling: the IS window slides, always `init`
    bars long) - as auto.py's run_auto actually produces."""
    rows = []
    for f in range(n_folds):
        te_s = init + f * tsize
        rows.append({"fold": f + 1, "train_bars": init, "test_bars": tsize,
                     "oos_pnl": 10.0 * (f + 1), "oos_trades": 5 * (f + 1), "oos_pf": 1.2,
                     "oos_wins": 3 * (f + 1)})
    return rows


def _anchored_rows(n_folds=3, init=1000, tsize=500):
    """train_bars GROWS every fold (anchored: the IS window always starts at bar 0) - but
    fold 1's train_bars is still `init`, exactly like rolling's."""
    rows = []
    for f in range(n_folds):
        rows.append({"fold": f + 1, "train_bars": init + f * tsize, "test_bars": tsize,
                     "oos_pnl": 10.0 * (f + 1), "oos_trades": 5 * (f + 1), "oos_pf": 1.2,
                     "oos_wins": 3 * (f + 1)})
    return rows


@pytest.mark.parametrize("rows_fn", [_rolling_rows, _anchored_rows])
def test_fold_bounds_are_scheme_agnostic_from_train_bars_fold1_plus_cumulative_test_bars(rows_fn):
    rows = rows_fn(n_folds=3, init=1000, tsize=500)
    bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
    assert reason is None
    # BOTH schemes must land on the SAME te_s/te_e - only fold 1's train_bars anchors it
    assert [(b["fold"], b["te_s"], b["te_e"]) for b in bounds] == [
        (1, 1000, 1500), (2, 1500, 2000), (3, 2000, 2500)]
    assert expect_n == 2500
    assert [b["row"] is r for b, r in zip(bounds, rows)]


def test_fold_bounds_sorts_out_of_order_rows():
    rows = _rolling_rows(3)
    rows = [rows[2], rows[0], rows[1]]           # fold 3, 1, 2
    bounds, _n, reason = B.fold_bounds_from_rows(rows)
    assert reason is None
    assert [b["fold"] for b in bounds] == [1, 2, 3]


def test_fold_bounds_refuses_a_gap_left_by_a_dropped_fold():
    # run_auto (auto.py / wf_pool.py) drops a fold's row entirely when none of its trials
    # clear min_trades -- e.g. fold 2 of 4 missing, leaving folds 1, 3, 4.
    rows = _rolling_rows(4)
    del rows[1]
    bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
    assert bounds is None and expect_n is None
    assert "[1, 3, 4]" in reason and "[1, 2, 3]" in reason, reason


def test_fold_bounds_refuses_a_duplicate_fold_number():
    rows = _rolling_rows(3)
    rows[2]["fold"] = 2                          # folds 1, 2, 2 -- no fold 3
    bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
    assert bounds is None and expect_n is None
    assert "[1, 2, 2]" in reason and "[1, 2, 3]" in reason, reason


def test_fold_bounds_refuses_empty_or_missing_rows():
    for rows in ([], None):
        bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
        assert bounds is None and expect_n is None
        assert "no top10_results fold rows" in reason


@pytest.mark.parametrize("mutate,expect", [
    (lambda rows: rows[0].pop("fold"), "carries no fold number"),
    (lambda rows: rows[0].pop("train_bars"), "fold 1 carries no train_bars"),
    (lambda rows: rows[1].pop("test_bars"), "fold 2 carries no test_bars"),
    (lambda rows: rows[1].update(test_bars=0), "fold 2 has test_bars <= 0"),
    (lambda rows: rows[2].pop("oos_pnl"), "fold 3 carries no oos_pnl"),
    (lambda rows: rows[2].pop("oos_trades"), "fold 3 carries no oos_trades"),
    (lambda rows: rows[2].pop("oos_pf"), "fold 3 carries no oos_pf"),
])
def test_fold_bounds_refusal_reasons(mutate, expect):
    rows = _rolling_rows(3)
    mutate(rows)
    bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
    assert bounds is None and expect_n is None
    assert expect in reason, reason


# ─────────────────────────────────────────────────────────────────────────────
# fold_params - per-fold param reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def test_fold_params_happy_path():
    rows = [{"fold": 1, "a": 1.0, "b": 2.0, "junk": 99}, {"fold": 2, "a": 3.0, "b": 4.0}]
    out, reason = B.fold_params(["a", "b"], rows)
    assert reason is None
    assert out == [{"a": 1.0, "b": 2.0}, {"a": 3.0, "b": 4.0}]


def test_fold_params_refuses_a_missing_knob():
    rows = [{"fold": 1, "a": 1.0, "b": 2.0}, {"fold": 2, "a": 3.0}]      # fold 2 lost "b"
    out, reason = B.fold_params(["a", "b"], rows)
    assert out is None
    assert "fold 2" in reason and "['b']" in reason and "not reconstructible" in reason


def test_fold_params_refuses_no_tunable_params():
    out, reason = B.fold_params([], [{"fold": 1}])
    assert out is None and "no tunable DEFAULT_PARAMS" in reason


# ─────────────────────────────────────────────────────────────────────────────
# rebuild_plan - every way a doc can fail to pin a replay
# ─────────────────────────────────────────────────────────────────────────────

def _doc(mode="rolling", n_folds=3, cost_pts=0.5, data_source="db_noadj_rth"):
    rows_fn = _rolling_rows if mode == "rolling" else _anchored_rows
    return {
        "strategy": "SYN_STRAT.py", "instrument": "NQ", "timeframe": "5m",
        "data_source": data_source, "cost_pts": cost_pts,
        # the whole-run window (runner.py's own date_from/date_to) -- display-only,
        # DIFFERENT from validate.windows.optimize (the pinned replay window below)
        "date_from": "2010-06-07", "date_to": "2025-06-07",
        "top10_results": rows_fn(n_folds),
        "validate": {"wf_ran": True, "wf_best_mode": mode,
                    "windows": {"optimize": ["2010-06-07", "2024-06-07"]}},
    }


def test_rebuild_plan_happy_path():
    d = _doc()
    plan, why = B.rebuild_plan(d)
    assert why is None
    assert plan["strategy"] == "SYN_STRAT.py"
    assert plan["session"] == "rth" and plan["source"] == "db_noadj_rth"
    assert plan["cost_pts"] == 0.5
    assert (plan["date_from"], plan["date_to"]) == ("2010-06-07", "2024-06-07")
    assert plan["mode"] == "rolling"
    assert plan["expect_n"] == 2500
    assert len(plan["folds"]) == 3


def test_rebuild_plan_normalizes_mode_case():
    d = _doc()
    d["validate"]["wf_best_mode"] = "ROLLING"
    plan, why = B.rebuild_plan(d)
    assert why is None and plan["mode"] == "rolling"


def test_rebuild_plan_refuses_a_non_dict():
    plan, why = B.rebuild_plan("not a dict")
    assert plan is None and why == "no doc"


@pytest.mark.parametrize("edit,expect", [
    (lambda d: d["validate"].update(wf_ran=False), "wf_ran is not True"),
    (lambda d: d["validate"].pop("wf_best_mode"), "no usable validate.wf_best_mode"),
    (lambda d: d["validate"].update(wf_best_mode="sideways"), "no usable validate.wf_best_mode"),
    (lambda d: d["validate"].update(evolved_file="evo.py"), "AI-evolved"),
    (lambda d: d.pop("top10_results"), "no top10_results fold rows"),
    (lambda d: d.pop("strategy"), "no strategy on the doc"),
    (lambda d: d.pop("instrument"), "no instrument on the doc"),
    (lambda d: d.pop("timeframe"), "no timeframe on the doc"),
    (lambda d: d.update(data_source="tv"), "unknown data_source"),
    (lambda d: d["validate"].update(windows={}), "no validate.windows.optimize window"),
    (lambda d: d["validate"]["windows"].update(optimize=["2010-01-01", None]), "no validate.windows.optimize window"),
    (lambda d: d.pop("cost_pts"), "no cost_pts on the doc"),
])
def test_rebuild_plan_refusal_reasons(edit, expect):
    d = _doc()
    edit(d)
    plan, why = B.rebuild_plan(d)
    assert plan is None and expect in why, why


# ─────────────────────────────────────────────────────────────────────────────
# build_fold_match - per-fold replay vs the saved figures
# ─────────────────────────────────────────────────────────────────────────────

def _fb(fold=1, te_s=1000, te_e=1500, row=None):
    row = row or {"fold": fold, "oos_pnl": 8.0, "oos_trades": 10, "oos_pf": 3.0, "oos_wins": 6}
    return {"fold": fold, "te_s": te_s, "te_e": te_e, "test_bars": te_e - te_s, "row": row}


def _ev_returning(trades, total_pnl=None, profit_factor=None, wins=None):
    """A stand-in for make_slice_evaluator's `ev` - ignores its args, always returns the
    SAME canned metrics (what a real evaluator would return for a fixed champion config)."""
    pnls = [t[2] for t in trades]
    def ev(a, b, params, keep_trades=False):
        out = {"trades": trades,
              "total_pnl": total_pnl if total_pnl is not None else sum(pnls),
              "num_trades": len(trades),
              "wins": (wins if wins is not None else sum(1 for x in pnls if x > 0))}
        if profit_factor is not None:
            out["profit_factor"] = profit_factor
        else:
            gw = sum(x for x in pnls if x > 0)
            gl = -sum(x for x in pnls if x < 0)
            out["profit_factor"] = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
        return out
    return ev


_TRADES_10 = [(i, i + 1, 2.0) for i in range(6)] + [(i, i + 1, -1.0) for i in range(6, 10)]
# sum = 12 - 4 = 8.0, 10 trades, 6 wins, PF = 12/4 = 3.0 -- matches _fb()'s default saved row


def test_build_fold_match_exact_agreement_is_ok():
    fb = _fb()
    ev = _ev_returning(_TRADES_10)
    m = B.build_fold_match(ev, None, fb, {"k": 1})
    assert m["ok"] and m["reason"] is None
    assert m["oos_trades"] == 10 and m["oos_pnl"] == pytest.approx(8.0)
    assert m["oos_pf"] == pytest.approx(3.0) and m["oos_wins"] == 6
    assert m["pnls"] == [2.0] * 6 + [-1.0] * 4


def test_build_fold_match_trade_count_mismatch():
    fb = _fb()
    ev = _ev_returning(_TRADES_10[:-1])          # replay has 9, saved says 10
    m = B.build_fold_match(ev, None, fb, {})
    assert not m["ok"] and "trades 9 vs saved 10" in m["reason"]


def test_build_fold_match_net_within_and_outside_tolerance():
    fb = _fb()
    # within: max(0.05, 1e-4*8.0)=0.05, so a 0.04 nudge on one trade still matches
    ev_ok = _ev_returning(_TRADES_10, total_pnl=8.04)
    assert B.build_fold_match(ev_ok, None, fb, {})["ok"]
    ev_bad = _ev_returning(_TRADES_10, total_pnl=8.10)
    m = B.build_fold_match(ev_bad, None, fb, {})
    assert not m["ok"] and "net 8.100 vs saved 8.000" in m["reason"]


def test_build_fold_match_relative_net_tolerance_on_a_large_saved_pnl():
    row = {"fold": 1, "oos_pnl": 100000.0, "oos_trades": 10, "oos_pf": 3.0, "oos_wins": 6}
    fb = _fb(row=row)
    # 1e-4 * 100000 = 10.0 pts tolerance -- an 8pt drift still matches, 12pt does not
    ev_ok = _ev_returning(_TRADES_10, total_pnl=100008.0)
    assert B.build_fold_match(ev_ok, None, fb, {})["ok"]
    ev_bad = _ev_returning(_TRADES_10, total_pnl=100012.0)
    assert not B.build_fold_match(ev_bad, None, fb, {})["ok"]


def test_build_fold_match_pf_tolerance_and_infinite_pf():
    fb = _fb()
    ev_ok = _ev_returning(_TRADES_10, profit_factor=3.0015)      # within 0.002
    assert B.build_fold_match(ev_ok, None, fb, {})["ok"]
    ev_bad = _ev_returning(_TRADES_10, profit_factor=3.01)
    m = B.build_fold_match(ev_bad, None, fb, {})
    assert not m["ok"] and "PF" in m["reason"]
    all_wins_row = {"fold": 1, "oos_pnl": 8.0, "oos_trades": 10, "oos_pf": float("inf"), "oos_wins": 6}
    fb_inf = _fb(row=all_wins_row)
    ev_inf = _ev_returning(_TRADES_10, profit_factor=float("inf"))
    assert B.build_fold_match(ev_inf, None, fb_inf, {})["ok"]        # inf == inf
    ev_finite = _ev_returning(_TRADES_10, profit_factor=999.0)
    assert not B.build_fold_match(ev_finite, None, fb_inf, {})["ok"]  # finite vs inf: refused


def test_build_fold_match_saved_null_pf_matches_a_replayed_infinite_pf():
    """A fold whose OOS trades were ALL winners has engine PF inf; the runner's json_safe
    saved it as null. That null must match a replayed inf -- and nothing else -- while
    trades / wins / net are still checked in full."""
    all_wins = [(i, i + 1, 2.0) for i in range(5)]                  # 5 winners, net 10
    row = {"fold": 1, "oos_pnl": 10.0, "oos_trades": 5, "oos_pf": None, "oos_wins": 5}
    ev_inf = _ev_returning(all_wins)                                  # PF inf (gl == 0)
    m = B.build_fold_match(ev_inf, None, _fb(row=row), {})
    assert m["ok"], m["reason"]
    assert m["saved"]["pf"] is None and m["d_pf"] == 0.0              # same infinite PF
    # a FINITE replayed PF against the saved null is a real disagreement
    m2 = B.build_fold_match(_ev_returning(all_wins, profit_factor=4.0), None, _fb(row=row), {})
    assert not m2["ok"] and "saved null" in m2["reason"] and m2["d_pf"] is None
    # the null PF waves NOTHING else through: a trade-count or net gap still refuses
    m3 = B.build_fold_match(_ev_returning(all_wins[:4]), None, _fb(row=row), {})
    assert not m3["ok"] and "trades 4 vs saved 5" in m3["reason"]
    m4 = B.build_fold_match(_ev_returning(all_wins, total_pnl=11.0), None, _fb(row=row), {})
    assert not m4["ok"] and "net 11.000 vs saved 10.000" in m4["reason"]
    m5 = B.build_fold_match(_ev_returning(all_wins, wins=4), None, _fb(row=row), {})
    assert not m5["ok"] and "wins 4 vs saved 5" in m5["reason"]


def test_build_fold_match_carries_saved_figures_and_deltas():
    fb = _fb()                               # saved: 10 trades, net 8.0, PF 3.0, 6 wins
    m = B.build_fold_match(_ev_returning(_TRADES_10, total_pnl=8.04, profit_factor=3.0015),
                           None, fb, {})
    assert m["ok"]
    assert m["saved"] == {"trades": 10, "net": 8.0, "pf": 3.0, "wins": 6}
    assert m["d_trades"] == 0
    assert m["d_net"] == pytest.approx(0.04)
    assert m["d_pf"] == pytest.approx(0.0015)
    bad = B.build_fold_match(_ev_returning(_TRADES_10[:-1]), None, fb, {})
    assert bad["d_trades"] == -1


def test_build_fold_match_wins_checked_only_when_saved():
    ev_diff_wins = _ev_returning(_TRADES_10, wins=5)
    fb = _fb()                                    # saved oos_wins = 6
    m = B.build_fold_match(ev_diff_wins, None, fb, {})
    assert not m["ok"] and "wins 5 vs saved 6" in m["reason"]
    row_no_wins = {"fold": 1, "oos_pnl": 8.0, "oos_trades": 10, "oos_pf": 3.0, "oos_wins": None}
    fb2 = _fb(row=row_no_wins)
    assert B.build_fold_match(ev_diff_wins, None, fb2, {})["ok"]      # no saved wins -> not checked


def test_build_fold_match_evaluator_returns_nothing():
    fb = _fb()                                    # saved 10 trades -> an empty replay is refused
    m = B.build_fold_match(lambda a, b, p, keep_trades=False: None, None, fb, {})
    assert not m["ok"] and "evaluator returned nothing" in m["reason"]
    assert "saved 10 trade(s)" in m["reason"]
    assert m["pnls"] == [] and m["oos_trades"] == 0


def test_build_fold_match_empty_replay_matches_a_fold_saved_empty():
    # a cold fold that never traded (NQDIP's 250-day trend): _wf_fold_row saves 0 / 0.0 when the
    #   evaluator returns nothing, so the replay's nothing is a match, not a refusal
    row = {"fold": 1, "oos_pnl": 0.0, "oos_trades": 0, "oos_pf": 0.0, "oos_wins": 0}
    m = B.build_fold_match(lambda a, b, p, keep_trades=False: None, None, _fb(row=row), {})
    assert m["ok"] and m["reason"] is None
    assert m["pnls"] == [] and m["oos_trades"] == 0 and m["oos_pnl"] == 0.0
    # a fold saved with zero trades but a non-zero win count disagrees with itself -> refused
    row_bad = dict(row, oos_wins=2)
    assert not B.build_fold_match(lambda a, b, p, keep_trades=False: None, None, _fb(row=row_bad), {})["ok"]


def test_build_block_with_an_empty_leading_fold():
    # every fold must still reach wf_oos_block, empty ones included, and the block must pool
    #   only the folds that traded
    empty = {"fold": 1, "ok": True, "pnls": [], "oos_pnl": 0.0, "oos_trades": 0, "oos_wins": 0,
             "oos_pf": 0.0, "from": "2011-01-03", "to": "2012-01-03"}
    full = {"fold": 2, "ok": True, "pnls": [2.0, -1.0, 3.0], "oos_pnl": 4.0, "oos_trades": 3,
            "oos_wins": 2, "oos_pf": 5.0, "from": "2012-01-04", "to": "2013-01-03"}
    blk = B.build_block([empty, full], "rolling")
    assert blk is not None
    assert blk["trades"] == 3 and blk["net"] == pytest.approx(4.0) and blk["n_folds"] == 2
    assert blk["from"] == "2011-01-03"


def test_plan_accepts_the_adjusted_daily_etf_source():
    assert B.SESSION.get("yahoo_adj") == "rth"


def test_plan_accepts_the_back_adjusted_databento_sources():
    """A back-adjusted master is the SAME session as its no-adjust twin -- only the price levels
    differ by the roll offsets -- so a run on one must be replayable. These were missing until
    2026-11-20, which refused every ENGU-Q run since the family's registered master moved to
    db_adj_eth (the NQ crown, the ES re-grade, the YM and RTY transfers) for a missing key."""
    assert B.SESSION.get("db_adj_eth") == "eth"
    assert B.SESSION.get("db_adj_rth") == "rth"
    for src, sess in (("db_adj_eth", "eth"), ("db_adj_rth", "rth")):
        plan, why = B.rebuild_plan(_doc(data_source=src))
        assert why is None, why
        assert plan["session"] == sess and plan["source"] == src


def test_plan_still_refuses_a_source_it_does_not_know():
    _plan, why = B.rebuild_plan(_doc(data_source="db_halfadj_eth"))
    assert why and "unknown data_source" in why


def test_build_fold_match_dates_from_the_index():
    fb = _fb(te_s=10, te_e=20)
    idx = pd.date_range("2020-01-01", periods=30, freq="1D", tz="US/Eastern")
    ev = _ev_returning(_TRADES_10)
    m = B.build_fold_match(ev, idx, fb, {})
    d0, d1 = B.bar_date_bounds(idx, 10, 20)
    assert (m["from"], m["to"]) == (d0, d1)


# ─────────────────────────────────────────────────────────────────────────────
# build_block - all-or-nothing across folds
# ─────────────────────────────────────────────────────────────────────────────

def _ok_matches(n_folds=2):
    out = []
    for f in range(1, n_folds + 1):
        out.append({"fold": f, "ok": True, "reason": None, "pnls": [2.0, -1.0],
                    "oos_pnl": 1.0, "oos_trades": 2, "oos_wins": 1, "oos_pf": 2.0,
                    "from": f"2020-0{f}-01", "to": f"2020-0{f}-28"})
    return out


def test_build_block_all_ok_returns_the_wf_oos_block():
    matches = _ok_matches(2)
    block = B.build_block(matches, "rolling")
    assert block is not None
    assert block["v"] == 1 and block["mode"] == "rolling" and block["src"] == "backfill"
    assert block["n_folds"] == 2 and block["trades"] == 4
    assert block["net"] == pytest.approx(2.0)


def test_build_block_any_mismatch_returns_none():
    matches = _ok_matches(2)
    matches[1]["ok"] = False
    assert B.build_block(matches, "rolling") is None
    assert B.build_block([], "rolling") is None


# ─────────────────────────────────────────────────────────────────────────────
# check_payload
# ─────────────────────────────────────────────────────────────────────────────

def _payload():
    matches = _ok_matches(2)
    block = B.build_block(matches, "anchored")
    block["backfill"] = {"tool": B.TOOL_VERSION, "at": "2026-09-15T00:00:00Z",
                         "matches": [B.provenance_row(m) for m in matches]}
    return {"validate.wf_oos": block}


def test_check_payload_accepts_a_well_formed_payload():
    assert B.check_payload(_payload()) is True


def test_check_payload_refuses_wrong_keys():
    p = _payload()
    p["extra"] = 1
    with pytest.raises(ValueError):
        B.check_payload(p)
    with pytest.raises(ValueError):
        B.check_payload({})


@pytest.mark.parametrize("mutate", [
    lambda block: block.update(v=2),
    lambda block: block.update(src="validate"),
    lambda block: block.pop("mode"),
    lambda block: block.pop("equity"),
    lambda block: block.pop("backfill"),
    lambda block: block["backfill"].pop("tool"),
    lambda block: block["backfill"].pop("at"),
    lambda block: block["backfill"].update(matches="not a list"),
    lambda block: block["backfill"]["matches"][0].pop("d_net"),       # no per-fold delta
    lambda block: block["backfill"]["matches"][1].pop("saved"),       # no saved figures
    lambda block: block["backfill"]["matches"].pop(),                 # a fold not covered
])
def test_check_payload_refuses_malformed_blocks(mutate):
    p = _payload()
    mutate(p["validate.wf_oos"])
    with pytest.raises(ValueError):
        B.check_payload(p)


# ─────────────────────────────────────────────────────────────────────────────
# orchestration on a fake Firestore (no network, no market data) - mirrors
# tools/backfill_lb_tails.py's own fakes
# ─────────────────────────────────────────────────────────────────────────────

class FailedPrecondition(Exception):
    pass


class ServiceUnavailable(Exception):
    pass


class _Snap:
    def __init__(self, doc, t):
        self._d, self.exists, self.update_time = copy.deepcopy(doc), doc is not None, t

    def to_dict(self):
        return copy.deepcopy(self._d)


class _Ref:
    def __init__(self, *reads):
        self.reads, self.gets, self.updates, self.fail = list(reads), 0, [], None
        self.land_then_fail = None
        # every `retry=` the tool passed, one per update() call - the write path must pass
        #   retry=None (a client retry of a landed commit trips its own precondition)
        self.retries = []

    def get(self):
        doc, t = self.reads[min(self.gets, len(self.reads) - 1)]
        self.gets += 1
        return _Snap(doc, t)

    def update(self, payload, option=None, retry="DEFAULT"):
        self.retries.append(retry)
        if self.land_then_fail is not None:
            doc, _t = self.reads[-1]
            self.reads.append((B.apply_update(doc, payload), "t-after"))
            self.updates.append((copy.deepcopy(payload), option))
            raise self.land_then_fail
        if self.fail is not None:
            raise self.fail
        self.updates.append((copy.deepcopy(payload), option))


class _DB:
    def __init__(self, ref):
        self.ref = ref

    def collection(self, name):
        return self

    def document(self, name):
        return self.ref if name == RUN else self

    def write_option(self, **kw):
        return ("precondition", kw)


RUN = "335"


def _matches_from_doc(plan):
    """A canned `rebuild` that reproduces every saved fold exactly - the 'everything
    matches' case most orchestration tests want, without touching market data. Takes
    the reconstructed PLAN (what `one()` actually calls `rebuild` with), not the doc."""
    out = []
    for fb in plan["folds"]:
        row = fb["row"]
        n = int(row["oos_trades"])
        wins = int(row.get("oos_wins") or 0)
        pnls = [2.0] * wins + [-1.0] * (n - wins)
        out.append({"fold": int(row["fold"]), "ok": True, "reason": None, "pnls": pnls,
                    "oos_pnl": float(row["oos_pnl"]), "oos_trades": n,
                    "oos_wins": wins, "oos_pf": float(row["oos_pf"]),
                    "from": f"2020-0{row['fold']}-01", "to": f"2020-0{row['fold']}-28"})
    return out


def _run(ref, rebuild_fn, **kw):
    log = []
    status = B.one(_DB(ref), int(RUN), rebuild=lambda plan, log=None: rebuild_fn(plan),
                   log=log.append, at="2026-09-15T12:00:00Z", **kw)
    return status, log


def _matching_doc(**kw):
    d = _doc(**kw)
    # make each fold's canned pnls (2 wins @2.0, rest @-1.0) reconcile with its saved
    # oos_pnl/oos_pf so build_block's own guard (via wf_oos_block) is happy too
    for row in d["top10_results"]:
        n = int(row["oos_trades"])
        wins = int(row.get("oos_wins") or 0)
        row["oos_pnl"] = 2.0 * wins - 1.0 * (n - wins)
        gw, gl = 2.0 * wins, 1.0 * (n - wins)
        row["oos_pf"] = (gw / gl) if gl > 0 else float("inf")
    return d


def test_one_no_doc():
    ref = _Ref((None, "t1"))
    status, log = _run(ref, lambda plan: [])
    assert status == "nodoc"


def test_one_skip_on_plan_refusal():
    d = _matching_doc()
    d.pop("top10_results")
    ref = _Ref((d, "t1"))
    status, log = _run(ref, lambda plan: [])
    assert status == "skip"
    assert "no top10_results" in "\n".join(log)


def test_one_covered_when_wf_oos_already_present():
    def _never(plan):
        raise AssertionError("should not replay a covered run")
    d = _matching_doc()
    d["validate"]["wf_oos"] = {"v": 1, "src": "validate"}
    ref = _Ref((d, "t1"))
    status, log = _run(ref, _never)
    assert status == "covered"
    assert "pass --force" in log[-1]


def test_one_dry_run_writes_nothing():
    d = _matching_doc()
    ref = _Ref((d, "t1"))
    status, log = _run(ref, _matches_from_doc)
    assert status == "dry" and ref.updates == [] and ref.gets == 1
    text = "\n".join(log)
    assert "window 2010-06-07..2024-06-07 (pinned) mode rolling 3 fold(s)" in text
    assert "dry run - not written" in text


def test_one_fold_mismatch_skips_the_run():
    d = _matching_doc()
    def bad(plan):
        m = _matches_from_doc(plan)
        m[1]["ok"] = False
        m[1]["reason"] = "trades 1 vs saved 10"
        return m
    ref = _Ref((d, "t1"))
    status, log = _run(ref, bad)
    assert status == "mismatch" and ref.updates == []
    assert "FOLD MISMATCH" in "\n".join(log)


def test_one_replayskip_is_a_skip():
    d = _matching_doc()
    def boom(plan):
        raise B.ReplaySkip("no master for NQ 5m rth db_noadj_rth")
    ref = _Ref((d, "t1"))
    status, log = _run(ref, boom)
    assert status == "skip"
    assert "no master" in "\n".join(log)


def test_one_write_uses_a_precondition_on_a_fresh_read():
    d = _matching_doc()
    ref = _Ref((d, "t1"), (dict(d, archived=True), "t2"))     # unrelated field changed
    status, log = _run(ref, _matches_from_doc, write=True)
    assert status == "written", log
    assert len(ref.updates) == 1
    payload, option = ref.updates[0]
    assert option == ("precondition", {"last_update_time": "t2"})
    assert ref.retries == [None]        # retry=None, not the client's default retry policy
    assert set(payload) == {"validate.wf_oos"}
    assert payload["validate.wf_oos"]["backfill"]["at"] == "2026-09-15T12:00:00Z"


def test_one_write_provenance_carries_saved_figures_and_deltas_per_fold():
    d = _matching_doc()

    def rebuild_with_deltas(plan):
        # what build_fold_match really returns: replayed figures + the saved ones + deltas
        out = _matches_from_doc(plan)
        for m, fb in zip(out, plan["folds"]):
            row = fb["row"]
            m["saved"] = {"trades": int(row["oos_trades"]), "net": float(row["oos_pnl"]),
                          "pf": row["oos_pf"], "wins": row.get("oos_wins")}
            m["d_trades"], m["d_net"], m["d_pf"] = 0, 0.0, 0.0
        return out
    ref = _Ref((d, "t1"), (d, "t2"))
    status, log = _run(ref, rebuild_with_deltas, write=True)
    assert status == "written", log
    rows = ref.updates[0][0]["validate.wf_oos"]["backfill"]["matches"]
    assert [r["f"] for r in rows] == [1, 2, 3]
    for r, saved_row in zip(rows, d["top10_results"]):
        assert set(B.PROVENANCE_KEYS) <= set(r)
        assert r["saved"]["trades"] == saved_row["oos_trades"]
        assert r["saved"]["net"] == pytest.approx(saved_row["oos_pnl"])
        assert (r["d_trades"], r["d_net"], r["d_pf"]) == (0, 0.0, 0.0)
    # the dry-run / write log prints the per-fold deltas too
    assert "(d +0)" in "\n".join(log) and "(d +0.0000)" in "\n".join(log)


def test_one_refuses_a_changed_top10_results():
    d = _matching_doc()
    changed = copy.deepcopy(d)
    changed["top10_results"][0]["oos_pnl"] += 1.0
    ref = _Ref((d, "t1"), (changed, "t2"))
    status, log = _run(ref, _matches_from_doc, write=True)
    assert status == "changed" and ref.updates == []


def test_one_refuses_a_race_with_another_backfill():
    d = _matching_doc()
    raced = copy.deepcopy(d)
    raced["validate"]["wf_oos"] = {"v": 1, "src": "backfill"}
    ref = _Ref((d, "t1"), (raced, "t2"))
    status, log = _run(ref, _matches_from_doc, write=True)
    assert status == "changed" and ref.updates == []


def test_one_force_writes_over_a_wf_oos_race():
    d = _matching_doc()
    raced = copy.deepcopy(d)
    raced["validate"]["wf_oos"] = {"v": 1, "src": "backfill"}
    ref = _Ref((d, "t1"), (raced, "t2"))
    status, log = _run(ref, _matches_from_doc, write=True, force=True)
    assert status == "written"


def test_one_refuses_an_oversized_doc():
    d = _matching_doc()
    ref = _Ref((d, "t1"))
    status, log = _run(ref, _matches_from_doc, write=True, budget=10)   # no real doc fits in 10 bytes
    assert status == "toobig" and ref.updates == []


def test_one_conflict_on_a_failed_precondition():
    d = _matching_doc()
    ref = _Ref((d, "t1"))
    ref.fail = FailedPrecondition("stale")
    status, _log = _run(ref, _matches_from_doc, write=True)
    assert status == "conflict"


def test_one_lost_reply_on_a_landed_write_is_reported_as_written():
    d = _matching_doc()
    ref = _Ref((d, "t1"), (d, "t2"))
    ref.land_then_fail = FailedPrecondition("the client's own retry tripped the precondition")
    status, log = _run(ref, _matches_from_doc, write=True)
    assert status == "written"
    assert "the reply was lost, the write landed" in "\n".join(log)
    ref2 = _Ref((d, "t1"), (d, "t2"))
    ref2.fail = ServiceUnavailable("503")
    with pytest.raises(ServiceUnavailable):
        _run(ref2, _matches_from_doc, write=True)


def test_one_force_rebuilds_a_covered_run():
    d = _matching_doc()
    d["validate"]["wf_oos"] = {"v": 1, "src": "backfill", "matches": []}
    ref = _Ref((d, "t1"), (d, "t2"))
    status, _log = _run(ref, _matches_from_doc, write=True, force=True)
    assert status == "written"


# ─────────────────────────────────────────────────────────────────────────────
# --list
# ─────────────────────────────────────────────────────────────────────────────

class _ListSnap:
    def __init__(self, doc_id, doc):
        self.id = doc_id
        self._d = doc

    def to_dict(self):
        return copy.deepcopy(self._d)


class _ListDB:
    """Just enough of the Firestore query chain for list_runs: .collection().document()
    .collection().select(...)[.order_by(field, direction=...)].limit(n).stream().

    Mirrors the two Firestore behaviours list_runs depends on: an UNORDERED query comes back
    in document-id order compared as STRINGS ("1000" sorts before "385" and "99"), and
    order_by(field) leaves out every doc that has no such field. Order is applied before the
    limit, as the server does."""
    def __init__(self, docs):
        self._docs = docs
        self._cap = None
        self._order = None
        self.order_calls = []

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def select(self, fields):
        self.fields = list(fields)
        return self

    def order_by(self, field, direction="ASCENDING"):
        self._order = (field, direction)
        self.order_calls.append((field, direction))
        return self

    def limit(self, n):
        self._cap = int(n)
        return self

    def stream(self):
        docs = sorted(self._docs, key=lambda kv: str(kv[0]))       # doc-id string order
        if self._order:
            field, direction = self._order
            docs = [kv for kv in docs if field in kv[1]]
            docs = sorted(docs, key=lambda kv: kv[1][field],
                          reverse=(direction == "DESCENDING"))
        if self._cap is not None:
            docs = docs[:self._cap]
        return [_ListSnap(i, d) for i, d in docs]


def test_list_row_formats_and_skips_non_wf_docs():
    d = _matching_doc()
    line = B.list_row("335", d)
    assert line.startswith("#335 SYN_STRAT.py NQ 5m 2010-06-07..2025-06-07 | mode rolling | 3 fold(s)")
    assert line.endswith("no wf_oos yet - a dry run would attempt this")
    d["validate"]["wf_oos"] = {"v": 1, "src": "backfill", "trades": 30, "net": 12.0}
    assert B.list_row("335", d).endswith("wf_oos v1 src='backfill' 30 trades net 12.0")
    d2 = _matching_doc()
    d2["validate"]["wf_ran"] = False
    assert B.list_row("335", d2).endswith("validate.wf_ran is False - nothing to backfill")
    assert B.list_row("1", {"strategy": "S"}) is None
    assert B.list_row("1", {"strategy": "S", "top10_results": [{"no_fold_here": 1}]}) is None


def test_list_runs_reports_and_respects_limit():
    docs = [(str(i), dict(_matching_doc(), id=i)) for i in (300, 301, 302)]
    log = []
    B.list_runs(_ListDB(docs), log=log.append, limit=2)
    assert log[-1] == "2 run(s) with walk-forward fold rows"
    assert len(log) == 3


def test_list_runs_limit_keeps_the_newest_runs_not_the_first_doc_ids():
    """Unordered, a Firestore limit returns the first doc ids as STRINGS - '1000' and '99'
    sort before '385' - so --limit 2 used to list two OLD runs. It must order by the run
    doc's numeric `id` DESCENDING before limiting."""
    ids = (99, 385, 1000, 384, 12)
    docs = [(str(i), dict(_matching_doc(), id=i)) for i in ids]
    docs.append(("777", _matching_doc()))              # no `id` field: out of an ordered query
    db = _ListDB(docs)
    log = []
    B.list_runs(db, log=log.append, limit=2)
    assert db.order_calls == [("id", "DESCENDING")]
    assert "id" in db.fields
    assert [ln.split()[0] for ln in log[:-1]] == ["#1000", "#385"]
    assert log[-1] == "2 run(s) with walk-forward fold rows"
    # sanity: the fake really does reproduce the old bug when nothing orders the query
    unordered = _ListDB(docs)
    unordered._cap = 2
    assert [s.id for s in unordered.stream()] == ["1000", "12"]


def test_list_runs_without_limit_streams_every_doc_unordered():
    docs = [(str(i), dict(_matching_doc(), id=i)) for i in (12, 385)]
    docs.append(("777", _matching_doc()))              # no `id`: still listed when unlimited
    db = _ListDB(docs)
    log = []
    B.list_runs(db, log=log.append)
    assert db.order_calls == []
    assert [ln.split()[0] for ln in log[:-1]] == ["#777", "#385", "#12"]


# ─────────────────────────────────────────────────────────────────────────────
# main() - help / no-args never touch Firestore; exit codes
# ─────────────────────────────────────────────────────────────────────────────

def test_help_and_no_arguments_never_touch_firestore(monkeypatch):
    def _boom():
        raise AssertionError("Firestore opened")
    monkeypatch.setattr(B, "_db", _boom)
    assert B.main([]) == 2
    with pytest.raises(SystemExit) as e:
        B.main(["--help"])
    assert e.value.code == 0
    out = subprocess.run([sys.executable, os.path.join(_TOOLS, "backfill_wf_oos.py"), "--help"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--write" in out.stdout and "--list" in out.stdout


class _FakeBeacon:
    """Stands in for research_beacon.beacon() -- a no-op context manager with `.step()`, so
    main()'s queue-bar marker never opens its OWN (independent-of-`B._db`) real Firestore
    client during a test run."""
    calls = []

    def __init__(self, label, total=0):
        self.label, self.total = label, total
        _FakeBeacon.calls.append((label, total))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def step(self, i):
        pass


def _isolate_main(monkeypatch):
    """B.main() does three process-global things a test must not leak into the rest of the
    suite: os.chdir(ROOT), and - when EDGELOG_UPLOADS / EDGELOG_DB_PATH are set in the shell
    - overwrites augur_engine.data.UPLOADS / DB_PATH and augur_engine.paths.DB_PATH. Unset
    both variables for the test and register the CURRENT globals with monkeypatch so they
    (and the cwd) are restored even if main() changes them."""
    import augur_engine.data as _data
    import augur_engine.paths as _paths
    monkeypatch.delenv("EDGELOG_DB_PATH", raising=False)
    monkeypatch.delenv("EDGELOG_UPLOADS", raising=False)
    monkeypatch.setattr(_data, "UPLOADS", _data.UPLOADS)
    monkeypatch.setattr(_data, "DB_PATH", _data.DB_PATH)
    monkeypatch.setattr(_paths, "DB_PATH", _paths.DB_PATH)
    monkeypatch.chdir(os.getcwd())


def test_main_restores_globals_it_may_override(monkeypatch):
    import augur_engine.data as _data
    import augur_engine.paths as _paths
    before = (_data.UPLOADS, _data.DB_PATH, _paths.DB_PATH, os.getcwd())
    with monkeypatch.context() as mp:
        _isolate_main(mp)
        # simulate a shell that DOES carry the overrides: main() must apply them...
        mp.setenv("EDGELOG_UPLOADS", os.path.join("X:", "fake_uploads"))
        mp.setenv("EDGELOG_DB_PATH", os.path.join("X:", "fake.db"))
        mp.setattr(B, "_db", lambda: object())
        mp.setattr(B, "one", lambda db, rid, write=False, force=False, **kw: "dry")
        mp.setattr(B, "_make_beacon", _FakeBeacon)
        assert B.main(["335"]) == 0
        assert _data.UPLOADS == os.path.join("X:", "fake_uploads")
        assert _paths.DB_PATH == _data.DB_PATH == os.path.join("X:", "fake.db")
    # ...and none of it survives the test
    assert (_data.UPLOADS, _data.DB_PATH, _paths.DB_PATH, os.getcwd()) == before


def test_dry_run_main_never_opens_the_beacon(monkeypatch):
    """The beacon is a Firestore write (a job record). A dry run promises nothing is
    written, so main() must not even call _make_beacon without --write."""
    _isolate_main(monkeypatch)
    monkeypatch.setattr(B, "_db", lambda: object())

    def _no_beacon(*a, **kw):
        raise AssertionError("a dry run opened the research beacon (a Firestore write)")
    monkeypatch.setattr(B, "_make_beacon", _no_beacon)
    seen = []
    monkeypatch.setattr(B, "one", lambda db, rid, write=False, force=False, **kw:
                        (seen.append((rid, write, force)), "dry")[1])
    assert B.main(["335", "382"]) == 0
    assert B.main(["325", "--force"]) == 0
    assert seen == [(335, False, False), (382, False, False), (325, False, True)]


def test_main_never_opens_a_real_beacon_and_exit_code_reflects_refusals(monkeypatch):
    _isolate_main(monkeypatch)
    monkeypatch.setattr(B, "_db", lambda: object())
    _FakeBeacon.calls.clear()
    monkeypatch.setattr(B, "_make_beacon", _FakeBeacon)

    def _boom_if_real_beacon_imported(*a, **kw):
        raise AssertionError("main() reached the real research_beacon - it must go through "
                             "B._make_beacon so tests never touch live Firestore")
    monkeypatch.setitem(sys.modules, "research_beacon",
                        types.SimpleNamespace(beacon=_boom_if_real_beacon_imported))

    seen = {}

    # **kw: main() also passes allow_off_era (the off-era write guard); these stubs pin the
    #   dispatch and exit codes, not that argument list.
    def _one(db, rid, write=False, force=False, **kw):
        seen[rid] = (write, force)
        if rid == 999:
            raise RuntimeError("boom")
        return {335: "written", 382: "dry", 325: "covered", 310: "mismatch",
               311: "conflict", 312: "toobig", 313: "changed", 314: "skip",
               315: "nodoc"}[rid]
    monkeypatch.setattr(B, "one", _one)
    assert B.main(["335", "382", "325", "--write"]) == 0
    assert seen[335] == (True, False)
    for bad in ("310", "311", "312", "313", "314", "315", "999"):
        assert B.main(["335", bad]) == 1, bad                       # dry runs: no beacon
        assert B.main(["335", bad, "--write"]) == 1, bad            # write runs: a beacon
    assert seen[335] == (True, False)
    # 1 + 7 --write calls opened a (fake) beacon; the 7 dry runs opened none
    assert len(_FakeBeacon.calls) == 8
    assert all(label.startswith("backfill_wf_oos [335") for label, _t in _FakeBeacon.calls)


# ─────────────────────────────────────────────────────────────────────────────
# end to end: fold-bound reconstruction against a REAL run_auto walk-forward,
# for BOTH rolling and anchored, replayed through a real make_slice_evaluator
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_arrays(n=4500, seed=7):
    idx = pd.date_range("2020-01-01", periods=n, freq="5min", tz="US/Eastern")
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0, 0.4, n))
    o = c + rng.normal(0, 0.05, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.1, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.1, n))
    return {"open": o, "high": h, "low": l, "close": c, "volume": None, "day_id": None,
            "index": idx, "meta": {"roll_mode": "none"}}


def _tiny_strategy():
    mod = types.ModuleType("fake_backfill_wf_oos_strategy")
    mod.STRATEGY_NAME = "SYN BACKFILL WFOOS"
    mod.DEFAULT_PARAMS = {"lookback": {"type": "int", "min": 4, "max": 40, "step": 1, "default": 10},
                          "thresh": {"type": "float", "min": 0.1, "max": 3.0, "step": 0.1, "default": 1.0}}

    def run_backtest(o, h, l, c, lookback=10, thresh=1.0, return_trades=False, **kw):
        n = len(c)
        step = max(4, int(lookback))
        entries = list(range(step, n - 1, step))
        trades = [(e, e + 1, float((e % 7 - 3) * thresh)) for e in entries]
        total = sum(t[2] for t in trades)
        wins = sum(1 for t in trades if t[2] > 0)
        losses = len(trades) - wins
        gw = sum(t[2] for t in trades if t[2] > 0)
        gl = -sum(t[2] for t in trades if t[2] < 0)
        out = {"total_pnl": total, "num_trades": len(trades),
               "win_rate": (100.0 * wins / len(trades)) if trades else 0.0,
               "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
               "max_drawdown": -1.0, "avg_pnl": (total / len(trades)) if trades else 0.0,
               "wins": wins, "losses": losses}
        if return_trades:
            out["trades"] = trades
        return out

    mod.run_backtest = run_backtest
    return mod


@pytest.mark.parametrize("wf_mode", ["rolling", "anchored"])
def test_fold_bound_reconstruction_end_to_end_against_real_run_auto(wf_mode):
    from augur_engine.auto import run_auto, make_slice_evaluator, _auto_space_from_params
    mod = _tiny_strategy()
    arrays = _synthetic_arrays()
    out = run_auto(mod, arrays=arrays, method="walkforward", wf_mode=wf_mode, wf_folds=3,
                   n_trials=5, seed=3, min_trades=1, cost_pts=0.0, oos=True,
                   auto_expand=False, workers=1)
    rows = out["top"]
    assert rows and all("fold" in r and "train_bars" in r for r in rows)

    bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
    assert reason is None
    assert expect_n == len(arrays["close"])

    pkeys = list(_auto_space_from_params(mod.DEFAULT_PARAMS).keys())
    params_list, why = B.fold_params(pkeys, [fb["row"] for fb in bounds])
    assert why is None

    ev = make_slice_evaluator(mod, arrays, 0.0)
    matches = [B.build_fold_match(ev, arrays["index"], fb, p)
              for fb, p in zip(bounds, params_list)]
    assert all(m["ok"] for m in matches), [(m["fold"], m["reason"]) for m in matches]

    block = B.build_block(matches, wf_mode)
    assert block is not None
    assert block["trades"] == sum(int(r["oos_trades"]) for r in rows)
    assert block["net"] == pytest.approx(sum(float(r["oos_pnl"]) for r in rows), abs=0.05)
    assert block["mode"] == wf_mode and block["src"] == "backfill"


# ─────────────────────────────────────────────────────────────────────────────
# bars_mismatch: dropped trailing fold(s) vs changed data - say which
# ─────────────────────────────────────────────────────────────────────────────

def test_bars_mismatch_reason_names_dropped_trailing_folds_when_the_surplus_is_a_fold():
    # 4-fold rolling run on 5000 bars: init 2000, tsize 750; folds 3 and 4 were DROPPED
    # (no training trial cleared min_trades), so the saved rows only account for
    # 2000 + 750 + 750 = 3500 bars while the (unchanged) window still has 5000.
    rows = _rolling_rows(n_folds=2, init=2000, tsize=750)
    bounds, expect_n, _r = B.fold_bounds_from_rows(rows)
    msg = B.bars_mismatch_reason(5000, expect_n, bounds)
    assert msg.startswith("bars_mismatch: window has 5000 bars, the fold rows expect 3500")
    assert "last fold(s) were likely dropped by run_auto" in msg
    assert "no training trial cleared min_trades" in msg
    assert "window itself looks unchanged" in msg              # int(0.40 * 5000) == 2000
    assert "data changed" not in msg


def test_bars_mismatch_reason_flags_a_possible_window_change_alongside_a_dropped_fold():
    rows = _rolling_rows(n_folds=2, init=2000, tsize=750)
    bounds, expect_n, _r = B.fold_bounds_from_rows(rows)
    msg = B.bars_mismatch_reason(5600, expect_n, bounds)       # int(0.40*5600)=2240 != 2000
    assert "likely dropped by run_auto" in msg
    assert "may ALSO have changed" in msg


@pytest.mark.parametrize("n", [3499, 3000, 3500 + 749])
def test_bars_mismatch_reason_blames_the_data_when_the_gap_is_not_a_whole_fold(n):
    rows = _rolling_rows(n_folds=2, init=2000, tsize=750)
    bounds, expect_n, _r = B.fold_bounds_from_rows(rows)
    msg = B.bars_mismatch_reason(n, expect_n, bounds)
    assert msg == (f"bars_mismatch: window has {n} bars, the fold rows expect 3500 "
                   "(the data changed since this run validated)")


def test_rebuild_refuses_honestly_when_run_auto_dropped_the_last_fold(monkeypatch):
    """End to end through rebuild_from_market_data: a REAL run_auto walk-forward whose last
    fold row is missing (what run_auto saves when that fold's training window cleared no
    trial) replayed against the SAME, unchanged arrays -> a ReplaySkip that names the
    dropped fold, not a data change."""
    import augur_engine.strategies as _strats
    import augur_engine.data as _data
    from augur_engine.auto import run_auto
    mod = _tiny_strategy()
    arrays = _synthetic_arrays()
    out = run_auto(mod, arrays=arrays, method="walkforward", wf_mode="rolling", wf_folds=3,
                   n_trials=5, seed=3, min_trades=1, cost_pts=0.0, oos=True,
                   auto_expand=False, workers=1)
    rows = sorted(out["top"], key=lambda r: int(r["fold"]))[:-1]     # drop the LAST fold
    bounds, expect_n, reason = B.fold_bounds_from_rows(rows)
    assert reason is None and expect_n < len(arrays["close"])
    plan = {"strategy": "SYN.py", "instrument": "NQ", "timeframe": "5m", "session": "rth",
            "source": "db_noadj_rth", "cost_pts": 0.0, "mode": "rolling",
            "date_from": "2020-01-01", "date_to": "2020-01-16", "expect_n": expect_n,
            "folds": bounds}
    monkeypatch.setattr(_strats, "load_strategy", lambda name: mod)
    monkeypatch.setattr(_data, "find_master", lambda *a, **k: {"name": "SYN"})
    monkeypatch.setattr(_data, "load_master_arrays", lambda master, **k: arrays)
    with pytest.raises(B.ReplaySkip) as e:
        B.rebuild_from_market_data(plan, log=lambda *_a: None)
    assert "last fold(s) were likely dropped by run_auto" in str(e.value)
    assert "window itself looks unchanged" in str(e.value)


# ─────────────────────────────────────────────────────────────────────────────
# WARM vs COLD fold scoring (ENGUQ, 2026-11-20)
#
# "Warm starts for every scored out-of-sample stretch" (7a95b816) landed 2026-09-20. Since then
# validate scores each fold from auto.WARM_DAYS sessions earlier and trims back, so a position
# already open when a stretch begins is carried in. This tool replayed every fold COLD, so it
# could not reproduce such a fold -- and because a mismatch REFUSES the block, the symptom was
# always "cannot verify", never a wrong number written.
#
# The two real runs that pinned this down straddle the commit, and their TIMESTAMPS are the
# fixtures below: ENGU-Q #335 validated 2026-09-08 19:01 (cold era) and reproduces 8 of 8 folds
# cold; #407 validated 2026-09-21 08:52, one day after the commit, and reproduces 2 of 8 cold --
# exactly the two folds with nothing carried across their boundary -- then 8 of 8 warm, every
# fold to the cent. Those end-to-end replays are NOT re-run here: each needs a 308 MB pre-fill
# tape and a detached worktree of the repo at the run's own commit, which a unit suite cannot
# carry. They are recorded in C:/EdgeLog/_anatomy_cache/book_stitched/ENGUQ_335_stitched_wf.md
# and ENGUQ_407_stitched_wf.md with their fold tables. What IS pinned here is every decision
# this tool makes about them.
# ─────────────────────────────────────────────────────────────────────────────

RUN335_TS = "2026-09-08 19:01"      # ENGU-Q #335, the cold era
RUN407_TS = "2026-09-21 08:52"      # ENGU-Q #407, one day after warm starts landed


def test_warm_days_for_doc_run335_is_cold_and_run407_is_warm():
    """The two runs that found the bug, by their own timestamps."""
    cold, why_cold = B.warm_days_for_doc({"timestamp": RUN335_TS})
    warm, why_warm = B.warm_days_for_doc({"timestamp": RUN407_TS})
    assert cold == 0
    assert warm == B._warm_days_now() > 0
    assert RUN335_TS in why_cold and "before warm starts" in why_cold
    assert RUN407_TS in why_warm and B.WARM_STARTS_FROM in why_warm


def test_warm_days_for_doc_boundary_day_counts_as_warm():
    """The commit landed ON 2026-09-20, so that day's runs were scored warm."""
    assert B.warm_days_for_doc({"timestamp": B.WARM_STARTS_FROM + " 00:01"})[0] > 0
    assert B.warm_days_for_doc({"timestamp": "2026-09-19 23:59"})[0] == 0


@pytest.mark.parametrize("doc", [{}, {"timestamp": ""}, {"timestamp": None}, None])
def test_warm_days_for_doc_without_a_timestamp_assumes_warm_and_says_so(doc):
    """Warm has been the engine's behaviour since 2026-09-20, so it is the right guess for an
    undated doc - and rebuild_from_market_data tries the other arm anyway."""
    n, why = B.warm_days_for_doc(doc)
    assert n == B._warm_days_now()
    assert "no timestamp" in why


@pytest.mark.parametrize("given,expect_warm", [(0, False), (300, True), (7, True)])
def test_warm_days_for_doc_explicit_override_beats_the_era(given, expect_warm):
    n, why = B.warm_days_for_doc({"timestamp": RUN335_TS}, warm_days=given)
    assert (n > 0) is expect_warm and n == given
    assert "explicitly" in why


def test_rebuild_plan_carries_the_era(monkeypatch):
    cold, _ = B.rebuild_plan(dict(_doc(), timestamp=RUN335_TS))
    warm, _ = B.rebuild_plan(dict(_doc(), timestamp=RUN407_TS))
    assert cold["warm_days"] == 0 and "before warm starts" in cold["warm_why"]
    assert warm["warm_days"] > 0 and "on or after" in warm["warm_why"]


# ── how the evaluator is CALLED ──────────────────────────────────────────────────────────────

def _ev_recording(trades):
    """An `ev` double that records the kwargs it was called with."""
    calls = []
    pnls = [t[2] for t in trades]

    def ev(a, b, params, keep_trades=False, **kw):
        calls.append(dict(a=a, b=b, keep_trades=keep_trades, **kw))
        gw = sum(x for x in pnls if x > 0)
        gl = -sum(x for x in pnls if x < 0)
        return {"trades": trades, "total_pnl": sum(pnls), "num_trades": len(trades),
                "wins": sum(1 for x in pnls if x > 0),
                "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)}
    return ev, calls


def test_build_fold_match_default_is_cold_and_never_passes_warm():
    """The pre-v2 call, unchanged. _ev_returning's double takes NO warm kwarg at all, so this
    also pins that every existing caller and test double keeps working."""
    ev, calls = _ev_recording(_TRADES_10)
    m = B.build_fold_match(ev, None, _fb(), {"k": 1})
    assert m["ok"] and m["warm_days"] == 0
    assert "warm" not in calls[0]
    # and the older double, which would raise TypeError on an unexpected kwarg:
    assert B.build_fold_match(_ev_returning(_TRADES_10), None, _fb(), {"k": 1})["ok"]


def test_build_fold_match_warm_days_calls_the_evaluator_warm():
    ev, calls = _ev_recording(_TRADES_10)
    m = B.build_fold_match(ev, None, _fb(), {"k": 1}, warm_days=300)
    assert m["ok"] and m["warm_days"] == 300
    assert calls[0]["warm"] is True and calls[0]["keep_trades"] is True


def test_build_fold_match_records_the_arm_on_an_empty_slice_too():
    """A fold the evaluator returns nothing for still has to say which arm produced that."""
    def ev(a, b, params, keep_trades=False, **kw):
        return None
    idx = pd.date_range("2020-01-01", periods=2000, freq="1D", tz="US/Eastern")
    fb = _fb(row={"fold": 1, "oos_pnl": 0.0, "oos_trades": 0, "oos_pf": 0.0, "oos_wins": 0})
    m = B.build_fold_match(ev, idx, fb, {}, warm_days=300)
    assert m["ok"] and m["warm_days"] == 300


# ── the #407 shape: a fold that ONLY reproduces warm ─────────────────────────────────────────

_TRADES_WARM = _TRADES_10                               # what the doc saved
_TRADES_COLD = _TRADES_10[:-2]                          # cold misses the carried position's pair


def _ev_warm_sensitive():
    """The real asymmetry, in miniature: warm carries in a position already open at te_s, so it
    returns the doc's trades; cold starts flat and returns fewer."""
    def ev(a, b, params, keep_trades=False, warm=False):
        trades = _TRADES_WARM if warm else _TRADES_COLD
        pnls = [t[2] for t in trades]
        gw = sum(x for x in pnls if x > 0)
        gl = -sum(x for x in pnls if x < 0)
        return {"trades": trades, "total_pnl": sum(pnls), "num_trades": len(trades),
                "wins": sum(1 for x in pnls if x > 0),
                "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)}
    return ev


def test_a_warm_scored_fold_mismatches_cold_and_reproduces_warm():
    ev, fb = _ev_warm_sensitive(), _fb()
    cold = B.build_fold_match(ev, None, fb, {"k": 1})
    warm = B.build_fold_match(ev, None, fb, {"k": 1}, warm_days=300)
    assert not cold["ok"] and "trades 8 vs saved 10" in cold["reason"]
    assert warm["ok"] and warm["reason"] is None
    assert warm["oos_trades"] == 10 and warm["oos_pnl"] == pytest.approx(8.0)


# ── provenance: no block leaves here without saying which arm built it ───────────────────────

def test_provenance_row_carries_warm_days():
    ev = _ev_warm_sensitive()
    m = B.build_fold_match(ev, None, _fb(), {"k": 1}, warm_days=300)
    assert B.provenance_row(m)["warm_days"] == 300


def test_block_stamp_records_the_arm():
    """A written block says which arm every fold was replayed on - backfill.warm_days, a single
    value because a block is only ever built when ALL folds matched on one arm."""
    d = _matching_doc()
    d["timestamp"] = RUN407_TS
    ref = _Ref((d, "t1"), (d, "t2"))

    def warm_rebuild(plan):
        assert plan["warm_days"] > 0 and "on or after" in plan["warm_why"]
        return [dict(m, warm_days=plan["warm_days"]) for m in _matches_from_doc(plan)]

    status, log = _run(ref, warm_rebuild, write=True)
    assert status == "written"
    payload, _opt = ref.updates[0]
    stamp = payload["validate.wf_oos"]["backfill"]
    assert stamp["warm_days"] == B._warm_days_now()
    assert stamp["tool"] == B.TOOL_VERSION and "warm-aware" in stamp["tool"]
    assert all(r["warm_days"] == B._warm_days_now() for r in stamp["matches"])
    assert "validated %s, on or after" % RUN407_TS in chr(10).join(log)


def test_one_logs_the_cold_era_for_a_pre_warm_run():
    d = _matching_doc()
    d["timestamp"] = RUN335_TS
    ref = _Ref((d, "t1"))
    status, log = _run(ref, _matches_from_doc)
    assert status == "dry"
    assert "before warm starts landed" in chr(10).join(log)


# ─────────────────────────────────────────────────────────────────────────────
# OFF-ERA: every fold reproduced, but on the arm the run's timestamp does NOT imply
# (MANAGER's VERIFIER point, 2026-11-20). The second arm exists because the era is inferred
# from a timestamp that can be missing, re-stamped by a repeat, or sit on the boundary day,
# so when the other arm reproduces every fold to the cent the inference is what is in doubt,
# not the replay. Verification still reports it; a WRITE is refused unless asked.
#
# Both halves are pinned here. The lines that SET the flag live in replay_arms(), which takes
# an ev_factory so the loop can be driven without a strategy or a master (see
# test_replay_arms_*); the lines that CONSUME it are driven through one(). The real end-to-end
# case behind all of it: ENGU-Q #407 on its own build goes 2 of 8 folds cold then 8 of 8 warm,
# recorded in book_stitched/ENGUQ_407_stitched_wf.md.
# ─────────────────────────────────────────────────────────────────────────────

def _off_era_matches(plan):
    """What the arm loop returns when the SECOND arm reproduced every fold: ok everywhere,
    plus off_era and the era it contradicts."""
    return [dict(m, off_era=True, warm_days=B._warm_days_now(), era_warm_days=0)
            for m in _matches_from_doc(plan)]


def test_a_dry_run_reports_an_off_era_replay_instead_of_refusing_it():
    """"Does this run reproduce?" deserves the honest yes, with the caveat attached."""
    d = _matching_doc()
    d["timestamp"] = RUN335_TS                      # the doc says COLD
    ref = _Ref((d, "t1"))
    status, log = _run(ref, _off_era_matches)
    text = chr(10).join(log)
    assert status == "dry" and ref.updates == []
    assert "OFF-ERA" in text and "the replay above is sound" in text.lower()


def test_a_write_of_an_off_era_block_is_refused_by_default():
    d = _matching_doc()
    d["timestamp"] = RUN335_TS
    ref = _Ref((d, "t1"), (d, "t2"))
    status, log = _run(ref, _off_era_matches, write=True)
    assert status == "offera"
    assert ref.updates == []
    assert "--allow-off-era" in chr(10).join(log)


def test_allow_off_era_writes_it_and_the_block_records_the_choice():
    d = _matching_doc()
    d["timestamp"] = RUN335_TS
    ref = _Ref((d, "t1"), (d, "t2"))
    status, _log = _run(ref, _off_era_matches, write=True, allow_off_era=True)
    assert status == "written"
    payload, _opt = ref.updates[0]
    off = payload["validate.wf_oos"]["backfill"]["off_era"]
    assert off["era_warm_days"] == 0 and off["replayed_warm_days"] == B._warm_days_now()
    assert "before warm starts landed" in off["why"]


def test_an_on_era_block_carries_no_off_era_stamp():
    d = _matching_doc()
    d["timestamp"] = RUN335_TS
    ref = _Ref((d, "t1"), (d, "t2"))
    status, _log = _run(ref, _matches_from_doc, write=True)
    assert status == "written"
    payload, _opt = ref.updates[0]
    assert "off_era" not in payload["validate.wf_oos"]["backfill"]


def test_provenance_row_flags_off_era_and_stays_null_otherwise():
    ev = _ev_warm_sensitive()
    on = B.build_fold_match(ev, None, _fb(), {"k": 1}, warm_days=300)
    assert B.provenance_row(on)["off_era"] is None
    assert B.provenance_row(dict(on, off_era=True))["off_era"] is True


def test_offera_is_not_an_ok_status():
    """main() must exit non-zero on it - it is a refusal, like mismatch."""
    assert "offera" not in B.OK_STATUSES


# -- the arm loop, where off_era is SET ------------------------------------------------------
#
# Driven through replay_arms()'s ev_factory, so no strategy and no master are needed: one stub
# evaluator per arm, the era arm deliberately missing. This is the #407 shape in miniature.

def _arm_plan(ts, folds=3):
    """A plan as rebuild_plan would hand it over, with the era already resolved from `ts`."""
    plan = {"mode": "rolling", "cost_pts": 0.783, "timestamp": ts}
    plan["warm_days"], plan["warm_why"] = B.warm_days_for_doc({"timestamp": ts})
    # _fb()'s default saved row is the one _TRADES_WARM (= _TRADES_10) reconciles with
    plan["folds"] = [_fb(fold=i + 1, te_s=1000 * (i + 1), te_e=1000 * (i + 1) + 500)
                     for i in range(folds)]
    return plan


def _arm_factory(matching_arm):
    """ev_factory whose evaluator reproduces the doc ONLY on `matching_arm` warm_days.
    Records which arms were built, so "the second arm is not run when the first matched" is
    checkable rather than assumed."""
    built = []

    def factory(wd):
        built.append(wd)
        trades = _TRADES_WARM if wd == matching_arm else _TRADES_COLD

        def ev(a, b, params, keep_trades=False, **kw):
            pnls = [t[2] for t in trades]
            gw = sum(x for x in pnls if x > 0)
            gl = -sum(x for x in pnls if x < 0)
            return {"trades": trades, "total_pnl": sum(pnls), "num_trades": len(trades),
                    "wins": sum(1 for x in pnls if x > 0),
                    "profit_factor": (gw / gl) if gl > 1e-9 else 0.0}
        return ev
    return factory, built


def _arm_run(ts, matching_arm, folds=3):
    plan = _arm_plan(ts, folds)
    factory, built = _arm_factory(matching_arm)
    log = []
    matches = B.replay_arms(plan, None, [{"k": 1}] * folds, factory, log=log.append)
    return plan, matches, built, chr(10).join(log)


def test_replay_arms_stamps_off_era_when_only_the_other_arm_reproduces():
    """The run's doc says COLD (#335's era), but only the WARM arm reproduces: every fold is
    returned ok, flagged off_era, and told which era it contradicts."""
    warm = B._warm_days_now()
    plan, matches, built, log = _arm_run(RUN335_TS, matching_arm=warm)
    assert built == [0, warm]                       # era arm first, then the second chance
    assert all(m["ok"] for m in matches)
    assert all(m["off_era"] is True for m in matches)
    assert all(m["warm_days"] == warm and m["era_warm_days"] == 0 for m in matches)
    assert "second chance" in log and "VERIFIED but OFF-ERA" in log
    assert "--allow-off-era" in log


def test_replay_arms_stamps_off_era_the_other_way_round_too():
    """And the mirror case: the doc says WARM (#407's era) but the COLD arm is the one that
    reproduces, which is what a re-stamped or repeated run looks like."""
    warm = B._warm_days_now()
    plan, matches, built, log = _arm_run(RUN407_TS, matching_arm=0)
    assert built == [warm, 0]
    assert all(m["ok"] and m["off_era"] is True for m in matches)
    assert all(m["warm_days"] == 0 and m["era_warm_days"] == warm for m in matches)


def test_replay_arms_on_the_era_arm_sets_no_flag_and_never_builds_the_second():
    plan, matches, built, log = _arm_run(RUN407_TS, matching_arm=B._warm_days_now())
    assert built == [B._warm_days_now()]            # the second arm is not even constructed
    assert all(m["ok"] and not m.get("off_era") for m in matches)
    assert "second chance" not in log and "OFF-ERA" not in log


def test_replay_arms_returns_the_ERA_arms_deltas_when_neither_reproduces():
    """A genuine mismatch must be reported against the arm the run was actually scored on, so
    the refusal shows the real deltas rather than the second guess's."""
    plan, matches, built, log = _arm_run(RUN335_TS, matching_arm=-1)   # no arm matches
    assert built == [0, B._warm_days_now()]
    assert all(not m["ok"] for m in matches)
    assert all(m["warm_days"] == 0 for m in matches)          # the ERA arm's, i.e. cold
    assert "trades 8 vs saved 10" in matches[0]["reason"]


# -- and the arm loop's REAL output carried through one() ------------------------------------
#
# The off-era consumer tests above use a hand-built stub; these two use what replay_arms
# actually returns, so the two halves cannot drift apart.

def _row_aware_factory(matching_arm, plan):
    """Like _arm_factory, but the folds come from a real run doc, so each one's canned trades
    are built from ITS OWN saved row (keyed by te_s, which replay_arms passes through to ev).
    The non-matching arm drops the last two trades - the #407 asymmetry in miniature."""
    rows = {fb["te_s"]: fb["row"] for fb in plan["folds"]}

    def factory(wd):
        def ev(a, b, params, keep_trades=False, **kw):
            row = rows[a]
            n, wins = int(row["oos_trades"]), int(row.get("oos_wins") or 0)
            pnls = [2.0] * wins + [-1.0] * (n - wins)
            if wd != matching_arm:
                pnls = pnls[:-2]
            gw = sum(x for x in pnls if x > 0)
            gl = -sum(x for x in pnls if x < 0)
            return {"trades": [(i, i + 1, p) for i, p in enumerate(pnls)],
                    "total_pnl": sum(pnls), "num_trades": len(pnls),
                    "wins": sum(1 for x in pnls if x > 0),
                    "profit_factor": (gw / gl) if gl > 1e-9 else 0.0}
        return ev
    return factory


def _off_era_rebuild_via_arm_loop(plan):
    factory = _row_aware_factory(B._warm_days_now(), plan)
    return B.replay_arms(plan, None, [{"k": 1}] * len(plan["folds"]), factory,
                         log=lambda *a: None)


def test_an_off_era_write_from_the_real_arm_loop_is_refused_without_the_flag():
    d = _matching_doc()
    d["timestamp"] = RUN335_TS                      # cold era; only the warm arm reproduces
    ref = _Ref((d, "t1"), (d, "t2"))
    status, log = _run(ref, _off_era_rebuild_via_arm_loop, write=True)
    assert status == "offera" and ref.updates == []
    assert "--allow-off-era" in chr(10).join(log)


def test_allow_off_era_writes_the_real_arm_loops_block_with_the_stamp():
    d = _matching_doc()
    d["timestamp"] = RUN335_TS
    ref = _Ref((d, "t1"), (d, "t2"))
    status, _log = _run(ref, _off_era_rebuild_via_arm_loop, write=True, allow_off_era=True)
    assert status == "written"
    stamp = ref.updates[0][0]["validate.wf_oos"]["backfill"]
    assert stamp["off_era"]["era_warm_days"] == 0
    assert stamp["off_era"]["replayed_warm_days"] == B._warm_days_now()
    assert "before warm starts landed" in stamp["off_era"]["why"]
    assert stamp["warm_days"] == B._warm_days_now()
    assert all(r["off_era"] is True for r in stamp["matches"])


def test_import_falls_back_when_pinned_engine_lacks_wf_oos_block(monkeypatch):
    """run_trades_series --pin puts an old engine first on sys.path; the tool must still import."""
    import importlib
    import sys
    import types
    old = types.ModuleType("augur_engine.analytics")   # an engine from before wf_oos_block existed
    monkeypatch.setitem(sys.modules, "augur_engine.analytics", old)
    monkeypatch.delitem(sys.modules, "tools.backfill_wf_oos", raising=False)
    mod = importlib.import_module("tools.backfill_wf_oos")
    assert callable(mod.wf_oos_block) and callable(mod.bar_date_bounds)
    monkeypatch.delitem(sys.modules, "tools.backfill_wf_oos", raising=False)
