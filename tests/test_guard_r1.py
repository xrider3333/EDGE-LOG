"""GUARD r1 (tools/guard_r1.py): synthetic-trade tests. No real Firestore, no master registry, no engine run.

The bar the harness implements is docs/GUARD_R1_PREREG.md; test_constants_match_prereg keeps the two in step.
Shared module attributes are never bare-assigned here: stand-ins are SimpleNamespace objects or monkeypatch.
"""
import datetime as dt
import importlib.util
import json
import os
import re
import types

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location("guard_r1_under_test", os.path.join(ROOT, "tools", "guard_r1.py"))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

CUT = dt.date(2026, 10, 30)
LIVE = dt.date(2026, 9, 28)
PNL_SENTINELS = (98765.43, 87654.32, 76543.21)      # distinctive dollar levels that must never be printed or stored


def unix(day, hhmm="10:00"):
    return int(pd.Timestamp(f"{day} {hhmm}", tz="US/Eastern").timestamp())


def mk(leg, day, hhmm="10:00", *, side=1, entry=20000.0, exit_=20010.0, size=1.0, pnl=None, open_=False,
       xday=None, xhhmm="15:55", backfill=None, mult=20.0):
    """A normalised trade (what norm_paper_row / norm_cold_trade return)."""
    eu = unix(day, hhmm)
    xu = unix(xday or day, xhhmm)
    pts = side * (exit_ - entry)
    usd = pnl if pnl is not None else pts * mult * size
    return {"id": G.trade_id(leg, eu), "leg": leg, "side": side, "entry_unix": eu, "exit_unix": xu,
            "entry_px": entry, "exit_px": exit_, "size": size, "pnl_pts": pts, "pnl_usd": usd, "open": open_,
            "close_day": None if open_ else (xday or day), "backfill": backfill,
            "entry_day": G._et_date(eu).isoformat()}


def pair(day, hhmm, **kw):
    return mk("ORB", day, hhmm, **kw), mk("ORB", day, hhmm, **kw)


