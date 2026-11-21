import datetime as dt
import json

import pytest

from tools import nt_real_days as nrd
from api import ntfy_push

NOW = dt.datetime(2026, 11, 20, 15, 0, tzinfo=nrd.NY)


@pytest.fixture
def env(tmp_path, monkeypatch):
    pushes, mirrors = [], []
    monkeypatch.setattr(ntfy_push, "push", lambda msg, **k: pushes.append(msg) or True)
    monkeypatch.setattr(nrd, "mirror", lambda data: mirrors.append(json.loads(json.dumps(data))))
    return {"data": str(tmp_path / "d.json"), "state": str(tmp_path / "s.json"),
            "pushes": pushes, "mirrors": mirrors}


def _bridge(monkeypatch, rows):
    monkeypatch.setattr(nrd, "bridge_accounts", lambda timeout=5: rows)


def test_records_only_real_accounts(env, monkeypatch):
    _bridge(monkeypatch, [{"name": "1810769", "realized": 125.5}, {"name": "Sim101", "realized": 9},
                          {"name": "DEMO123", "realized": 4}, {"name": "Playback101", "realized": 1}])
    assert nrd.record(env["data"], now=NOW)
    d = json.load(open(env["data"]))
    assert list(d) == ["1810769"] and d["1810769"]["2026-11-20"]["realized"] == 125.5
    assert len(env["mirrors"]) == 1
    assert not nrd.record(env["data"], now=NOW)          # unchanged -> no write
    assert len(env["mirrors"]) == 1
    _bridge(monkeypatch, [{"name": "1810769", "realized": 130}])
    assert nrd.record(env["data"], now=NOW)              # last value of the day wins
    assert json.load(open(env["data"]))["1810769"]["2026-11-20"]["realized"] == 130


def test_bridge_down_is_noop(env, monkeypatch):
    _bridge(monkeypatch, None)
    assert nrd.record(env["data"], now=NOW) is False
    assert not env["mirrors"]
    import os
    assert not os.path.exists(env["data"])


def _seed(path, data):
    json.dump(data, open(path, "w"))


def test_mismatch_pushes_once(env):
    _seed(env["data"], {"1810769": {"2026-11-18": {"realized": 200.0, "seen_at": "x"}}})
    trades = [{"date": "2026-11-17", "account": "1810769", "pnl": 10, "broker": "NinjaTrader"}]
    sent = nrd.check(10, env["data"], env["state"], now=NOW, trades=trades, log=lambda m: None)
    assert len(sent) == 1 and "NT real 1810769 2026-11-18" in sent[0] and "(0 trades)" in sent[0]
    assert nrd.check(10, env["data"], env["state"], now=NOW, trades=trades, log=lambda m: None) == []
    assert len(env["pushes"]) == 1


def test_matched_day_does_not_push(env):
    _seed(env["data"], {"1810769": {"2026-11-18": {"realized": 200.0, "seen_at": "x"}}})
    trades = [{"date": "2026-11-18", "account": "1810769", "pnl": 190, "grossPnl": 201,
               "broker": "NinjaTrader"}]
    assert nrd.check(10, env["data"], env["state"], now=NOW, trades=trades, log=lambda m: None) == []
    assert not env["pushes"]


def test_sim_account_ignored(env):
    _seed(env["data"], {"Sim101": {"2026-11-18": {"realized": 500.0, "seen_at": "x"}}})
    assert nrd.check(10, env["data"], env["state"], now=NOW, trades=[], log=lambda m: None) == []
    assert not env["pushes"]
