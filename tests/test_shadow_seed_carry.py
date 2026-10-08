"""tests/test_shadow_seed_carry.py -- SHADOW SEED CARRY (2026-10-07, MANAGER #87;
api/cloud_signal.py SEED_OPEN_FORMAT / _seeded_entry_event / _carry_seeded_open).

THE BUG. ENGUQ_335 became a no-order shadow leg on 2026-09-28. Its shadow store cold-started
on 2026-09-29 09:30 while the strategy was holding the 09-28 12:32 long @ 738.0295, and the
cold-start rule (written for executors: "an executor that never entered cannot exit")
recorded that open trade as exit_emitted -- so the shadow ledger will never log it, and the
leg showed 0 trades for 7 sessions.

COVERS:
  1. A shadow leg cold-starting while holding a trade writes SEED + ONE seeded ENTRY at the
     trade's own time and price; its EXIT (same trade id, same size) follows when the
     strategy closes it; nothing repeats, also after a state.json round trip (a restart).
  2. A shadow leg cold-starting flat writes SEED only, as before.
  3. The LIVE (order-placing) legs keep the old rule exactly: SEED only, and no EXIT ever.
  4. The one-time upgrade of a leg seeded before this existed, in the box's own shape
     (ENGUQ_335's 09-28 long): still open -> one seeded ENTRY now, EXIT later; already
     closed -> ENTRY then EXIT on the same call; gone from the window -> nothing, counted;
     runs once; never on a live leg; closed seed history is never touched.
  5. A seeded record wins a trade-id merge (_merge_rank) -- its EXIT is still owed.
  6. tools/shadow_legs_report.py counts and prices a seeded trade and says how many there are.
"""
import json
import os
import sys
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                       # noqa: E402
import tools.shadow_legs_report as rpt              # noqa: E402

LEG = "ENGUQ_335"
SHADOW_CFG = {"shadow": True}
TID = "ENGUQ_335-20260928T163200Z-L"


def _now(day, hh, mm):
    return dt.datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:30").replace(tzinfo=cs._zi(cs.TZ))


def _t(entry_time, entry_px, exit_time=None, exit_px=None, side="long", shares=135, size=1.0):
    return {"entry_time": entry_time, "side": side, "entry_px": entry_px, "shares": shares,
            "still_open": exit_time is None, "exit_time": exit_time, "exit_px": exit_px,
            "size": size}


CLOSED = _t("2026-09-24T12:17:00-04:00", 739.3717, "2026-09-28T10:42:00-04:00", 734.6301)
OPEN = _t("2026-09-28T12:32:00-04:00", 738.0295)
CLOSED_LATER = dict(OPEN, still_open=False, exit_time="2026-10-08T10:05:00-04:00", exit_px=741.5)


def _diff(trades, leg_state, now, cfg=SHADOW_CFG):
    return cs._diff_leg(LEG, trades, leg_state, now, max_entry_age_sec=11 * 60,
                        bar_source="webull", cfg=cfg)


def _restart(leg_state):
    """What state.json hands the next process: a JSON round trip."""
    return json.loads(json.dumps(leg_state, default=str))


def _box_shape_leg_state():
    """ENGUQ_335's shadow state on the box before this fix (copied 2026-10-07, two of its
    twelve records): seeded 09-29, the 09-28 long absorbed as exit_emitted with no exit."""
    return {"trades": {
        "ENGUQ_335-20260924T161700Z-L": {
            "entry_time": "2026-09-24T12:17:00-04:00", "side": "long", "entry_px": 739.3717,
            "shares": 135, "exit_emitted": True, "exit_time": "2026-09-28T10:42:00-04:00",
            "exit_px": 734.6301, "seeded": True},
        TID: {"entry_time": "2026-09-28T12:32:00-04:00", "side": "long", "entry_px": 738.0295,
              "shares": 135, "exit_emitted": True, "exit_time": None, "exit_px": None,
              "seeded": True}},
        "seeded": True, "key_format": cs.TRADE_KEY_FORMAT,
        "asof": "2026-10-07T15:59:00-04:00"}