def twenty(**kw):
    days = [(dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat() for i in range(20)]
    return [mk("ORB", d, **kw) for d in days]


def compare(paper, cold, *, key="ORB", instrument="NQ", timeframe="5m", mult=20.0, n=1, live=LIVE, cutoff=CUT,
            through=None, artifacts=frozenset()):
    through = through if through is not None else unix("2026-11-02", "16:00")
    return G.compare_leg(key, mult=mult, n_contracts=n, instrument=instrument, timeframe=timeframe, live_from=live,
                         cutoff=cutoff, paper=paper, cold=cold, master_through_unix=through, artifacts=set(artifacts))


def verdict(res, **kw):
    return G.evaluate_leg(res, post_close_ids=kw.pop("post", []), **kw)


# --------------------------------------------------------------------------------------------- per-leg comparison
def test_exact_match_passes():
    paper, cold = twenty(), twenty()
    res = compare(paper, cold)
    ev = verdict(res)
    f = res["forward"]
    assert ev["verdict"] == "PASS", ev
    assert (f["matched"], f["in_band"], f["exact_n"], f["denominator"]) == (20, 20, 20, 20)
    assert not f["missing"] and not f["extra"]


def test_price_band_match_and_the_exact_threshold():
    paper = twenty()
    cold = twenty()
    cold[3]["entry_px"] += 0.5            # inside the NQ band (1.0): in band, not exact
    cold[3]["pnl_usd"] -= 0.5 * 20.0
    ev = verdict(compare(paper, cold))
    assert ev["verdict"] == "PASS"        # 19 of 20 exact = 95%, the bar
    cold[7]["exit_px"] += 0.75
    cold[7]["pnl_usd"] += 0.75 * 20.0
    res = compare(paper, cold)
    ev = verdict(res)
    assert res["forward"]["in_band"] == 20 and res["forward"]["exact_n"] == 18
    assert ev["verdict"] == "FAIL" and [d["cond"] for d in ev["defects"]] == ["C2 exact"]


def test_price_outside_band_fails_c1_and_names_the_trade():
    paper, cold = twenty(), twenty()
    cold[5]["entry_px"] += 1.5            # outside the 1.0 NQ band
    cold[5]["pnl_usd"] -= 1.5 * 20.0
    res = compare(paper, cold)
    ev = verdict(res)
    assert ev["verdict"] == "FAIL"
    d = next(x for x in ev["defects"] if x["cond"] == "C1 in-band")
    assert paper[5]["id"] in d["trade_ids"]
    assert "entry price differs" in d["detail"][0]["reasons"][0]


def test_es_band_is_half_a_point():
    paper = [mk("TTM_299_SSOF2", "2026-10-05", entry=6000.0, exit_=6010.0, mult=50.0)]
    cold = [mk("TTM_299_SSOF2", "2026-10-05", entry=6000.4, exit_=6010.0, mult=50.0)]
    res = compare(paper, cold, key="TTM_299_SSOF2", instrument="ES", timeframe="30m", mult=50.0, n=7)
    assert res["forward"]["in_band"] == 1
    cold[0]["entry_px"] = 6000.6
    assert compare(paper, cold, key="TTM_299_SSOF2", instrument="ES", timeframe="30m", mult=50.0, n=7)["forward"]["in_band"] == 0


def test_dollars_may_differ_only_as_much_as_the_prices_allow():
    paper, cold = twenty(), twenty()
    cold[2]["pnl_usd"] += 40.0            # prices identical, dollars off by $40: a cost / size / fill drift
    res = compare(paper, cold)
    assert res["forward"]["out"] == 1
    assert "dollars differ" in res["forward"]["out_detail"][0]["reasons"][0]


def test_missing_trade_fails_and_names_it():
    paper, cold = twenty(), twenty()
    gone = paper.pop(4)
    res = compare(paper, cold)
    ev = verdict(res)
    assert ev["verdict"] == "FAIL"
    d = next(x for x in ev["defects"] if x["cond"] == "C3 missing")
    assert d["trade_ids"] == [gone["id"]]


def test_extra_trade_fails_and_names_it():
    paper, cold = twenty(), twenty()
    extra = mk("ORB", "2026-10-25", "11:15")
    paper.append(extra)
    res = compare(paper, cold)
    ev = verdict(res)
    d = next(x for x in ev["defects"] if x["cond"] == "C4 extra")
    assert d["trade_ids"] == [extra["id"]]


def test_adjacent_bar_pair_is_flagged_as_a_stamping_shift():
    paper, cold = twenty(), twenty()
    shifted = mk("ORB", "2026-10-03", "10:05")        # the cold trade one 5m bar later than the paper trade at 10:00
    cold[2] = shifted
    res = compare(paper, cold)
    f = res["forward"]
    assert len(f["missing"]) == 1 and len(f["extra"]) == 1 and f["adjacent_pairs"] == 1


def test_opposite_side_on_the_same_bar_is_a_defect():
    paper, cold = twenty(), twenty()
    cold[1]["side"] = -1
    ev = verdict(compare(paper, cold))
    assert ev["verdict"] == "FAIL" and any(d["cond"] == "C4 side" for d in ev["defects"])


def test_explained_roll_artifact_extra_passes():
    paper, cold = twenty(), twenty()
    art = mk("ORB", "2026-10-09", "09:45", entry=20000.0, exit_=19950.0)
    paper.append(art)                                          # in the paper record only (the splice made it)
    assert verdict(compare(paper, cold))["verdict"] == "FAIL"
    res = compare(paper, cold, artifacts={("ORB", art["entry_unix"])})
    ev = verdict(res)
    assert ev["verdict"] == "PASS" and art["id"] in res["forward"]["explained"]
    assert res["forward"]["denominator"] == 20                 # explained leaves numerator and denominator


def test_explained_roll_artifact_out_of_band_and_cold_only_on_the_same_day():
    paper, cold = twenty(), twenty()
    art = paper[6]
    cold[6]["exit_px"] -= 80.0                                 # the splice moved the paper trade's exit
    cold[6]["pnl_usd"] -= 80.0 * 20.0
    assert verdict(compare(paper, cold))["verdict"] == "FAIL"
    assert verdict(compare(paper, cold, artifacts={("ORB", art["entry_unix"])}))["verdict"] == "PASS"
    # a cold-only trade is explained only on a day that has a listed artifact for the leg
    cold2 = twenty()
    cold2.append(mk("ORB", paper[6]["entry_day"], "13:00"))
    assert verdict(compare(twenty(), cold2))["verdict"] == "FAIL"
    assert verdict(compare(twenty(), cold2, artifacts={("ORB", paper[6]["entry_unix"])}))["verdict"] == "PASS"


def test_open_trade_at_the_cutoff_compares_on_entry_only():
    paper, cold = twenty(), twenty()
    paper[-1].update(open=True, close_day=None, exit_px=20003.0, pnl_usd=60.0, exit_unix=unix("2026-10-20", "15:55"))
    cold[-1].update(open=True, close_day=None, exit_px=20031.0, pnl_usd=620.0, exit_unix=unix("2026-10-21", "09:30"))
    res = compare(paper, cold)
    assert verdict(res)["verdict"] == "PASS" and res["forward"]["open_either"] == 1
    cold[-1].update(open=False, close_day="2026-10-21")      # the cold master ran on and closed it: still entry-only
    assert verdict(compare(paper, cold))["verdict"] == "PASS"
    cold[-1]["entry_px"] += 3.0                                 # but a wrong ENTRY on an open trade still fails
    assert verdict(compare(paper, cold))["verdict"] == "FAIL"


def test_backfill_trades_do_not_enter_the_verdict_but_are_reported():
    paper = twenty()
    cold = twenty()
    old_p = mk("ORB", "2026-09-15", "10:00")                  # before LIVE (09-28): backfill
    paper.append(old_p)                                        # a backfill trade the cold reference does not have
    res = compare(paper, cold)
    assert verdict(res)["verdict"] == "PASS"
    assert res["backfill"]["extra"] == [old_p["id"]]


def test_backfill_flag_disagreeing_with_live_from_fails():
    paper = twenty()
    paper[0]["backfill"] = True                                # a forward trade marked backfill
    ev = verdict(compare(paper, twenty()))
    assert ev["verdict"] == "FAIL" and any(d["cond"] == "backfill flag" for d in ev["defects"])


def test_trades_after_the_cutoff_are_excluded_on_both_sides():
    paper, cold = twenty(), twenty()
    paper.append(mk("ORB", "2026-11-03", "10:00"))
    assert verdict(compare(paper, cold))["verdict"] == "PASS"


def test_uncovered_and_short_master_and_cold_failure_are_incomplete_not_pass():
    paper, cold = twenty(), twenty()
    paper.append(mk("ORB", "2026-10-29", "15:00"))
    through = unix("2026-10-28", "16:00")
    res = compare(paper, cold, through=through)
    ev = verdict(res)
    assert ev["verdict"] == "INCOMPLETE" and res["forward"]["uncovered"] == [paper[-1]["id"]]
    assert verdict(compare(twenty(), twenty(), through=unix("2026-10-28", "16:00")))["verdict"] == "INCOMPLETE"   # master ends before cut-off
    assert verdict(compare(twenty(), twenty()), cold_failed="no master")["verdict"] == "INCOMPLETE"
    assert verdict(compare(twenty(), twenty()), bundle_stale=True)["verdict"] == "INCOMPLETE"


def test_no_forward_trades_reads_no_trades_not_pass():
    ev = verdict(compare([], []))
    assert ev["verdict"] == "NO TRADES"
    ev = verdict(compare([], [mk("ORB", "2026-10-06")]))        # the cold run has one, the record none
    assert ev["verdict"] == "FAIL"


def test_the_99_percent_rule_is_integer_exact():
    paper = [mk("ORB", (dt.date(2026, 10, 1) + dt.timedelta(days=i % 28)).isoformat(), f"{9 + i // 28}:{(i * 7) % 60:02d}")
             for i in range(200)]
    cold = [dict(t) for t in paper]
    cold[0]["exit_px"] += 5.0
    cold[0]["pnl_usd"] += 100.0
    cold[1]["exit_px"] += 5.0
    cold[1]["pnl_usd"] += 100.0
    res = compare(paper, cold)
    assert res["forward"]["in_band"] == 198 and verdict(res)["verdict"] == "PASS"     # 198/200 = 99% exactly
    cold[2]["exit_px"] += 5.0
    cold[2]["pnl_usd"] += 100.0
    assert verdict(compare(paper, cold))["verdict"] == "FAIL"


# ------------------------------------------------------------------------------------------------ price basis
def test_basis_offsets_put_an_adjusted_cold_price_on_the_paper_basis():
    times = [unix("2026-09-10", "10:00"), unix("2026-09-14", "10:00"), unix("2026-09-15", "10:00")]
    adj = [20296.5, 20300.0, 20400.0]          # back-adjusted: the pre-roll bars carry +296.5
    raw = [20000.0, 20003.5, 20400.0]
    off = G.BasisOffsets.from_arrays(times, adj, times, raw)
    assert off.at(times[0]) == pytest.approx(296.5) and off.at(times[2]) == pytest.approx(0.0)
    assert off.at(times[0] - 10) == pytest.approx(296.5)       # before the first common bar: the first offset
    assert off.at(times[2] + 86400) == pytest.approx(0.0)      # after the last: the last (a capture tail on today's contract)
    assert G.BasisOffsets.zero().at(123) == 0.0
    cold_trade = {"entry_dt": pd.Timestamp("2026-09-10 10:00", tz="US/Eastern"), "exit_dt": pd.Timestamp("2026-09-10 15:55", tz="US/Eastern"),
                  "side": 1, "entry_px": 20296.5, "exit_px": 20326.5, "size": 1.0, "pnl_pts": 29.5, "pnl_usd": 590.0, "open": False}
    nt = G.norm_cold_trade(cold_trade, "ORB", off)
    assert nt["entry_px"] == pytest.approx(20000.0) and nt["id"] == f"pt_ORB_{unix('2026-09-10', '10:00')}"


def test_paper_row_size_is_derived_from_the_bundle_fields():
    row = {"id": "pt_NOISE_422_1", "leg": "NOISE_422", "side": 1, "entryTime": unix("2026-10-05"), "exitTime": unix("2026-10-05", "15:55"),
           "entry_px": 20000.0, "exit_px": 20010.0, "pnl_pts": 10.0, "pnl_usd": 350.0, "open": False, "close_day": "2026-10-05"}
    nt = G.norm_paper_row(row, 20.0)
    assert nt["size"] == pytest.approx(1.75) and nt["close_day"] == "2026-10-05" and nt["entry_day"] == "2026-10-05"
    row["size"] = 2.0
    assert G.norm_paper_row(row, 20.0)["size"] == 2.0
    assert G.norm_paper_row({"leg": "ORB"}, 20.0) is None


# ----------------------------------------------------------------------------------------------- post-close changes
def _report(day, legs, **extra):
    d = {"legs": {k: {"pnl_usd": v} for k, v in legs.items()}}
    d.update(extra)
    return d


def test_post_close_change_report_versus_trade_docs():
    t1 = mk("ORB", "2026-10-06", pnl=100.0, xday="2026-10-06")
    t2 = mk("ORB", "2026-10-06", "11:00", pnl=30.0, xday="2026-10-06")
    reports = {"2026-10-06": _report("2026-10-06", {"ORB": 100.0})}           # the day was written when t2 had not closed
    out = G.check_report_vs_docs(reports, {"ORB": [t1, t2]}, ["ORB"], CUT)
    m = out["ORB"]["mismatches"]
    assert len(m) == 1 and m[0]["day"] == "2026-10-06" and m[0]["diff_usd"] == -30.0 and set(m[0]["trade_ids"]) == {t1["id"], t2["id"]}
    ev = verdict(compare(twenty(), twenty()), post=[i for x in m for i in x["trade_ids"]])
    assert ev["verdict"] == "FAIL" and any(d["cond"] == "C5 post-close" for d in ev["defects"])
    clean = {"2026-10-06": _report("2026-10-06", {"ORB": 130.0})}
    assert G.check_report_vs_docs(clean, {"ORB": [t1, t2]}, ["ORB"], CUT)["ORB"]["mismatches"] == []


def test_post_close_report_check_ignores_open_trades_and_pre_cutover_days():
    closed = mk("ORB", "2026-09-20", pnl=50.0, xday="2026-09-21")
    held = mk("ORB", "2026-10-06", pnl=999.0, open_=True)
    reports = {"2026-09-21": _report("x", {"ORB": 0.0}), "2026-10-06": _report("x", {"ORB": 0.0})}
    out = G.check_report_vs_docs(reports, {"ORB": [closed, held]}, ["ORB"], CUT)
    assert out["ORB"]["mismatches"] == [] and len(out["ORB"]["legacy"]) == 1         # entry-day era: information only


def test_post_close_snapshot_diff_changed_and_absent_and_reopened():
    a = mk("ORB", "2026-10-06", pnl=100.0)
    b = mk("ORB", "2026-10-07", pnl=50.0)
    c = mk("ORB", "2026-10-08", pnl=10.0)
    prev = G.make_snapshot({"ORB": [a, b, c]}, ["ORB"], dt.date(2026, 10, 9))
    assert set(prev) == {a["id"], b["id"], c["id"]}
    a2, c2 = dict(a), dict(c)
    a2["pnl_usd"] = 100.01                       # a closed trade's dollars moved
    c2.update(open=True, close_day=None)        # and one re-opened
    now = {"ORB": [a2, c2]}                      # b is gone
    diff = G.diff_snapshot(prev, now, ["ORB"])["ORB"]
    assert dict(diff) == {a["id"]: "changed", b["id"]: "absent", c["id"]: "changed"}
    assert G.diff_snapshot(prev, {"ORB": [a, b, c]}, ["ORB"])["ORB"] == []
    assert G.diff_snapshot(None, now, ["ORB"])["ORB"] == []


def test_snapshot_holds_digests_not_dollars():
    a = mk("ORB", "2026-10-06", pnl=PNL_SENTINELS[0])
    snap = G.make_snapshot({"ORB": [a]}, ["ORB"], CUT)
    assert "98765" not in json.dumps(snap)


def test_prior_snapshot_is_the_newest_earlier_cutoff(tmp_path):
    for name, cut in (("guard_r1_2026-09-30_20261005T010101Z.json", "2026-09-30"),
                      ("guard_r1_2026-10-30_20261101T010101Z.json", "2026-10-30"),
                      ("guard_r1_2026-08-31_20260901T010101Z.json", "2026-08-31")):
        (tmp_path / name).write_text(json.dumps({"cutoff": cut, "snapshot": {"k": cut}}), encoding="utf-8")
    snap, meta = G.load_prior_snapshot(str(tmp_path), "2026-10-30")
    assert snap == {"k": "2026-09-30"} and meta["cutoff"] == "2026-09-30"
    assert G.load_prior_snapshot(str(tmp_path / "nope"), "2026-10-30") == (None, None)
    assert G.load_prior_snapshot(str(tmp_path), "2026-08-01") == (None, None)


# ----------------------------------------------------------------------------------------------------------- lines
def _line_doc(legs, line="book", pnl=None, weights=None):
    w = weights or G.LINES[line]
    total = sum(w.get(k, 0.0) * v for k, v in legs.items()) if pnl is None else pnl
    return {"legs": {k: {"pnl_usd": v} for k, v in legs.items()}, line: {"pnl_usd": total, "weights": dict(w)}}


def test_line_sum_of_legs_within_a_cent():
    legs = {"ORB": 100.0, "ENGUQ_335": -40.5, "TTM_299_SSOF2": 12.25, "NOISE_422": 7.0}
    ok = {"2026-10-06": _line_doc(legs)}
    assert G.check_lines(ok, CUT)["book"]["defects"] == []
    near = {"2026-10-06": _line_doc(legs, pnl=sum(G.LINES["book"][k] * v for k, v in legs.items()) + 0.009)}
    assert G.check_lines(near, CUT)["book"]["defects"] == []
    bad = {"2026-10-06": _line_doc(legs, pnl=sum(G.LINES["book"][k] * v for k, v in legs.items()) + 0.02)}
    d = G.check_lines(bad, CUT)["book"]["defects"]
    assert len(d) == 1 and d[0]["kind"] == "L1 sum of legs" and d[0]["diff_usd"] == pytest.approx(0.02)
    assert G.line_verdict(G.check_lines(bad, CUT)["book"]) == "FAIL"


def test_line_uses_the_docs_own_weights_but_composition_is_checked_from_the_line_start():
    legs = {"ORB": 10.0, "ENGUQ_335": 10.0, "TTM_299_SSOF2": 10.0, "NOISE_422": 10.0}
    old_w = {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 0.0}       # an older composition
    before = {"2026-09-20": _line_doc(legs, weights=old_w)}
    assert G.check_lines(before, CUT)["book"]["defects"] == []                          # before LINE_FROM: only the sum is checked
    after = {"2026-10-06": _line_doc(legs, weights=old_w)}
    d = G.check_lines(after, CUT)["book"]["defects"]
    assert [x["kind"] for x in d] == ["L1b composition"]


def test_a_leg_missing_from_the_doc_counts_zero_like_the_nightly_run():
    legs = {"ORB": 10.0, "ENGUQ_335": 5.0, "TTM_299_SSOF2": 1.0}                         # NOISE_422 absent
    doc = {"legs": {k: {"pnl_usd": v} for k, v in legs.items()},
           "book": {"pnl_usd": 10.0 + 5.0 + 3.0, "weights": dict(G.LINES["book"])}}
    assert G.check_lines({"2026-10-06": doc}, CUT)["book"]["defects"] == []


def test_vt_identity_and_cold_multiplier():
    book = 500.0
    doc = {"legs": {}, "book": {"pnl_usd": book}, "book_shadow_vt": {"pnl_usd": 1.3 * book, "multiplier": 1.3}}
    day = "2026-10-06"
    assert G.check_lines({day: doc}, CUT, cold_vt={day: 1.3})["book_shadow_vt"]["defects"] == []
    assert G.check_lines({day: doc}, CUT, cold_vt={day: 1.34})["book_shadow_vt"]["defects"] == []     # inside the 0.055 slack
    d = G.check_lines({day: doc}, CUT, cold_vt={day: 1.4})["book_shadow_vt"]["defects"]
    assert d[0]["kind"] == "L3 multiplier" and d[0]["stored"] == 1.3
    doc2 = {"legs": {}, "book": {"pnl_usd": book}, "book_shadow_vt": {"pnl_usd": 1.3 * book + 0.5, "multiplier": 1.3}}
    assert G.check_lines({day: doc2}, CUT, cold_vt={day: 1.3})["book_shadow_vt"]["defects"][0]["kind"] == "L2 identity"
    err = {"legs": {}, "book": {"pnl_usd": book}, "book_shadow_vt": {"error": "stale master data"}}
    assert G.check_lines({day: err}, CUT)["book_shadow_vt"]["defects"][0]["kind"] == "L2 no figure"
    pre = {"2026-09-29": err}
    assert G.check_lines(pre, CUT)["book_shadow_vt"]["defects"] == []                      # before the first VT day


def test_a_missing_report_day_makes_the_line_incomplete():
    legs = {"ORB": 1.0}
    reports = {"2026-10-06": _line_doc(legs)}
    days = lambda a, b: [dt.date(2026, 10, 5), dt.date(2026, 10, 6), dt.date(2026, 10, 7)]   # noqa: E731
    rec = G.check_lines(reports, CUT, session_days=days)["book"]
    assert rec["missing_days"] == ["2026-10-05", "2026-10-07"] and G.line_verdict(rec) == "INCOMPLETE"


def test_a_line_that_starts_after_the_cutoff_has_no_window_and_is_not_incomplete():
    days = lambda a, b: [a, b]      # noqa: E731  (what sessions_between does when its arguments are swapped)
    rec = G.check_lines({}, dt.date(2026, 9, 30), session_days=days)["book_shadow_q4"]      # q4 starts 2026-10-01
    assert rec["missing_days"] == [] and G.line_verdict(rec) == "NO DAYS"
    rec = G.check_lines({}, dt.date(2026, 9, 30), session_days=days)["book_shadow"]          # starts 2026-09-29: a real window
    assert G.line_verdict(rec) == "INCOMPLETE"


def test_vt_unrounded_matches_the_nightly_multiplier():
    from api import book_shadow as bs
    rng = np.random.default_rng(7)
    M = pd.Series(rng.normal(0, 1500, 700), index=pd.bdate_range("2023-01-02", periods=700))
    raw = G.vt_unrounded(M)
    assert (raw.round(1) == bs.vt_multipliers(M)).all()


def test_a_line_whose_leg_is_not_clean_is_read_from_the_cold_reference():
    line_res = {k: {"days": 3, "defects": [], "missing_days": []} for k in G.LINES}
    legs = {k: {"verdict": "PASS"} for k in G.LEG_KEYS}
    src = G.lines_read_source(line_res, legs)
    assert all(v["source"] == "paper record" for v in src.values())
    legs["ORB_R6"]["verdict"] = "FAIL"
    legs["DIP_ES_452"]["verdict"] = "INCOMPLETE"
    src = G.lines_read_source(line_res, legs)
    assert src["book_shadow_orb314"]["source"].startswith("COLD") and src["book_shadow_q4"]["legs_not_clean"] == ["ORB_R6"]
    assert src["book"]["source"] == "paper record" and src["book_shadow_orb239"]["source"] == "paper record"
    line_res["book"]["defects"] = [{"day": "x", "kind": "L1 sum of legs"}]
    assert G.lines_read_source(line_res, legs)["book"]["source"].startswith("COLD")


# --------------------------------------------------------------------------------- the cold run's pipeline patching
def _fake_paper(record):
    def run_shadow(leg, today):
        record.append((dict(leg), today, p.find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth")),
                       p._load_fresh_ticks(leg["instrument"])))
        return {"trades": [{"x": 1}], "warnings": [], "ran_ok": True}
    p = types.SimpleNamespace(find_master=lambda *a, **k: "THE UNPINNED MASTER", _load_fresh_ticks=lambda i="NQ": ("TICKS", "path"),
                              run_shadow=run_shadow)
    return p


def test_the_cold_run_pins_the_master_removes_the_tail_forces_history_and_restores():
    rec = []
    p = _fake_paper(rec)
    orig_fm, orig_lt = p.find_master, p._load_fresh_ticks
    trades, warns, ok = G.run_cold_leg(p, {"key": "ORB", "instrument": "NQ", "timeframe": "5m", "session": "rth"}, "PINNED", "2026-09-30")
    assert ok and trades == [{"x": 1}]
    leg, today, master, ticks = rec[0]
    assert master == "PINNED" and ticks[0] is None and leg["history_from"] == G.HISTORY_FROM and today == dt.date(2026, 9, 30)
    assert p.find_master is orig_fm and p._load_fresh_ticks is orig_lt


def test_the_cold_run_restores_the_pipeline_even_when_it_raises():
    p = _fake_paper([])
    orig_fm = p.find_master

    def boom(leg, today):
        raise RuntimeError("engine fell over")
    p.run_shadow = boom
    with pytest.raises(RuntimeError):
        G.run_cold_leg(p, {"key": "ORB", "instrument": "NQ", "timeframe": "5m"}, "PINNED", "2026-09-30")
    assert p.find_master is orig_fm


# ------------------------------------------------------------------------------------------------------ read-only
class _FakeSnap:
    def __init__(self, d):
        self._d = d
        self.exists = d is not None
        self.id = "x"

    def to_dict(self):
        return self._d


class _FakeDoc:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def get(self):
        return _FakeSnap(self.store.get(self.path))

    def collection(self, name):
        return _FakeColl(self.store, self.path + "/" + name)

    def set(self, *a, **k):
        raise AssertionError("a WRITE reached the fake Firestore (set)")

    update = delete = set


class _FakeColl:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, i):
        return _FakeDoc(self.store, self.path + "/" + str(i))

    def stream(self):
        pre = self.path + "/"
        for p, d in sorted(self.store.items()):
            if p.startswith(pre) and "/" not in p[len(pre):]:
                yield _FakeSnap(d)

    def add(self, *a, **k):
        raise AssertionError("a WRITE reached the fake Firestore (add)")


