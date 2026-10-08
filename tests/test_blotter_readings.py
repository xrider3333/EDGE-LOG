"""get_blotter `readings`: the run report's SECOND reading, served beside the trade list.

The web can only reach augur_engine.cost_readings / run_limits through the PC runner, which it
already asks for a run's trades (get_blotter -> api.blotter.load_blotter_rows). A truthy
payload["readings"] makes load_blotter_rows attach out["readings"]; without it the response is
exactly what it was before. These pin: the flag gate, the cost contract (pnl_pts is NET, the
module adds the charged cost back itself), computed-from-ALL-rows (the MAXR cap trims what is
SENT, never what is counted), no realistic reading for an instrument without published inputs,
no guessed cost, and that a failure inside the engine can never take the blotter down.

No network, no live paths: every test builds its own temp root.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import blotter as B  # noqa: E402
from api.util import pack_command_result  # noqa: E402
from augur_engine import cost_readings as CR  # noqa: E402

COST = 0.5      # points per round trip the run was charged
MULT = 20.0     # NQ: dollars per point
# GROSS points 3.0 / -1.0 / 2.5 -> NET (what the blotter holds) 2.5 / -1.5 / 2.0
GROSS3 = [3.0, -1.0, 2.5]
NET3 = [g - COST for g in GROSS3]


def make_rows(nets, mult=MULT, start_day=1, month="2024-03"):
    rows, cum = [], 0.0
    for i, p in enumerate(nets, 1):
        usd = p * mult
        cum += usd
        d = "%s-%02d" % (month, start_day + i - 1)
        rows.append({"trade_no": i, "entry_time": d + " 09:35", "exit_time": d + " 10:05",
                     "hold_bars": 6, "entry_px": 100.0, "exit_px": 100.0 + p,
                     "pnl_pts": p, "pnl_usd": round(usd, 2), "cum_usd": round(cum, 0),
                     "side": "long"})
    return rows


def make_root(tmp_path, rows, rid=7, inst="NQ", tf="5m"):
    root = str(tmp_path)
    B.write_csv(rows, os.path.join(root, "blotters", "run%s_%s_%s.csv" % (rid, inst, tf)))
    return root


def payload(**kw):
    p = {"run_id": 7, "instrument": "NQ", "timeframe": "5m", "cost_pts": COST, "mult": MULT}
    p.update(kw)
    return p


def serve(tmp_path, nets=NET3, **kw):
    root = make_root(tmp_path, make_rows(nets), inst=kw.get("instrument", "NQ"))
    return B.load_blotter_rows(root, payload(**kw), log=lambda *_: None)


# ============================================================ the flag gate

def test_readings_absent_without_the_flag(tmp_path):
    out = serve(tmp_path)
    assert out["ok"] is True and out["n"] == 3 and len(out["rows"]) == 3
    assert "readings" not in out


@pytest.mark.parametrize("flag", [False, None, 0, ""])
def test_readings_absent_for_a_falsy_flag(tmp_path, flag):
    assert "readings" not in serve(tmp_path, readings=flag)


def test_readings_present_with_the_flag(tmp_path):
    out = serve(tmp_path, readings=True)
    r = out["readings"]
    assert r["ok"] is True
    assert set(r) >= {"ok", "n_rows", "n_trades", "cost", "realistic", "limits", "summary"}
    assert out["n"] == 3 and len(out["rows"]) == 3       # the trade list is untouched


# ============================================================ the cost contract

def test_net_at_the_charged_cost_equals_the_csv_net_sum(tmp_path):
    """The blotter holds NET points. Re-costing adds the charge back, so 'net at the flat
    cost' must come out as the CSV's own net sum - not net minus a second charge."""
    out = serve(tmp_path, readings=True)
    c = out["readings"]["cost"]
    csv_net = sum(float(r["pnl_pts"]) for r in out["rows"])
    assert csv_net == pytest.approx(3.0)
    assert c["ok"] is True
    assert c["net_flat_pts"] == pytest.approx(csv_net)
    assert c["net_flat_usd"] == pytest.approx(csv_net * MULT)


def test_breakeven_cost_matches_a_hand_calculation(tmp_path):
    # gross = 3.0 - 1.0 + 2.5 = 4.5 over 3 trades -> break-even 1.5 points per round trip
    c = serve(tmp_path, readings=True)["readings"]["cost"]
    assert c["n_trades"] == 3 and c["cost_pts"] == COST
    assert c["gross_pts"] == pytest.approx(4.5)
    assert c["breakeven_cost_pts"] == pytest.approx(1.5)
    assert c["breakeven_cost_usd"] == pytest.approx(30.0)
    assert c["headroom_x"] == pytest.approx(3.0)              # 1.5 / 0.5
    assert c["net_double_pts"] == pytest.approx(1.5)          # 4.5 - 3 * (2 * 0.5)
    assert c["net_double_usd"] == pytest.approx(30.0)


def test_a_loser_before_cost_has_no_breakeven(tmp_path):
    c = serve(tmp_path, nets=[-1.0, -2.0, 0.5], readings=True)["readings"]["cost"]
    assert c["breakeven_cost_pts"] is None and c["headroom_x"] is None
    assert any("loses money before any cost" in s
               for s in serve(tmp_path, nets=[-1.0, -2.0, 0.5], readings=True)["readings"]["summary"])


def test_summary_is_the_modules_own_sentences(tmp_path):
    r = serve(tmp_path, readings=True)["readings"]
    assert r["summary"] and all(isinstance(s, str) for s in r["summary"])
    assert any("breaks even at 1.500 points per round trip" in s for s in r["summary"])
    assert any("realistic" in s for s in r["summary"])         # NQ: the realistic line is in


# ============================================================ realistic: published inputs only

def test_nq_realistic_reading_from_published_inputs(tmp_path):
    rl = serve(tmp_path, readings=True)["readings"]["realistic"]
    # fee 2.09 x (0.25 / 5.0) = 0.1045, spread 0.5 tick x 0.25 x 2 = 0.25, slippage 0 (no ATR)
    assert rl["ok"] is True and rl["instrument"] == "NQ" and rl["contracts"] == 1
    assert rl["slippage_included"] is False and rl["atr_pts"] is None and rl["fitted"] is False
    assert rl["realistic_cost_pts"] == pytest.approx(0.3545)
    assert rl["realistic_breakdown"]["slippage_pts"] == 0.0
    assert rl["realistic_breakdown"]["fitted"] is False
    assert rl["net_realistic_pts"] == pytest.approx(4.5 - 3 * 0.3545)
    assert rl["net_realistic_usd"] == pytest.approx((4.5 - 3 * 0.3545) * MULT)
    assert rl["survives"] is True
    assert rl["realistic_over_breakeven"] == pytest.approx(0.3545 / 1.5)


def test_qqq_has_published_inputs_too(tmp_path):
    # QQQ is per SHARE: mult 1, cost 0.02/share. Net 0.20/0.05/0.10 -> gross 0.22/0.07/0.12.
    nets = [0.20, 0.05, 0.10]
    r = serve(tmp_path, nets=nets, instrument="QQQ", cost_pts=0.02, mult=1.0,
              readings=True)["readings"]
    assert r["realistic"]["ok"] is True and r["realistic"]["instrument"] == "QQQ"
    # 0.30 fee/share + 1 tick (0.01) spread round trip
    assert r["realistic"]["realistic_cost_pts"] == pytest.approx(0.30 + 0.02)
    assert r["realistic"]["survives"] is False           # 0.32/share cost vs ~0.14 edge


def test_instrument_without_published_inputs_gets_no_realistic_reading(tmp_path):
    """The module silently falls back to NQ's inputs for an unknown name - wrong for GLD."""
    r = serve(tmp_path, instrument="GLD", readings=True)["readings"]
    assert r["realistic"] == {"ok": False, "why": "no published cost inputs for GLD"}
    assert r["cost"]["ok"] is True                         # the cost reading itself is fine
    assert not any("realistic" in s for s in r["summary"])