# ── 1. a shadow leg's cold start while holding a trade ───────────────────────────────────
def test_shadow_cold_start_carries_the_open_trade_and_its_exit_follows():
    ls = {"trades": {}}
    ev = _diff([CLOSED, OPEN], ls, _now("2026-09-29", 9, 30))
    assert [e["event"] for e in ev] == ["SEED", "ENTRY"]
    assert "carried as an open would-be trade" in ev[0]["reason"]
    e = ev[1]
    assert (e["leg"], e["side"], e["ref_time"], e["ref_price"], e["shares"], e["trade_id"]) == \
        (LEG, "long", "2026-09-28T12:32:00-04:00", 738.0295, 135, TID)
    assert e["reason"].startswith(cs.SEEDED_REASON_TAG)
    assert e["size"] == 1.0 and e["keel_size"] == ""
    rec = ls["trades"][TID]
    assert rec["seeded"] and rec["seeded_open"] and rec["exit_emitted"] is False
    assert ls["trades"]["ENGUQ_335-20260924T161700Z-L"]["exit_emitted"] is True, \
        "closed history is still absorbed silently"
    assert ls["seed_open_format"] == cs.SEED_OPEN_FORMAT

    ls = _restart(ls)
    assert _diff([CLOSED, OPEN], ls, _now("2026-10-07", 15, 59)) == [], "written once"
    ls = _restart(ls)
    ev = _diff([CLOSED, CLOSED_LATER], ls, _now("2026-10-08", 10, 6))
    assert [e["event"] for e in ev] == ["EXIT"]
    x = ev[0]
    assert (x["trade_id"], x["ref_time"], x["ref_price"], x["size"]) == \
        (TID, "2026-10-08T10:05:00-04:00", 741.5, 1.0)
    assert x["reason"].startswith("strategy_exit")
    assert _diff([CLOSED, CLOSED_LATER], _restart(ls), _now("2026-10-08", 10, 7)) == []


def test_a_keel_shadow_leg_carries_at_plugin_size_and_never_scores_keel(monkeypatch):
    """A KEEL shadow leg (NOISE_422_FIXED / _KEEL) holding a trade at its seed: plugin size,
    blank keel_size, on both rows -- KEEL is scored only for a fresh entry."""
    monkeypatch.setattr(cs, "_keel_size_for_entry",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("KEEL scored")))
    ls = {"trades": {}}
    cfg = {"shadow": True, "keel": {"version": "v12"}}
    ev = cs._diff_leg("NOISE_422_KEEL", [_t("2026-09-29T10:05:00-04:00", 700.0, size=1.75)], ls,
                      _now("2026-09-29", 10, 7), bar_source="webull", cfg=cfg)
    assert [e["event"] for e in ev] == ["SEED", "ENTRY"]
    assert ev[1]["size"] == 1.75 and ev[1]["keel_size"] == ""
    ev = cs._diff_leg("NOISE_422_KEEL",
                      [_t("2026-09-29T10:05:00-04:00", 700.0, "2026-09-29T11:00:00-04:00", 701.0,
                          size=1.75)], ls, _now("2026-09-29", 11, 2), bar_source="webull", cfg=cfg)
    assert [e["event"] for e in ev] == ["EXIT"] and ev[0]["size"] == 1.75 and ev[0]["keel_size"] == ""


# ── 2. a shadow leg's cold start while flat ──────────────────────────────────────────────
def test_shadow_cold_start_while_flat_writes_seed_only():
    ls = {"trades": {}}
    ev = _diff([CLOSED], ls, _now("2026-09-29", 9, 30))
    assert [e["event"] for e in ev] == ["SEED"]
    assert "carried" not in ev[0]["reason"] and "open_at_seed=none" in ev[0]["reason"]
    assert ls["seed_open_format"] == cs.SEED_OPEN_FORMAT


# ── 3. the live legs keep the executor rule ──────────────────────────────────────────────
def test_live_leg_cold_start_is_unchanged_and_never_exits_an_absorbed_trade():
    for cfg in (None, {}, {"shadow": False}):
        ls = {"trades": {}}
        ev = _diff([CLOSED, OPEN], ls, _now("2026-09-29", 9, 30), cfg=cfg)
        assert [e["event"] for e in ev] == ["SEED"]
        assert "carried" not in ev[0]["reason"]
        rec = ls["trades"][TID]
        assert rec["exit_emitted"] is True and "seeded_open" not in rec
        assert "seed_open_format" not in ls
        assert _diff([CLOSED, CLOSED_LATER], ls, _now("2026-10-08", 10, 6), cfg=cfg) == [], \
            "an executor that never entered cannot exit"


