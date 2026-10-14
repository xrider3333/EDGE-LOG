"""tests/test_live_parity_check.py -- tools/live_parity_check.py, the NIGHTLY PARITY CHECK
(OWNER ORDER 2026-10-14 via MANAGER #163, after the live ORB leg silently dropped five trades
09-21..09-25).

Synthetic inputs only: every home is a tmp_path, nothing touches the network or a live path, and
the push is a recording fake. Most tests stub the replay (the comparison logic is the subject);
test_real_orb_replay_* runs the engine's own path (cloud_signal.leg_decision_trades ->
run_leg_trades -> ORB_3_6_R6.py) on a synthetic QQQ 5m cache.
"""
import csv
import datetime as dt
import json
import os

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs
from api import market_calendar, ntfy_push
from api import trade_id as TID
import tools.live_parity_check as LP

TZ = cs._zi(cs.TZ)
DAY = dt.date(2026, 9, 21)              # the first silent ORB drop
NOW = dt.datetime(2026, 9, 21, 16, 25, tzinfo=TZ)
ORB_CFG = dict(cs.CROWN_LEGS["ORB_R6"])

BROKER_COLS = ["ts_et", "leg", "intent", "side", "shares", "signal_id", "client_order_id", "mode",
               "ok", "sent", "shadow_px", "broker_fill_px", "slippage", "reason", "duplicate",
               "host_id", "outcome"]


# ── fixtures / builders ──────────────────────────────────────────────────────────────────
def at(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=TZ)


def eng_trade(side, entry, exit_=None, slot=None):
    """A trade dict in run_leg_trades' shape."""
    t = {"side": side, "entry_time": entry.isoformat(), "entry_px": 700.0, "shares": 142,
         "exit_time": exit_.isoformat() if exit_ else None, "exit_px": 701.0 if exit_ else None,
         "still_open": exit_ is None, "size": 1.0, "entry_bar": 0}
    if slot:
        t["slot"] = slot
    return t


def sig_row(leg, event, side, ref, entry=None, emitted=None, reason="", tid=None, slot=None):
    entry = entry or ref
    if tid is None and event in ("ENTRY", "EXIT", "VOID_ENTRY"):
        tid = TID.make(leg, entry, side, slot=slot)
    return {"emitted_at": (emitted or ref + dt.timedelta(minutes=5, seconds=5)).isoformat(),
            "leg": leg, "event": event, "side": side if event != "SEED" else "",
            "ref_time": ref.isoformat() if event != "SEED" else "", "ref_price": "700.0",
            "shares": "142", "reason": reason, "bar_source": "webull", "trade_id": tid or "",
            "size": "1.0"}


def seed_row(leg, when):
    return {"emitted_at": when.isoformat(), "leg": leg, "event": "SEED", "side": "",
            "ref_time": "", "ref_price": "", "shares": "", "reason": "cold start", "trade_id": ""}


def broker_row(tid, intent, ok=True, fill="700.10", outcome="OK", reason="", mode="PAPER",
               sent=None, leg="ORB", when=None):
    return {"ts_et": (when or at(DAY, "10:00")).strftime("%Y-%m-%d %H:%M:%S"), "leg": leg,
            "intent": intent, "side": "BUY", "shares": "10",
            "signal_id": TID.broker_signal_base(tid, intent), "client_order_id": "",
            "mode": mode, "ok": str(bool(ok)), "sent": str(bool(ok if sent is None else sent)),
            "shadow_px": "700.0", "broker_fill_px": fill if ok else "", "slippage": "",
            "reason": reason, "duplicate": "False", "host_id": "box", "outcome": outcome}


def _write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def make_home(tmp_path, signals=None, broker=None, cache=True):
    home = str(tmp_path / "home")
    p = LP.parity_paths(home)
    os.makedirs(p["ohlc_dir"], exist_ok=True)
    os.makedirs(p["exec_dir"], exist_ok=True)
    if cache:
        # a present (tiny) cache: the stubbed replay ignores it, the check only needs it readable
        t0 = int(at(DAY, "09:30").timestamp())
        pd.DataFrame({"time": [t0, t0 + 300], "open": [700.0, 700.1], "high": [700.5, 700.6],
                      "low": [699.5, 699.6], "close": [700.1, 700.2],
                      "volume": [1000.0, 1000.0]}).to_csv(os.path.join(p["ohlc_dir"], "QQQ_5m.csv"),
                                                          index=False)
    if signals is not None:
        _write_csv(p["signals_path"], cs.SIGNAL_COLS, signals)
    if broker is not None:
        _write_csv(p["broker_orders_csv"], BROKER_COLS, broker)
    return home