def test_no_instrument_is_not_nq(tmp_path):
    root = make_root(tmp_path, make_rows(NET3), inst="")
    out = B.load_blotter_rows(root, payload(instrument="", readings=True), log=lambda *_: None)
    assert out["readings"]["realistic"]["ok"] is False


# ============================================================ never guess the charged cost

def test_missing_cost_pts_fails_the_cost_part_not_guessed_as_zero(tmp_path):
    p = payload(readings=True)
    del p["cost_pts"]
    root = make_root(tmp_path, make_rows(NET3))
    out = B.load_blotter_rows(root, p, log=lambda *_: None)
    r = out["readings"]
    assert out["ok"] is True and len(out["rows"]) == 3     # blotter still served
    assert r["ok"] is True
    assert r["cost"]["ok"] is False and "cost_pts" in r["cost"]["error"]
    assert "net_flat_pts" not in r["cost"]
    assert r["realistic"]["ok"] is False
    assert r["summary"] == []
    # the limits list does not assert a flat-cost item it cannot support
    assert "flat_cost" not in [i["key"] for i in r["limits"]["items"]]


@pytest.mark.parametrize("bad", [None, "", "abc", float("nan"), -0.5])
def test_unusable_cost_pts_is_refused(tmp_path, bad):
    r = serve(tmp_path, cost_pts=bad, readings=True)["readings"]
    assert r["cost"]["ok"] is False


