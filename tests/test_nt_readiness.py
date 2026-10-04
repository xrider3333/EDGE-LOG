"""Tests for tools/nt_readiness.py - the premarket NinjaTrader readiness check.

Every test builds a small fake world in tmp_path (bridge answers, ENGU-Q state file, two 10s CSVs,
state/result files) and points the module at it with monkeypatch. Nothing here touches the real
bridge, the real gate, C:\\EdgeLog, or ntfy.
"""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import nt_readiness as R                                    # noqa: E402

ET = ZoneInfo("America/New_York")


def et_ts(y, m, d, hh, mm):
    return int(dt.datetime(y, m, d, hh, mm, tzinfo=ET).timestamp())


WED_0915 = et_ts(2026, 10, 7, 9, 15)        # a normal trading Wednesday, inside the window
SAT_0915 = et_ts(2026, 10, 10, 9, 15)

GOOD_STRATS = [
    {"account": "DEMO7240108", "name": "EdgeLogNOISE", "state": "Realtime", "instrument": "MNQ 12-26", "position": "Flat 0"},
    {"account": "DEMO7240108", "name": "EdgeLogENGUQ1m", "state": "Realtime", "instrument": "NQ 12-26", "position": "Flat 0"},
]
ACCOUNTS = {"accounts": [{"name": "DEMO7240108", "cash": 49000, "connection": "Connected", "connected": True},
                         {"name": "1810769", "cash": 1600, "connection": "Connected", "connected": True}]}


def write_capture(path, now_ts, overnight_pct=100, recent_pct=100, last_age=0):
    """10s rows from the 18:00 ET overnight start to now - last_age. Rows older than 30 minutes use
    overnight_pct classified, the last 30 minutes use recent_pct."""
    start = R.overnight_start_ts(R.to_et(now_ts))
    end = now_ts - last_age
    lines = ["time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt"]
    for i, t in enumerate(range(start + 10, end + 1, 10)):
        pct = recent_pct if t > now_ts - 1800 else overnight_pct
        cls = (i % 100) < pct
        lines.append("%d,100,101,99,100,5,1,%d,%d,5,%d" % (t, 3 if cls else 0, 2 if cls else 0, 1 if cls else 3))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = {
        "now": WED_0915,
        "bridge": {"/health": {"ok": True}, "/accounts": ACCOUNTS,
                   "/strategies": {"strategies": list(GOOD_STRATS)},
                   "/positions": {"positions": []}, "/orders": {"orders": []}},
        "gate": {"ok": True},
        "pushes": [],
        "state": {"inPos": False, "qty": 1, "instrument": "NQ 12-26"},
    }

    def fake_get(url, timeout=4):
        if url == R.GATE_URL:
            return w["gate"]
        for path, body in w["bridge"].items():
            if url.endswith(path):
                return body
        return None

    def fake_push(message, title=None, priority=None, timeout=8, log=None):
        w["pushes"].append({"message": message, "title": title, "priority": priority})
        return True

    monkeypatch.setattr(R, "_http_get_json", fake_get)
    monkeypatch.setattr(R, "_roster", lambda: (["EdgeLogNOISE", "EdgeLogENGUQ1m"], "test"))
    monkeypatch.setattr(R, "RESULT_PATH", str(tmp_path / "nt_readiness.json"))
    monkeypatch.setattr(R, "STATE_PATH", str(tmp_path / "nt_readiness_state.json"))
    monkeypatch.setattr(R, "ENGUQ_STATE_PATH", str(tmp_path / "enguq_state.json"))
    monkeypatch.setattr(R, "NTFY_ENV_PATH", str(tmp_path / "no_ntfy.env"))
    monkeypatch.setattr(R, "CAPTURE_PATHS", {"NQ": str(tmp_path / "NQ_10s.csv"), "ES": str(tmp_path / "ES_10s.csv")})
    from api import ntfy_push
    monkeypatch.setattr(ntfy_push, "push", fake_push)
    w["tmp"] = tmp_path

    def write_all(**kw):
        for inst in ("NQ", "ES"):
            write_capture(tmp_path / ("%s_10s.csv" % inst), w["now"], **kw)
        (tmp_path / "enguq_state.json").write_text(json.dumps(w["state"]), encoding="utf-8")
    w["write_all"] = write_all
    write_all()

    def run(*argv, now=None):
        (tmp_path / "enguq_state.json").write_text(json.dumps(w["state"]), encoding="utf-8")
        return R.main(list(argv), now_ts=now or w["now"])
    w["run"] = run
    w["result"] = lambda: json.loads((tmp_path / "nt_readiness.json").read_text(encoding="utf-8"))
    return w