class FakeDB:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        return _FakeColl(self.store, name)

    def batch(self):
        raise AssertionError("a WRITE reached the fake Firestore (batch)")


def test_read_only_wrapper_refuses_every_write_and_counts_reads():
    store = {"users/u/paper_reports/2026-10-06": {"a": 1}}
    db = G.ReadOnlyDB(FakeDB(store))
    doc = db.collection("users").document("u").collection("paper_reports").document("2026-10-06")
    assert doc.get().to_dict() == {"a": 1} and db.reads[0] == 1
    for bad in ("set", "update", "delete", "create"):
        with pytest.raises(G.ReadOnlyViolation):
            getattr(doc, bad)
    with pytest.raises(G.ReadOnlyViolation):
        db.batch()
    with pytest.raises(G.ReadOnlyViolation):
        db.collection("users").add
    with pytest.raises(G.ReadOnlyViolation):
        db.collection("users").document("u").collection("meta").set


# ----------------------------------------------------------------------------------------------- the whole run
class FakeSource:
    def __init__(self, rows, reports, gen=None):
        self.rows, self.rep = rows, reports
        self.gen = gen if gen is not None else str(unix("2026-11-02", "16:10"))
        self.n_reads = 0

    def paper_trades(self):
        self.n_reads += 3
        return self.rows, {"via": "bundle", "gen": self.gen, "n_total": len(self.rows), "parts": 1}

    def report(self, day):
        self.n_reads += 1
        return self.rep.get(day)

    def reads(self):
        return self.n_reads