def test_an_explicit_zero_cost_is_a_real_cost(tmp_path):
    r = serve(tmp_path, nets=[1.0, -0.5], cost_pts=0, readings=True)["readings"]["cost"]
    assert r["ok"] is True and r["cost_pts"] == 0.0 and r["net_flat_pts"] == pytest.approx(0.5)
    assert r["headroom_x"] is None                        # no charged cost to be a multiple of


def test_zero_cost_does_not_lose_the_readings_to_a_summary_failure(tmp_path):
    """cost_readings.summary_lines formats headroom_x with %.1f, which is None at cost 0 and
    raises. The sentences are a convenience: the numbers must survive that."""
    r = serve(tmp_path, nets=[1.0, -0.5], cost_pts=0, readings=True)["readings"]
    assert r["ok"] is True and r["cost"]["ok"] is True and r["realistic"]["ok"] is True
    assert r["summary"] == [] and "summary_error" in r


def test_missing_mult_fails_the_cost_part(tmp_path):
    p = payload(readings=True)
    del p["mult"]
    root = make_root(tmp_path, make_rows(NET3))
    r = B.load_blotter_rows(root, p, log=lambda *_: None)["readings"]
    assert r["cost"]["ok"] is False and "mult" in r["cost"]["error"]


# ============================================================ all rows, never the capped ones

def test_the_maxr_cap_trims_what_is_sent_not_what_is_counted(tmp_path, monkeypatch):
    nets = [1.0, -0.5, 2.0, 0.25, -1.0, 0.75, 1.5]            # 7 rows
    root = make_root(tmp_path, make_rows(nets))
    full = B.load_blotter_rows(root, payload(readings=True), log=lambda *_: None)
    monkeypatch.setattr(B, "MAXR", 3)
    capped = B.load_blotter_rows(root, payload(readings=True), log=lambda *_: None)
    assert len(capped["rows"]) == 3 and capped["capped"] == 4 and capped["n"] == 7
    assert [r["trade_no"] for r in capped["rows"]] == ["5", "6", "7"]      # most recent kept
    assert capped["readings"]["n_trades"] == 7 and capped["readings"]["n_rows"] == 7
    assert capped["readings"]["cost"]["n_trades"] == 7
    assert capped["readings"]["limits"]["basis"]["n_trades"] == 7
    assert capped["readings"] == full["readings"]               # identical to the uncapped read
    assert capped["readings"]["cost"]["net_flat_pts"] == pytest.approx(sum(nets))