def stub_replay(by_leg, calls=None):
    def _replay(key, cfg, day, paths, bars):
        if calls is not None:
            calls.append(key)
        return {"trades": list(by_leg.get(key, [])), "error": None, "bars": 78, "complete": True}
    return _replay


class Pusher:
    def __init__(self, result=(True, "HTTP 200")):
        self.notes, self.result = [], result

    def __call__(self, note):
        self.notes.append(note)
        return self.result


def run(home, trades, legs=None, pusher=None, push=True, calls=None, now=NOW, day=DAY):
    lines = []
    legs = legs if legs is not None else {"ORB_R6": ORB_CFG}
    doc = LP.run_check(home, day, push=push, now=now, log=lines.append, legs=legs, skipped={},
                       replay=stub_replay(trades, calls), pusher=pusher or Pusher())
    return doc, lines


def kinds(doc):
    return sorted(f["kind"] for f in doc["findings"])


ORB_SEED = seed_row("ORB_R6", dt.datetime(2026, 9, 9, 11, 39, tzinfo=TZ))


# ── (i) the 09-21 case: an engine trade with no live signal ──────────────────────────────
def test_engine_trade_with_no_live_signal_is_engine_only_and_pushes_once(tmp_path):
    home = make_home(tmp_path, signals=[ORB_SEED], broker=[])
    pusher = Pusher()
    doc, lines = run(home, {"ORB_R6": [eng_trade("long", at(DAY, "09:40"), at(DAY, "15:55"))]},
                     pusher=pusher)
    assert kinds(doc) == ["ENGINE_ONLY"]           # its 15:55 exit is folded into the one finding
    f = doc["findings"][0]
    assert (f["leg"], f["event"], f["side"], f["hhmm"]) == ("ORB_R6", "ENTRY", "long", "09:40")
    # one log line naming leg, side and the bar time
    hits = [ln for ln in lines if "ENGINE_ONLY" in ln]
    assert len(hits) == 1 and "ORB_R6 entry long 09:40" in hits[0]
    # ONE plain push naming 'ORB 09:40 long' -- on the owner's clock (Arizona), as every plain push
    assert len(pusher.notes) == 1
    note = pusher.notes[0]
    owner_clock = ntfy_push.hhmm(at(DAY, "09:40"), now=at(DAY, "09:40"))
    assert owner_clock == "06:40"
    assert f"ORB {owner_clock} long" in note["message"]
    assert note["priority"] == "high" and note["title"] == "Live vs backtest: CHECK NOW"
    assert ntfy_push.lint(note) == []
    assert doc["push"]["sent"] is True and doc["ok"] is False


def test_engine_only_names_the_live_engines_own_skip_reason(tmp_path):
    home = make_home(tmp_path, signals=[ORB_SEED], broker=[])
    tr = eng_trade("long", at(DAY, "09:40"), at(DAY, "15:55"))
    tid = cs._entry_key("ORB_R6", tr)
    p = LP.parity_paths(home)
    os.makedirs(p["state_dir"], exist_ok=True)
    with open(p["state_path"], "w", encoding="utf-8") as fh:
        json.dump({"legs": {"ORB_R6": {"trades": {tid: {"skipped": "late"}}}}}, fh)
    doc, _ = run(home, {"ORB_R6": [tr]})
    assert doc["findings"][0]["engine_skip"] == "late"
    assert "skipped as 'late'" in doc["findings"][0]["detail"]