def _row(t, backfill=False):
    return {"id": t["id"], "leg": t["leg"], "side": t["side"], "entryTime": t["entry_unix"], "exitTime": t["exit_unix"],
            "entry_px": t["entry_px"], "exit_px": t["exit_px"], "pnl_pts": t["pnl_pts"], "pnl_usd": t["pnl_usd"],
            "open": t["open"], "close_day": t["close_day"], "backfill": backfill}


def _leg_info():
    from_ = {"ORB": "2026-09-28"}
    out = {}
    for k in G.LEG_KEYS:
        inst = "ES" if k.startswith(("TTM", "DIP_ES")) else "NQ"
        out[k] = {"mult": 50.0 if inst == "ES" else 20.0, "instrument": inst, "timeframe": "5m", "session": "rth",
                  "live_from": from_.get(k, "2026-09-28")}
    return out


def _run(rows, reports, cold, *, dry=True, out_dir=None, only=None, artifacts=frozenset(), vt=None, prior=None, source=None):
    through = unix("2026-11-02", "16:00")

    def cold_provider(key):
        return {"trades": cold.get(key, []), "master_through_unix": through, "master": {"last_bar_et": "2026-11-02"}, "failed": None}

    return G.run_guard(CUT, dry_run=dry, source=source or FakeSource(rows, reports), cold_provider=cold_provider,
                       vt_provider=(lambda first: vt or {}), leg_info=_leg_info(), artifacts=set(artifacts),
                       session_days=None, only=only, prior_snapshot=prior, prereg_hash="abc", git_rev="deadbee", now=1_800_000_000)