def status(w, item_id):
    return next(i for i in w["result"]()["items"] if i["id"] == item_id)["status"]


def held_nq(w, qty=1, stops=1, state_in_pos=True, strat_pos="Long 1"):
    """ENGU-Q holds NQ 12-26 long, with `stops` working sell stops and a matching state file."""
    w["bridge"]["/positions"] = {"positions": [{"account": "DEMO7240108", "instrument": "NQ 12-26", "side": "Long",
                                                "qty": qty, "avg_price": 31000}]}
    strats = [dict(s) for s in GOOD_STRATS]
    strats[1]["position"] = strat_pos
    w["bridge"]["/strategies"] = {"strategies": strats}
    w["bridge"]["/orders"] = {"orders": [{"account": "DEMO7240108", "order_id": "s%d" % i, "instrument": "NQ 12-26",
                                          "action": "Sell", "type": "StopMarket", "state": "Working", "qty": qty,
                                          "stop": 30900} for i in range(stops)]}
    w["state"] = {"inPos": state_in_pos, "qty": qty, "instrument": "NQ 12-26", "sl": 30900, "ep": 31000}


# ------------------------------------------------------------------------------------------

def test_all_pass(world):
    assert world["run"]() == 0
    res = world["result"]()
    assert res["ok"] and res["failed"] == []
    assert world["pushes"] == []
    ids = {i["id"] for i in res["items"]}
    assert {"bridge", "roster", "positions", "capture_fresh_NQ", "capture_overnight_ES", "gate"} <= ids


def test_strategy_missing_pushes_once(world):
    world["bridge"]["/strategies"] = {"strategies": [GOOD_STRATS[0]]}
    assert world["run"]() == 1
    assert status(world, "roster") == "fail"
    assert len(world["pushes"]) == 1
    msg = world["pushes"][0]["message"]
    assert "ENGU-Q is missing" in msg and "only reads" in msg
    assert world["pushes"][0]["priority"] == "high"


def test_strategy_not_realtime_fails(world):
    strats = [dict(s) for s in GOOD_STRATS]
    strats[0]["state"] = "Terminated"
    world["bridge"]["/strategies"] = {"strategies": strats}
    assert world["run"]() == 1
    assert "NOISE is not running live" in world["pushes"][0]["message"]


def test_unmanaged_position_fails(world):
    world["bridge"]["/positions"] = {"positions": [{"account": "DEMO7240108", "instrument": "MNQ 12-26",
                                                    "side": "Long", "qty": 3, "avg_price": 31000}]}
    assert world["run"]() == 1
    assert status(world, "positions") == "fail"
    assert "no strategy owns" in world["pushes"][0]["message"]


def test_managed_position_passes(world):
    held_nq(world)
    assert world["run"]() == 0
    assert status(world, "positions") == "pass"


def test_two_stops_fails(world):
    held_nq(world, stops=2)
    assert world["run"]() == 1
    assert "2 exit stops instead of one" in world["pushes"][0]["message"]


def test_no_stop_fails(world):
    held_nq(world, stops=0)
    assert world["run"]() == 1
    assert "0 exit stops" in world["pushes"][0]["message"]


def test_state_file_not_in_position_fails(world):
    held_nq(world, state_in_pos=False)
    assert world["run"]() == 1
    assert "saved trade does not match" in world["pushes"][0]["message"]