# ── (ii) everything matches -> no push, 'parity OK' ──────────────────────────────────────
def _matched_inputs(day=DAY, entry="09:40", exit_="15:55", side="long"):
    e, x = at(day, entry), at(day, exit_)
    tid = TID.make("ORB_R6", e, side)
    signals = [ORB_SEED, sig_row("ORB_R6", "ENTRY", side, e),
               sig_row("ORB_R6", "EXIT", side, x, entry=e, reason="strategy_exit; eod_settle")]
    broker = [broker_row(tid, "OPEN"), broker_row(tid, "CLOSE")]
    return signals, broker, [eng_trade(side, e, x)]


def test_all_matched_means_no_push_and_a_parity_ok_line(tmp_path):
    signals, broker, trades = _matched_inputs()
    home = make_home(tmp_path, signals=signals, broker=broker)
    pusher = Pusher()
    doc, lines = run(home, {"ORB_R6": trades}, pusher=pusher)
    assert doc["findings"] == [] and doc["ok"] is True
    assert pusher.notes == []
    assert doc["push"]["sent"] is None and doc["push"]["wanted"] is False
    assert any("parity OK" in ln for ln in lines)
    assert doc["legs"]["ORB_R6"]["matched"] == 2


# ── (iii) a live row the replay lacks -> LIVE_ONLY ───────────────────────────────────────
def test_live_row_the_replay_lacks_is_live_only(tmp_path):
    signals, broker, _trades = _matched_inputs(entry="10:00", exit_="15:55", side="short")
    home = make_home(tmp_path, signals=signals, broker=broker)
    pusher = Pusher()
    doc, lines = run(home, {"ORB_R6": []}, pusher=pusher)
    assert kinds(doc) == ["LIVE_ONLY"]              # its live EXIT is folded into the same finding
    f = doc["findings"][0]
    assert (f["event"], f["side"], f["hhmm"]) == ("ENTRY", "short", "10:00")
    assert "its live exit at the 15:55 bar" in f["detail"]
    assert len(pusher.notes) == 1 and "is not in the backtest" in pusher.notes[0]["message"]


# ── (iv) a bar restated 5 minutes -> TIME_DIFF, not ENGINE_ONLY ──────────────────────────
def test_bar_restated_five_minutes_is_time_diff_not_engine_only(tmp_path):
    signals, broker, _ = _matched_inputs(entry="09:40")
    home = make_home(tmp_path, signals=signals, broker=broker)
    pusher = Pusher()
    doc, _ = run(home, {"ORB_R6": [eng_trade("long", at(DAY, "09:45"), at(DAY, "15:55"))]},
                 pusher=pusher)
    assert kinds(doc) == ["TIME_DIFF"]
    f = doc["findings"][0]
    assert f["event"] == "ENTRY" and f["minutes"] == -5 and f["hhmm"] == "09:45"
    # restatements alone are a low-priority heads-up, still one push
    assert len(pusher.notes) == 1 and pusher.notes[0]["priority"] == "low"
    assert ntfy_push.lint(pusher.notes[0]) == []


def test_more_than_thirty_minutes_apart_is_a_miss_and_an_extra(tmp_path):
    signals, broker, _ = _matched_inputs(entry="09:40")
    home = make_home(tmp_path, signals=signals, broker=broker)
    doc, _ = run(home, {"ORB_R6": [eng_trade("long", at(DAY, "10:15"), at(DAY, "15:55"))]})
    assert kinds(doc) == ["ENGINE_ONLY", "LIVE_ONLY"]


# ── (v) a live ENTRY with no Webull fill -> NO_FILL with the broker's reason ─────────────
def test_live_entry_with_no_fill_is_no_fill_with_the_broker_reason(tmp_path):
    signals, _broker, trades = _matched_inputs()
    tid = TID.make("ORB_R6", at(DAY, "09:40"), "long")
    broker = [broker_row(tid, "OPEN", ok=False, outcome="BLOCKED", mode="BLOCKED", sent=False,
                         reason="leg 'ORB' already has an open position "
                                "(one_open_position_per_leg)"),
              broker_row(tid, "CLOSE", ok=False, outcome="BLOCKED", mode="BLOCKED", sent=False,
                         reason="nothing to close at the broker for leg 'ORB'")]
    home = make_home(tmp_path, signals=signals, broker=broker)
    pusher = Pusher()
    doc, _ = run(home, {"ORB_R6": trades}, pusher=pusher)
    assert kinds(doc) == ["NO_FILL"]                # the CLOSE of a never-filled OPEN is folded
    f = doc["findings"][0]
    assert f["event"] == "ENTRY" and f["exec_leg"] == "ORB"
    assert "BLOCKED" in f["detail"] and "one_open_position_per_leg" in f["detail"]
    assert len(pusher.notes) == 1 and "No Webull fill for ORB" in pusher.notes[0]["message"]
    assert pusher.notes[0]["priority"] == "high"


