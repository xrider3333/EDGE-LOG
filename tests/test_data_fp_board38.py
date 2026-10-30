"""C5 data fingerprint + board 38 fold-bound re-read guard."""
import json

import numpy as np
import pandas as pd
import pytest

from augur_engine import fold_anchor as FA
from tools import backfill_wf_oos as B


def _arrays(n=200, start="2024-01-02 14:30", bump=0.0):
    idx = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    c = np.linspace(100, 110, n) + bump
    return {"index": idx, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": np.ones(n)}


def test_fp_shape_size_and_stability(monkeypatch):
    monkeypatch.delenv("AUGUR_DATA_FP", raising=False)
    a = _arrays()
    fp = FA.data_fp(a, {"filename": "NQ_5m.csv"})
    assert set(fp) == {"v", "master", "bars", "first_ts", "last_ts", "hash"}
    assert fp["master"] == "NQ_5m.csv" and fp["bars"] == 200
    assert len(json.dumps(fp)) < 1024
    assert FA.data_fp(_arrays(), {"filename": "NQ_5m.csv"}) == fp          # stable
    assert FA.data_fp(_arrays(bump=0.25), {"filename": "x"})["hash"] != fp["hash"]
    assert FA.data_fp(_arrays(n=201), None)["hash"] != fp["hash"]


@pytest.mark.parametrize("val", ["0", "off", "false"])
def test_kill_switch(monkeypatch, val):
    monkeypatch.setenv("AUGUR_DATA_FP", val)
    assert FA.data_fp(_arrays()) is None


def _plan(rows, expect_n, fp=None):
    folds, n, _ = B.fold_bounds_from_rows(rows)
    return {"folds": folds, "expect_n": expect_n if expect_n is not None else n, "run_id": 491,
            "date_from": "a", "date_to": "b", "data_fp": fp}


def _rows(ts_index=None):
    rows = []
    for f, (s, e) in enumerate([(100, 150), (150, 200)], 1):
        r = {"fold": f, "train_bars": 100, "test_bars": e - s, "oos_pnl": 0, "oos_trades": 0, "oos_pf": 0,
             "test_start": s, "test_end": e}
        if ts_index is not None:
            r["test_start_ts"] = str(ts_index[s]); r["test_end_ts"] = str(ts_index[e - 1])
        rows.append(r)
    return rows


def test_rereader_prefers_timestamps_after_a_fill():
    old = _arrays(200)
    rows = _rows(old["index"])
    # a fill: 40 bars inserted before the first bound -> indices shift, timestamps do not
    new_idx = pd.date_range("2024-01-01 14:30", periods=40, freq="5min", tz="UTC").append(old["index"])
    out = B.resolve_fold_bounds(_plan(rows, 200), new_idx, len(new_idx))
    assert [(f["te_s"], f["te_e"]) for f in out] == [(140, 190), (190, 240)]


def test_indices_only_and_bar_count_changed_refuses_one_line():
    idx = _arrays(240)["index"]
    with pytest.raises(B.ReplaySkip) as e:
        B.resolve_fold_bounds(_plan(_rows(), 200), idx, 240)
    assert str(e.value).startswith("FOLD BOUNDS UNSAFE: run #491 stored bar indices only and the data "
                                   "changed since (bars 200 -> 240); not re-reading")


def test_indices_only_fingerprint_differs_refuses_even_at_same_count():
    a = _arrays(200)
    fp = dict(FA.data_fp(a), date_from="a", date_to="b")
    plan = dict(_plan(_rows(), 200, fp), today_fp=FA.data_fp(_arrays(200, bump=1.0)))
    with pytest.raises(B.ReplaySkip, match="FOLD BOUNDS UNSAFE"):
        B.resolve_fold_bounds(plan, a["index"], 200)
    plan["today_fp"] = FA.data_fp(a)
    assert B.resolve_fold_bounds(plan, a["index"], 200) == plan["folds"]


def test_fold_bounds_check_helper():
    assert FA.fold_bounds_check({"test_start_ts": "x", "test_end_ts": "y", "test_start": 1})[0] == "ts"
    assert FA.fold_bounds_check({"test_start": 1, "test_end": 5}, {"bars": 10}, today_bars=10)[0] == "idx"
    with pytest.raises(FA.BoundsDrift, match=r"run #7 stored bar indices only .*bars 10 -> 12"):
        FA.fold_bounds_check({"test_start": 1, "test_end": 5}, {"bars": 10}, today_bars=12, run_label=7)


def test_runner_data_fp_of(monkeypatch):
    import augur_engine.data as _data
    from api import runner as R
    a = _arrays()
    monkeypatch.setattr(_data, "load_master_arrays", lambda m, **k: a)
    monkeypatch.delenv("AUGUR_DATA_FP", raising=False)
    fp = R.FirestoreQueue._data_fp_of(None, {"date_from": "2024-01-02"}, {"filename": "NQ.csv"})
    assert fp["bars"] == 200 and fp["date_from"] == "2024-01-02" and len(json.dumps(fp)) < 1024
    assert R.FirestoreQueue._data_fp_of(None, {"type": "book"}, {"filename": "NQ.csv"}) is None
    monkeypatch.setenv("AUGUR_DATA_FP", "0")
    assert R.FirestoreQueue._data_fp_of(None, {}, {"filename": "NQ.csv"}) is None
