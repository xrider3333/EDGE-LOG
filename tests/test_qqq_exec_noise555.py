"""THREE NOISE LEGS AT ONCE (2026-11-22): NOISE (#382), NOISE555 (#555.1 keel) and NOISE545
(#545.1 keel) trade the ONE netted Webull QQQ paper account side by side.

Drives api/qqq_exec.tick() through a scripted session against a REAL OrderAdapter in PAPER mode
on test_webull_resting.FakeWebullBook (Webull's own rules: a close never sells through zero,
a short is a separate SHORT order). All three legs go long, NOISE555 flips short while the
others hold, NOISE545 exits and re-enters short, then everything is flat at the 15:59 close.
Checks, after every settled step: the book's net (the signed sum of every open lot) equals the
broker's net; Webull never refused an order (no un-split send through zero); each leg's trades
are its own rows with its own P&L; an account-rail cut is recorded against the leg it cut.
Plus the cloud_signal / books_toggle wiring of the two new legs.
"""
import csv
import datetime
import io
import json
import os
import types

import pytest

from api import books_toggle as bt
from api import cloud_signal as cs
from api import qqq_exec as qe
from api import webull_orders as WO

from test_webull_resting import FakeWebullBook

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    NY = None

NOOP = lambda *a, **k: None  # noqa: E731
DAY = "2026-09-28"


def at(h, m, s=0):
    return datetime.datetime(2026, 9, 28, h, m, s, tzinfo=NY)


class _Book(FakeWebullBook):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.refused = []

    def place_order(self, account_id, new_orders, client_combo_order_id=None):
        try:
            return super().place_order(account_id, new_orders, client_combo_order_id)
        except Exception as e:
            self.refused.append((new_orders[0]["side"], new_orders[0].get("quantity"), str(e)))
            raise


class _Clock:
    def __init__(self):
        self.now = at(9, 50)

    def time(self):
        return self.now.timestamp()

    def sleep(self, s):
        pass

    def monotonic(self):
        return self.now.timestamp()


def _wo_cfg(tmp_path, total_cap):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"].update(session_start="00:00", session_end="23:59",
                        max_shares_per_leg=100, max_total_position_shares=total_cap)
    for k, name in (("state_path", "wo_state.json"), ("paper_keys_path", "paper_keys.json"),
                    ("live_keys_path", "live_keys.json"), ("arm_live_file", "ARM_LIVE"),
                    ("kill_file", "WO_KILL")):
        cfg[k] = str(tmp_path / name)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    return cfg


def _row(emitted, leg, event, side, ref, px, tid):
    return {"emitted_at": f"{DAY}T{emitted}-04:00", "leg": leg, "event": event, "side": side,
            "ref_time": f"{DAY}T{ref}-04:00", "ref_price": px, "shares": 135, "reason": "",
            "bar_source": "webull", "trade_id": tid}


T382 = "NOISE_382-20260928T140000Z-L"
T555L = "NOISE_555-20260928T140000Z-L"
T545L = "NOISE_545-20260928T140000Z-L"
T555S = "NOISE_555-20260928T143000Z-S"
T545S = "NOISE_545-20260928T153000Z-S"

# (tick time, price, rows added at this tick)
SCRIPT = [
    (at(9, 50), 700.0, []),
    (at(10, 0, 6), 700.0, [_row("10:00:05", "NOISE_382", "ENTRY", "long", "10:00:00", 700.0, T382),
                           _row("10:00:05", "NOISE_555", "ENTRY", "long", "10:00:00", 700.0, T555L),
                           _row("10:00:05", "NOISE_545", "ENTRY", "long", "10:00:00", 700.0, T545L)]),
    (at(10, 0, 11), 700.0, []),
    (at(10, 0, 16), 700.0, []),
    # NOISE555 flips short while NOISE and NOISE545 hold long
    (at(10, 30, 6), 702.0, [_row("10:30:05", "NOISE_555", "EXIT", "long", "10:30:00", 702.0, T555L),
                            _row("10:30:05", "NOISE_555", "ENTRY", "short", "10:30:00", 702.0, T555S)]),
    (at(10, 30, 11), 702.0, []),
    (at(10, 30, 16), 702.0, []),
    # NOISE545 exits its long, then goes short
    (at(11, 0, 6), 701.0, [_row("11:00:05", "NOISE_545", "EXIT", "long", "11:00:00", 701.0, T545L)]),
    (at(11, 0, 11), 701.0, []),
    (at(11, 30, 6), 699.0, [_row("11:30:05", "NOISE_545", "ENTRY", "short", "11:30:00", 699.0, T545S)]),
    (at(11, 30, 11), 699.0, []),
    (at(11, 30, 16), 699.0, []),
    # EOD: every NOISE leg flat at flat_by
    (at(15, 59, 1), 698.0, []),
    (at(15, 59, 6), 698.0, []),
    (at(16, 1), 698.0, []),
]