def _good_world():
    """Every leg has 3 trades matching cold exactly; one report day per trade-close day, lines consistent."""
    rows, cold, legs_by_day = [], {}, {}
    for k in G.LEG_KEYS:
        m = _leg_info()[k]["mult"]
        base = 6000.0 if k.startswith(("TTM", "DIP_ES")) else 20000.0
        # exit chosen so that dollars = the sentinel level (pnl_usd = pnl_pts * mult * size, as in the real record)
        ts = [mk(k, d, mult=m, entry=base, exit_=base + PNL_SENTINELS[i % 3] / m)
              for i, d in enumerate(("2026-10-06", "2026-10-07", "2026-10-08"))]
        cold[k] = [dict(t) for t in ts]
        rows += [_row(t) for t in ts]
        for t in ts:
            legs_by_day.setdefault(t["close_day"], {})[k] = legs_by_day.get(t["close_day"], {}).get(k, 0.0) + t["pnl_usd"]
    reports = {}
    for day, legs in legs_by_day.items():
        doc = {"legs": {k: {"pnl_usd": v} for k, v in legs.items()}}
        for line, w in G.LINES.items():
            if line == "book_shadow_vt":
                continue
            doc[line] = {"pnl_usd": sum(x * legs.get(k, 0.0) for k, x in w.items()), "weights": dict(w)}
        doc["book_shadow_vt"] = {"multiplier": 1.2, "pnl_usd": 1.2 * doc["book"]["pnl_usd"]}
        reports[day] = doc
    return rows, reports, cold, {d: 1.2 for d in reports}


