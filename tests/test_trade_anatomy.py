"""
Fast synthetic-data tests for tools/trade_anatomy.py:
  1. causality: no feature at decision bar i depends on bars >= i+1 (entry_bar).
  2. discovery/holdout split: excludes lockbox, respects the 60% calendar boundary.
  3. a planted single-condition skip rule is recovered by the rule search.
  4. the with-direction path features (path_with{12,24,60}_atr) flip sign for shorts.
  5. a rule that raises average-net-per-trade but lowers total net $ is never labelled
     "carries" -- it must come out "regime artifact" or "no".

Run: python -m pytest tests/test_trade_anatomy.py -q
"""
import os
import sys
import datetime
import importlib.util as _ilu

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_ta():
    fp = os.path.join(ROOT, "tools", "trade_anatomy.py")
    spec = _ilu.spec_from_file_location("trade_anatomy_test", fp)
    m = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def ta():
    return _load_ta()


def _make_synthetic_bars(n_days=90, bars_per_day=30, seed=7):
    """RTH-like synthetic 5-minute bars: n_days sessions of bars_per_day bars each,
    tz-aware US/Eastern, with an open/high/low/close/volume + _dt/_end/day_id shape
    matching what feature_board.load() produces."""
    rng = np.random.default_rng(seed)
    rows = []
    day_id = 0
    price = 1000.0
    for d in range(n_days):
        date = pd.Timestamp("2015-01-05") + pd.Timedelta(days=d * 7 // 5)  # roughly weekdays
        sess_start = pd.Timestamp(date.date()).tz_localize("US/Eastern") + pd.Timedelta(hours=9, minutes=30)
        for b in range(bars_per_day):
            t = sess_start + pd.Timedelta(minutes=5 * b)
            ret = rng.normal(0, 1.0)
            o = price
            c = price + ret
            h = max(o, c) + abs(rng.normal(0, 0.5))
            l = min(o, c) - abs(rng.normal(0, 0.5))
            vol = float(rng.integers(100, 1000))
            rows.append((t, o, h, l, c, vol, day_id))
            price = c
        day_id += 1
    df = pd.DataFrame(rows, columns=["_dt", "open", "high", "low", "close", "volume", "day_id"])
    df["_end"] = df["_dt"] + pd.Timedelta(minutes=5)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 1. causality
# ─────────────────────────────────────────────────────────────────────────────

def test_causality_no_lookahead(ta):
    df = _make_synthetic_bars(n_days=90, bars_per_day=30)
    n = len(df)
    entry_bar = 1900          # well past warmup, mid-session (not bar-of-day 0)
    assert entry_bar < n - 5

    X1, entry_date1, valid1 = ta.build_feature_matrix(df, [entry_bar], tf_min=5)
    assert bool(valid1[0]), "decision bar should have enough history to be valid"

    df2 = df.copy()
    rng = np.random.default_rng(99)
    tail = df2.index >= entry_bar          # entry bar and everything after
    n_tail = int(tail.sum())
    df2.loc[tail, "open"] = rng.normal(2000, 50, n_tail)
    df2.loc[tail, "close"] = rng.normal(2000, 50, n_tail)
    df2.loc[tail, "high"] = df2.loc[tail, ["open", "close"]].max(axis=1) + 5
    df2.loc[tail, "low"] = df2.loc[tail, ["open", "close"]].min(axis=1) - 5
    df2.loc[tail, "volume"] = rng.integers(1, 50, n_tail).astype(float)

    X2, entry_date2, valid2 = ta.build_feature_matrix(df2, [entry_bar], tf_min=5)

    assert entry_date1[0] == entry_date2[0]
    assert list(X1.columns) == ta.FEATURE_NAMES, "build_feature_matrix must emit every FEATURE_META column"
    row1 = X1.iloc[0].to_numpy(float)
    row2 = X2.iloc[0].to_numpy(float)
    bad = [c for c, a, b in zip(ta.FEATURE_NAMES, row1, row2)
          if not (np.isnan(a) and np.isnan(b)) and not np.isclose(a, b, equal_nan=True)]
    assert not bad, f"features that leaked future information: {bad}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. discovery/holdout split
# ─────────────────────────────────────────────────────────────────────────────

def test_split_sets_excludes_lockbox_and_respects_boundary(ta):
    date_from = datetime.date(2020, 1, 1)
    lockbox_from = datetime.date(2021, 1, 1)   # 366-day pre-lockbox span
    date_to = datetime.date(2021, 6, 1)

    all_days = pd.date_range(date_from, date_to, freq="D").date
    labels, boundary = ta.split_sets(all_days, date_from, lockbox_from)

    span_days = (lockbox_from - date_from).days
    expected_boundary = date_from + datetime.timedelta(days=int(round(span_days * 0.6)))
    assert boundary == expected_boundary

    labels = np.asarray(labels)
    all_days = np.asarray(all_days)

    # every date >= lockbox_from is labeled lockbox, and ONLY those
    assert set(labels[all_days >= lockbox_from]) == {"lockbox"}
    assert "lockbox" not in set(labels[all_days < lockbox_from])

    # discovery = [date_from, boundary), holdout = [boundary, lockbox_from)
    pre = all_days < lockbox_from
    assert set(labels[pre & (all_days < boundary)]) == {"discovery"}
    assert set(labels[pre & (all_days >= boundary)]) == {"holdout"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. a planted skip rule is recovered
# ─────────────────────────────────────────────────────────────────────────────

def test_planted_skip_rule_is_recovered(ta):
    rng = np.random.default_rng(11)
    n = 600
    f_signal = rng.uniform(0.0, 1.0, n)
    noise1 = rng.normal(size=n)
    noise2 = rng.normal(size=n)

    bad = f_signal > 0.7                                  # planted: high f_signal -> losers
    usd = np.where(bad, rng.normal(-200.0, 30.0, n), rng.normal(50.0, 30.0, n))

    Xd = pd.DataFrame({"f_signal": f_signal, "noise1": noise1, "noise2": noise2})
    entry_date = pd.bdate_range("2018-01-01", periods=n).date

    candidates = ta.mine_skip_rules(Xd, usd, entry_date, min_keep_frac=0.6)
    assert candidates, "no candidate rules were generated"

    best = max(candidates, key=lambda d: d["net_per_trade"])
    assert best["feature"] == "f_signal"
    assert best["direction"] == "skip_above"
    assert 0.6 <= best["threshold"] <= 0.8

    baseline = float(np.mean(usd))
    assert best["net_per_trade"] > baseline + 50.0        # materially better than doing nothing


# ─────────────────────────────────────────────────────────────────────────────
# 4. with-direction path features flip sign for shorts
# ─────────────────────────────────────────────────────────────────────────────

def test_with_direction_feature_flips_sign_for_shorts(ta):
    df = _make_synthetic_bars(n_days=90, bars_per_day=30)
    entry_bar = 1900

    X_long, _, valid_long = ta.build_feature_matrix(df, [entry_bar], tf_min=5, side=[1])
    X_short, _, valid_short = ta.build_feature_matrix(df, [entry_bar], tf_min=5, side=[-1])
    assert bool(valid_long[0]) and bool(valid_short[0])

    for col in ("path_with12_atr", "path_with24_atr", "path_with60_atr"):
        v_long = float(X_long[col].iloc[0])
        v_short = float(X_short[col].iloc[0])
        assert not np.isnan(v_long) and not np.isnan(v_short)
        assert v_long != 0.0, f"{col} should be non-zero on this synthetic path"
        assert np.isclose(v_long, -v_short), f"{col} did not flip sign for a short (long={v_long}, short={v_short})"

    # default (no side passed) matches an explicit long -- the causality test above relies on this
    X_default, _, _ = ta.build_feature_matrix(df, [entry_bar], tf_min=5)
    assert np.isclose(float(X_default["path_with24_atr"].iloc[0]), float(X_long["path_with24_atr"].iloc[0]))


# ─────────────────────────────────────────────────────────────────────────────
# 5. a rule that raises the per-trade average but lowers total money is never "carries"
# ─────────────────────────────────────────────────────────────────────────────

def test_regime_artifact_never_labeled_carries_when_total_money_falls(ta):
    # 20 trades: bottom half (x < 10) skipped by the rule are SMALL WINNERS (+5 each);
    # top half (x >= 10) kept are BIGGER WINNERS (+50 each). Dropping the skipped half
    # raises the average per trade (50 > base avg 27.5) but total money falls (500 < 550)
    # because those +5 trades' total ($50) is thrown away entirely. Same shape in both
    # windows so total money falls in discovery AND holdout.
    n = 20
    x = np.arange(n, dtype=float)
    usd = np.where(x < 10, 5.0, 50.0)
    entry_date = pd.bdate_range("2019-01-01", periods=n).date
    Xset = pd.DataFrame({"path_with24_atr": x})

    rule = dict(feature="path_with24_atr", direction="skip_below", pctile=50.0, threshold=9.5)

    base_avg = float(np.mean(usd))
    kept_mask = ta.rule_mask(Xset, rule)
    kept_avg = float(np.mean(usd[kept_mask]))
    assert kept_avg > base_avg, "test setup should raise the per-trade average under the rule"
    assert float(usd[kept_mask].sum()) < float(usd.sum()), "test setup should lower total money under the rule"

    row_d = ta.money_ledger_row(rule, Xset, usd, entry_date, years_span=1.0)
    row_h = ta.money_ledger_row(rule, Xset, usd, entry_date, years_span=1.0)
    assert row_d["pct_change"] < 0 and row_h["pct_change"] < 0

    verdict = ta.classify_verdict(row_d, row_h)
    assert verdict in ("regime artifact", "no")
    assert verdict != "carries"


# ─────────────────────────────────────────────────────────────────────────────
# 6. leg_from_run field mapping — no network, drives the pure
#    _leg_dict_from_run_doc(rid, d) core directly on a fake run doc.
# ─────────────────────────────────────────────────────────────────────────────

def test_leg_from_run_field_mapping_full_doc(ta):
    fake_doc = {
        "strategy": "ORB_3_6_R6.py", "instrument": "NQ", "timeframe": "5m",
        "session": None, "data_source": "db_noadj_rth", "source_name": "NQ 5m RTH - no-adj",
        "cost_pts": 0.533, "multiplier": 20.0, "date_from": "2010-06-07", "date_to": "2026-08-13",
        "lockbox_months": None, "best_params": {"or_bars": 2, "target_R": 5.0},
        "gate_validate": {
            "lockbox_from": "2025-08-13",
            "ungated_full": {"num_trades": 2299, "total_pnl": 19857.51, "profit_factor": 1.37},
            "ungated_pre": {"num_trades": 2130, "total_pnl": 15000.0, "profit_factor": 1.3},
        },
    }
    leg = ta._leg_dict_from_run_doc(314, fake_doc)
    assert leg["key"] == "RUN_314"
    assert leg["family"] == "ORB"
    assert leg["file"] == "ORB_3_6_R6.py"
    assert leg["label"] == "#314 ORB_3_6_R6.py"
    assert leg["run"] == 314

    cfg = leg["_resolved_cfg"]
    assert cfg["instrument"] == "NQ" and cfg["timeframe"] == "5m"
    # session absent on the doc -> inferred from data_source ("db_noadj_rth" -> RTH)
    assert cfg["session"] == "RTH"
    assert cfg["cost_pts"] == 0.533
    assert cfg["mult"] == 20.0
    assert cfg["date_from"] == "2010-06-07" and cfg["date_to"] == "2026-08-13"
    assert cfg["lockbox_from"] == "2025-08-13"
    assert cfg["best_params"] == {"or_bars": 2, "target_R": 5.0}
    assert cfg["parity_source"] == "run#314"
    assert cfg["parity_expected"]["full"] == dict(n=2299, net_pts=19857.51, pf=1.37)
    assert cfg["parity_expected"]["pre"] == dict(n=2130, net_pts=15000.0, pf=1.3)
    assert "lockbox" not in cfg["parity_expected"]


def test_leg_from_run_infers_eth_and_falls_back_lockbox_months(ta):
    fake_doc = {
        "strategy": "ENGUQ_1M_ETH_ER_1_0.py", "instrument": "NQ", "timeframe": "1m",
        "data_source": "db_noadj_eth", "cost_pts": 0.533, "mult": 20.0,
        "date_from": "2010-06-07", "date_to": "2026-06-30", "best_params": {"tl_len": 206},
        "gate_validate": {},   # no lockbox_from on this doc
    }
    leg = ta._leg_dict_from_run_doc(309, fake_doc)
    assert leg["family"] == "ENGUQ"
    cfg = leg["_resolved_cfg"]
    assert cfg["session"] == "ETH"
    assert cfg["mult"] == 20.0            # falls back to "mult" when "multiplier" is absent
    assert cfg["lockbox_from"] is None
    assert cfg["lockbox_months"] == 12    # missing on the doc -> assumed default
    assert cfg["parity_expected"] == {}   # no ungated_* blocks on this doc


def test_leg_from_run_missing_strategy_field_refuses(ta):
    with pytest.raises(SystemExit):
        ta._leg_dict_from_run_doc(999, {"instrument": "NQ"})


# ─────────────────────────────────────────────────────────────────────────────
# 7. summary JSON round-trips through --compare and the replication score
#    counts correctly; a feature confirmed on 3 runs is CONSISTENT, a 4th run
#    with a holdout sign flip does not block those 3 and is not itself counted.
# ─────────────────────────────────────────────────────────────────────────────

def _write_fake_summary(ta, out_dir, key, lift_r, lift_q, hold_lift, feature="path_r1",
                        extra_winner=(), ledger_rows=()):
    """Writes <key>_summary.json directly via write_summary_json, on hand-built inputs
    (no leg replay, no bar data) -- exercises exactly the function run_leg() calls."""
    winner_rows = [dict(feature=feature, group=ta.FEATURE_GROUP.get(feature, "path"),
                        mean_top_decile=1.0, mean_bottom_decile=-1.0, mean_all=0.0,
                        std_diff=0.4, lift=lift_r, lift_p=0.001 if lift_q is not None else None,
                        lift_q=lift_q)] + list(extra_winner)
    tercile_rows = [dict(feature=feature, threshold_top=1.0, threshold_bot=-1.0,
                         disc_lift=lift_r, hold_lift=hold_lift,
                         same_sign=(None if lift_r is None or hold_lift is None
                                    else (lift_r > 0) == (hold_lift > 0)))]
    leg_info = dict(key=key, label=f"leg {key}", family="TEST", file="TEST_1_0.py", run=None)
    meta = dict(cfg=dict(instrument="NQ", timeframe="5m", session="RTH",
                        date_from="2020-01-01", date_to="2021-01-01"),
               boundary=datetime.date(2020, 7, 1), lockbox_from="2021-01-01",
               n_discovery=100, n_holdout=50, n_lockbox_excluded=10, r_unit=200.0,
               parity=dict(source="test", got_n=150, got_net=1000.0, expected_n=None,
                          expected_net=None, ok=None))
    return ta.write_summary_json(key, leg_info, meta, winner_rows, list(ledger_rows), tercile_rows, out_dir)


def test_summary_json_roundtrip_and_replication_score(ta, tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "DOCS_ROOT", str(tmp_path))
    keys = ["A", "B", "C", "D"]
    # A, B, C: positive discovery lift, q < 0.10, holdout agrees (positive) -> should score.
    # D: also positive discovery lift with q < 0.10, but holdout FLIPS negative -> must not score,
    #    and must not block A/B/C.
    specs = {"A": (0.50, 0.01, 0.40), "B": (0.60, 0.02, 0.30),
            "C": (0.55, 0.03, 0.35), "D": (0.40, 0.02, -0.20)}
    for k, (lift_r, lift_q, hold_lift) in specs.items():
        fp = _write_fake_summary(ta, str(tmp_path), k, lift_r, lift_q, hold_lift)
        assert os.path.exists(fp)

    # round-trip: what load_summary reads back must be usable by build_replication_table
    summaries = {k: ta.load_summary(k) for k in keys}
    for k in keys:
        assert summaries[k]["winner_anatomy"][0]["feature"] == "path_r1"
        assert summaries[k]["tercile_lift_holdout"][0]["hold_lift"] == round(specs[k][2], 4)

    rep_rows = ta.build_replication_table(summaries, keys)
    row = next(r for r in rep_rows if r["feature"] == "path_r1")
    assert row["rep_score"] == 3, "A, B, C should score (sig + holdout agree); D should not"
    assert row["per_run"]["D"]["sig"] is True and row["per_run"]["D"]["agree"] is False

    consistent = ta.consistent_conditions(rep_rows, keys, min_runs=3)
    hit = [c for c in consistent if c["feature"] == "path_r1"]
    assert len(hit) == 1
    assert hit[0]["sign"] == 1
    assert sorted(hit[0]["runs"]) == ["A", "B", "C"]
    assert "D" not in hit[0]["runs"], "the holdout sign flip on D must not be listed as consistent"


def test_ledger_rollup_robust_flag(ta, tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "DOCS_ROOT", str(tmp_path))
    rule = dict(feature="ind_rsi14_bar", direction="skip_below", threshold=30.0, pctile=20, kind="skip")

    def ledger_row(verdict, thr):
        r = dict(rule)
        r["threshold"] = thr
        return dict(rule=r,
                   disc=dict(kept_pct=70.0, net_rule=1000.0, net_base=800.0, pct_change=25.0,
                            pf=1.5, dd=500.0, mar=2.0, base_mar=1.6, yrs_helped="2/3",
                            tilt_net=1200.0, tilt_dd=600.0, tilt_mar=2.0),
                   hold=dict(kept_pct=68.0, net_rule=400.0, net_base=300.0, pct_change=33.0,
                            pf=1.4, dd=200.0, mar=2.0, base_mar=1.5, yrs_helped="1/2",
                            tilt_net=450.0, tilt_dd=220.0, tilt_mar=2.0),
                   verdict=verdict)

    keys = ["A", "B", "C", "D"]
    verdicts = {"A": "carries", "B": "carries", "C": "carries as tilt", "D": "regime artifact"}
    for k in keys:
        _write_fake_summary(ta, str(tmp_path), k, lift_r=None, lift_q=None, hold_lift=None,
                            feature="unrelated", ledger_rows=[ledger_row(verdicts[k], thr=29.0 + hash(k) % 5)])

    summaries = {k: ta.load_summary(k) for k in keys}
    rollup = ta.ledger_rollup(summaries, keys)
    assert len(rollup) == 1
    row = rollup[0]
    assert row["n_carries"] == 2 and row["n_tilt"] == 1 and row["n_regime"] == 1
    assert row["robust"] is False, "one regime-artifact run must veto ROBUST even with 3 carrying runs"

    # drop D (the regime artifact) -> 3 runs carry (either form), 0 regime artifacts -> ROBUST
    rollup2 = ta.ledger_rollup({k: summaries[k] for k in ("A", "B", "C")}, ["A", "B", "C"])
    assert rollup2[0]["robust"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 8. cal_ calendar day table: OPEX / month-end / month-start / FOMC / holiday-
#    adjacent flags on a small hand-built trading-day calendar with known answers.
# ─────────────────────────────────────────────────────────────────────────────

def test_calendar_opex_month_end_and_fomc_flags(ta, tmp_path):
    # day_id 0=Fri 2021-01-15 (the 3rd Friday of Jan 2021 -> opex day/week),
    #        1=Wed 2021-01-27 (planted FOMC day),
    #        2=Fri 2021-01-29 (last trading day of Jan in this synthetic calendar
    #          -> month-end-2; also 2 weekdays after day 1, so both 1 and 2 are
    #          holiday-adjacent),
    #        3=Mon 2021-02-01 (first trading day of Feb -> month-start-2).
    dates = [datetime.date(2021, 1, 15), datetime.date(2021, 1, 27),
            datetime.date(2021, 1, 29), datetime.date(2021, 2, 1)]
    rows = []
    for i, d in enumerate(dates):
        t = pd.Timestamp(d).tz_localize("US/Eastern") + pd.Timedelta(hours=9, minutes=30)
        rows.append((t, 100.0, 101.0, 99.0, 100.5, 500.0, i))
    df = pd.DataFrame(rows, columns=["_dt", "open", "high", "low", "close", "volume", "day_id"])
    df["_end"] = df["_dt"] + pd.Timedelta(minutes=5)

    fomc_fp = tmp_path / "fomc.csv"
    fomc_fp.write_text("date,note\n2021-01-27,decision day\n")

    cal = ta.build_calendar_day_table(df, fomc_path=str(fomc_fp))

    assert bool(cal.loc[0, "cal_is_opex_day"]), "Jan 15 2021 is the 3rd Friday of the month"
    assert bool(cal.loc[0, "cal_is_opex_week"])
    assert not bool(cal.loc[1, "cal_is_opex_day"])
    assert not bool(cal.loc[3, "cal_is_opex_week"])

    assert bool(cal.loc[2, "cal_is_month_end_2"]), "Jan 29 is the last trading day of Jan in this calendar"
    assert not bool(cal.loc[0, "cal_is_month_end_2"])
    assert bool(cal.loc[3, "cal_is_month_start_2"]), "Feb 1 is the first trading day of Feb"
    assert not bool(cal.loc[2, "cal_is_month_start_2"])

    assert bool(cal.loc[1, "cal_is_fomc_day"])
    assert not bool(cal.loc[0, "cal_is_fomc_day"])
    assert bool(cal.loc[0, "cal_is_fomc_next_day"]), "day 0's next trading day (day 1) is the planted FOMC day"
    assert bool(cal.loc[2, "cal_is_fomc_prev_day"]), "day 2's previous trading day (day 1) was the FOMC day"
    assert not bool(cal.loc[1, "cal_is_fomc_prev_day"])

    # Jan 27 -> Jan 29 skips Jan 28 (a weekday) -- more than 1 weekday gap on both sides
    assert bool(cal.loc[1, "cal_is_holiday_adjacent"])
    assert bool(cal.loc[2, "cal_is_holiday_adjacent"])

    # dense calendar, isolated from the sparse one above, to also prove a NORMAL
    # next-business-day step (including over a plain weekend) is NOT flagged:
    # Tue 26 -> Wed 27 (FOMC, normal) -> Fri 29 (skips Thu 28, a real holiday) -> Mon Feb 1 (normal weekend).
    dense_dates = [datetime.date(2021, 1, 26), datetime.date(2021, 1, 27),
                  datetime.date(2021, 1, 29), datetime.date(2021, 2, 1)]
    rows2 = []
    for i, d in enumerate(dense_dates):
        t = pd.Timestamp(d).tz_localize("US/Eastern") + pd.Timedelta(hours=9, minutes=30)
        rows2.append((t, 100.0, 101.0, 99.0, 100.5, 500.0, i))
    df2 = pd.DataFrame(rows2, columns=["_dt", "open", "high", "low", "close", "volume", "day_id"])
    df2["_end"] = df2["_dt"] + pd.Timedelta(minutes=5)
    cal2 = ta.build_calendar_day_table(df2, fomc_path=str(fomc_fp))
    assert not bool(cal2.loc[0, "cal_is_holiday_adjacent"]), "Tue->Wed is a normal next-business-day step"
    assert bool(cal2.loc[1, "cal_is_holiday_adjacent"]), "Wed->Fri skips Thursday, a real holiday"
    assert bool(cal2.loc[2, "cal_is_holiday_adjacent"])
    assert not bool(cal2.loc[3, "cal_is_holiday_adjacent"]), "Fri->Mon is a normal weekend step"


# ─────────────────────────────────────────────────────────────────────────────
# 9. xm_ cross-market vs ES: relative-return math on synthetic ES bars, and
#    forward-fill-within-session-only (a full-day ES data hole must read as NaN,
#    never silently filled from the prior session's last ES value).
# ─────────────────────────────────────────────────────────────────────────────

def test_xm_relative_return_and_session_fill(ta, monkeypatch):
    df = _make_synthetic_bars(n_days=10, bars_per_day=30, seed=3)
    n = len(df)
    close = df["close"].to_numpy(float)
    es_close = close * 0.9 + 5.0                    # deterministic, so the relative return is exact
    es = pd.DataFrame({"_dt": df["_dt"], "open": es_close, "high": es_close + 0.3,
                       "low": es_close - 0.3, "close": es_close, "day_id": df["day_id"]})

    monkeypatch.setattr(ta.os.path, "exists", lambda p: True)
    monkeypatch.setattr(ta.FB, "load", lambda inst, tf, session, d0, d1: es)
    cfg = dict(instrument="NQ", timeframe="5m", session="RTH",
              date_from="2015-01-01", date_to="2020-01-01")

    out = ta.build_xm_arrays(df, tf_min=5, cfg=cfg)
    atr_bar = ta.calc_atr(df["high"].to_numpy(float), df["low"].to_numpy(float), close, 14)
    i = 100
    expected = ((close[i] - close[i - 12]) - (es_close[i] - es_close[i - 12])) / atr_bar[i]
    assert np.isclose(out["xm_relret_12b_atr"][i], expected)

    # black out ES for an entire middle session (day_id 1) -- a whole-day data hole
    es_holes = es.copy()
    hole_mask = (df["day_id"] == 1).to_numpy()
    es_holes.loc[hole_mask, ["open", "high", "low", "close"]] = np.nan
    monkeypatch.setattr(ta.FB, "load", lambda inst, tf, session, d0, d1: es_holes)

    out2 = ta.build_xm_arrays(df, tf_min=5, cfg=cfg)
    day1_bars = np.flatnonzero(hole_mask)
    assert np.isnan(out2["xm_es_rsi14"][day1_bars]).all(), (
        "an ES data hole spanning a whole session must read NaN, never forward-filled "
        "from the previous session's last value")

    # cfg=None / missing ES master -> all-NaN, never a crash
    empty = ta.build_xm_arrays(df, tf_min=5, cfg=None)
    for nm in ta.XM_NAMES:
        assert np.isnan(empty[nm]).all()
