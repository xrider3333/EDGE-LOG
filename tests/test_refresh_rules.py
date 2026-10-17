"""augur_engine/refresh_rules.py: what the runner's Yahoo refresh may change in a master (MANAGER #67/#68).

2026-10-14: the refresh merged a 7-day Yahoo pull with Yahoo winning every overlap, so every pass rewrote the
last week of the NQ no-adjust masters over NinjaTrader-spliced bars, relabelled every row's source and replaced
the registry provenance (deleting the 10-12 / 10-14 NT splice records). Pure functions, synthetic data.
"""
import json
import os

import pandas as pd

from augur_engine import refresh_rules as RR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _frame(times, px=100.0, naive=False):
    idx = pd.to_datetime(times, unit="s", utc=True)
    if naive:
        idx = idx.tz_localize(None)
    return pd.DataFrame({"Open": px, "High": px + 1, "Low": px - 1, "Close": px, "Volume": 10}, index=idx)


def _combine(frames, labels):
    """combine_ohlcv_frames' tagging and overlap rule: concat, '__src' per frame, later frames win."""
    tagged = []
    for f, lbl in zip(frames, labels):
        g = f.copy()
        g.index = pd.to_datetime(g.index, utc=True)
        g["__src"] = lbl
        tagged.append(g)
    m = pd.concat(tagged)
    return m[~m.index.duplicated(keep="last")].sort_index()


def test_only_no_adjust_masters_are_append_only():
    assert RR.append_only("db_noadj_rth") and RR.append_only("db_noadj_eth")
    assert RR.append_only("nt_noadj_eth")                       # MANAGER #74 C: an NT master never loses an overlap
    assert not any(RR.append_only(s) for s in ("tv", "merged", "yahoo", "db_adj_rth", "", None))


def test_a_pull_is_cut_to_the_bars_past_the_last_stored_one_naive_or_aware():
    held = _frame([1000, 1300, 1600])
    pull = _frame([1300, 1600, 1900, 2200], px=105.0)
    assert RR.past_last_bar(pull, held).index.tolist() == pull.index[2:].tolist()
    assert len(RR.past_last_bar(pull, _frame([1000, 1300, 1600], naive=True))) == 2   # naive read as UTC
    assert RR.past_last_bar(pull, held.iloc[:0]) is pull                               # empty master: all of it


def test_a_still_forming_bar_is_left_for_the_next_pass():
    """MANAGER #74 B. A 5m pull at 22:13 holds the 22:10 bar three minutes in; it is final 15 min after its end."""
    held = _frame([1000])
    pull = _frame([1300, 1600, 1900], px=103.0)
    cut = RR.past_last_bar(pull, held, bar_s=300, now=1900 + 300 + 899)
    assert cut.index.tolist() == pull.index[:2].tolist()
    assert RR.past_last_bar(pull, held, bar_s=300, now=1900 + 300 + 900) is pull
    assert len(RR.past_last_bar(pull, held.iloc[:0], bar_s=300, now=1300 + 300 + 900)) == 1   # empty master too
    assert RR.past_last_bar(pull, held, bar_s=None, now=0) is pull                           # unknown length: no cut


def test_bar_lengths_from_timeframe_labels():
    assert [RR.bar_seconds(t) for t in ("1m", "5m", "15m", "1h", " 5M ")] == [60, 300, 900, 3600, 300]
    assert [RR.bar_seconds(t) for t in ("1d", "daily", "", None, "m")] == [None] * 5


def test_an_append_only_merge_keeps_every_stored_bar_and_its_tag(tmp_path):
    """The 10-14 shape: NT-spliced bars inside Yahoo's 7-day window come through untouched and stay tagged."""
    p = tmp_path / "NOADJ_NQ_5m_RTH.csv"
    pd.DataFrame({"time": [1000, 1300, 1600], "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                  "volume": 10, "source": ["existing", "nt_hist_splice", "nt_hist_splice"]}).to_csv(p, index=False)
    held = _frame([1000, 1300, 1600])
    pull = RR.past_last_bar(_frame([1300, 1600, 1900], px=102.25), held)
    merged = RR.keep_source_tags(_combine([held, pull], ["existing", "yahoo"]), RR.stored_source_tags(str(p)))
    assert merged["Close"].tolist() == [100.0, 100.0, 100.0, 102.25]
    assert merged["__src"].tolist() == ["existing", "nt_hist_splice", "nt_hist_splice", "yahoo"]


def test_a_bar_the_pull_did_replace_keeps_the_pulls_label(tmp_path):
    """Masters that are not append-only (tv, merged) still take Yahoo over an overlap; their label must say so."""
    p = tmp_path / "tv_NQ_5m.csv"
    pd.DataFrame({"time": [1000, 1300], "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
                  "source": ["tv-drop", "tv-drop"]}).to_csv(p, index=False)
    merged = RR.keep_source_tags(_combine([_frame([1000, 1300]), _frame([1300, 1600], px=7.0)],
                                          ["existing", "yahoo"]), RR.stored_source_tags(str(p)))
    assert merged["__src"].tolist() == ["tv-drop", "yahoo", "yahoo"]


def test_a_master_without_a_source_column_is_left_as_labelled(tmp_path):
    p = tmp_path / "old.csv"
    pd.DataFrame({"time": [1000], "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}).to_csv(p, index=False)
    assert RR.stored_source_tags(str(p)) == {} and RR.stored_source_tags(str(tmp_path / "missing.csv")) == {}
    m = _combine([_frame([1000])], ["existing"])
    assert RR.keep_source_tags(m, {}) is m


def test_the_splice_and_repair_history_survives_a_rebuilt_provenance():
    old = json.dumps({"source": "db_noadj_rth", "built_at": "2026-10-14T09:00",
                      "splices": [{"date": "2020-02-28", "nt_sha256": "ab"}], "repairs": [{"date": "2026-06-30"}]})
    new = json.dumps({"source": "db_noadj_rth", "built_at": "2026-10-14T10:14", "total_rows": 5})
    out = json.loads(RR.carry_provenance(new, old))
    assert out["built_at"] == "2026-10-14T10:14" and out["total_rows"] == 5
    assert out["splices"] == [{"date": "2020-02-28", "nt_sha256": "ab"}] and out["repairs"] == [{"date": "2026-06-30"}]
    assert RR.carry_provenance(new, "") == new and RR.carry_provenance(new, "not json") == new


def test_the_runner_refresh_path_actually_applies_the_rules_before_it_saves():
    """optimizer.auto_refresh_masters is what api/augur_refresh.py runs every 240 min. Pins the wiring."""
    src = open(os.path.join(ROOT, "optimizer.py"), encoding="utf-8").read()
    body = src[src.index("def auto_refresh_masters"):]
    body = body[:body.index("\ndef ", 10)]
    assert "from augur_engine import refresh_rules" in src
    assert body.index("refresh_rules.append_only(src)") < body.index("combine_ohlcv_frames(frames")
    assert body.index("refresh_rules.past_last_bar(") < body.index("combine_ohlcv_frames(frames")
    assert "refresh_rules.past_last_bar(frames[_i], existing_df, refresh_rules.bar_seconds(tf))" in body
    assert body.index("refresh_rules.keep_source_tags(") < body.index("ok, _r = save_master_csv")
    assert "refresh_rules.carry_provenance(_build_provenance(" in body