# ── 4. the one-time upgrade of a leg seeded before this existed (the box) ────────────────
def test_upgrade_carries_the_box_s_enguq_long_once_then_its_exit():
    ls = _box_shape_leg_state()
    ev = _diff([CLOSED, OPEN], ls, _now("2026-10-08", 9, 31))
    assert [e["event"] for e in ev] == ["ENTRY"]
    e = ev[0]
    assert (e["ref_time"], e["ref_price"], e["trade_id"]) == ("2026-09-28T12:32:00-04:00", 738.0295, TID)
    assert e["reason"].startswith(cs.SEEDED_REASON_TAG) and "carried on 2026-10-08" in e["reason"]
    assert ls["seed_open_format"] == cs.SEED_OPEN_FORMAT and "seed_open_lost" not in ls
    assert ls["trades"]["ENGUQ_335-20260924T161700Z-L"]["exit_emitted"] is True
    ls = _restart(ls)
    assert _diff([CLOSED, OPEN], ls, _now("2026-10-08", 9, 32)) == [], "runs once"
    ev = _diff([CLOSED, CLOSED_LATER], _restart(ls), _now("2026-10-08", 10, 6))
    assert [e["event"] for e in ev] == ["EXIT"] and ev[0]["trade_id"] == TID


def test_upgrade_after_the_strategy_already_exited_writes_entry_then_exit():
    ls = _box_shape_leg_state()
    ev = _diff([CLOSED, CLOSED_LATER], ls, _now("2026-10-08", 10, 6))
    assert [(e["event"], e["trade_id"]) for e in ev] == [("ENTRY", TID), ("EXIT", TID)]
    assert ev[1]["ref_price"] == 741.5
    assert _diff([CLOSED, CLOSED_LATER], _restart(ls), _now("2026-10-08", 10, 7)) == []


def test_upgrade_when_the_window_no_longer_holds_the_trade_counts_it_and_stays_quiet():
    ls = _box_shape_leg_state()
    assert _diff([CLOSED], ls, _now("2026-12-20", 10, 0)) == []
    assert ls["seed_open_lost"] == 1 and ls["seed_open_format"] == cs.SEED_OPEN_FORMAT
    assert ls["trades"][TID]["exit_emitted"] is True
    assert _diff([CLOSED], ls, _now("2026-12-20", 10, 1)) == [] and ls["seed_open_lost"] == 1


def test_upgrade_never_runs_on_a_live_leg():
    ls = _box_shape_leg_state()
    assert _diff([CLOSED, OPEN], ls, _now("2026-10-08", 9, 31), cfg=None) == []
    assert _diff([CLOSED, CLOSED_LATER], ls, _now("2026-10-08", 10, 6), cfg=None) == []
    assert "seed_open_format" not in ls and ls["trades"][TID]["exit_emitted"] is True


# ── 5. trade-id merge ────────────────────────────────────────────────────────────────────
def test_merge_rank_keeps_a_carried_seed_record():
    absorbed = {"seeded": True, "exit_emitted": True}
    carried = {"seeded": True, "seeded_open": True, "exit_emitted": False}
    assert cs._merge_rank(carried) > cs._merge_rank({"seeded": True, "exit_emitted": False})
    assert cs._merge_rank(carried)[0] is True and cs._merge_rank(absorbed)[0] is False


# ── 6. the report ────────────────────────────────────────────────────────────────────────
def test_shadow_legs_report_counts_and_prices_a_seeded_trade(tmp_path, capsys):
    live = cs._paths(home=str(tmp_path))
    sp = cs.shadow_paths(live)
    ls = {"trades": {}}
    events = _diff([CLOSED, OPEN], ls, _now("2026-09-29", 9, 30))
    cs._append_signals(events, sp)
    s = rpt.build_report(str(tmp_path))["legs"][LEG]
    assert (s["trades"], s["open"], s["seeded"], s["net_usd"]) == (0, 1, 1, 0.0)
    cs._append_signals(_diff([CLOSED, CLOSED_LATER], ls, _now("2026-10-08", 10, 6)), sp)
    s = rpt.build_report(str(tmp_path))["legs"][LEG]
    assert (s["trades"], s["open"], s["seeded"]) == (1, 0, 1)
    assert s["net_usd"] == round((741.5 - 738.0295) * rpt.BASE_SHARES, 2)
    assert rpt.main(["--home", str(tmp_path)]) == 0
    assert "1 carried from the leg's cold start" in capsys.readouterr().out