# ============================================================ the regenerated path

def test_readings_ride_the_regenerated_path_too(tmp_path, monkeypatch):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "augur_strategies"))
    open(os.path.join(root, "augur_strategies", "FAKE.py"), "w").close()
    rows = make_rows(NET3)

    def fake_champion(strategy, instrument, timeframe, **kw):
        assert kw["cost_pts"] == COST and kw["mult"] == MULT
        return rows, {"master": "fake_master"}
    monkeypatch.setattr(B, "champion_blotter", fake_champion)
    p = payload(readings=True, strategy="FAKE", params={"a": 1})
    out = B.load_blotter_rows(root, p, log=lambda *_: None)
    assert out["regenerated"] is True
    assert out["readings"]["ok"] is True
    assert out["readings"]["cost"]["net_flat_pts"] == pytest.approx(3.0)   # numeric rows, not CSV text
    # and without the flag the regenerated response has no readings either
    os.remove(os.path.join(root, "blotters", "run7_NQ_5m.csv"))
    out2 = B.load_blotter_rows(root, payload(strategy="FAKE", params={"a": 1}), log=lambda *_: None)
    assert out2["regenerated"] is True and "readings" not in out2


# ============================================================ a failure never takes the blotter down

def test_an_engine_exception_leaves_the_blotter_served(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("engine blew up")
    monkeypatch.setattr(CR, "readings", boom)
    out = serve(tmp_path, readings=True)
    assert out["ok"] is True and out["n"] == 3 and len(out["rows"]) == 3
    assert out["readings"]["ok"] is False
    assert "engine blew up" in out["readings"]["error"]
    json.dumps(out)                                            # and it still serializes


def test_run_limits_exception_is_contained_too(tmp_path, monkeypatch):
    from augur_engine import run_limits as RL
    monkeypatch.setattr(RL, "not_modelled", lambda run: 1 / 0)
    out = serve(tmp_path, readings=True)
    assert out["ok"] is True and len(out["rows"]) == 3
    assert out["readings"]["ok"] is False and "ZeroDivisionError" in out["readings"]["error"]


# ============================================================ limits: what the run does not model

def test_limits_follow_the_run_settings(tmp_path):
    r = serve(tmp_path, readings=True, source="db_noadj", date_from="2024-01-01",
              date_to="2024-12-31", family="ORB", fill_rule="stop-through")["readings"]["limits"]
    keys = [i["key"] for i in r["items"]]
    assert r["ok"] is True
    assert {"flat_cost", "fill_rule", "no_adjust_rolls", "no_margin", "no_forward_test"} <= set(keys)
    fill = next(i for i in r["items"] if i["key"] == "fill_rule")
    assert "stop-through" in fill["text"]
    assert "summer_hole" not in keys and "secondary_feed" not in keys     # window ends 2024
    assert r["counts"]["total"] == len(r["items"])
    assert r["counts"]["material"] == sum(1 for i in r["items"] if i["severity"] == "material")
    assert len(r["lines"]) == len(r["items"])
    assert r["basis"]["n_trades"] == 3 and r["basis"]["cost_pts"] == COST
    assert r["basis"]["family"] == "ORB"


def test_a_window_into_the_summer_hole_is_flagged(tmp_path):
    r = serve(tmp_path, readings=True, source="databento_raw", date_from="2026-05-01",
              date_to="2026-09-01")["readings"]["limits"]
    keys = [i["key"] for i in r["items"]]
    assert "summer_hole" in keys and "secondary_feed" in keys


def test_thin_sample_only_when_the_rows_say_so(tmp_path):
    r = serve(tmp_path, readings=True)["readings"]["limits"]
    assert "thin_sample" in [i["key"] for i in r["items"]]      # 3 trades < 100


def test_no_lockbox_keys_without_lockbox_from(tmp_path):
    b = serve(tmp_path, readings=True)["readings"]["limits"]["basis"]
    assert not any(k.startswith("lockbox") for k in b) and "pnl_units" not in b


def test_lockbox_reading_from_the_rows_after_the_seal_date(tmp_path):
    # 5 trades on 03-01..03-05; the seal date 03-04 keeps trades 4 and 5.
    nets = [1.0, 1.0, 1.0, 4.0, 0.5]
    root = make_root(tmp_path, make_rows(nets))
    r = B.load_blotter_rows(root, payload(readings=True, lockbox_from="2024-03-04"),
                            log=lambda *_: None)["readings"]["limits"]
    b = r["basis"]
    assert b["lockbox_trades"] == 2 and b["pnl_units"] == "usd"
    assert b["lockbox_net"] == pytest.approx((4.0 + 0.5) * MULT)           # the rows' pnl_usd
    assert b["lockbox_top_trade_net"] == pytest.approx(4.0 * MULT)
    keys = {i["key"]: i for i in r["items"]}
    assert "thin_lockbox" in keys and "only 2 trades" in keys["thin_lockbox"]["text"]
    assert "one_trade_lockbox" in keys                                      # 4.0 of 4.5 = 89%
    assert "89%" in keys["one_trade_lockbox"]["text"]
    assert "points_not_money" not in keys                                   # usd, not points


def test_lockbox_falls_back_to_points_times_mult_then_to_points(tmp_path):
    rows = make_rows([1.0, 2.0, 0.5])
    for r in rows:
        r["pnl_usd"] = ""                                                   # no money on the rows
    root = make_root(tmp_path, rows)
    b = B.load_blotter_rows(root, payload(readings=True, lockbox_from="2024-03-02"),
                            log=lambda *_: None)["readings"]["limits"]["basis"]
    assert b["pnl_units"] == "usd" and b["lockbox_net"] == pytest.approx(2.5 * MULT)
    # no mult either -> read in points, and the points note appears
    p = payload(readings=True, lockbox_from="2024-03-02")
    del p["mult"]
    out = B.load_blotter_rows(root, p, log=lambda *_: None)["readings"]["limits"]
    assert out["basis"]["pnl_units"] == "pts" and out["basis"]["lockbox_net"] == pytest.approx(2.5)
    assert "points_not_money" in [i["key"] for i in out["items"]]


def test_a_window_that_ends_before_the_seal_date_has_no_lockbox(tmp_path):
    b = serve(tmp_path, readings=True, lockbox_from="2025-01-01", date_to="2024-06-30"
              )["readings"]["limits"]["basis"]
    assert "lockbox_trades" not in b


def test_a_malformed_lockbox_date_is_ignored(tmp_path):
    b = serve(tmp_path, readings=True, lockbox_from="March 4")["readings"]["limits"]["basis"]
    assert "lockbox_trades" not in b


# ============================================================ JSON safety

def test_readings_are_plain_json_with_no_nan(tmp_path):
    rows = make_rows([1.0, 2.0, -0.5, 1.5])
    rows[1]["pnl_pts"] = "nan"                                              # a torn / blank value
    rows[2]["pnl_pts"] = ""
    root = make_root(tmp_path, rows)
    out = B.load_blotter_rows(root, payload(readings=True, lockbox_from="2024-03-01"),
                              log=lambda *_: None)
    r = out["readings"]
    assert r["n_rows"] == 4 and r["n_trades"] == 2          # only the numeric pnl_pts count
    json.dumps(r, allow_nan=False)                           # strict: raises on NaN / inf / numpy
    json.dumps(pack_command_result(out), allow_nan=False)    # and survives the runner's packer


def test_a_zero_trade_run_reads_cleanly(tmp_path):
    rows = make_rows([1.0])
    rows[0]["pnl_pts"] = "x"
    root = make_root(tmp_path, rows)
    r = B.load_blotter_rows(root, payload(readings=True), log=lambda *_: None)["readings"]
    assert r["ok"] is True and r["n_trades"] == 0
    assert r["cost"]["breakeven_cost_pts"] is None
    assert r["summary"] == ["No trades, so there is nothing to re-cost."]
    json.dumps(r, allow_nan=False)