def test_strategy_position_mismatch_fails(world):
    held_nq(world, strat_pos="Flat 0")
    assert world["run"]() == 1
    assert status(world, "positions") == "fail"


def test_state_says_held_but_account_flat_fails(world):
    world["state"] = {"inPos": True, "qty": 1, "instrument": "NQ 12-26"}
    assert world["run"]() == 1
    assert "does not have" in world["pushes"][0]["message"]


def test_stale_capture_fails_and_skips_coverage(world):
    world["write_all"](last_age=600)
    assert world["run"]() == 1
    assert status(world, "capture_fresh_NQ") == "fail"
    assert status(world, "capture_30m_NQ") == "skip"
    assert "stopped" in world["pushes"][0]["message"]


def test_low_overnight_coverage_reports_percent(world):
    world["write_all"](overnight_pct=50)
    assert world["run"]() == 1
    items = {i["id"]: i for i in world["result"]()["items"]}
    assert items["capture_overnight_NQ"]["status"] == "fail"
    assert "50.0%" in items["capture_overnight_NQ"]["detail"] or "5" in items["capture_overnight_NQ"]["detail"]
    assert items["capture_30m_NQ"]["status"] == "pass"           # the last 30 minutes are fine
    assert "overnight" in world["pushes"][0]["message"]


def test_low_recent_coverage_fails(world):
    world["write_all"](recent_pct=40)
    assert world["run"]() == 1
    assert status(world, "capture_30m_ES") == "fail"


def test_gate_down_is_warning_but_still_pushes(world):
    world["gate"] = None
    assert world["run"]() == 1
    item = next(i for i in world["result"]()["items"] if i["id"] == "gate")
    assert item["status"] == "fail" and item["level"] == "warn"
    assert len(world["pushes"]) == 1
    assert world["pushes"][0]["priority"] == "default"            # warning-only set is not high priority


def test_gate_unhealthy_fails(world):
    world["gate"] = {"ok": False}
    assert world["run"]() == 1
    assert status(world, "gate") == "fail"


def test_bridge_down_skips_dependents(world):
    world["bridge"] = {}
    assert world["run"]() == 1
    assert status(world, "bridge") == "fail"
    assert status(world, "roster") == "skip" and status(world, "positions") == "skip"
    assert len(world["pushes"]) == 1


def _later(w, minutes, *argv):
    """Advance the clock and rewrite the captures so they are fresh again at the new time."""
    w["now"] += minutes * 60
    w["write_all"]()
    return w["run"](*argv, now=w["now"])


def test_push_dedupe_twenty_minutes(world):
    world["now"] = et_ts(2026, 10, 7, 9, 12)                      # leave room for +22 min inside the window
    world["write_all"]()
    world["gate"] = None
    world["run"]()
    _later(world, 5)
    assert len(world["pushes"]) == 1                              # same set inside 20 minutes
    _later(world, 16)
    assert len(world["pushes"]) == 2                              # 21 minutes on: quiet period over
    world["bridge"]["/strategies"] = {"strategies": [GOOD_STRATS[0]]}
    _later(world, 1)
    assert len(world["pushes"]) == 3                              # a different set pushes at once


def test_clean_pass_rearms_alert(world):
    world["gate"] = None
    world["run"]()
    world["gate"] = {"ok": True}
    _later(world, 1)
    world["gate"] = None
    _later(world, 1)
    assert len(world["pushes"]) == 2


def test_weekend_skip(world, capsys):
    assert world["run"](now=SAT_0915) == 0
    assert "SKIPPED" in capsys.readouterr().out
    assert world["pushes"] == []
    assert not (world["tmp"] / "nt_readiness.json").exists()


def test_outside_window_skips_and_force_overrides(world, capsys):
    late = et_ts(2026, 10, 7, 13, 0)
    assert world["run"](now=late) == 0
    assert "SKIPPED" in capsys.readouterr().out
    assert world["run"]("--force", "--dry-run", now=late) in (0, 1)
    assert "NinjaTrader bridge" in capsys.readouterr().out