def test_no_broker_row_at_all_says_the_executor_never_acted(tmp_path):
    signals, _broker, trades = _matched_inputs()
    home = make_home(tmp_path, signals=signals, broker=[])
    doc, _ = run(home, {"ORB_R6": trades})
    assert kinds(doc) == ["NO_FILL"]
    assert "never acted" in doc["findings"][0]["detail"]


def test_a_resent_order_that_filled_counts_as_a_fill(tmp_path):
    signals, _broker, trades = _matched_inputs()
    tid = TID.make("ORB_R6", at(DAY, "09:40"), "long")
    refused = broker_row(tid, "OPEN", ok=False, outcome="REFUSED", reason="HTTP 417")
    resent = broker_row(tid, "OPEN")
    resent["signal_id"] = TID.broker_signal_base(tid, "OPEN") + "R1"
    home = make_home(tmp_path, signals=signals, broker=[refused, resent,
                                                        broker_row(tid, "CLOSE")])
    doc, _ = run(home, {"ORB_R6": trades})
    assert doc["findings"] == []


# ── (vi) a no-order tracker leg is never compared ────────────────────────────────────────
def test_order_legs_are_exactly_the_live_crown_legs():
    legs, skipped = LP.order_legs()
    assert set(legs) == {k for k, c in cs.CROWN_LEGS.items() if not c.get("shadow")}
    assert {"ORB_R6", "NOISE_382", "DIP_424"} <= set(legs)
    assert "ENGUQ_335" not in legs and "ENGUQ_335" in skipped
    for k in cs.SHADOW_LEGS:
        assert k not in legs and k in skipped


def test_a_tracker_leg_is_never_replayed_or_compared(tmp_path):
    crown = {"ORB_R6": ORB_CFG,
             "ENGUQ_335": dict(cs.SHADOW_LEGS["ENGUQ_335"])}         # carries "shadow": True
    legs, skipped = LP.order_legs(crown=crown, shadow={}, sends_orders=lambda k: True)
    assert set(legs) == {"ORB_R6"} and "ENGUQ_335" in skipped
    signals, broker, trades = _matched_inputs()
    # the tracker's rows (here even in the live ledger) and its would-be trade change nothing
    signals += [sig_row("ENGUQ_335", "ENTRY", "long", at(DAY, "11:00"))]
    home = make_home(tmp_path, signals=signals, broker=broker)
    calls, pusher = [], Pusher()
    doc, _ = run(home, {"ORB_R6": trades,
                        "ENGUQ_335": [eng_trade("long", at(DAY, "12:00"), at(DAY, "13:00"))]},
                 legs=legs, pusher=pusher, calls=calls)
    assert calls == ["ORB_R6"]
    assert doc["findings"] == [] and pusher.notes == []
    assert "ENGUQ_335" not in doc["legs"]
    assert doc["other_live_rows"] == {"ENGUQ_335": 1}


def test_a_leg_before_its_live_since_or_first_seed_is_not_compared(tmp_path):
    dip_cfg = dict(cs.CROWN_LEGS["DIP_424"])            # live_since 2026-10-12
    noise_cfg = dict(cs.CROWN_LEGS["NOISE_382"])
    signals = [ORB_SEED, seed_row("NOISE_382", dt.datetime(2026, 9, 24, 9, 30, tzinfo=TZ))]
    home = make_home(tmp_path, signals=signals, broker=[])
    calls = []
    doc, _ = run(home, {"DIP_424": [eng_trade("long", at(DAY, "09:30"), slot="RSI")],
                        "NOISE_382": [eng_trade("long", at(DAY, "09:40"), at(DAY, "10:05"))]},
                 legs={"DIP_424": dip_cfg, "NOISE_382": noise_cfg}, calls=calls)
    assert calls == [] and doc["findings"] == []
    assert "not live until" in doc["legs"]["DIP_424"]["why_not"]
    assert "first SEED" in doc["legs"]["NOISE_382"]["why_not"]