def test_end_to_end_all_pass_prints_and_stores_no_pnl_level(tmp_path):
    rows, reports, cold, vt = _good_world()
    res = _run(rows, reports, cold, vt=vt)
    assert res["overall"] == "PASS", json.dumps({k: v["verdict"] for k, v in res["legs"].items()})
    assert res["dry_run"] and not res["binding"]
    text = G.render(res)
    assert text.startswith("GUARD r1 DRY RUN - NOT THE BINDING READ (first binding read 2026-10-30)")
    path, cpath = G.write_outputs(res, str(tmp_path))
    blob = text + open(path, encoding="utf-8").read()
    for s in PNL_SENTINELS:
        assert f"{s:.2f}" not in blob and str(int(s)) not in blob
    assert cpath is None                                            # no cold P&L is stored for passing legs
    d = json.load(open(path, encoding="utf-8"))
    assert set(d["lines"]) == set(G.LINES) and len(d["legs"]) == 13 and d["snapshot"]
    G.assert_no_pnl_level(d)
    for bad in ({"a": {"pnl_usd": 1}}, {"ROC": 3}, [{"Sortino": 1}], {"x": {"cumulative": 2}}):
        with pytest.raises(AssertionError):
            G.assert_no_pnl_level(bad)


def test_end_to_end_a_failing_leg_names_leg_statistic_and_ids_and_writes_only_its_cold_rows(tmp_path):
    rows, reports, cold, vt = _good_world()
    dropped = next(r for r in rows if r["leg"] == "ORB_R6")
    rows.remove(dropped)                                            # the record lost one ORB_R6 trade
    res = _run(rows, reports, cold, vt=vt)
    assert res["overall"] == "FAIL"
    orb = res["legs"]["ORB_R6"]
    assert orb["verdict"] == "FAIL" and orb["defects"][0]["cond"] == "C3 missing" and orb["defects"][0]["trade_ids"] == [dropped["id"]]
    text = G.render(res)
    assert "FAIL C3 missing" in text and "leg ORB_R6" in text and dropped["id"] in text
    # the legs/lines that stand on it read from the cold reference until it passes
    assert res["lines"]["book_shadow_orb314"]["forward_read_source"].startswith("COLD")
    assert res["lines"]["book"]["forward_read_source"] == "paper record"
    path, cpath = G.write_outputs(res, str(tmp_path))
    cold_file = json.load(open(cpath, encoding="utf-8"))
    assert list(cold_file["legs"]) == ["ORB_R6"]                    # only the non-passing leg's cold rows
    assert "pnl_usd" not in open(path, encoding="utf-8").read()