def _drive(tmp_path, monkeypatch, total_cap=500, n555=10):
    home = tmp_path / "home"
    out = home / "qqq_exec"
    out.mkdir(parents=True)
    for attr, fname in (("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv"), ("SERVING_LOCK", "SERVING.lock"),
                        ("STATE_PATH", "state.json"), ("CONFIG_PATH", "config.json")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    paths = cs._paths(home=str(home / "cs"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    clock = _Clock()
    fake_time = types.SimpleNamespace(time=clock.time, sleep=clock.sleep,
                                      monotonic=clock.monotonic, perf_counter=clock.monotonic)
    monkeypatch.setattr(qe, "time", fake_time)
    monkeypatch.setattr(WO, "time", fake_time)
    monkeypatch.setattr(qe, "_now_et", lambda: clock.now)
    monkeypatch.setattr(qe, "_PROCESS", {"booted": False})
    monkeypatch.setattr(qe, "_BREAKER_ADJ_CACHE", {"key": None, "val": 0.0})
    monkeypatch.setattr(qe, "_ENGINE_PX_CACHE", {"key": None, "val": {}})
    if hasattr(qe, "_resting_inflight"):
        monkeypatch.setattr(qe, "_resting_inflight",
                            {"future": None, "what": None, "timed_out_at": 0.0})
    monkeypatch.setattr(qe, "_notify", NOOP)
    fake = _Book(price=700.0)
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (fake.price, "live_stream"))
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (fake.price, "engine_cache"))
    monkeypatch.setattr(qe, "_maybe_run_reprice", NOOP)
    monkeypatch.setattr(qe, "_maybe_send_eod_summary", NOOP)
    monkeypatch.setattr(qe, "_maybe_read_account_equity", NOOP)
    monkeypatch.setattr(qe, "BROKER_FILL_CAPTURE_FIRST_DELAY_SEC", 0.0)
    monkeypatch.setattr(qe, "BROKER_FILL_CAPTURE_RETRY_GAP_SEC", 0.0)
    adapter = WO.OrderAdapter(config=_wo_cfg(tmp_path, total_cap), log=NOOP)
    monkeypatch.setattr(adapter, "_build_client", lambda m: fake)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
    cfg.update(signal_source="engine", max_shares_per_leg=60, slippage_per_share=0.0,
               kill_file=str(tmp_path / "KILL"), daily_loss_limit_usd=5000)
    # config.json names only ORB / ENGUQ / NOISE: the two new legs ride the code default
    cfg["shares"] = dict(cfg["shares"], ORB=10, ENGUQ=10, NOISE=10)
    if n555 != 10:
        cfg["shares"]["NOISE555"] = n555
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    state = qe._default_state()
    rows, steps = [], []
    for now, px, add in SCRIPT:
        clock.now = now
        fake.price = px
        rows += add
        with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})
        with open(paths["heartbeat_path"], "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.datetime.now(NY).isoformat(), "ok": True}, f)
        _c, state, _doc = qe.tick(cfg=cfg, state=state, now=now, quote_fn=NOOP, ratio_fn=NOOP,
                                  log=NOOP)
        book = {}
        for leg, lot in (state.get("legs") or {}).items():
            if lot:
                n = int(lot.get("shares_remaining") or 0)
                book[leg] = n if lot.get("side") == "long" else -n
        steps.append((now, dict(book), fake.pos))

    def read(p):
        with open(p, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    return {"steps": steps, "fake": fake, "orders": read(qe.ORDERS_CSV),
            "trades": read(qe.TRADES_CSV)}


@pytest.fixture
def session(tmp_path, monkeypatch):
    # NOISE555 trades 40 a lot here so its flip takes the ACCOUNT through zero (+60 -> -20):
    # the broker must close the long and open the short as separate orders
    return _drive(tmp_path, monkeypatch, n555=40)


def test_new_legs_are_mapped_and_sized():
    assert qe.ENGINE_LEG_MAP["NOISE_555"] == "NOISE555"
    assert qe.ENGINE_LEG_MAP["NOISE_545"] == "NOISE545"
    assert qe.ENGINE_LEG_MAP["NOISE_382"] == "NOISE"
    for leg in ("NOISE555", "NOISE545"):
        assert leg in qe.LEGS and leg in qe.NOISE_EXEC_LEGS
        assert qe.DEFAULT_CONFIG["shares"][leg] == 10
        assert qe._leg_word(leg).startswith("NOISE #5")
    # a config.json "shares" block naming only the old legs keeps the new legs' default
    merged = json.loads(json.dumps(qe.DEFAULT_CONFIG))
    merged["shares"].update({"ORB": 5, "ENGUQ": 10, "NOISE": 10})
    assert merged["shares"]["NOISE555"] == 10 and merged["shares"]["NOISE545"] == 10


def test_book_net_equals_broker_net_every_settled_step(session):
    steps = session["steps"]
    by = {now: (book, pos) for now, book, pos in steps}
    # every leg's own lot at the checkpoints
    assert by[at(10, 0, 16)][0] == {"NOISE": 10, "NOISE555": 40, "NOISE545": 10}
    assert by[at(10, 30, 16)][0] == {"NOISE": 10, "NOISE555": -40, "NOISE545": 10}
    assert by[at(11, 0, 11)][0] == {"NOISE": 10, "NOISE555": -40}
    assert by[at(11, 30, 16)][0] == {"NOISE": 10, "NOISE555": -40, "NOISE545": -10}
    assert by[at(16, 1)][0] == {}
    for t in (at(10, 0, 16), at(10, 30, 16), at(11, 0, 11), at(11, 30, 16), at(16, 1)):
        book, pos = by[t]
        assert sum(book.values()) == pos, (t, book, pos)
    assert session["fake"].pos == 0


def test_no_send_through_zero_unsplit(session):
    """Webull's own rule (the fake enforces it at placement): a SELL past the long or a BUY past
    the short is refused, so every order that reached Webull and FILLED was a legal one-sided
    order. NOISE555's flip (+60 -> -20) was split into a closing SELL 20 and a SHORT 20. The
    SHORT part can meet a 417 while the account's earlier close (NOISE555's own SELL 40, a
    market order the fake fills on its first lookup) still reads open -- the adapter keeps it
    unsent and the book re-sends it (R1); it must then fill, and the nets must agree."""
    f = session["fake"]
    orders = list(f.orders.values())
    assert all(o["status"] == "FILLED" for o in orders), orders
    split = [o for o in orders if o["coid"].startswith("qxNOISE55520260928T143000ZSO")]
    assert sorted((o["side"], o["qty"]) for o in split) == [("SELL", 20), ("SHORT", 20)]
    for side, qty, why in f.refused:
        assert "SIDE_NOT_MATCH_WITH_POSITION" in why, why
        assert any(o["side"] == side and str(o["qty"]) == str(qty) and "R" in o["coid"][-3:]
                   for o in orders), (side, qty)
    assert f.pos == 0


def test_each_leg_keeps_its_own_trades_and_pnl(session):
    tr = session["trades"]
    by_tid = {r["trade_id"]: r for r in tr}
    assert set(by_tid) == {T382, T555L, T555S, T545L, T545S}
    want_leg = {T382: "NOISE", T555L: "NOISE555", T555S: "NOISE555",
                T545L: "NOISE545", T545S: "NOISE545"}
    want_side = {T382: "long", T555L: "long", T555S: "short", T545L: "long", T545S: "short"}
    for tid, r in by_tid.items():
        assert r["leg"] == want_leg[tid]
        assert r["side"] == want_side[tid]
        sh, e, x = int(r["shares"]), float(r["entry_px"]), float(r["exit_px"])
        sign = 1 if r["side"] == "long" else -1
        assert float(r["pnl"]) == pytest.approx(sign * (x - e) * sh, abs=0.02), tid
    # the shadow fills at the scripted prices: each leg's P&L is its own move
    assert float(by_tid[T555L]["pnl"]) == pytest.approx(80.0, abs=0.02)    # 700 -> 702 long x40
    assert float(by_tid[T555S]["pnl"]) == pytest.approx(160.0, abs=0.02)   # 702 -> 698 short x40
    assert float(by_tid[T545L]["pnl"]) == pytest.approx(10.0, abs=0.02)    # 700 -> 701 long
    assert float(by_tid[T545S]["pnl"]) == pytest.approx(10.0, abs=0.02)    # 699 -> 698 short
    assert float(by_tid[T382]["pnl"]) == pytest.approx(-20.0, abs=0.02)    # 700 -> 698 long


def test_account_rail_cut_is_recorded_against_its_leg(tmp_path, monkeypatch):
    """No combined NOISE cap: the account's own total cap (25 shares here) clamps the THIRD
    entry of the bar, and the orders.csv row names that leg, the shares wanted vs sent and the
    rail."""
    out = _drive(tmp_path, monkeypatch, total_cap=25)
    enters = [r for r in out["orders"] if r["action"] == "ENTER" and r["ts_et"].startswith(DAY + " 10:00")]
    by_leg = {r["leg"]: r for r in enters}
    assert set(by_leg) == {"NOISE", "NOISE555", "NOISE545"}
    cut = [r for r in enters if "clamped" in r["reason"]]
    assert len(cut) == 1, enters
    r = cut[0]
    assert "total cap 25" in r["reason"]
    assert int(r["shares"]) == 5 and int(r["shares_wanted"]) == 10
    others = [x for x in enters if x is not r]
    assert all(x["reason"] == "signal entry" and int(x["shares"]) == 10 for x in others)
    assert out["fake"].refused == []
    assert out["fake"].pos == 0


# ── cloud_signal / books_toggle wiring ────────────────────────────────────────────────────

@pytest.mark.parametrize("key,strategy,params", [
    ("NOISE_555", "NOISE_1_8_CT304H_FT.py", {"tilt_mult": 1.75, "gate_len": 16, "gate_ratio": 1.15}),
    ("NOISE_545", "NOISE_1_8_CT304H_KFX.py",
     {"tilt_mult": 2.75, "gate_len": 16, "fri_mult": 2.0, "gate_ratio": 1.15}),
])
def test_cloud_signal_leg_has_its_own_keel(key, strategy, params):
    leg = cs.CROWN_LEGS[key]
    assert leg["strategy"] == strategy and leg["params"] == params
    assert leg["timeframe"] == "5m" and leg["decide_at_close"] and leg["eod_flat"]
    assert leg["resting_levels"] and leg["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS
    assert key in cs.KEEL_LIVE_LEARN_LEGS
    k = leg["keel"]
    assert k["version"] == "v12" and cs.keel_mode(k) == cs.KEEL_MODE_LEARNED
    own = cs.keel_paths(key, "v12")
    for name in ("state_path", "summary_path", "live_path", "live_prev_path", "live_ack_path",
                 "live_cut_path", "appends_path", "xrows_path"):
        assert k[name] == own[name]
        assert os.path.basename(k[name]).startswith(key + "_")
        assert k[name] != cs.CROWN_LEGS["NOISE_382"]["keel"][name]
    # NOISE_382 itself is unchanged
    assert cs.CROWN_LEGS["NOISE_382"]["params"] == cs.NOISE_382_PARAMS
    assert cs._keel_leg_word(key) == "NOISE " + key.split("_")[1]
    assert cs._keel_leg_word("NOISE_382") == "NOISE"


def test_strategy_files_accept_the_champion_cells():
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for key in ("NOISE_555", "NOISE_545"):
        cfg = cs.CROWN_LEGS[key]
        spec = importlib.util.spec_from_file_location(
            "_m_" + key, os.path.join(root, "augur_strategies", cfg["strategy"]))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        adm = m._ADMISSIBLE
        for p, v in cfg["params"].items():
            assert v in adm[p], (key, p, v)


def test_keel_tools_see_every_live_learning_leg():
    from tools import keel_live_state as L
    legs = {d["leg_key"]: d for d in L.resolve_legs()}
    for key in ("NOISE_382", "NOISE_555", "NOISE_545"):
        assert key in legs and legs[key]["live"]
        assert legs[key]["strategy"] == cs.CROWN_LEGS[key]["strategy"]
    assert L.resolve_leg(None)["leg_key"] == "NOISE_382"
    assert L.RUN_ID_FOR_LEG["NOISE_555"] == 555 and L.RUN_ID_FOR_LEG["NOISE_545"] == 545


def test_keel_intraday_runs_every_leg_on_its_own(monkeypatch, tmp_path):
    from tools import keel_intraday as KI
    seen = []
    # a leg with no nightly state yet is skipped (nothing to cut from) -- give the new legs one
    for leg in cs.KEEL_LIVE_LEARN_LEGS[1:]:
        sp = cs.keel_paths(leg, "v12", home=str(tmp_path))["state_path"]
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        open(sp, "wb").close()
    monkeypatch.setattr(KI, "verify_live_state", lambda home, leg, **k: seen.append(leg) or {"ok": True})
    assert KI.main(["--home", str(tmp_path), "--verify"]) == 0
    assert seen == list(cs.KEEL_LIVE_LEARN_LEGS)
    seen.clear()
    assert KI.main(["--home", str(tmp_path), "--verify", "--leg", "NOISE_555"]) == 0
    assert seen == ["NOISE_555"]
    seen.clear()
    os.remove(cs.keel_paths("NOISE_545", "v12", home=str(tmp_path))["state_path"])
    assert KI.main(["--home", str(tmp_path), "--verify"]) == 0
    assert seen == ["NOISE_382", "NOISE_555"]


def test_books_toggle_new_legs_are_paper():
    for bid, leg, run in (("NOISE555", "NOISE555", "#555.1 keel"), ("NOISE545", "NOISE545", "#545.1 keel")):
        c = bt.BOOK_LEG_CLASS[bid]
        assert c["cls"] == "paper" and c["max"] == "PAPER" and c["exec_leg"] == leg
        assert leg in qe.LEGS
        assert bt.BOX_VERSION[leg] == run