def test_trades_absorbed_at_a_seed_are_not_expected_live(tmp_path):
    """DIP_424's cold start on 10-13 09:30 absorbed its open positions: neither an ENTRY nor, on
    a later day, an EXIT is expected for them; that day's own 09:30 entries still are."""
    d = dt.date(2026, 10, 13)
    dip_cfg = dict(cs.CROWN_LEGS["DIP_424"])
    seed = seed_row("DIP_424", dt.datetime(2026, 10, 13, 9, 30, 29, tzinfo=TZ))
    e = at(d, "09:30")
    signals = [seed, sig_row("DIP_424", "ENTRY", "long", e, slot="STREAK")]
    tid = TID.make("DIP_424", e, "long", slot="STREAK")
    home = make_home(tmp_path, signals=signals,
                     broker=[broker_row(tid, "OPEN", leg="DIP_STREAK", when=at(d, "09:35"))])
    trades = [eng_trade("long", at(dt.date(2026, 10, 9), "09:30"), at(d, "09:30"), slot="PB"),
              eng_trade("long", e, slot="STREAK")]
    doc, _ = run(home, {"DIP_424": trades}, legs={"DIP_424": dip_cfg}, day=d,
                 now=dt.datetime(2026, 10, 13, 16, 25, tzinfo=TZ))
    assert doc["findings"] == []
    assert doc["legs"]["DIP_424"]["not_expected_live"][0]["why"] == "absorbed at the SEED"


def test_a_dip_slot_is_part_of_the_match(tmp_path):
    d = dt.date(2026, 10, 14)
    e = at(d, "09:30")
    signals = [seed_row("DIP_424", dt.datetime(2026, 10, 13, 9, 30, 29, tzinfo=TZ)),
               sig_row("DIP_424", "ENTRY", "long", e, slot="STREAK")]
    tid = TID.make("DIP_424", e, "long", slot="STREAK")
    home = make_home(tmp_path, signals=signals, broker=[broker_row(tid, "OPEN", leg="DIP_STREAK")])
    doc, _ = run(home, {"DIP_424": [eng_trade("long", e, slot="STREAK"),
                                    eng_trade("long", e, slot="GAPDN")]},
                 legs={"DIP_424": dict(cs.CROWN_LEGS["DIP_424"])}, day=d,
                 now=dt.datetime(2026, 10, 14, 16, 25, tzinfo=TZ))
    assert kinds(doc) == ["ENGINE_ONLY"]
    assert doc["findings"][0]["slot"] == "GAPDN"


def test_seed_and_levels_and_void_rows_are_not_trades(tmp_path):
    signals, broker, trades = _matched_inputs()
    signals += [sig_row("ORB_R6", "LEVELS", "long", at(DAY, "10:30"), entry=at(DAY, "09:40")),
                sig_row("ORB_R6", "VOID_ENTRY", "long", at(DAY, "11:00"))]
    home = make_home(tmp_path, signals=signals, broker=broker)
    doc, _ = run(home, {"ORB_R6": trades})
    assert doc["findings"] == []


# ── (vii) the JSON is written atomically ─────────────────────────────────────────────────
def test_json_written_atomically_beside_the_target(tmp_path, monkeypatch):
    signals, broker, trades = _matched_inputs()
    home = make_home(tmp_path, signals=signals, broker=broker)
    real_replace = os.replace
    seen = []

    def spy(src, dst):
        seen.append((src, dst))
        return real_replace(src, dst)
    monkeypatch.setattr(LP.os, "replace", spy)
    doc, _ = run(home, {"ORB_R6": trades})
    out = os.path.join(home, "cloud_signal", "parity", "2026-09-21.json")
    assert doc["_path"] == out and os.path.exists(out)
    assert len(seen) == 1 and seen[0][1] == out
    assert os.path.dirname(seen[0][0]) == os.path.dirname(out) and seen[0][0] != out
    on_disk = json.load(open(out, encoding="utf-8"))
    assert on_disk["day"] == "2026-09-21" and on_disk["ok"] is True
    assert os.listdir(os.path.dirname(out)) == ["2026-09-21.json"]      # no temp file left


