"""tools/run_trades_series.py - the per-run WF OOS trade list + daily series (board 131 / 132, 11-22).

Pins, with no Firestore and no market data: the New York session day (ETH 18:00 roll), the zero-filled daily
series, the levels -> initial-risk alignment (warm-trimmed tails), the to-the-dollar chain verify, and the
1 MiB chunking of the stored doc."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import run_trades_series as R  # noqa: E402


def test_session_day_rth_is_calendar():
    assert R.session_day("2024-03-05 15:55:00-05:00") == "2024-03-05"


def test_session_day_eth_rolls_at_18_et():
    assert R.session_day("2024-03-05 17:59:00-05:00", eth=True) == "2024-03-05"
    assert R.session_day("2024-03-05 18:00:00-05:00", eth=True) == "2024-03-06"
    # a Friday evening bar belongs to Monday's session
    assert R.session_day("2024-03-08 18:30:00-05:00", eth=True) == "2024-03-11"


def test_session_day_utc_input_converted():
    # 2024-07-01 22:30 UTC = 18:30 EDT -> next session on ETH, same calendar day on RTH
    assert R.session_day("2024-07-01 22:30:00+00:00", eth=True) == "2024-07-02"
    assert R.session_day("2024-07-01 22:30:00+00:00", eth=False) == "2024-07-01"


def test_daily_zero_fills_every_weekday():
    d = R.daily_from_trades(["2024-01-03", "2024-01-03", "2024-01-08"], [100.0, -40.0, 5.5],
                            "2024-01-02", "2024-01-09")
    assert d["d"] == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    assert d["p"] == [0.0, 60.0, 0.0, 0.0, 5.5, 0.0]
    assert d["n"] == [0, 2, 0, 0, 1, 0]


def test_daily_keeps_a_weekend_exit_day():
    d = R.daily_from_trades(["2024-01-06"], [10.0], "2024-01-05", "2024-01-08")
    assert "2024-01-06" in d["d"] and d["p"][d["d"].index("2024-01-06")] == 10.0


def test_risk_from_levels_exact_and_entry_minus_stop():
    lv = [{"entry_bar": 3, "risk": 12.5}, {"entry_bar": 9, "entry": 100.0, "stop": 104.0}]
    assert R.risk_from_levels(lv, 2, [3, 9]) == [12.5, 4.0]


def test_risk_from_levels_warm_tail_alignment():
    # a warm replay trimmed the first trade; levels still hold all three rows (warm-frame bars)
    lv = [{"entry_bar": 1, "risk": 9.0}, {"entry_bar": 50, "risk": 7.0}, {"entry_bar": 58, "risk": 5.0}]
    assert R.risk_from_levels(lv, 2, [0, 8]) == [7.0, 5.0]
    # gaps disagree -> refuse rather than mis-assign
    assert R.risk_from_levels(lv, 2, [0, 9]) is None


def test_risk_from_levels_short_or_missing():
    assert R.risk_from_levels(None, 2) is None
    assert R.risk_from_levels([{"risk": 1.0}], 2) is None
    assert R.risk_from_levels([{"entry_bar": 0, "risk": 0.0}], 1) == [None]


def _m(f, net, saved, ok=True, trades=3):
    return {"fold": f, "ok": ok, "oos_pnl": net, "oos_trades": trades, "reason": None if ok else "x",
            "saved": {"trades": trades, "net": saved}}


def test_verify_chain_to_the_dollar():
    ok, info = R.verify_chain([_m(1, 10.0, 10.0), _m(2, -2.5, -2.5)], 20.0, 7.5)
    assert ok and info["d_usd"] == 0.0 and info["replay_usd"] == 150.0
    ok, info = R.verify_chain([_m(1, 10.0, 10.0), _m(2, -2.5, -2.56)], 20.0)
    assert not ok and "chain total off" in info["why"]          # $1.20 > $1


def test_verify_chain_refuses_a_fold_miss_and_wf_net():
    ok, info = R.verify_chain([_m(1, 10.0, 10.0), _m(2, 3.0, 3.0, ok=False)], 20.0)
    assert not ok and "fold 2" in info["why"]
    ok, info = R.verify_chain([_m(1, 10.0, 10.0)], 20.0, 12.0)
    assert not ok and "wf_oos.net" in info["why"]


def _payload(n):
    tr = [{"e": 1700000000 + i, "x": 1700000300 + i, "s": 1, "p": 1.25, "z": 1, "r": 10.0, "f": 1} for i in range(n)]
    daily = {"d": ["2024-01-02"], "p": [0.0], "n": [0]}
    return R.series_payload(1, {"strategy": "S.py", "instrument": "NQ", "timeframe": "5m", "cost_pts": 0.5},
                            20.0, tr, daily, {"d_usd": 0.0}, "replay", None, "cold", "levels")


def test_payload_columnar_and_single_doc_when_small():
    p = _payload(5)
    assert p["n_trades"] == 5 and p["risk_n"] == 5 and p["risk_src"] == "levels"
    assert set(p["trades"]) == {"e", "x", "s", "p", "z", "r", "f"} and len(p["trades"]["p"]) == 5
    docs = R.chunk_payload(p)
    assert [d for d, _ in docs] == ["wf"] and docs[0][1]["t_chunks"] == 0


def test_chunking_splits_trades_under_budget_and_round_trips():
    p = _payload(3000)
    docs = R.chunk_payload(p, budget=40_000)
    assert docs[0][0] == "wf" and "trades" not in docs[0][1] and docs[0][1]["t_chunks"] == len(docs) - 1 >= 2
    for _, body in docs:
        assert len(json.dumps(body, separators=(",", ":"), default=str)) <= 40_000
    back = []
    for _, body in docs[1:]:
        back += body["trades"]["e"]
    assert back == p["trades"]["e"]