def test_end_to_end_post_close_change_between_two_runs(tmp_path):
    rows, reports, cold, vt = _good_world()
    first = _run(rows, reports, cold, vt=vt)
    assert first["overall"] == "PASS" and "baseline written" in G.render(first)
    prior = (first["snapshot"], {"file": "guard_r1_2026-10-30_x.json", "cutoff": "2026-10-30"})
    changed = [dict(r) for r in rows]
    victim = next(r for r in changed if r["leg"] == "NOISE_304")
    victim["pnl_usd"] += 12.5                                       # a closed trade re-upserted with other dollars
    second = _run(changed, reports, cold, vt=vt, prior=prior)
    nl = second["legs"]["NOISE_304"]
    assert nl["verdict"] == "FAIL" and any(d["cond"] == "C5 post-close" and victim["id"] in d["trade_ids"] for d in nl["defects"])
    assert "compared with guard_r1_2026-10-30_x.json" in G.render(second)


def test_end_to_end_line_sum_mismatch_and_binding_flag(tmp_path):
    rows, reports, cold, vt = _good_world()
    day = sorted(reports)[0]
    reports[day]["book_shadow_q4"]["pnl_usd"] += 0.05
    res = _run(rows, reports, cold, vt=vt, dry=False, only=None)
    assert res["overall"] == "FAIL" and res["lines"]["book_shadow_q4"]["verdict"] == "FAIL"
    assert res["lines"]["book_shadow_q4"]["defects"][0]["kind"] == "L1 sum of legs"
    assert res["binding"] is True and G.render(res).startswith("GUARD r1 BINDING READ")
    sub = _run(rows, reports, cold, vt=vt, dry=False, only={"ORB"})
    assert sub["binding"] is False and sub["subset"] == ["ORB"]