def test_a_failed_rename_leaves_the_old_json_and_no_temp_file(tmp_path, monkeypatch):
    path = str(tmp_path / "parity" / "2026-09-21.json")
    LP.write_json_atomic(path, {"v": 1})

    def boom(src, dst):
        raise OSError("locked")
    monkeypatch.setattr(LP.os, "replace", boom)
    with pytest.raises(OSError):
        LP.write_json_atomic(path, {"v": 2})
    assert json.load(open(path, encoding="utf-8")) == {"v": 1}
    assert os.listdir(os.path.dirname(path)) == ["2026-09-21.json"]


def test_a_rerun_with_the_same_findings_does_not_push_again(tmp_path):
    home = make_home(tmp_path, signals=[ORB_SEED], broker=[])
    pusher = Pusher()
    trades = {"ORB_R6": [eng_trade("long", at(DAY, "09:40"), at(DAY, "15:55"))]}
    first, _ = run(home, trades, pusher=pusher)
    assert first["push"]["sent"] is True and first["push"]["sent_this_run"] is True
    for push in (True, False, True):          # catch-up run, a manual --no-push re-check, again
        doc, _lines = run(home, trades, pusher=pusher, push=push)
        assert len(pusher.notes) == 1
        assert doc["push"]["sent"] is True and doc["push"]["sent_this_run"] is False
        assert "already pushed" in doc["push"]["detail"]
        assert doc["push"]["pushed_at"] == first["push"]["pushed_at"]
    # a NEW finding the same night does push
    trades["ORB_R6"].append(eng_trade("short", at(DAY, "13:00"), at(DAY, "14:00")))
    run(home, trades, pusher=pusher)
    assert len(pusher.notes) == 2


def test_a_failed_push_is_retried_by_the_next_run(tmp_path):
    home = make_home(tmp_path, signals=[ORB_SEED], broker=[])
    trades = {"ORB_R6": [eng_trade("long", at(DAY, "09:40"), at(DAY, "15:55"))]}
    down = Pusher(result=(False, "URLError: offline"))
    doc, _ = run(home, trades, pusher=down)
    assert doc["push"]["sent"] is False and len(down.notes) == 1
    up = Pusher()
    doc, _ = run(home, trades, pusher=up)
    assert len(up.notes) == 1 and doc["push"]["sent_this_run"] is True


def test_no_push_flag_never_pushes(tmp_path):
    home = make_home(tmp_path, signals=[ORB_SEED], broker=[])
    pusher = Pusher()
    doc, _ = run(home, {"ORB_R6": [eng_trade("long", at(DAY, "09:40"))]}, pusher=pusher,
                 push=False)
    assert pusher.notes == [] and doc["push"]["detail"] == "--no-push"
    assert doc["push"]["title"] == "Live vs backtest: CHECK NOW"


# ── (viii) main never raises on missing inputs; one 'unreadable' push ────────────────────
def test_main_on_an_empty_home_writes_unreadable_and_pushes_once(tmp_path):
    home = str(tmp_path / "empty_home")
    os.makedirs(home)
    lines, pusher = [], Pusher()
    argv = ["--home", home, "--day", "2026-09-21"]
    assert LP.main(argv, log=lines.append, pusher=pusher, now=NOW) == 0
    out = os.path.join(home, "cloud_signal", "parity", "2026-09-21.json")
    doc = json.load(open(out, encoding="utf-8"))
    assert doc["findings"] and {f["kind"] for f in doc["findings"]} == {"UNREADABLE"}
    texts = " ".join(f["detail"] for f in doc["findings"])
    assert "signals.csv" in texts and "bar cache" in texts
    assert len(pusher.notes) == 1
    note = pusher.notes[0]
    assert note["title"] == "Live vs backtest: needs a fix" and note["priority"] == "default"
    assert ntfy_push.lint(note) == []
    # the timer's catch-up re-run the same night does not push a second time
    assert LP.main(argv, log=lines.append, pusher=pusher, now=NOW) == 0
    assert len(pusher.notes) == 1


