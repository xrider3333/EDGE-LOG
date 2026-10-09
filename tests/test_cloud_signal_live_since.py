"""ENGU-Q BACK ON THE LIVE BOOK (OWNER DECISION 2026-10-09, via MANAGER #102) -- the engine half:
api/cloud_signal.py's LIVE SINCE (_apply_live_since) and the after-close "not taken" log line.

THE TRAP (verified on the box 2026-10-09). The box's LIVE cloud_signal state.json still held
legs.ENGUQ_335 from before 2026-09-28, when the leg left CROWN_LEGS: the 09-28 12:32 long
(ENGUQ_335-20260928T163200Z-L) with exit_emitted False -- the strategy closed it 2026-10-08
13:01 @ 746.8612 -- plus two phantom ghosts (09-17, 09-23) with exit_emitted False. Re-adding
the leg as-is would emit an EXIT for that trade on the very first tick: a SELL for a position
the book closed at 15:59 on 09-28. The owner's spec: START FLAT, no catch-up buy.

THE FIX. CROWN_LEGS["ENGUQ_335"]["live_since"] = "2026-10-09". A leg whose stored state does
not carry that same live_since has it discarded and cold-starts: one SEED row, every trade in
the window absorbed (one still open at the seed included), nothing entered or exited; then the
state is stamped. A leg without the key behaves exactly as before.

COVERS:
  1. The box's own state shape -> the first step emits exactly ["SEED"] (no ENTRY, no EXIT),
     the old records and ghosts are gone, the stamp and the discard record are on the state;
     a repeat tick emits []; the trade open at the seed closing later emits nothing; a
     brand-new entry after the seed emits ENTRY, then its EXIT, normally.
  2. The same state on a leg WITHOUT live_since: exactly today's behaviour -- which is the
     trap itself (the stale EXIT for the 09-28 trade goes out).
  3. A direct _diff_leg caller (the stream path's shape) gets the same cold start; the reset
     runs once per live_since value; a cfg without the key is never touched.
  4. A live leg's NEW entry first seen after the session close is still never emitted, but
     gets ONE plain log line (strategy, side, signal time, why); never twice; never for a
     shadow leg. The same for an entry from the PREVIOUS session first seen the next morning
     (a "stale" skip); an older stale entry (a left-edge re-mint) stays silent.
  5. step()'s own discard runs before the "no new bar" short-circuit and with no usable bar
     yet, and is saved on that same tick.
No network: every step here runs with fetch=False against a temp 1m bar cache.
"""
import json
import os
import sys
import types

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                       # noqa: E402
from api import trade_id as T                       # noqa: E402

LEG = "ENGUQ_335"
DAYS = ["2026-09-28", "2026-10-08", "2026-10-09"]
OLD_TID = "ENGUQ_335-20260928T163200Z-L"
GHOST_0917 = "ENGUQ_335-20260917T190700Z-L"
GHOST_0923 = "ENGUQ_335-20260923T180000Z-L"
QUIET = lambda *a, **k: None   # noqa: E731

# (entry_ts, exit_ts or None, side, entry_px, exit_px) -- what the strategy "takes"
ENGINE_OLD = ("2026-09-28T12:32:00-04:00", "2026-10-08T13:01:00-04:00", 1, 738.0295, 746.8612)
OPEN_AT_SEED = ("2026-10-09T09:40:00-04:00", "2026-10-09T10:05:00-04:00", 1, 741.0, 742.5)
NEW = ("2026-10-09T10:15:00-04:00", "2026-10-09T11:00:00-04:00", -1, 743.0, 742.0)


def _now(day, hh, mm, ss=10):
    return pd.Timestamp(f"{day} {hh:02d}:{mm:02d}:{ss:02d}", tz=cs.TZ).to_pydatetime()


