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
    row1 = X1.iloc[0].to_numpy(float)
    row2 = X2.iloc[0].to_numpy(float)
    bad = [c for c, a, b in zip(X1.columns, row1, row2)
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