def test_main_turns_a_crash_into_an_unreadable_finding(tmp_path, monkeypatch):
    home = str(tmp_path / "h")
    os.makedirs(home)

    def boom(*a, **k):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(LP, "run_check", boom)
    pusher, lines = Pusher(), []
    assert LP.main(["--home", home, "--day", "2026-09-21"], log=lines.append, pusher=pusher,
                   now=NOW) == 0
    doc = json.load(open(os.path.join(home, "cloud_signal", "parity", "2026-09-21.json"),
                         encoding="utf-8"))
    assert doc["findings"][0]["kind"] == "UNREADABLE"
    assert "synthetic failure" in doc["findings"][0]["detail"]
    assert len(pusher.notes) == 1


def test_main_exit_codes_for_bad_arguments_and_quiet_days(tmp_path):
    home = str(tmp_path / "h")
    os.makedirs(home)
    lines = []
    assert LP.main(["--home", home, "--day", "2026-13-45"], log=lines.append, now=NOW) == 1
    assert LP.main(["--home", home, "--bogus"], log=lines.append, now=NOW) == 1
    assert LP.main(["--home", home, "--day", "2026-09-22"], log=lines.append, now=NOW) == 1
    # a weekend: nothing to check, exit 0, nothing written
    assert LP.main(["--home", home, "--day", "2026-09-20", "--no-push"], log=lines.append,
                   now=NOW) == 0
    # today before the session has settled: nothing checked
    early = dt.datetime(2026, 9, 21, 15, 0, tzinfo=TZ)
    assert LP.main(["--home", home, "--day", "2026-09-21", "--no-push"], log=lines.append,
                   now=early) == 0
    assert not os.path.exists(os.path.join(home, "cloud_signal", "parity"))


def test_default_day_is_the_last_settled_session():
    assert LP.default_day(dt.datetime(2026, 9, 21, 16, 20, tzinfo=TZ)) == dt.date(2026, 9, 21)
    # the catch-up run the next morning checks the session it missed
    assert LP.default_day(dt.datetime(2026, 9, 22, 8, 0, tzinfo=TZ)) == dt.date(2026, 9, 21)
    # a Monday morning checks Friday
    assert LP.default_day(dt.datetime(2026, 9, 21, 9, 0, tzinfo=TZ)) == dt.date(2026, 9, 18)


# ── the REAL engine path: ORB_R6 through run_leg_trades on a synthetic cache ──────────────
def _synthetic_epoch_df(n_sessions=90, seed=7):
    """Deterministic QQQ-like sessions on real full session days (78 x 5m bars): a tight opening
    range, then a random walk with a per-session drift (tests/test_orb_resting_levels.py's
    generator)."""
    rng = np.random.default_rng(seed)
    rows, d, px, made = [], dt.date(2026, 3, 2), 500.0, 0
    while made < n_sessions:
        if market_calendar.is_session(d) and market_calendar.session_close_et(d) != "13:00":
            start = dt.datetime.combine(d, dt.time(9, 30), tzinfo=TZ)
            drift = rng.choice([-0.12, -0.05, 0.0, 0.05, 0.12])
            for b in range(78):
                o = px
                if b < 2:
                    step_, spread = rng.normal(0.0, 0.03), 0.10
                else:
                    step_ = drift + rng.normal(0.0, 0.18)
                    if rng.random() < 0.02:
                        step_ += rng.choice([-1.5, 1.5])
                    spread = abs(rng.normal(0.0, 0.10)) + 0.02
                c = round(o + step_, 2)
                rows.append((int((start + dt.timedelta(minutes=5 * b)).timestamp()), round(o, 2),
                             round(max(o, c) + spread, 2), round(min(o, c) - spread, 2), c,
                             float(rng.integers(1_000, 50_000))))
                px = c
            made += 1
        d += dt.timedelta(days=1)
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


