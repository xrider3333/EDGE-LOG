"""api/nt_drawdown_alert.py - the intraday drawdown ping, in the one plain phone format (2026-10-07).

Never touches the live bridge, the live latch file (C:\\EdgeLog\\dd_alert_state.json) or ntfy: _get is a stub,
STATE_PATH is under tmp_path and _notify is recorded.
"""
import pytest

from api import nt_drawdown_alert as D
from api import ntfy_push as N

PAPER, REAL = "DEMO7240108", "1810769"


@pytest.fixture
def dd(tmp_path, monkeypatch):
    w = {"risk": {"limits": {"max_daily_loss_usd": -12000}, "accounts": [
        {"account": PAPER, "realized_today": -945.76, "net_contracts": 0}]}, "pushes": []}
    monkeypatch.setattr(D, "STATE_PATH", str(tmp_path / "dd_alert_state.json"))
    monkeypatch.setattr(D, "_get", lambda path: w["risk"] if path == "/risk" else None)
    monkeypatch.setattr(D, "_notify", lambda msg, title, priority="high":
                        w["pushes"].append({"message": msg, "title": title, "priority": priority}))
    monkeypatch.setattr(D, "_now_et_date", lambda: "2026-10-07")

    def set_loss(account, real, net=0):
        for a in w["risk"]["accounts"]:
            if a["account"] == account:
                a["realized_today"], a["net_contracts"] = real, net
    w["set"] = set_loss
    return w


def test_first_breach_text_is_the_owners_example(dd):
    D.check()
    assert len(dd["pushes"]) == 1
    p = dd["pushes"][0]
    assert p["title"] == "Paper NT8: down $946 today"
    assert p["message"].split("\n") == ["Trading: not affected (flat).",
                                        "Alert line -$500; automatic stop at -$12,000 ($11,054 away).",
                                        "Do: nothing."]
    assert p["priority"] == "low" and not N.lint(p)
    assert "DEMO7240108" not in p["title"] + p["message"] and "realized" not in p["message"]


def test_one_push_per_breach_and_none_below_the_alert_line(dd):
    dd["set"](PAPER, -400)
    D.check()
    assert dd["pushes"] == []
    dd["set"](PAPER, -600)
    D.check()
    D.check()
    dd["set"](PAPER, -700)
    D.check()
    assert len(dd["pushes"]) == 1


def test_open_position_is_named_in_the_trading_line(dd):
    dd["set"](PAPER, -800, net=2)
    D.check()
    assert dd["pushes"][0]["message"].split("\n")[0] == "Trading: not affected (holding 2 contracts)."
    assert dd["pushes"][0]["priority"] == "low"


def test_high_priority_only_within_25_percent_of_the_automatic_stop(dd):
    dd["set"](PAPER, -8999)                                     # 3,001 of 12,000 away: more than 25% left
    D.check()
    assert [p["priority"] for p in dd["pushes"]] == ["low"]
    dd["set"](PAPER, -9000)                                     # exactly 25% left: the near-stop zone
    D.check()
    assert [p["priority"] for p in dd["pushes"]] == ["low", "high"]                      # worse: pushes again at once
    near = dd["pushes"][1]
    assert near["message"].split("\n")[0] == "Trading: AFFECTED - the automatic stop is close."
    assert "($3,000 away)" in near["message"] and near["message"].split("\n")[2] == "Do: check NinjaTrader now."
    assert not N.lint(near)
    dd["set"](PAPER, -11000)
    D.check()
    assert len(dd["pushes"]) == 2                                                        # same level: quiet


def test_straight_to_the_near_zone_is_one_high_push(dd):
    dd["set"](PAPER, -10500)
    D.check()
    assert [p["priority"] for p in dd["pushes"]] == ["high"]


def test_recovery_clears_the_latch_so_a_second_breach_pushes(dd):
    D.check()
    dd["set"](PAPER, -100)
    D.check()
    dd["set"](PAPER, -700)
    D.check()
    assert len(dd["pushes"]) == 2


def test_an_older_true_latch_still_means_already_alerted(dd, tmp_path):
    import json
    (tmp_path / "dd_alert_state.json").write_text(json.dumps({"day": "2026-10-07", "alerted": {PAPER: True}}))
    D.check()
    assert dd["pushes"] == []


def test_real_account_says_so_in_words_and_has_no_automatic_stop_clause(dd):
    dd["risk"]["accounts"].append({"account": REAL, "realized_today": -1500.0, "net_contracts": 0})
    dd["set"](PAPER, -100)
    D.check()
    p = dd["pushes"][0]
    assert p["title"] == "Real account: down $1,500 today"
    assert p["message"].split("\n")[1] == "Alert line -$500."
    assert "1810769" not in p["title"] + p["message"] and not N.lint(p)


def test_no_known_stop_level_leaves_the_clause_out_and_never_goes_high(dd):
    dd["risk"]["limits"] = {}
    dd["set"](PAPER, -50000)
    D.check()
    p = dd["pushes"][0]
    assert p["message"].split("\n")[1] == "Alert line -$500." and p["priority"] == "low"


def test_notify_still_passes_title_priority_and_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(N, "push", lambda message, title=None, priority=None, timeout=8, log=None:
                        calls.append((title, priority, timeout)) or True)
    monkeypatch.undo()                                                                    # use the real _notify below
    monkeypatch.setattr(N, "push", lambda message, title=None, priority=None, timeout=8, log=None:
                        calls.append((title, priority, timeout)) or True)
    D._notify("m", "Paper NT8: down $946 today", priority="low")
    assert calls == [("Paper NT8: down $946 today", "low", D.TIMEOUT_SEC)]


def test_a_bug_in_the_plain_text_never_loses_the_alert(dd, monkeypatch):
    monkeypatch.setattr(D, "build_note", lambda *a, **k: 1 / 0)
    D.check()
    assert len(dd["pushes"]) == 1 and dd["pushes"][0]["title"] == "Drawdown alert"
    D.check()
    assert len(dd["pushes"]) == 1                                                        # and still latched