def test_end_to_end_runs_against_a_write_forbidding_firestore():
    rows, reports, cold, vt = _good_world()
    store = {}
    for r in rows:
        store[f"users/u/paper_trades/{r['id']}"] = r
    for d, doc in reports.items():
        store[f"users/u/paper_reports/{d}"] = doc
    db = G.ReadOnlyDB(FakeDB(store))
    src = G.FirestoreSource(db, uid="u")
    # no bundle in the fake store: the source falls back to streaming the trade docs, read-only
    got, meta = src.paper_trades()
    assert meta["via"] == "direct" and len(got) == len(rows)
    assert src.report("2026-10-06") == reports["2026-10-06"] and src.report("2026-10-04") is None
    assert src.reads() > len(rows)


def test_bundle_older_than_the_cutoff_day_is_incomplete():
    rows, reports, cold, vt = _good_world()
    src = FakeSource(rows, reports, gen=str(unix("2026-10-29", "16:10")))
    res = _run(rows, reports, cold, vt=vt, source=src)
    assert res["bundle_stale"] and res["overall"] == "INCOMPLETE"


# ----------------------------------------------------------------------------------- calendar, constants, registry
def test_default_cutoff_is_the_last_trading_day_of_the_latest_ended_month():
    wk = lambda d: d.weekday() < 5       # noqa: E731
    assert G.default_cutoff(dt.date(2026, 10, 5), wk) == dt.date(2026, 9, 30)
    assert G.default_cutoff(dt.date(2026, 11, 2), wk) == dt.date(2026, 10, 30)          # 10-31 is a Saturday
    assert G.default_cutoff(dt.date(2026, 10, 31), wk) == dt.date(2026, 9, 30)          # the month has not ended before today
    assert G.default_cutoff(dt.date(2026, 11, 30)) == dt.date(2026, 10, 30)             # the real calendar too


def test_constants_match_prereg():
    assert G.prereg_constants() == G.constants_dict()
    assert len(G.LEG_KEYS) == 13 and len(set(G.LEG_KEYS)) == 13
    assert len(G.prereg_sha256()) == 64


def test_prereg_names_each_leg_and_its_decision_points():
    s = open(G.PREREG_PATH, encoding="utf-8").read()
    for k in G.LEG_KEYS:
        assert f"| {k} |" in s, k
    for needle in ("DRY RUN - NOT THE BINDING READ", "2026-10-30", "within **$0.01**", "99%", "95%"):
        assert needle in s


def test_registry_agrees_with_the_paper_pipeline_and_the_book_job():
    from api import book_shadow as bs
    from api import paper
    legs = {l["key"]: l for l in paper.PAPER_LEGS}
    assert paper.PAPER_START == G.PAPER_START
    for k in G.LEG_KEYS:
        assert k in legs and k in paper.LEG_LIVE_FROM, k
        assert legs[k]["instrument"] in G.BAND_PTS
    by_strategy = {l["strategy"]: l for l in bs.BOOK463_LEGS}
    for k in ("ORB", "ENGUQ_335", "TTM_299_SSOF2", "NOISE_422"):
        assert G.PINNED[k] == by_strategy[legs[k]["strategy"]]["source"], k           # the pinned source IS the book job's
    src = open(os.path.join(os.path.dirname(paper.__file__), "paper.py"), encoding="utf-8").read()
    book = eval(re.search(r"^    _BOOK = (\{[^}]*\})", src, re.M).group(1))
    shadow = eval(re.search(r"^    _BOOK_SHADOW = (\{[^}]*\})", src, re.M).group(1))
    assert G.LINES["book"] == book and G.LINES["book_shadow"] == shadow and G.LINES["book_shadow_vt"] == book
    for k, spec in bs.SUM_SHADOWS.items():
        if k in G.LINES:             # a line added to SUM_SHADOWS later is flagged at run time (a NOTE), not by a red build
            assert G.LINES[k] == spec["weights"] and G.LINE_FROM[k] == spec["from"]
    assert set(G.LINES) == set(G.SUM_LINES) | {"book_shadow_vt"}
    assert G.VT_FIRST_DAY == "2026-09-30" and G.EXITDAY_CUTOVER == "2026-10-02"


def test_an_unregistered_line_in_the_reports_is_noted_not_skipped():
    rows, reports, cold, vt = _good_world()
    day = sorted(reports)[0]
    reports[day]["book_shadow_future"] = {"pnl_usd": 1.0, "weights": {"ORB": 1.0}}
    res = _run(rows, reports, cold, vt=vt)
    assert any("book_shadow_future" in n and "NOT checked" in n for n in res["notes"])
    assert "book_shadow_future" in G.render(res)


def test_config_drift_note_names_the_enguq_cost_difference():
    paper_legs = [{"key": "ENGUQ_335", "strategy": "S.py", "instrument": "NQ", "timeframe": "1m", "session": "eth",
                   "cost_pts": 0.533, "mult": 20.0, "params": {"a": 1}}]
    book = [{"strategy": "S.py", "instrument": "NQ", "timeframe": "1m", "session": "eth", "cost_pts": 0.783, "mult": 20, "params": {"a": 1}}]
    notes = G.config_drift_notes(paper_legs, book)
    assert len(notes) == 1 and "cost_pts: paper 0.533 vs registered 0.783" in notes[0]
    book[0]["cost_pts"] = 0.533
    assert G.config_drift_notes(paper_legs, book) == []