@pytest.fixture(scope="module")
def orb_real(tmp_path_factory):
    """A synthetic home whose cache gives the real ORB_R6 replay a same-day trade, and that day."""
    home = str(tmp_path_factory.mktemp("orb_real") / "home")
    p = LP.parity_paths(home)
    os.makedirs(p["ohlc_dir"])
    df = _synthetic_epoch_df()
    df.to_csv(os.path.join(p["ohlc_dir"], "QQQ_5m.csv"), index=False)
    days = sorted({dt.datetime.fromtimestamp(t, TZ).date() for t in df["time"]})
    for day in reversed(days[-25:]):
        res = LP.engine_replay("ORB_R6", ORB_CFG, day, p)
        assert res["error"] is None and res["complete"] and res["bars"] == 78
        same_day = [t for t in res["trades"] if t["entry_time"][:10] == day.isoformat()
                    and (t["exit_time"] or "")[:10] == day.isoformat()]
        if same_day:
            return home, day, same_day[0]
    pytest.fail("the synthetic cache gave ORB_R6 no same-day trade in its last 25 sessions")


def test_real_orb_replay_flags_the_missing_live_trade(orb_real, tmp_path):
    home, day, t = orb_real
    p = LP.parity_paths(home)
    _write_csv(p["signals_path"], cs.SIGNAL_COLS,
               [seed_row("ORB_R6", dt.datetime(2026, 3, 2, 9, 31, tzinfo=TZ))])
    _write_csv(p["broker_orders_csv"], BROKER_COLS, [])
    pusher, lines = Pusher(), []
    now = dt.datetime.combine(day, dt.time(16, 25), tzinfo=TZ)
    doc = LP.run_check(home, day, now=now, log=lines.append, legs={"ORB_R6": ORB_CFG},
                       skipped={}, pusher=pusher)
    entry = LP._parse_ts(t["entry_time"])
    assert kinds(doc) == ["ENGINE_ONLY"]
    f = doc["findings"][0]
    assert (f["event"], f["side"], f["hhmm"]) == ("ENTRY", t["side"], f"{entry:%H:%M}")
    assert len(pusher.notes) == 1
    assert f"ORB {ntfy_push.hhmm(entry, now=entry)} {t['side']}" in pusher.notes[0]["message"]


def test_real_orb_replay_matches_the_live_rows_it_would_have_written(orb_real):
    home, day, t = orb_real
    p = LP.parity_paths(home)
    e, x = LP._parse_ts(t["entry_time"]), LP._parse_ts(t["exit_time"])
    tid = TID.make("ORB_R6", e, t["side"])
    _write_csv(p["signals_path"], cs.SIGNAL_COLS,
               [seed_row("ORB_R6", dt.datetime(2026, 3, 2, 9, 31, tzinfo=TZ)),
                sig_row("ORB_R6", "ENTRY", t["side"], e),
                sig_row("ORB_R6", "EXIT", t["side"], x, entry=e)])
    _write_csv(p["broker_orders_csv"], BROKER_COLS,
               [broker_row(tid, "OPEN"), broker_row(tid, "CLOSE")])
    pusher, lines = Pusher(), []
    now = dt.datetime.combine(day, dt.time(16, 25), tzinfo=TZ)
    doc = LP.run_check(home, day, now=now, log=lines.append, legs={"ORB_R6": ORB_CFG},
                       skipped={}, pusher=pusher)
    assert doc["findings"] == [] and pusher.notes == []
    assert any("parity OK" in ln for ln in lines)
    assert doc["legs"]["ORB_R6"]["engine_trades"]


def test_real_replay_reports_an_incomplete_session_as_unreadable(orb_real, tmp_path):
    home, day, _t = orb_real
    src = LP.parity_paths(home)
    df = pd.read_csv(os.path.join(src["ohlc_dir"], "QQQ_5m.csv"))
    cut = int(dt.datetime.combine(day, dt.time(15, 0), tzinfo=TZ).timestamp())
    short_home = str(tmp_path / "short")
    p = LP.parity_paths(short_home)
    os.makedirs(p["ohlc_dir"])
    df[df["time"] < cut].to_csv(os.path.join(p["ohlc_dir"], "QQQ_5m.csv"), index=False)
    res = LP.engine_replay("ORB_R6", ORB_CFG, day, p)
    assert res["trades"] is None and "incomplete" in res["error"]