def test_holiday_skips(world, capsys):
    # Thanksgiving 2026-11-26 is a market holiday
    assert world["run"](now=et_ts(2026, 11, 26, 9, 15)) == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_dry_run_writes_and_pushes_nothing(world):
    world["gate"] = None
    assert world["run"]("--dry-run") == 1
    assert world["pushes"] == []
    assert not (world["tmp"] / "nt_readiness.json").exists()
    assert not (world["tmp"] / "nt_readiness_state.json").exists()


def test_early_run_holds_back_startup_failures_but_pushes_safety(world):
    world["bridge"]["/strategies"] = {"strategies": [GOOD_STRATS[0]]}          # roster: start-up class
    assert world["run"]("--early") == 1
    assert world["pushes"] == []
    world["bridge"]["/positions"] = {"positions": [{"account": "DEMO7240108", "instrument": "MNQ 12-26",
                                                    "side": "Long", "qty": 3, "avg_price": 1}]}
    world["bridge"]["/strategies"] = {"strategies": list(GOOD_STRATS)}          # roster healthy again
    world["run"]("--early")
    assert len(world["pushes"]) == 1 and "no strategy owns" in world["pushes"][0]["message"]


def test_live_account_exposure_is_a_safety_failure(world):
    world["bridge"]["/strategies"] = {"strategies": GOOD_STRATS + [
        {"account": "1810769", "name": "EdgeLogNOISE", "state": "Realtime", "instrument": "MNQ 12-26", "position": "Flat 0"}]}
    assert world["run"]("--early") == 1
    assert len(world["pushes"]) == 1 and "LIVE account" in world["pushes"][0]["message"]


def test_json_output_is_valid(world, capsys):
    assert world["run"]("--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["items"]


def test_ntfy_env_loaded_without_override_or_echo(world, monkeypatch, capsys):
    env = world["tmp"] / "ntfy.env"
    env.write_text("# c\nNTFY_TOPIC=secret-topic-xyz\n", encoding="utf-8")
    monkeypatch.setattr(R, "NTFY_ENV_PATH", str(env))
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    R._load_ntfy_env()
    assert os.environ["NTFY_TOPIC"] == "secret-topic-xyz"
    monkeypatch.delenv("NTFY_TOPIC", raising=False)               # restore a clean env for later tests
    assert "secret-topic-xyz" not in capsys.readouterr().out


def test_cme_open_calendar():
    assert not R.cme_open(R.to_et(et_ts(2026, 10, 10, 12, 0)))    # Saturday
    assert not R.cme_open(R.to_et(et_ts(2026, 10, 9, 17, 30)))    # Friday after 17:00
    assert not R.cme_open(R.to_et(et_ts(2026, 10, 11, 17, 59)))   # Sunday before 18:00
    assert R.cme_open(R.to_et(et_ts(2026, 10, 11, 18, 0)))
    assert not R.cme_open(R.to_et(et_ts(2026, 10, 7, 17, 30)))    # daily break
    assert R.cme_open(R.to_et(et_ts(2026, 10, 7, 9, 15)))


def test_overnight_start_is_prior_evening():
    assert R.overnight_start_ts(R.to_et(WED_0915)) == et_ts(2026, 10, 6, 18, 0)
    mon = et_ts(2026, 10, 12, 9, 15)                                # Monday: Sunday 18:00
    assert R.overnight_start_ts(R.to_et(mon)) == et_ts(2026, 10, 11, 18, 0)


def test_runs_before_0910_hold_back_startup_failures(world):
    world["now"] = et_ts(2026, 10, 7, 8, 30)
    world["write_all"]()
    world["bridge"] = {}                                           # NinjaTrader still starting
    assert world["run"]() == 1
    assert world["pushes"] == []
    _later(world, 50)                                              # 09:20 ET: now it is a real problem
    assert len(world["pushes"]) == 1
