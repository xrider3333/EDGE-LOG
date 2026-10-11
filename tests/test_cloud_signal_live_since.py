"""LIVE SINCE -- api/cloud_signal.py's _apply_live_since -- and the after-close "not taken" log line.
Written for ENGU-Q's return to the live book (OWNER DECISION 2026-10-09, MANAGER #102); ENGU-Q
became a no-order TRACKER again the same evening (OWNER DECISION ~20:20 MST, MANAGER #113)
before the box ever ran it live, so NO shipped leg carries live_since today. The mechanism stays,
generic, for the next leg that (re)joins the book (DIP #424 later), and is tested here on a
TEST-LOCAL live leg: ENGU-Q's own cfg (shipped as a shadow leg) without "shadow", plus
live_since 2026-10-09 -- exactly the shape it had live (LIVE_CFG below).

THE TRAP (verified on the box 2026-10-09). The box's LIVE cloud_signal state.json still held
legs.ENGUQ_335 from before 2026-09-28, when the leg left CROWN_LEGS: the 09-28 12:32 long
(ENGUQ_335-20260928T163200Z-L) with exit_emitted False -- the strategy closed it 2026-10-08
13:01 @ 746.8612 -- plus two phantom ghosts (09-17, 09-23) with exit_emitted False. Re-adding
the leg as-is would emit an EXIT for that trade on the very first tick: a SELL for a position
the book closed at 15:59 on 09-28. The owner's spec: START FLAT, no catch-up buy.

THE FIX. A live leg's cfg carries "live_since" (ENGU-Q's had "2026-10-09"). A leg whose stored
state does not carry that same live_since has it discarded and cold-starts: one SEED row, every
trade in the window absorbed (one still open at the seed included), nothing entered or exited;
then the state is stamped. A leg without the key behaves exactly as before. A SHADOW leg is never
touched (its state is its tracker history), even with the key.

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
  6. SHADOW LEGS (ENGU-Q a tracker again, 2026-10-09 ~20:20 MST): no shipped leg carries
     live_since; a shadow cfg that did is never discarded; and the box's SHADOW ENGUQ_335 state
     (seeded 2026-09-29, seed_open_format 1, the 09-28 carry closed, last stepped 2026-10-09
     09:31) simply continues through the shipped cfg and run_shadow_step: no new SEED, no
     replay of what it missed while it was not stepped, its next own trade ENTRY then EXIT.
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
LIVE_SINCE = "2026-10-09"
# the TEST-LOCAL live leg: ENGU-Q's shipped cfg (a shadow leg -- a tracker) as the live leg it was
# for a few hours of code on 2026-10-09: no "shadow", plus live_since
LIVE_CFG = dict({k: v for k, v in cs.SHADOW_LEGS[LEG].items() if k != "shadow"}, live_since=LIVE_SINCE)

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
    """LIVE_CFG with the strategy swapped for `trades` and a short window."""
    cfg = dict(LIVE_CFG, strategy=_scripted(trades), warmup_sessions=10)
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
    assert ls["live_since"] == LIVE_SINCE and ls["seeded"] is True
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


def test_a_live_leg_does_nothing_before_its_live_since_date(tmp_path):
    """FIXER 10-10: live_since is also a DATE GATE. A step on an earlier day (a deploy that lands
    before the GO date) emits nothing, discards nothing and seeds nothing -- the earlier stint's
    state is left exactly as it was; the leg cold-starts on its live_since day as before. The
    same holds for a direct _diff_leg caller."""
    paths = _home(tmp_path)
    legs = {LEG: _cfg([ENGINE_OLD, OPEN_AT_SEED, NEW])}
    before = _leg_state(paths)
    for now in (_now("2026-10-08", 9, 45), _now("2026-10-08", 13, 30)):
        assert cs.step(now=now, legs=legs, paths=paths, fetch=False) == []
    assert _leg_state(paths) == before, "untouched until the live_since day"
    assert not os.path.exists(paths["signals_path"]) or _ledger_events(paths) == []
    ls = _box_leg_state()
    old = _trade(ENGINE_OLD[0], ENGINE_OLD[1], exit_px=ENGINE_OLD[4])
    assert cs._diff_leg(LEG, [old], ls, _now("2026-10-08", 13, 30), max_entry_age_sec=660,
                        cfg=LIVE_CFG, log=QUIET) == []
    assert ls == _box_leg_state()
    assert cs._before_live_since(LIVE_CFG, _now("2026-10-08", 23, 59)) is True
    assert cs._before_live_since(LIVE_CFG, _now("2026-10-09", 0, 0)) is False
    assert cs._before_live_since(dict(LIVE_CFG, shadow=True), _now("2026-10-08", 9, 45)) is False
    assert cs._before_live_since({}, _now("2026-10-08", 9, 45)) is False
    first = cs.step(now=_now("2026-10-09", 9, 45), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in first] == ["SEED"] and "live_since=2026-10-09" in first[0]["reason"]


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
                      bar_source="webull", cfg=LIVE_CFG, log=logs.append)
    assert [e["event"] for e in ev] == ["SEED"]
    assert ls["live_since"] == "2026-10-09" and "last_bar_epoch" not in ls
    assert len([m for m in logs if "live since 2026-10-09" in m]) == 1
    assert "3 trade record(s), 3 with an exit still owed" in logs[0]
    assert cs._diff_leg(LEG, [old], ls, _now("2026-10-09", 9, 46), max_entry_age_sec=660,
                        bar_source="webull", cfg=LIVE_CFG, log=logs.append) == []


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
            "live_since": LIVE_SINCE}


def test_an_entry_first_seen_after_the_close_gets_one_plain_log_line():
    ls = _seeded_state()
    late = _trade("2026-10-09T15:59:00-04:00", entry_px=745.12)
    logs = []
    now = _now("2026-10-09", 16, 0, 35)
    ev = cs._diff_leg(LEG, [late], ls, now, max_entry_age_sec=660, bar_source="webull",
                      cfg=LIVE_CFG, log=logs.append)
    assert ev == [] and ls["after_close_skipped"] == 1
    assert logs == [
        "[cloud-signal] ENGU-Q long signal at 15:59 ET on 2026-10-09 (ENGUQ_335) not taken: "
        "the market is closed -- the strategy's entry was first seen at 16:00:35 ET, after the "
        "16:00 close. No order."]
    # the trade's record stops a repeat, also once it closes
    closed = dict(late, still_open=False, exit_time="2026-10-12T09:45:00-04:00", exit_px=746.0)
    assert cs._diff_leg(LEG, [late], ls, _now("2026-10-09", 16, 1, 5), max_entry_age_sec=660,
                        cfg=LIVE_CFG, log=logs.append) == []
    assert cs._diff_leg(LEG, [closed], ls, _now("2026-10-12", 9, 46), max_entry_age_sec=660,
                        cfg=LIVE_CFG, log=logs.append) == []
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
                      cfg=LIVE_CFG, log=logs.append)
    assert ev == [] and ls["stale_skipped"] == 2
    assert logs == [
        "[cloud-signal] ENGU-Q long signal at 15:57 ET on 2026-10-09 (ENGUQ_335) not taken: "
        "the market is closed -- the strategy's entry was first seen at 09:34:05 ET on "
        "2026-10-12, after that session's 16:00 close. No order."]
    assert cs._diff_leg(LEG, [old, prev], ls, _now("2026-10-12", 9, 35, 5),
                        max_entry_age_sec=660, cfg=LIVE_CFG, log=logs.append) == []
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
    assert cs._diff_leg(LEG, [late], ls, now, cfg=LIVE_CFG, log=logs.append,
                        not_taken_log=False) == []
    assert logs == [] and ls["after_close_skipped"] == 1, "dropped, still recorded"
    ls = _seeded_state()
    cs._diff_leg(LEG, [late], ls, now, cfg=LIVE_CFG, log=logs.append,
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


# ── 6. shadow legs: never discarded; the box's shadow ENGUQ_335 simply continues ────────
def test_only_the_live_dip_leg_carries_live_since_and_enguq_is_a_shadow_leg():
    """OWNER DECISION 2026-10-09 ~20:20 MST (MANAGER #113): ENGU-Q is a no-order tracker --
    a shadow leg with no live_since. The one shipped leg carrying the key is the live DIP_424
    (OWNER GO 2026-10-10, MANAGER #115: 2026-10-13, its one cold start --
    tests/test_dip424_live_engine.py)."""
    assert LEG in cs.SHADOW_LEGS and LEG not in cs.CROWN_LEGS
    assert cs.SHADOW_LEGS[LEG]["shadow"] is True
    carrying = {}
    for key, cfg in list(cs.CROWN_LEGS.items()) + list(cs.SHADOW_LEGS.items()):
        if cs.LIVE_SINCE_KEY in cfg:
            carrying[key] = cfg[cs.LIVE_SINCE_KEY]
    assert carrying == {"DIP_424": "2026-10-13"} and cs.DIP_424_LIVE_SINCE == "2026-10-13"
    assert not cs.CROWN_LEGS["DIP_424"].get("shadow")


def test_a_leg_never_seen_before_seeds_with_no_earlier_state():
    """A brand-new live leg (DIP_424's first cold start): the live_since stamp records it had no
    state, and the SEED says so -- "no earlier state, starts flat", never "discarded"."""
    ls = {"trades": {}}
    assert cs._apply_live_since("NEW_1", {"live_since": "2026-10-13"}, ls, log=QUIET) is True
    assert ls["live_since_reset"]["had_state"] is False and ls["live_since_reset"]["discarded_trades"] == 0
    ev = cs._diff_leg("NEW_1", [], ls, _now("2026-10-13", 9, 30), cfg={"live_since": "2026-10-13"},
                      log=QUIET)
    assert [e["event"] for e in ev] == ["SEED"]
    assert ev[0]["reason"].endswith("; live_since=2026-10-13 (no earlier state, starts flat)")
    # a state from an earlier stint still reads "discarded" (and a stamp written before had_state
    # existed reads as discarded too)
    old = _box_leg_state()
    assert cs._apply_live_since(LEG, dict(LIVE_CFG, live_since="2026-10-13"), old, log=QUIET)
    assert old["live_since_reset"]["had_state"] is True
    assert cs._live_since_discarded(old) is True
    assert cs._live_since_discarded({"live_since_reset": {"discarded_trades": 0}}) is True


def test_a_shadow_cfg_with_live_since_never_discards_its_state():
    """A leg moved to SHADOW_LEGS with its live_since left on by mistake: its state is its tracker
    history and is never discarded -- by _apply_live_since, a direct _diff_leg, or step()."""
    ls = _box_leg_state()
    bad = dict(cs.SHADOW_LEGS[LEG], live_since=LIVE_SINCE)
    assert cs._apply_live_since(LEG, bad, ls, log=QUIET) is False
    assert ls == _box_leg_state(), "not one field touched"
    logs = []
    old = _trade(ENGINE_OLD[0], ENGINE_OLD[1], exit_px=ENGINE_OLD[4])
    ev = cs._diff_leg(LEG, [old], ls, _now("2026-10-09", 9, 45), max_entry_age_sec=660,
                      bar_source="webull", cfg=bad, log=logs.append)
    assert "live_since" not in ls and not [m for m in logs if "live since" in m]
    assert "SEED" not in [e["event"] for e in ev], "no cold start: the tracker keeps its history"


def _box_shadow_state():
    """legs.ENGUQ_335 in the box's SHADOW state.json (the tracker's own store): seeded 2026-09-29
    09:30 holding the 09-28 12:32 long, carried (seed_open_format 1, its seeded ENTRY written) and
    closed by the strategy 2026-10-08 13:01 (its EXIT written); last stepped 2026-10-09 09:31."""
    last = int(pd.Timestamp("2026-10-09 09:30", tz=cs.TZ).tz_convert("UTC").timestamp())
    return {
        "trades": {
            OLD_TID: {"entry_time": "2026-09-28T12:32:00-04:00", "side": "long",
                      "entry_px": 738.0295, "shares": 135, "exit_emitted": True,
                      "exit_time": "2026-10-08T13:01:00-04:00", "exit_px": 746.8612,
                      "seeded": True, "seeded_open": True, "size": 1.0, "keel_size": ""},
        },
        "seeded": True, "seed_open_format": cs.SEED_OPEN_FORMAT, "key_format": cs.TRADE_KEY_FORMAT,
        "last_bar_epoch": last, "asof": "2026-10-09T09:31:05-04:00"}


def test_the_box_s_shadow_enguq_state_simply_continues(tmp_path):
    """The tracker resumes on the shipped shadow cfg through run_shadow_step (the box's own path),
    the next session (Monday 10-12) after a gap: no new SEED, nothing re-emitted for the closed
    09-28 carry, nothing replayed for the trades it missed while it was not stepped (a 10-09 trade
    closed that day, another still open), and its next own trade is an ENTRY then an EXIT."""
    days = ["2026-09-28", "2026-10-08", "2026-10-09", "2026-10-12"]
    rows = []
    for d in days:
        start = pd.Timestamp(f"{d} 09:30", tz=cs.TZ)
        for b in range(390):
            t = start + pd.Timedelta(minutes=b)
            px = 740.0 + 0.01 * b
            rows.append((int(t.tz_convert("UTC").timestamp()), px, px + 0.05, px - 0.05, px + 0.01, 1000.0))
    live = cs._paths(home=str(tmp_path))
    os.makedirs(live["ohlc_dir"], exist_ok=True)
    pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).to_csv(
        os.path.join(live["ohlc_dir"], "QQQ_1m.csv"), index=False)
    sp = cs.shadow_paths(live)
    os.makedirs(sp["state_dir"], exist_ok=True)
    with open(sp["state_path"], "w", encoding="utf-8") as f:
        json.dump({"legs": {LEG: _box_shadow_state()}}, f)
    missed_closed = ("2026-10-09T11:00:00-04:00", "2026-10-09T14:00:00-04:00", -1, 742.0, 741.0)
    missed_open = ("2026-10-09T15:00:00-04:00", None, 1, 743.0, None)
    mon = ("2026-10-12T09:40:00-04:00", "2026-10-12T10:10:00-04:00", 1, 740.10, 740.40)
    cfg = dict(cs.SHADOW_LEGS[LEG], strategy=_scripted([ENGINE_OLD, missed_closed, missed_open, mon]),
               warmup_sessions=10)
    assert "live_since" not in cfg and cfg["shadow"] is True

    def tick(day, hh, mm, ss=10):
        return cs.run_shadow_step(now=_now(day, hh, mm, ss), fetch=False, live_legs={},
                                  shadow_legs={LEG: cfg}, live_paths=live, log=QUIET)

    assert tick("2026-10-12", 9, 35) == [], "no SEED, no carry, no replay"
    ls = json.load(open(sp["state_path"], encoding="utf-8"))["legs"][LEG]
    assert ls["seeded"] is True and ls["seed_open_format"] == cs.SEED_OPEN_FORMAT
    assert "live_since" not in ls and "live_since_reset" not in ls
    assert ls["trades"][OLD_TID] == _box_shadow_state()["trades"][OLD_TID], "the 09-28 carry untouched"
    assert ls["stale_skipped"] == 2, "the two trades it missed are recorded, never emitted"
    entry = tick("2026-10-12", 9, 45)
    want = T.make(LEG, mon[0], "long")
    assert [(e["event"], e["trade_id"]) for e in entry] == [("ENTRY", want)]
    exit_ = tick("2026-10-12", 10, 11)
    assert [(e["event"], e["trade_id"]) for e in exit_] == [("EXIT", want)]
    assert tick("2026-10-12", 15, 0) == [], "the missed open trade never exits either"
    assert _ledger_events(sp) == ["ENTRY", "EXIT"]
    assert not os.path.exists(live["signals_path"]), "nothing in the LIVE ledger"