def _bars():
    rows = []
    for d in DAYS:
        start = pd.Timestamp(f"{d} 09:30", tz=cs.TZ)
        for b in range(390):
            t = start + pd.Timedelta(minutes=b)
            px = 740.0 + 0.01 * b
            rows.append((int(t.tz_convert("UTC").timestamp()), px, px + 0.05, px - 0.05,
                         px + 0.01, 1000.0))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def _scripted(trades):
    """A strategy that takes exactly `trades` whenever their entry bar is in the window it is
    handed -- matched by bar TIME, so the rolling window's start never moves a trade. A trade
    whose exit bar is not in the window yet is still open (marked at the last close, which
    run_leg_trades reads as open)."""
    mod = types.ModuleType("live_since_scripted")
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        pos = {pd.Timestamp(x).value: i for i, x in enumerate(index)}
        n = len(closes)
        out = []
        for entry_ts, exit_ts, side, entry_px, exit_px in trades:
            i = pos.get(pd.Timestamp(entry_ts).value)
            if i is None:
                continue
            j = pos.get(pd.Timestamp(exit_ts).value) if exit_ts else None
            if j is None:
                out.append((i, n - 1, (float(closes[n - 1]) - entry_px) * side, side, entry_px))
            else:
                out.append((i, j, (exit_px - entry_px) * side, side, entry_px))
        return {"trades": out if return_trades else None, "num_trades": len(out),
                "total_pnl": sum(t[2] for t in out), "win_rate": 0, "profit_factor": 0,
                "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}

    mod.run_backtest = run_backtest
    return mod


def _cfg(trades, live_since=True):
    """The SHIPPED ENGUQ_335 cfg with the strategy swapped for `trades` and a short window."""
    cfg = dict(cs.CROWN_LEGS[LEG], strategy=_scripted(trades), warmup_sessions=10)
    if not live_since:
        cfg.pop("live_since")
    return cfg


def _box_leg_state():
    """legs.ENGUQ_335 in the box's LIVE state.json as of 2026-10-09 (from before 09-28)."""
    last = int(pd.Timestamp("2026-09-28 15:59", tz=cs.TZ).tz_convert("UTC").timestamp())
    return {
        "trades": {
            GHOST_0917: {"entry_time": "2026-09-17T15:07:00-04:00", "side": "long",
                         "entry_px": 716.8592, "shares": 139, "exit_emitted": False,
                         "exit_time": None, "exit_px": None, "skipped": None, "ghost": True},
            GHOST_0923: {"entry_time": "2026-09-23T14:00:00-04:00", "side": "long",
                         "entry_px": 741.1147, "shares": 134, "exit_emitted": False,
                         "exit_time": None, "exit_px": None, "skipped": None, "ghost": True},
            OLD_TID: {"entry_time": "2026-09-28T12:32:00-04:00", "side": "long",
                      "entry_px": 738.0295, "shares": 135, "exit_emitted": False,
                      "exit_time": None, "exit_px": None, "skipped": None, "size": 1.0,
                      "keel_size": ""},
        },
        "seeded": True, "key_format": cs.TRADE_KEY_FORMAT,
        "last_bar_epoch": last, "asof": "2026-09-28T15:59:00-04:00"}


def _home(tmp_path):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    os.makedirs(paths["state_dir"], exist_ok=True)
    _bars().to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        json.dump({"legs": {LEG: _box_leg_state()}}, f)
    return paths


def _leg_state(paths):
    with open(paths["state_path"], encoding="utf-8") as f:
        return json.load(f)["legs"][LEG]


def _ledger_events(paths):
    import csv
    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        return [r["event"] for r in csv.DictReader(f)]


# ── 1. the box's state: SEED only, starts flat, then trades normally ────────────────────
def test_box_state_cold_starts_to_one_seed_then_trades_normally(tmp_path):
    paths = _home(tmp_path)
    legs = {LEG: _cfg([ENGINE_OLD, OPEN_AT_SEED, NEW])}

    first = cs.step(now=_now("2026-10-09", 9, 45), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in first] == ["SEED"], "no ENTRY, no EXIT -- start flat"
    seed = first[0]
    assert "live_since=2026-10-09" in seed["reason"]
    assert "open_at_seed=long @ 741.0" in seed["reason"], "the open trade is absorbed, not bought"
    ls = _leg_state(paths)
    assert ls["live_since"] == cs.ENGUQ_LIVE_SINCE == "2026-10-09" and ls["seeded"] is True
    assert not ({OLD_TID, GHOST_0917, GHOST_0923} - {OLD_TID}) & set(ls["trades"]), "ghosts gone"
    # the 09-28 trade is in the engine's window again -- absorbed as history, exit done
    assert ls["trades"][OLD_TID]["exit_emitted"] is True and ls["trades"][OLD_TID]["seeded"]
    assert all(r["exit_emitted"] for r in ls["trades"].values())
    reset = ls["live_since_reset"]
    assert reset["discarded_trades"] == 3
    assert reset["discarded_exit_owed"] == sorted([GHOST_0917, GHOST_0923, OLD_TID])
    assert reset["at"] == _now("2026-10-09", 9, 45).isoformat()

    assert cs.step(now=_now("2026-10-09", 9, 45), legs=legs, paths=paths, fetch=False) == []
    assert cs.step(now=_now("2026-10-09", 9, 46), legs=legs, paths=paths, fetch=False) == [], \
        "a repeat tick emits nothing"
    assert cs.step(now=_now("2026-10-09", 10, 6), legs=legs, paths=paths, fetch=False) == [], \
        "the trade open at the seed closes with NO exit -- the book never entered it"
    assert _leg_state(paths)["live_since_reset"] == reset, "the discard ran once"

    entry = cs.step(now=_now("2026-10-09", 10, 16), legs=legs, paths=paths, fetch=False)
    want = T.make(LEG, NEW[0], "short")
    assert [(e["event"], e["side"], e["trade_id"]) for e in entry] == [("ENTRY", "short", want)]
    assert entry[0]["ref_price"] == 743.0
    exit_ = cs.step(now=_now("2026-10-09", 11, 1), legs=legs, paths=paths, fetch=False)
    assert [(e["event"], e["trade_id"]) for e in exit_] == [("EXIT", want)]
    assert exit_[0]["ref_price"] == 742.0
    assert _ledger_events(paths) == ["SEED", "ENTRY", "EXIT"]


# ── 2. the same state on a leg WITHOUT live_since: unchanged -- the trap itself ─────────
def test_a_leg_without_live_since_is_unchanged_which_is_the_trap(tmp_path):
    paths = _home(tmp_path)
    legs = {LEG: _cfg([ENGINE_OLD, OPEN_AT_SEED, NEW], live_since=False)}
    ev = cs.step(now=_now("2026-10-09", 9, 45), legs=legs, paths=paths, fetch=False)
    assert [(e["event"], e["trade_id"]) for e in ev] == [
        ("EXIT", OLD_TID), ("ENTRY", T.make(LEG, OPEN_AT_SEED[0], "long"))], \
        "today's rule on the old state: the 09-28 trade's stale EXIT goes out first"
    assert ev[0]["ref_price"] == 746.8612
    ls = _leg_state(paths)
    assert "live_since" not in ls and "live_since_reset" not in ls
    assert ls["trades"][GHOST_0917]["exit_emitted"] is False, "ghosts untouched as before"


# ── 3. direct _diff_leg callers, once per value, no key -> untouched ────────────────────
def _trade(entry_ts, exit_ts=None, side="long", entry_px=738.0295, exit_px=None):
    return {"entry_time": entry_ts, "side": side, "entry_px": entry_px, "shares": 135,
            "still_open": exit_ts is None, "exit_time": exit_ts, "exit_px": exit_px,
            "size": 1.0}


def test_a_direct_diff_leg_caller_gets_the_same_cold_start():
    ls = _box_leg_state()
    old = _trade(ENGINE_OLD[0], ENGINE_OLD[1], exit_px=ENGINE_OLD[4])
    logs = []
    ev = cs._diff_leg(LEG, [old], ls, _now("2026-10-09", 9, 45), max_entry_age_sec=660,
                      bar_source="webull", cfg=cs.CROWN_LEGS[LEG], log=logs.append)
    assert [e["event"] for e in ev] == ["SEED"]
    assert ls["live_since"] == "2026-10-09" and "last_bar_epoch" not in ls
    assert len([m for m in logs if "live since 2026-10-09" in m]) == 1
    assert "3 trade record(s), 3 with an exit still owed" in logs[0]
    assert cs._diff_leg(LEG, [old], ls, _now("2026-10-09", 9, 46), max_entry_age_sec=660,
                        bar_source="webull", cfg=cs.CROWN_LEGS[LEG], log=logs.append) == []


def test_live_since_resets_once_per_value_and_never_without_the_key():
    ls = _box_leg_state()
    assert cs._apply_live_since(LEG, {}, ls, log=QUIET) is False
    assert cs._apply_live_since(LEG, None, ls, log=QUIET) is False
    assert ls == _box_leg_state(), "no key: not one field touched"
    cfg = {"live_since": "2026-10-09"}
    assert cs._apply_live_since(LEG, cfg, ls, log=QUIET) is True
    assert set(ls) == {"trades", "live_since", "live_since_reset"} and ls["trades"] == {}
    assert cs._apply_live_since(LEG, cfg, ls, log=QUIET) is False, "stamped: never again"
    ls["seeded"] = True
    assert cs._apply_live_since(LEG, {"live_since": "2026-11-02"}, ls, log=QUIET) is True, \
        "a new live_since value is a new stint"
    assert ls["live_since_reset"]["previous_live_since"] == "2026-10-09"


# ── 4. after the close: never emitted, never silent ─────────────────────────────────────
def _seeded_state():
    return {"trades": {}, "seeded": True, "key_format": cs.TRADE_KEY_FORMAT,
            "live_since": cs.ENGUQ_LIVE_SINCE}


def test_an_entry_first_seen_after_the_close_gets_one_plain_log_line():
    ls = _seeded_state()
    late = _trade("2026-10-09T15:59:00-04:00", entry_px=745.12)
    logs = []
    now = _now("2026-10-09", 16, 0, 35)
    ev = cs._diff_leg(LEG, [late], ls, now, max_entry_age_sec=660, bar_source="webull",
                      cfg=cs.CROWN_LEGS[LEG], log=logs.append)
    assert ev == [] and ls["after_close_skipped"] == 1
    assert logs == [
        "[cloud-signal] ENGU-Q long signal at 15:59 ET on 2026-10-09 (ENGUQ_335) not taken: "
        "the market is closed -- the strategy's entry was first seen at 16:00:35 ET, after the "
        "16:00 close. No order."]
    # the trade's record stops a repeat, also once it closes
    closed = dict(late, still_open=False, exit_time="2026-10-12T09:45:00-04:00", exit_px=746.0)
    assert cs._diff_leg(LEG, [late], ls, _now("2026-10-09", 16, 1, 5), max_entry_age_sec=660,
                        cfg=cs.CROWN_LEGS[LEG], log=logs.append) == []
    assert cs._diff_leg(LEG, [closed], ls, _now("2026-10-12", 9, 46), max_entry_age_sec=660,
                        cfg=cs.CROWN_LEGS[LEG], log=logs.append) == []
    assert len(logs) == 1


def test_a_shadow_leg_s_after_close_entry_stays_quiet():
    ls = {"trades": {}, "seeded": True, "key_format": cs.TRADE_KEY_FORMAT,
          "seed_open_format": cs.SEED_OPEN_FORMAT}
    logs = []
    ev = cs._diff_leg("NOISE_422_PLAIN", [_trade("2026-10-09T15:55:00-04:00")], ls,
                      _now("2026-10-09", 16, 0, 35), cfg=cs.SHADOW_LEGS["NOISE_422_PLAIN"],
                      log=logs.append)
    assert ev == [] and ls["after_close_skipped"] == 1 and logs == []


def test_an_entry_from_the_previous_session_first_seen_next_morning_gets_one_line():
    """phantom_safe: a 15:5x setup's 10-bar fill window runs past the last bar, so a later real
    entry only shows once the NEXT session's bars finish that window -- a "stale" skip, which
    used to be counted only. It now gets the same one line; an older stale entry (the rolling
    window's left edge re-minting a trade) stays silent."""
    ls = _seeded_state()
    prev = _trade("2026-10-09T15:57:00-04:00", entry_px=745.12)          # Friday
    old = _trade("2026-10-01T10:00:00-04:00", "2026-10-01T11:00:00-04:00", exit_px=740.0)
    logs = []
    now = _now("2026-10-12", 9, 34, 5)                                   # Monday's open
    ev = cs._diff_leg(LEG, [old, prev], ls, now, max_entry_age_sec=660, bar_source="webull",
                      cfg=cs.CROWN_LEGS[LEG], log=logs.append)
    assert ev == [] and ls["stale_skipped"] == 2
    assert logs == [
        "[cloud-signal] ENGU-Q long signal at 15:57 ET on 2026-10-09 (ENGUQ_335) not taken: "
        "the market is closed -- the strategy's entry was first seen at 09:34:05 ET on "
        "2026-10-12, after that session's 16:00 close. No order."]
    assert cs._diff_leg(LEG, [old, prev], ls, _now("2026-10-12", 9, 35, 5),
                        max_entry_age_sec=660, cfg=cs.CROWN_LEGS[LEG], log=logs.append) == []
    assert len(logs) == 1, "once per trade"
    # a shadow leg: quiet
    shadow_logs = []
    cs._diff_leg("NOISE_422_PLAIN", [prev], {"trades": {}, "seeded": True,
                                             "key_format": cs.TRADE_KEY_FORMAT,
                                             "seed_open_format": cs.SEED_OPEN_FORMAT},
                 now, cfg=cs.SHADOW_LEGS["NOISE_422_PLAIN"], log=shadow_logs.append)
    assert shadow_logs == []


def test_not_taken_log_routes_or_drops_the_line():
    """The stream path's dry runs (throwaway state copies) pass not_taken_log: False drops the
    line, a callable receives it instead of `log`."""
    late = _trade("2026-10-09T15:59:00-04:00")
    now = _now("2026-10-09", 16, 0, 35)
    logs, got = [], []
    ls = _seeded_state()
    assert cs._diff_leg(LEG, [late], ls, now, cfg=cs.CROWN_LEGS[LEG], log=logs.append,
                        not_taken_log=False) == []
    assert logs == [] and ls["after_close_skipped"] == 1, "dropped, still recorded"
    ls = _seeded_state()
    cs._diff_leg(LEG, [late], ls, now, cfg=cs.CROWN_LEGS[LEG], log=logs.append,
                 not_taken_log=got.append)
    assert logs == [] and len(got) == 1 and "not taken: the market is closed" in got[0]


# ── 5. step()'s own discard: before the short-circuit, saved with no usable bar ─────────
def test_step_discards_the_old_state_with_no_usable_bar_yet(tmp_path):
    paths = _home(tmp_path)
    os.remove(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"))          # no 1m bars at all yet
    legs = {LEG: _cfg([ENGINE_OLD, OPEN_AT_SEED, NEW])}
    assert cs.step(now=_now("2026-10-09", 9, 31), legs=legs, paths=paths, fetch=False) == []
    ls = _leg_state(paths)
    assert ls["live_since"] == "2026-10-09" and ls["trades"] == {}, "saved on that same tick"
    assert "seeded" not in ls and ls["live_since_reset"]["discarded_trades"] == 3
    _bars().to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)
    ev = cs.step(now=_now("2026-10-09", 9, 45), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in ev] == ["SEED"], "then the normal cold start, nothing else"


def test_step_discards_the_old_state_before_the_no_new_bar_short_circuit(tmp_path):
    """The old state's last_bar_epoch equals this tick's newest bar: without step()'s own
    discard the leg would short-circuit and keep the stale records (and their owed EXIT) on
    disk for another bar."""
    paths = _home(tmp_path)
    with open(paths["state_path"], encoding="utf-8") as f:
        state = json.load(f)
    state["legs"][LEG]["last_bar_epoch"] = int(
        pd.Timestamp("2026-10-09 09:44", tz=cs.TZ).tz_convert("UTC").timestamp())
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        json.dump(state, f)
    legs = {LEG: _cfg([ENGINE_OLD, OPEN_AT_SEED, NEW])}
    ev = cs.step(now=_now("2026-10-09", 9, 45), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in ev] == ["SEED"]
    ls = _leg_state(paths)
    assert ls["live_since"] == "2026-10-09" and not ({GHOST_0917, GHOST_0923} & set(ls["trades"]))
