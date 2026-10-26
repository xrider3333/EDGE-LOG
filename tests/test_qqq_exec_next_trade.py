r"""ITEM 53 (owner 2026-10-20) -- doc["next_trade"]: what each leg of the Webull paper book would
send if it fired next, for the board's line under each flat strategy and the TOTAL CAP row.

api/cloud_signal.py writes the engine half (NOISE_382 / ORB_R6 next-bar size, levels, exit rule)
to a local sidecar, <state_dir>/next_entry.json; api/qqq_exec.py's _build_next_trade lays this
book's own sizing (a mirror of _open_lot's fixed mode), the 85-share gross cap, the shared $400
daily stop, DIP's own -$800 rail and its slots on top. These tests build against hand-written
sidecars (the v2 contract's example, section 1.9) -- never the engine.

COVERS: the contract's doc example (section 2.2) reproduced field for field; rounding (half to
even); the per-leg and total-cap clamps and refusals; PARITY with the real _open_lot (a table of
sizes, caps and room, and the Env-driven tick on the DIP + ORB book); DIP slots / DIP cap /
Webull fit; the shared stop as the breaker sees it and DIP's rail (never realized_pnl_dip);
blocks, send blocks and the refusal order (the router's: busy before late, cross-checked on the
real tick); a weekday holiday; the adapter's own daily limit and per-leg send blocks; the adapter
singleton built with the doc's log; the fingerprint (0 extra Firestore writes); the size budget
and no array inside an array (Firestore rejects it); a missing / bad / other-version sidecar;
the read memo; the conftest isolation.
"""
import importlib.util
import json
import os
from datetime import datetime

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import webull_orders as wo

NOOP = lambda *a, **k: None  # noqa: E731

# tests/ is not a package: the DIP live leg's tick()-driven book is loaded straight from its file
_spec = importlib.util.spec_from_file_location(
    "_next_trade_dip_live_env", os.path.join(os.path.dirname(__file__), "test_qqq_exec_dip_live.py"))
_dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dl)
Env, at, ds, noise_entry, _dip_and_orb_held = _dl.Env, _dl.at, _dl.ds, _dl.noise_entry, _dl._dip_and_orb_held
DIP_DAY, DIP_SLOTS = _dl.DAY, _dl.SLOTS

DAY = "2026-10-20"      # Tuesday
NOW = datetime(2026, 10, 20, 10, 41, 15, tzinfo=qe._NY)

# the engine's exact wording (api/cloud_signal.py _noise_next_entry / _orb_next_entry, pinned
# there by tests/test_next_entry_preview.py): the page's fixture copies these. ORB's words are
# the same in every orb_resting mode -- where its stop lives (a resting Webull order, or a market
# sell after a finished bar) is the page's to say, from doc.orb_resting.mode
NOISE_EXIT = ("Out at the next open after a 5-min close back across VWAP (now 721.40), after a bar "
              "touches the stop (1.75x the band width), or at the close. No target.")
ORB_EXIT = ("Stop 4.60 a share from the entry close (2.5x the opening range), target 5x "
            "that; stop to the entry once a close is 2.30 up. Out at the close.")
NOISE_BASIS = "1.75x the band width from the fill (the next bar open); not checked on the fill bar"
ORB_BASIS = "2.5x the opening range from the entry close"

# the box's own adapter rails (C:\EdgeLog\box_backup\2026-10-20_1445\webull_orders\config.json);
# the conftest adapter starts on webull_orders.DEFAULT_RAILS (10 a leg, $200)
BOX_RAILS = {"max_shares_per_leg": 60, "max_total_position_shares": 85, "daily_loss_limit_usd": 400.0}


def _sidecar():
    """The contract's sidecar example (section 1.9), verbatim but for a real check.tid."""
    return {
        "v": 1, "computed_at": "2026-10-20T10:40:31-04:00", "host": "cloud", "cost_ms": 142,
        "next_session": "2026-10-21",
        "legs": {
            "NOISE_382": {
                "status": "ok", "why": None,
                "bar": "2026-10-20T10:35:00-04:00", "bar_close": "2026-10-20T10:40:00-04:00",
                "next": {"decide_bar": "10:40", "decide_close": "10:45", "fill_bar": "10:45",
                         "size": 2.0, "plugin": 2.0, "sq30": True,
                         "keel": 1.0, "fri": False, "sq60": False, "fomc": False,
                         "branch": "fixed-only", "model_on": False,
                         "trust": 0.0, "t_fast": -0.967, "z": 0.0,
                         "keel_src": "live", "keel_fb": None, "may_change": []},
                "range_today": {"lo": 1.0, "hi": 3.0},
                "next_session": {"date": "2026-10-21", "lo": 1.0, "hi": 3.0, "fri": False,
                                 "fomc": False},
                "px": 722.12, "vwap": 721.4, "vwap_dist": 0.72, "ref_hi": 722.35, "ref_lo": 718.7,
                "vol_pct": 63.2,
                "long": {"ok": True, "why": None, "trigger": 724.1, "stop_dist": 3.06,
                         "stop_est": 721.04, "basis": NOISE_BASIS},
                "short": {"ok": True, "why": None, "trigger": 715.22, "stop_dist": 6.0891,
                          "stop_est": 721.31, "basis": NOISE_BASIS},
                "exit_rule": NOISE_EXIT,
                "check": {"tid": "NOISE_382-20261020T143000Z-L", "bar": "10:25",
                          "at": "2026-10-20T10:30:41-04:00", "preview": 2.0, "actual": 2.0,
                          "match": True, "board": 2.0, "board_match": True}},
            "ORB_R6": {
                "status": "ok", "why": None,
                "bar": "2026-10-20T10:35:00-04:00", "bar_close": "2026-10-20T10:40:00-04:00",
                "next": {"decide_bar": "10:40", "decide_close": "10:45"},
                "size": 1.0, "dir": "long", "or_hi": 724.4, "or_lo": 722.56, "rng": 1.84,
                "trigger": 724.86, "px": 722.12, "risk": 4.6,
                "stop_est": 720.26, "target_est": 747.86, "be_est": 727.16, "target_r": 5.0,
                "be_r": 0.5, "pace": 0.93,
                "basis": ORB_BASIS,
                "exit_rule": ORB_EXIT}}}


# the contract's doc example (section 2.2), field for field
EXPECTED = {
    "v": 1,
    "at": "2026-10-20 10:41:15",
    "src": {"bar": "2026-10-20 10:35", "bar_close": "2026-10-20 10:40:00",
            "computed_at": "2026-10-20 10:40:31", "age_s": 44, "host": "cloud",
            "next_session": "2026-10-21"},
    "cap": {"cap": 85, "held": 12, "room": 73},
    "loss": {"limit": 400.0, "input": -43.59, "used": 43.59, "left": 356.41, "tripped": False,
             "checked": True},
    "dip_rail": {"limit": 800.0, "input": 9.12, "used": 0.0, "left": 809.12, "blocked": False,
                 "tripped_on": None, "until": None},
    "blocks": [],
    "send_blocks": [],
    "legs": {
        "ORB": {"status": "ok", "why": None, "decide_bar": "10:40", "decide_close": "10:45",
                "base": 10, "size": 1.0, "wanted": 10, "sent": 10, "refused": None,
                "clamped": False, "clamp_by": None,
                "send_block": None,
                "dir": "long", "trigger": 724.86, "px": 722.12, "rng": 1.84, "risk": 4.6,
                "stop": 720.26, "target": 747.86, "max_loss": 46.0,
                "exit": ORB_EXIT},
        "NOISE": {"status": "ok", "why": None, "decide_bar": "10:40", "decide_close": "10:45",
                  "base": 10, "size": 2.0, "wanted": 20, "sent": 20, "refused": None,
                  "clamped": False, "clamp_by": None,
                  "send_block": None,
                  "plugin": 2.0, "sq30": True, "keel": 1.0, "fri": False, "sq60": False,
                  "fomc": False, "branch": "fixed-only", "model_on": False, "trust": 0.0,
                  "t_fast": -0.967, "z": 0.0, "keel_src": "live", "keel_fb": None, "may_change": [],
                  "lo_sh": 10, "hi_sh": 30,
                  "next_session": {"date": "2026-10-21", "lo_sh": 10, "hi_sh": 30, "fri": False,
                                   "fomc": False},
                  "px": 722.12, "vwap": 721.4,
                  "long": {"ok": True, "why": None, "trigger": 724.1, "stop_dist": 3.06,
                           "stop": 721.04, "max_loss": 61.2},
                  "short": {"ok": True, "why": None, "trigger": 715.22, "stop_dist": 6.0891,
                            "stop": 721.31, "max_loss": 121.78},
                  "exit": NOISE_EXIT,
                  "check": {"bar": "10:25", "preview": 2.0, "actual": 2.0, "match": True,
                            "board": 2.0}},
        "DIP": {"lot": 6, "slots_total": 7, "slots_free": 5, "held_lots": 2, "held_sh": 12,
                "dip_cap": 42, "book_fit": 5, "webull_fit": 5, "refused": None,
                "exit": qe.DIP_NEXT_EXIT_TEXT}}}


def _cfg(tmp_path, **kw):
    """The box's sizing: ORB / NOISE 10, cap 60, the shared $400 -- DIP's 6 a lot, 42 cap and
    -$800 rail from the code defaults."""
    cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
    cfg.update(signal_source="engine", max_shares_per_leg=60, daily_loss_limit_usd=400,
               kill_file=str(tmp_path / "KILL"))
    cfg["shares"].update({"ORB": 10, "ENGUQ": 10, "NOISE": 10})
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    cfg.update(kw)
    return cfg


def _lot(leg, shares, side="long"):
    return {"leg": leg, "side": side, "shares_total": shares, "shares_remaining": shares,
            "entry_px": 700.0, "entry_ts": f"{DAY} 09:35:10"}


def _state(**kw):
    """Two DIP lots held (12 sh), the breaker's figure -43.59, DIP's rail figure +9.12."""
    st = {"trading_day": DAY, "events": [],
          "legs": {"DIP_RSI": _lot("DIP_RSI", 6), "DIP_DBL": _lot("DIP_DBL", 6)},
          "_breaker_input": {"day": DAY, "pnl": -43.59},
          "_dip_rail_input": {"day": DAY, "pnl": 9.12, "realized": 0.0, "fill_adj": 0.0,
                              "unrealized": 9.12},
          "realized_pnl_today_dip": -50.0}
    st.update(kw)
    return st


BROKER_OK = {"effective_mode": "PAPER", "halted": False, "lease_ok_to_send": True, "daily_pnl": -43.59}


@pytest.fixture
def sidecar_file(tmp_path, monkeypatch):
    """Writes a sidecar to a temp file and points the book's read at it."""
    path = tmp_path / "cs_state" / "next_entry.json"
    path.parent.mkdir()
    monkeypatch.setattr(qe, "_next_entry_path", lambda: str(path))
    monkeypatch.setattr(qe, "_NEXT_TRADE_ERR", {"last": 0.0, "held": 0})
    writes = [0]

    def write(doc=None, raw=None):
        path.write_text(raw if raw is not None else json.dumps(doc if doc is not None else _sidecar()),
                        encoding="utf-8")
        writes[0] += 1   # a strictly newer mtime every write, whatever the clock's resolution
        t = 1_760_000_000_000_000_000 + writes[0] * 1_000_000_000
        os.utime(path, ns=(t, t))
        return path
    write.path = path
    return write


@pytest.fixture
def side(sidecar_file, monkeypatch):
    """sidecar_file, with the clock at 10:41:15 ET on Tue 10-20, the Webull room at (73, 12, 85)
    and the box's adapter rails on conftest's OFF adapter unless a test says otherwise."""
    monkeypatch.setattr(qe, "_now_et", lambda: NOW)
    monkeypatch.setattr(qe, "_broker_total_room", lambda log=print: (73, 12, 85))
    monkeypatch.setitem(qe._ORDER_ADAPTER.cfg, "rails", dict(qe._ORDER_ADAPTER.cfg["rails"], **BOX_RAILS))
    return sidecar_file


def _nt(cfg, state=None, feed_stale=False, broker=None, day=DAY):
    return qe._build_next_trade(cfg, state if state is not None else _state(), feed_stale,
                                {"broker": BROKER_OK if broker is None else broker}, day, log=NOOP)


def _codes(lst):
    return [(b["code"], b["scope"]) for b in lst]


def _no_nested_array(v):
    if isinstance(v, dict):
        return all(_no_nested_array(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return all(not isinstance(x, (list, tuple)) and _no_nested_array(x) for x in v)
    return True


# ── the contract's example ───────────────────────────────────────────────────────────────

def test_the_contract_example_is_reproduced_field_for_field(side, tmp_path):
    side()
    nt = _nt(_cfg(tmp_path))
    assert nt == EXPECTED
    assert json.dumps(nt, allow_nan=False)
    assert _no_nested_array(nt), "Firestore rejects an array inside an array"


def test_the_trim_case_dip_42_and_orb_10_held_noise_4_5_on_a_friday(side, tmp_path, monkeypatch):
    """The page's pinned trim string: 33 sh (10 x 2.00 x KEEL 2.25 = 45 wanted, capped by the
    85-share cap), rest of today 15-45 sh; planned loss at the stop 33 x $3.06 = $100.98."""
    monkeypatch.setattr(qe, "_broker_total_room", lambda log=print: (33, 52, 85))
    doc = _sidecar()
    n = doc["legs"]["NOISE_382"]
    n["next"].update(decide_bar="11:00", decide_close="11:05", size=4.5, plugin=2.0, keel=2.25,
                     fri=True)
    n["range_today"] = {"lo": 1.5, "hi": 4.5}
    side(doc)
    legs = {leg: _lot(leg, 6) for leg in qe.DIP_LEGS}
    legs["ORB"] = _lot("ORB", 10)
    nt = _nt(_cfg(tmp_path), _state(legs=legs))
    noise = nt["legs"]["NOISE"]
    assert (noise["base"], noise["size"], noise["wanted"], noise["sent"]) == (10, 4.5, 45, 33)
    assert (noise["clamped"], noise["clamp_by"], noise["refused"]) == (True, "cap", None)
    assert (noise["lo_sh"], noise["hi_sh"]) == (15, 45)
    assert noise["long"]["max_loss"] == 100.98 and noise["short"]["max_loss"] == round(33 * 6.0891, 2)
    assert nt["legs"]["ORB"]["refused"] == "busy" and nt["legs"]["ORB"]["sent"] is None
    assert nt["legs"]["DIP"]["refused"] == "all_held"
    assert nt["cap"] == {"cap": 85, "held": 52, "room": 33}


# ── 1. rounding and the per-leg rail ─────────────────────────────────────────────────────

@pytest.mark.parametrize("size,wanted", [(0.25, 2), (0.75, 8), (2.25, 22), (4.5, 45), (6.0, 60)])
def test_rounding_is_half_to_even_like_the_order_path(tmp_path, size, wanted):
    sh = qe._next_trade_shares(_cfg(tmp_path), "NOISE", size, None)
    assert (sh["wanted"], sh["sent"], sh["clamped"], sh["refused"]) == (wanted, wanted, False, None)


def test_the_per_leg_rail_refuses_an_unsized_lot_whole_and_clamps_a_sized_one(tmp_path):
    sh = qe._next_trade_shares(_cfg(tmp_path, max_shares_per_leg=5), "ORB", 1.0, None)
    assert (sh["wanted"], sh["sent"], sh["refused"]) == (10, None, "per_leg")
    sh = qe._next_trade_shares(_cfg(tmp_path), "NOISE", 6.5, None)
    assert (sh["wanted"], sh["sent"], sh["clamped"], sh["clamp_by"]) == (65, 60, True, "per_leg")
    cfg = _cfg(tmp_path)
    cfg["shares"]["NOISE"] = 0
    sh = qe._next_trade_shares(cfg, "NOISE", 2.0, None)
    assert (sh["base"], sh["wanted"], sh["sent"], sh["refused"]) == (0, 0, None, "off")
    sh = qe._next_trade_shares(_cfg(tmp_path, max_shares_per_leg=0), "ORB", 1.0, None)
    assert sh["refused"] == "per_leg", "0 / missing max_shares_per_leg refuses every unsized lot"
    # an unusable engine size is unsized (1.0), exactly as _resolve_entry_size reads it
    assert qe._next_trade_shares(_cfg(tmp_path), "NOISE", "nan", None)["wanted"] == 10


# ── 2. the total cap ─────────────────────────────────────────────────────────────────────

def test_the_total_cap_clamps_to_the_room_and_refuses_with_none_left(tmp_path):
    cfg = _cfg(tmp_path)
    assert qe._next_trade_shares(cfg, "NOISE", 4.5, None)["sent"] == 45, "no cap read: no clamp"
    sh = qe._next_trade_shares(cfg, "NOISE", 4.5, (33, 52, 85))
    assert (sh["wanted"], sh["sent"], sh["clamped"], sh["clamp_by"]) == (45, 33, True, "cap")
    for total in ((0, 85, 85), (-3, 88, 85)):
        sh = qe._next_trade_shares(cfg, "NOISE", 4.5, total)
        assert (sh["sent"], sh["refused"]) == (None, "cap_full")
    sh = qe._next_trade_shares(cfg, "ORB", 1.0, (7, 78, 85))
    assert (sh["wanted"], sh["sent"], sh["clamp_by"]) == (10, 7, "cap")


# ── 3. parity with the real _open_lot ────────────────────────────────────────────────────

@pytest.mark.parametrize("leg,base,size,max_shares,total", [
    ("NOISE", 10, s, m, t)
    for s in (None, "", 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.25, 3.0, 4.5, 6.0, 6.5, "x", -1)
    for m in (0, 5, 22, 60)
    for t in (None, (73, 12, 85), (33, 52, 85), (1, 84, 85), (0, 85, 85), (-3, 88, 85))
] + [("ORB", b, 1.0, m, t) for b in (0, 10, 61) for m in (0, 60) for t in (None, (7, 78, 85), (0, 85, 85))])
def test_the_mirror_matches_open_lot(tmp_path, monkeypatch, leg, base, size, max_shares, total):
    """_open_lot itself, with only its outside effects stubbed: the mirror's `sent` is the lot's
    shares_total (None = no lot opened), its `wanted` the lot's shares_wanted."""
    for name in ("_record_order", "_log_event", "_say", "_mirror_to_broker"):
        monkeypatch.setattr(qe, name, NOOP)
    monkeypatch.setattr(qe, "_broker_total_room", lambda log=print: total)
    cfg = _cfg(tmp_path, max_shares_per_leg=max_shares)
    cfg["shares"][leg] = base
    state = {"legs": {}, "events": [], "_px_source": "test"}
    opened = qe._open_lot(state, cfg, leg, "long", base, None, 700.0, 0.0, f=None, log=NOOP, size=size)
    sh = qe._next_trade_shares(cfg, leg, size, total)
    lot = state["legs"].get(leg)
    assert opened is (lot is not None)
    assert sh["sent"] == (lot["shares_total"] if lot else None)
    if lot:
        assert sh["wanted"] == lot["shares_wanted"] and sh["size"] == round(lot["size"], 4)
        assert sh["clamped"] is (lot["shares_total"] < lot["shares_wanted"])
    else:
        assert sh["refused"] in ("off", "per_leg", "cap_full")


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def _env_sidecar(side, hh, mm, size):
    """NOISE ok with a next decision whose ENTRY row's bar (the fill bar) is hh:mm."""
    doc = _sidecar()
    n = doc["legs"]["NOISE_382"]
    n["next"].update(decide_bar=f"{hh:02d}:{mm - 5:02d}", decide_close=f"{hh:02d}:{mm:02d}", size=size)
    side(doc)


def test_parity_on_the_dip_and_orb_book_the_block_says_33_and_the_tick_sends_33(env, sidecar_file):
    """The Env's own clock, its real PAPER adapter's room and the real tick: no stubs between."""
    e = env
    _dip_and_orb_held(e)
    _env_sidecar(sidecar_file, 10, 30, 4.5)
    e.clock[0] = at(DIP_DAY, 10, 30, 1)
    nt = qe._build_next_trade(e.cfg, e.state, False, {"broker": BROKER_OK}, ds(DIP_DAY), log=NOOP)
    noise = nt["legs"]["NOISE"]
    assert nt["cap"] == {"cap": 85, "held": 52, "room": 33}
    assert (noise["wanted"], noise["sent"], noise["clamp_by"], noise["refused"]) == (45, 33, "cap", None)
    e.tick(at(DIP_DAY, 10, 30, 10), events=[noise_entry(DIP_DAY, 10, 30, "long", 700.0, 4.5)])
    lot = e.lot("NOISE")
    assert (lot["shares_total"], lot["shares_wanted"]) == (noise["sent"], noise["wanted"])
    nt = qe._build_next_trade(e.cfg, e.state, False, {"broker": BROKER_OK}, ds(DIP_DAY), log=NOOP)
    assert nt["legs"]["NOISE"]["refused"] == "busy" and nt["cap"]["room"] == 0


def test_parity_with_no_room_the_block_says_cap_full_and_the_entry_is_refused(env, sidecar_file):
    e = env
    _dip_and_orb_held(e)
    e.adapter.cfg["rails"]["max_total_position_shares"] = 52
    _env_sidecar(sidecar_file, 10, 30, 4.5)
    e.clock[0] = at(DIP_DAY, 10, 30, 1)
    nt = qe._build_next_trade(e.cfg, e.state, False, {"broker": BROKER_OK}, ds(DIP_DAY), log=NOOP)
    assert (nt["legs"]["NOISE"]["sent"], nt["legs"]["NOISE"]["refused"]) == (None, "cap_full")
    e.tick(at(DIP_DAY, 10, 30, 10), events=[noise_entry(DIP_DAY, 10, 30, "long", 700.0, 4.5)])
    assert "NOISE" not in e.state["legs"]


def test_parity_dip_with_cap_40_seven_slots_fit_the_book_six_fit_webull(env, sidecar_file):
    e = env
    e.adapter.cfg["rails"]["max_total_position_shares"] = 40
    sidecar_file()
    e.clock[0] = at(DIP_DAY, 9, 35, 1)
    e.state["trading_day"] = ds(DIP_DAY)
    nt = qe._build_next_trade(e.cfg, e.state, False, {"broker": BROKER_OK}, ds(DIP_DAY), log=NOOP)
    dip = nt["legs"]["DIP"]
    assert (dip["slots_free"], dip["book_fit"], dip["webull_fit"]) == (7, 7, 6)
    e.enter_dip(DIP_SLOTS, DIP_DAY, 700.0)
    assert len(e.sent()) == dip["webull_fit"] and len([k for k in e.state["legs"] if qe.is_dip_leg(k)]) == 7


# ── 4. DIP ───────────────────────────────────────────────────────────────────────────────

def test_dip_slots_held_shares_and_the_dip_cap(tmp_path):
    cfg = _cfg(tmp_path)
    st = _state()
    st["legs"]["DIP_PB"] = dict(_lot("DIP_PB", 6), book_only=True)   # a book-only lot counts too
    d = qe._next_trade_dip(cfg, st, (73, 12, 85), DAY)
    assert (d["lot"], d["slots_total"], d["slots_free"], d["held_lots"], d["held_sh"]) == (6, 7, 4, 3, 18)
    assert (d["dip_cap"], d["book_fit"], d["webull_fit"], d["refused"]) == (42, 4, 4, None)
    d = qe._next_trade_dip(_cfg(tmp_path, dip_max_total_shares=24), st, None, DAY)
    assert (d["book_fit"], d["webull_fit"]) == (1, None), "24 - 18 = 6 fits one lot; no cap read"
    d = qe._next_trade_dip(_cfg(tmp_path, dip_max_total_shares=18), st, None, DAY)
    assert (d["book_fit"], d["refused"]) == (0, "dip_cap")
    d = qe._next_trade_dip(_cfg(tmp_path, dip_max_total_shares=0), st, None, DAY)
    assert d["book_fit"] == 4, "0 = no DIP cap"
    # the Webull room fits fewer: never a clamp (a DIP lot is refused whole, book-only)
    d = qe._next_trade_dip(cfg, st, (8, 77, 85), DAY)
    assert (d["book_fit"], d["webull_fit"], d["refused"]) == (4, 1, None)
    assert "clamped" not in d and "sent" not in d
    d = qe._next_trade_dip(cfg, st, (-2, 87, 85), DAY)
    assert d["webull_fit"] == 0


def test_dip_all_held_rail_kill_feed_and_no_live_slot(tmp_path):
    cfg = _cfg(tmp_path)
    full = _state(legs={leg: _lot(leg, 6) for leg in qe.DIP_LEGS})
    d = qe._next_trade_dip(cfg, full, (43, 42, 85), DAY)
    assert (d["slots_free"], d["held_sh"], d["book_fit"], d["refused"]) == (0, 42, 0, "all_held")
    railed = _state(dip_rail={"tripped_on": "2026-10-19", "blocks_until": DAY, "loss_usd": -812.0})
    assert qe._next_trade_dip(cfg, railed, None, DAY)["refused"] == "dip_rail"
    assert qe._next_trade_dip(cfg, railed, None, "2026-10-21")["refused"] is None, "past blocks_until"
    assert qe._next_trade_dip(cfg, railed, None, DAY, feed_stale=True)["refused"] == "feed"
    assert qe._next_trade_dip(cfg, _state(px_feed_stale=True), None, DAY)["refused"] == "feed"
    assert qe._next_trade_dip(cfg, dict(railed, kill_done=True), None, DAY)["refused"] == "kill"
    (tmp_path / "KILL").write_text("")
    assert qe._next_trade_dip(cfg, _state(), None, DAY)["refused"] == "kill"
    off = _cfg(tmp_path)
    for leg in qe.DIP_LEGS:
        off["shares"][leg] = 0
    assert qe._next_trade_dip(off, _state(), None, DAY) == {}


def test_no_dip_leg_configured_leaves_legs_dip_off_the_block(side, tmp_path):
    side()
    cfg = _cfg(tmp_path)
    for leg in qe.DIP_LEGS:
        cfg["shares"][leg] = 0
    nt = _nt(cfg)
    assert set(nt["legs"]) == {"ORB", "NOISE"}


# ── 5. the shared daily stop: the breaker's own figure ───────────────────────────────────

@pytest.fixture
def box(tmp_path, monkeypatch):
    """Every file _build_doc reads -> tmp; the slow or outside-world builders stubbed exactly
    like tests/test_qqq_exec_ledger13.py does."""
    out = tmp_path / "qqq_exec_out"
    out.mkdir()
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "_notify", NOOP)
    monkeypatch.setattr(qe, "_trade_parity", lambda row, log=print: {})
    monkeypatch.setattr(qe, "_load_reprice_sidecar", lambda log=print: {})
    monkeypatch.setattr(qe, "_engine_prices_by_trade", lambda *a, **k: {})
    monkeypatch.setattr(qe, "_build_price_status", lambda cfg, state, log=print: {})
    monkeypatch.setattr(qe, "_build_run_location", lambda: {})
    monkeypatch.setattr(qe, "_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {})
    monkeypatch.setattr(qe, "_build_broker_status", lambda state, log=print: dict(BROKER_OK))
    monkeypatch.setattr(qe, "_build_trade_id_status", lambda state, day: {})
    qe._BREAKER_ADJ_CACHE["key"] = None

    def doc(cfg, state, feed_stale=False):
        return qe._build_doc(cfg, state, feed_stale, 0.0, log=NOOP)
    return doc


def test_the_loss_block_is_the_breaker_s_own_figure(box, side, tmp_path):
    side()
    doc = box(_cfg(tmp_path), _state())
    loss = doc["next_trade"]["loss"]
    assert loss["input"] == doc["today"]["breaker_input"] == -43.59
    assert (loss["used"], loss["left"], loss["checked"], loss["tripped"]) == (43.59, 356.41, True, False)
    up = box(_cfg(tmp_path), _state(_breaker_input={"day": DAY, "pnl": 25.5}))["next_trade"]["loss"]
    assert (up["used"], up["left"]) == (0.0, 425.5), "an up day: more left than the limit"
    hit = box(_cfg(tmp_path), _state(breaker_tripped=True, _breaker_input={"day": DAY, "pnl": -401.2}))
    assert hit["next_trade"]["loss"]["left"] == 0.0 and hit["next_trade"]["loss"]["tripped"] is True
    none = box(_cfg(tmp_path), _state(_breaker_input={"day": "2026-10-19", "pnl": -10.0}))
    loss = none["next_trade"]["loss"]
    assert none["today"]["breaker_input"] is None
    assert (loss["input"], loss["checked"], loss["used"], loss["left"]) == (None, False, None, None)


# ── 6. DIP's own rail ────────────────────────────────────────────────────────────────────

def test_the_dip_rail_block_is_its_own_rail_figure_never_realized_pnl_dip(box, side, tmp_path):
    side()
    doc = box(_cfg(tmp_path), _state())
    dr = doc["next_trade"]["dip_rail"]
    assert dr["input"] == doc["today"]["dip_rail_input"]["pnl"] == 9.12
    assert doc["today"]["realized_pnl_dip"] != dr["input"]
    assert (dr["limit"], dr["used"], dr["left"], dr["blocked"]) == (800.0, 0.0, 809.12, False)
    st = _state(_dip_rail_input={"day": DAY, "pnl": -812.0},
                dip_rail={"tripped_on": DAY, "blocks_until": "2026-10-21", "loss_usd": -812.0})
    dr = box(_cfg(tmp_path), st)["next_trade"]["dip_rail"]
    assert (dr["used"], dr["left"], dr["blocked"]) == (812.0, 0.0, qe._dip_rail_blocking(st, DAY))
    assert (dr["tripped_on"], dr["until"]) == (DAY, "2026-10-21") and dr["blocked"] is True
    st = _state(_dip_rail_input={"day": DAY, "pnl": -20.0},
                dip_rail={"tripped_on": "2026-10-19", "blocks_until": DAY, "loss_usd": -830.0})
    dr = qe._next_trade_dip_rail(_cfg(tmp_path), st, DAY)
    assert (dr["left"], dr["blocked"]) == (780.0, True), "the session after the trip: today's own figure"
    assert qe._next_trade_dip_rail(_cfg(tmp_path, dip_daily_loss_limit_usd=0), st, DAY) is None


# ── 7. blocks, send blocks and the refusal order ─────────────────────────────────────────

def _refused(nt):
    return {k: nt["legs"][k]["refused"] for k in nt["legs"]}


def test_blocks_and_each_leg_s_refusal(side, tmp_path, monkeypatch):
    side()
    cfg = _cfg(tmp_path)
    nt = _nt(cfg, _state(kill_done=True))
    assert _codes(nt["blocks"]) == [("kill", "all")]
    assert _refused(nt) == {"ORB": "kill", "NOISE": "kill", "DIP": "kill"}
    assert nt["legs"]["NOISE"]["sent"] is None and nt["legs"]["NOISE"]["wanted"] == 20
    nt = _nt(cfg, feed_stale=True)
    assert _codes(nt["blocks"]) == [("feed", "all")]
    assert _refused(nt) == {"ORB": "feed", "NOISE": "feed", "DIP": "feed"}
    nt = _nt(cfg, _state(breaker_tripped=True))
    assert _codes(nt["blocks"]) == [("breaker", "shared")]
    assert _refused(nt) == {"ORB": "breaker", "NOISE": "breaker", "DIP": None}, "DIP is off the breaker"
    nt = _nt(cfg, _state(dip_rail={"tripped_on": DAY, "blocks_until": "2026-10-21"}))
    assert _codes(nt["blocks"]) == [("dip_rail", "dip")]
    assert _refused(nt) == {"ORB": None, "NOISE": None, "DIP": "dip_rail"}
    nt = _nt(cfg, _state(legs={"NOISE": _lot("NOISE", 20, "short")}))
    assert _refused(nt)["NOISE"] == "busy" and _refused(nt)["ORB"] is None
    (tmp_path / "KILL").write_text("")
    assert _codes(_nt(cfg)["blocks"]) == [("kill", "all")]
    os.remove(tmp_path / "KILL")
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 10, 20, 17, 5, tzinfo=qe._NY))
    nt = _nt(cfg, _state(kill_done=True, breaker_tripped=True))
    assert _codes(nt["blocks"]) == [("closed", "all"), ("kill", "all"), ("breaker", "shared")]
    assert _refused(nt) == {"ORB": "closed", "NOISE": "closed", "DIP": "kill"}


def test_the_refusal_order_closed_kill_busy_late_feed_breaker(side, tmp_path):
    """The ROUTER's order: with the kill on the tick routes nothing; a lot open on the leg is
    entry_leg_busy before the late guard looks; late before the feed / breaker gate."""
    side()
    held = {"NOISE": _lot("NOISE", 10)}
    st = _state(kill_done=True, breaker_tripped=True, legs=held)
    assert _refused(_nt(_cfg(tmp_path), st, feed_stale=True))["NOISE"] == "kill"
    # LATE: the ENTRY row's bar is NOISE's decide_close (the fill bar) -- 10:45 > last_entry 10:40;
    # ORB's row bar is its decide_bar, 10:40, not after it
    cfg = _cfg(tmp_path)
    cfg["session"]["last_entry"] = "10:40"
    # busy beats late (and everything after it)
    assert _refused(_nt(cfg, _state(breaker_tripped=True, legs=held), feed_stale=True))["NOISE"] == "busy"
    # late beats feed and the breaker
    nt = _nt(cfg, _state(breaker_tripped=True), feed_stale=True)
    assert _refused(nt)["NOISE"] == "late" and _refused(nt)["ORB"] == "feed"
    assert nt["legs"]["NOISE"]["sent"] is None
    # feed beats the breaker
    st = _state(breaker_tripped=True)
    assert _refused(_nt(_cfg(tmp_path), st, feed_stale=True))["NOISE"] == "feed"
    assert _refused(_nt(_cfg(tmp_path), st))["NOISE"] == "breaker"
    assert _refused(_nt(cfg, _state()))["ORB"] is None
    cfg["session"]["last_entry"] = "10:45"
    assert _refused(_nt(cfg, _state()))["NOISE"] is None


def test_busy_beats_late_on_the_real_tick_too(env, sidecar_file):
    """The router itself: a NOISE lot open AND the next row's bar past last_entry -- the tick
    refuses it as entry_leg_busy (never entry_too_late), and the block says busy."""
    e = env
    e.tick(at(DIP_DAY, 10, 30, 10), events=[noise_entry(DIP_DAY, 10, 30, "long", 700.0, 2.0)])
    assert e.lot("NOISE")["shares_total"] == 20
    e.cfg["session"]["last_entry"] = "10:35"
    _env_sidecar(sidecar_file, 10, 40, 2.0)         # the next row's bar: 10:40, after 10:35
    e.clock[0] = at(DIP_DAY, 10, 36, 1)
    nt = qe._build_next_trade(e.cfg, e.state, False, {"broker": BROKER_OK}, ds(DIP_DAY), log=NOOP)
    assert (nt["legs"]["NOISE"]["refused"], nt["legs"]["NOISE"]["sent"]) == ("busy", None)
    e.tick(at(DIP_DAY, 10, 40, 10), events=[noise_entry(DIP_DAY, 10, 40, "long", 701.0, 2.0)])
    assert e.issues().get("entry_leg_busy") == 1
    assert not [ev for ev in e.state["events"] if ev.get("kind") == "entry_too_late"]
    assert e.lot("NOISE")["shares_total"] == 20, "the first lot is still the one held"
    # flat again, the same row would be late -- and the block says so
    del e.state["legs"]["NOISE"]
    nt = qe._build_next_trade(e.cfg, e.state, False, {"broker": BROKER_OK}, ds(DIP_DAY), log=NOOP)
    assert nt["legs"]["NOISE"]["refused"] == "late"
    assert qe._late_entry_reason(at(DIP_DAY, 10, 40, 10), at(DIP_DAY, 10, 40), e.cfg["session"])


def test_a_weekday_holiday_is_closed(side, tmp_path, monkeypatch):
    """Thanksgiving Thursday at 10:00: _in_market_window says open (a weekday inside 09:25-16:05),
    but tick() stops on market_calendar.is_session -- nothing trades, and the block says so."""
    thanks = datetime(2026, 11, 26, 10, 0, tzinfo=qe._NY)
    assert qe._in_market_window(thanks) and not qe.market_calendar.is_session(thanks)
    monkeypatch.setattr(qe, "_now_et", lambda: thanks)
    side()
    hol = "2026-11-26"
    nt = _nt(_cfg(tmp_path), _state(trading_day=hol), day=hol)
    assert {"code": "closed", "scope": "all"} in nt["blocks"]
    assert _refused(nt)["NOISE"] == "closed" and _refused(nt)["ORB"] == "closed"
    assert nt["legs"]["NOISE"]["sent"] is None and nt["legs"]["ORB"]["sent"] is None
    # the Wednesday before is a session: no block
    wed = datetime(2026, 11, 25, 10, 0, tzinfo=qe._NY)
    assert qe.market_calendar.is_session(wed)
    monkeypatch.setattr(qe, "_now_et", lambda: wed)
    nt = _nt(_cfg(tmp_path), _state(trading_day="2026-11-25"), day="2026-11-25")
    assert nt["blocks"] == [] and _refused(nt)["NOISE"] is None and nt["legs"]["NOISE"]["sent"] == 20


def test_a_late_entry_matches_the_router_s_own_guard(side, tmp_path):
    """The same _late_entry_reason the router runs on the row: decided at the 15:50 bar's close
    (row bar 15:55) is in time; a 15:55 decision (row bar 16:00) is not."""
    doc = _sidecar()
    doc["legs"]["NOISE_382"]["next"].update(decide_bar="15:50", decide_close="15:55")
    side(doc)
    assert _refused(_nt(_cfg(tmp_path)))["NOISE"] is None
    doc["legs"]["NOISE_382"]["next"].update(decide_bar="15:55", decide_close="16:00")
    side(doc)
    assert _refused(_nt(_cfg(tmp_path)))["NOISE"] == "late"


@pytest.mark.parametrize("broker,codes", [
    ({"effective_mode": "OFF"}, [("adapter_off", "all")]),
    ({}, [("adapter_off", "all")]),
    (dict(BROKER_OK, halted=True), [("halted", "all")]),
    (dict(BROKER_OK, lease_ok_to_send=False), [("lease", "all")]),
    (dict(BROKER_OK, daily_pnl=-400.0), [("broker_daily", "send_shared")]),
    (dict(BROKER_OK, daily_pnl=-399.99), []),
    (dict(BROKER_OK, daily_pnl=None), []),
    (dict(BROKER_OK, effective_mode="LIVE"), []),
])
def test_send_blocks_from_the_doc_s_broker_block(side, tmp_path, broker, codes):
    side()
    nt = _nt(_cfg(tmp_path), broker=broker)
    assert _codes(nt["send_blocks"]) == codes
    assert nt["blocks"] == [] and nt["legs"]["NOISE"]["sent"] == 20, "the book lot still opens"


def test_adapter_off_only_when_the_adapter_s_mode_is_known(side, tmp_path, monkeypatch):
    """A broker block that failed to read (_build_broker_status -> {"error": ...}) says nothing
    of the mode: the order path asks the adapter's effective_mode() (_mirror_to_broker), so the
    block does too -- PAPER: no adapter_off (the orders still go out); the conftest's OFF
    adapter: adapter_off; an adapter that cannot be read: no claim at all."""
    side()
    adapter = qe._ORDER_ADAPTER
    err = {"error": "OSError: status read failed"}
    assert adapter.effective_mode()[0] == wo.MODE_OFF
    assert _codes(_nt(_cfg(tmp_path), broker=err)["send_blocks"]) == [("adapter_off", "all")]
    monkeypatch.setattr(adapter, "effective_mode", lambda: (wo.MODE_PAPER, "test"))
    nt = _nt(_cfg(tmp_path), broker=err)
    assert nt["send_blocks"] == [] and nt["cap"] == {"cap": 85, "held": 12, "room": 73}
    # the doc's own block, when it has a mode, is this tick's status() of the same adapter
    assert _codes(_nt(_cfg(tmp_path), broker={"effective_mode": "OFF"})["send_blocks"]) == [("adapter_off", "all")]

    def broken():
        raise OSError("no mode")
    monkeypatch.setattr(adapter, "effective_mode", broken)
    assert _nt(_cfg(tmp_path), broker=err)["send_blocks"] == []
    now = NOW
    assert qe._next_trade_blocks(_cfg(tmp_path), _state(), False, err, now, BOX_RAILS) == ([], [])
    assert qe._next_trade_blocks(_cfg(tmp_path), _state(), False, BROKER_OK, now, BOX_RAILS) == ([], [])


def test_broker_daily_uses_the_adapter_s_own_limit(side, tmp_path, monkeypatch):
    """The adapter refuses an OPEN on ITS daily_pnl against ITS limit (_check_rails), whatever
    this book's daily_loss_limit_usd says."""
    side()
    adapter = qe._ORDER_ADAPTER
    rails = adapter.cfg["rails"]
    cfg = _cfg(tmp_path, daily_loss_limit_usd=400)
    down = dict(BROKER_OK, daily_pnl=-200.0)
    monkeypatch.setitem(rails, "daily_loss_limit_usd", 150.0)
    nt = _nt(cfg, broker=down)
    assert _codes(nt["send_blocks"]) == [("broker_daily", "send_shared")]
    assert nt["blocks"] == [] and nt["loss"]["limit"] == 400.0, "the book's own stop is not hit"
    # ... and the adapter's own rail agrees
    monkeypatch.setitem(adapter._state, "daily_pnl", -200.0)
    ok, why = adapter._check_rails("NOISE", 20, "OPEN")
    assert not ok and "daily loss limit hit" in why
    assert adapter._check_rails("DIP_RSI", 6, "OPEN")[1] != why, "DIP carries its own rail"
    monkeypatch.setitem(rails, "daily_loss_limit_usd", 400.0)
    assert _nt(cfg, broker=down)["send_blocks"] == []
    # no adapter rails: DEFAULT_RAILS ($200), as the adapter itself reads them
    monkeypatch.setattr(adapter, "cfg", {})
    assert wo.DEFAULT_RAILS["daily_loss_limit_usd"] == 200.0
    assert _codes(_nt(cfg, broker=down)["send_blocks"]) == [("broker_daily", "send_shared")]
    assert _nt(cfg, broker=dict(BROKER_OK, daily_pnl=-199.99))["send_blocks"] == []

    def no_adapter(log=print):
        raise RuntimeError("no adapter")
    monkeypatch.setattr(qe, "_get_broker_adapter", no_adapter)
    nt = _nt(cfg, broker=down)
    assert nt["cap"] is None and _codes(nt["send_blocks"]) == [("broker_daily", "send_shared")]
    assert nt["legs"]["NOISE"]["sent"] == 20, "no cap read: no clamp, as _open_lot"


def test_send_block_broker_open_and_per_leg(side, tmp_path, monkeypatch):
    side()
    adapter = qe._ORDER_ADAPTER
    nt = _nt(_cfg(tmp_path))
    assert nt["legs"]["NOISE"]["send_block"] is None and nt["legs"]["ORB"]["send_block"] is None
    assert "send_block" not in nt["legs"]["DIP"]
    # Webull's book still holds NOISE while this book is flat: the next OPEN stays book-only
    held_at_webull = dict(BROKER_OK, open_legs=["DIP_CAP", "DIP_IBS", "NOISE"])
    nt = _nt(_cfg(tmp_path), broker=held_at_webull)
    noise = nt["legs"]["NOISE"]
    assert (noise["send_block"], noise["sent"], noise["refused"]) == ("broker_open", 20, None)
    assert nt["legs"]["ORB"]["send_block"] is None and "send_block" not in nt["legs"]["DIP"]
    # ... the adapter's own one_open_position_per_leg rail (its session window opened all day)
    monkeypatch.setitem(adapter.cfg["rails"], "session_start", "00:00")
    monkeypatch.setitem(adapter.cfg["rails"], "session_end", "23:59")
    monkeypatch.setitem(adapter._state, "open_legs", {"NOISE": True})
    ok, why = adapter._check_rails("NOISE", 20, "OPEN")
    assert not ok and "one_open_position_per_leg" in why
    # while this book holds the leg too, it is the book's own refusal (busy), not a send block
    nt = _nt(_cfg(tmp_path), _state(legs={"NOISE": _lot("NOISE", 20)}), broker=held_at_webull)
    assert (nt["legs"]["NOISE"]["refused"], nt["legs"]["NOISE"]["send_block"]) == ("busy", None)
    # the adapter's max_shares_per_leg 20, NOISE sending 33 (the book's own 60 takes it)
    monkeypatch.setitem(adapter.cfg["rails"], "max_shares_per_leg", 20)
    doc = _sidecar()
    doc["legs"]["NOISE_382"]["next"].update(size=3.3, keel=1.65)
    side(doc)
    nt = _nt(_cfg(tmp_path))
    noise = nt["legs"]["NOISE"]
    assert (noise["sent"], noise["clamped"], noise["send_block"]) == (33, False, "broker_per_leg")
    assert nt["legs"]["ORB"]["send_block"] is None, "ORB's 10 is under 20"
    monkeypatch.setitem(adapter._state, "open_legs", {})
    ok, why = adapter._check_rails("NOISE", 33, "OPEN")
    assert not ok and "exceeds max_shares_per_leg 20" in why
    monkeypatch.setitem(adapter.cfg["rails"], "max_shares_per_leg", 33)
    assert _nt(_cfg(tmp_path))["legs"]["NOISE"]["send_block"] is None, "at the limit: sent"
    assert adapter._check_rails("NOISE", 33, "OPEN")[0] is True
    # a refused leg sends nothing, so it is never over the adapter's share limit
    monkeypatch.setitem(adapter.cfg["rails"], "max_shares_per_leg", 5)
    nt = _nt(_cfg(tmp_path), _state(kill_done=True))
    assert nt["legs"]["NOISE"]["send_block"] is None and nt["legs"]["ORB"]["send_block"] is None


def test_the_adapter_singleton_is_built_with_the_doc_log(sidecar_file, tmp_path, monkeypatch):
    """_broker_total_room hands its log on to _get_broker_adapter: were the block the first to
    build the process's adapter, every later order log line would go to the no-op one."""
    sidecar_file()
    monkeypatch.setattr(qe, "_now_et", lambda: NOW)
    built = []

    class FakeAdapter:
        def __init__(self, config=None, config_path=None, log=print):
            built.append(log)
            self.log = log
            self.cfg = {"rails": dict(wo.DEFAULT_RAILS, **BOX_RAILS)}

        def effective_mode(self):
            return wo.MODE_PAPER, "test"

        def total_position_room(self):
            return 73, 12, 85

    monkeypatch.setattr(qe, "_ORDER_ADAPTER", None)
    monkeypatch.setattr(wo, "OrderAdapter", FakeAdapter)

    def mylog(*a, **k):
        pass
    nt = qe._build_next_trade(_cfg(tmp_path), _state(), False, {"broker": BROKER_OK}, DAY, log=mylog)
    assert built == [mylog] and qe._ORDER_ADAPTER.log is mylog
    assert nt["cap"] == {"cap": 85, "held": 12, "room": 73}, "the real _broker_total_room read it"
    assert nt["legs"]["NOISE"]["send_block"] is None, "its rails, read off its cfg"
    qe._build_next_trade(_cfg(tmp_path), _state(), False, {"broker": BROKER_OK}, DAY, log=NOOP)
    assert built == [mylog], "built once"


# ── engine statuses ──────────────────────────────────────────────────────────────────────

def test_engine_statuses_that_do_not_size_keep_the_base_and_null_the_shares(side, tmp_path):
    doc = _sidecar()
    n, o = doc["legs"]["NOISE_382"], doc["legs"]["ORB_R6"]
    n.update(status="no_more_today", next=None, long=None, short=None, range_today=None, check=None)
    o.update(status="traded_today", next=None)
    side(doc)
    nt = _nt(_cfg(tmp_path))
    for leg in ("NOISE", "ORB"):
        L = nt["legs"][leg]
        assert L["base"] == 10 and L["decide_close"] is None
        assert [L[k] for k in ("size", "wanted", "sent", "refused", "clamped")] == [None] * 5
    noise = nt["legs"]["NOISE"]
    assert noise["status"] == "no_more_today" and noise["long"] is None and noise["check"] is None
    assert noise["next_session"] == {"date": "2026-10-21", "lo_sh": 10, "hi_sh": 30, "fri": False,
                                     "fomc": False}, "the off-session wording still has its range"
    assert noise["may_change"] == [] and (noise["lo_sh"], noise["hi_sh"]) == (None, None)


def test_orb_range_pending_and_paused_are_sized_at_its_fixed_10(side, tmp_path):
    doc = _sidecar()
    o = doc["legs"]["ORB_R6"]
    o.update(status="range_pending", dir=None, trigger=None, risk=None, rng=None, stop_est=None,
             target_est=None)
    o["next"] = {"decide_bar": "09:35", "decide_close": "09:40"}
    side(doc)
    orb = _nt(_cfg(tmp_path))["legs"]["ORB"]
    assert (orb["status"], orb["sent"], orb["risk"], orb["max_loss"], orb["dir"]) == (
        "range_pending", 10, None, None, None)
    o.update(status="paused", why="pace", dir="short", trigger=715.0, risk=4.6)
    side(doc)
    orb = _nt(_cfg(tmp_path))["legs"]["ORB"]
    assert (orb["status"], orb["why"], orb["sent"], orb["dir"], orb["max_loss"]) == (
        "paused", "pace", 10, "short", 46.0)


def test_orb_s_planned_loss_keeps_the_risk_s_half_cent(side, tmp_path):
    """2.5 x an odd-cent opening range is a half cent a share: the doc keeps the sidecar's 4 dp,
    so sent x risk is the planned loss the board prints (10 x 4.575 = 45.75, never 10 x 4.58)."""
    doc = _sidecar()
    doc["legs"]["ORB_R6"].update(rng=1.83, risk=4.575)
    side(doc)
    orb = _nt(_cfg(tmp_path))["legs"]["ORB"]
    assert (orb["rng"], orb["risk"], orb["sent"], orb["max_loss"]) == (1.83, 4.575, 10, 45.75)


def test_the_planned_loss_is_rounded_half_up_in_decimal(side, tmp_path):
    """shares x the doc's own 4-dp distance, rounded half up to the cent IN DECIMAL: 10 x 5.8435
    is 58.435, which the float product (58.434999...) would round to 58.43 -- the board would
    then print 10 sh x $5.8435 = $58.43. ORB the same: 10 x 4.5875 = 45.875 -> 45.88."""
    assert 10 * 5.8435 < 58.435 and round(10 * 5.8435, 2) == 58.43, "the float trap"
    doc = _sidecar()
    n = doc["legs"]["NOISE_382"]
    n["next"].update(size=1.0, plugin=1.0, keel=1.0, sq30=False)
    n["short"].update(stop_dist=5.8435)
    n["long"].update(stop_dist=2.9690)
    doc["legs"]["ORB_R6"].update(rng=1.835, risk=4.5875)
    side(doc)
    nt = _nt(_cfg(tmp_path))
    noise, orb = nt["legs"]["NOISE"], nt["legs"]["ORB"]
    assert (noise["sent"], noise["short"]["stop_dist"], noise["short"]["max_loss"]) == (10, 5.8435, 58.44)
    assert (noise["long"]["stop_dist"], noise["long"]["max_loss"]) == (2.969, 29.69)
    assert (orb["sent"], orb["risk"], orb["max_loss"]) == (10, 4.5875, 45.88)
    assert (qe._next_trade_loss_at_stop(20, 6.0891), qe._next_trade_loss_at_stop(33, 3.06)) == (121.78, 100.98)
    assert [qe._next_trade_loss_at_stop(*a) for a in ((None, 4.6), (0, 4.6), (10, None), (10, 0.0),
                                                      (10, -1.0), (10, 1e308))] == [None] * 6


def test_the_page_fixture_carries_the_engine_s_own_exit_words():
    """tools/fixtures/qqq_exec_next_trade.json -- the board probe's next_trade cases -- holds the
    exit rules as the engine writes them and this book copies them: the tue case word for word,
    every case in the same mode-neutral form at its own numbers (the page adds where ORB's stop
    lives from doc.orb_resting.mode; the engine never says "Resting")."""
    import re
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tools", "fixtures", "qqq_exec_next_trade.json")
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    assert cases["tue"]["next_trade"]["legs"]["ORB"]["exit"] == ORB_EXIT
    assert cases["tue"]["next_trade"]["legs"]["NOISE"]["exit"] == NOISE_EXIT
    for name, c in cases.items():
        legs = c["next_trade"]["legs"]
        orb, noise = legs["ORB"], legs["NOISE"]
        if "exit" in orb:              # a case may carry a leg cut down to its share fields
            # the breakeven arms on a close that far in the trade's favour: up long, down short
            way = {"long": "up", "short": "down"}[orb["dir"]]
            assert orb["exit"] == (f"Stop {cs._ne_dist(orb['risk'])} a share from the entry close "
                                   f"(2.5x the opening range), target 5x that; stop to the entry "
                                   f"once a close is {cs._ne_dist(0.5 * orb['risk'])} {way}. Out at "
                                   f"the close."), name
        if "exit" in noise:
            assert noise["exit"] == (f"Out at the next open after a 5-min close back across VWAP "
                                     f"(now {noise['vwap']:.2f}), after a bar touches the stop "
                                     f"(1.75x the band width), or at the close. No target."), name
        assert legs["DIP"]["exit"] == qe.DIP_NEXT_EXIT_TEXT, name
        assert not re.search(r"[Rr]esting", json.dumps(c["next_trade"])), name
        assert "send_block" in orb and "send_block" in noise and "send_block" not in legs["DIP"], name


def test_a_failed_leg_and_a_model_on_estimate(side, tmp_path):
    doc = _sidecar()
    doc["legs"]["ORB_R6"] = {"status": "error", "why": "ValueError: " + "x" * 300,
                             "bar": "2026-10-20T10:35:00-04:00", "bar_close": "2026-10-20T10:40:00-04:00"}
    doc["legs"]["NOISE_382"]["next"].update(branch="shade", model_on=True, trust=0.31, z=-0.42,
                                            size=2.84, keel=1.42, may_change=["model", "junk"],
                                            keel_src="fallback", keel_fb="no KEEL state\nhere")
    side(doc)
    nt = _nt(_cfg(tmp_path))
    orb = nt["legs"]["ORB"]
    assert orb["status"] == "error" and orb["sent"] is None
    assert orb["why"] == "ValueError: " + "x" * 145 + "...", "one word: cut at the cap"
    assert len(orb["why"]) == 160 and len(qe._next_trade_text("a " * 200)) <= 160
    noise = nt["legs"]["NOISE"]
    assert (noise["model_on"], noise["trust"], noise["z"], noise["branch"]) == (True, 0.31, -0.42, "shade")
    assert (noise["wanted"], noise["sent"]) == (28, 28) and noise["may_change"] == ["model"]
    assert noise["keel_fb"] == "no KEEL state here", "one line"


def test_a_nan_or_a_bool_in_the_sidecar_never_reaches_the_doc(side, tmp_path):
    raw = json.dumps(_sidecar()).replace('"px": 722.12', '"px": NaN').replace('"risk": 4.6', '"risk": true')
    side(raw=raw)
    nt = _nt(_cfg(tmp_path))
    assert nt["legs"]["NOISE"]["px"] is None and nt["legs"]["ORB"]["px"] is None
    assert nt["legs"]["ORB"]["risk"] is None and nt["legs"]["ORB"]["max_loss"] is None
    assert json.dumps(nt, allow_nan=False)
    # finite inputs whose product is not: a 1e308 risk, a negative stop distance -- no inf, and
    # never a negative "planned loss"
    doc = _sidecar()
    doc["legs"]["ORB_R6"]["risk"] = 1e308
    doc["legs"]["NOISE_382"]["long"]["stop_dist"] = -1.0
    doc["legs"]["NOISE_382"]["short"]["stop_dist"] = -1e308
    side(doc)
    nt = _nt(_cfg(tmp_path))
    assert nt["legs"]["ORB"]["risk"] == 1e308 and nt["legs"]["ORB"]["max_loss"] is None
    assert nt["legs"]["NOISE"]["long"]["max_loss"] is None and nt["legs"]["NOISE"]["short"]["max_loss"] is None
    assert json.dumps(nt, allow_nan=False)


# ── 8. the fingerprint: 0 extra Firestore writes ─────────────────────────────────────────

def test_next_trade_is_not_in_the_fingerprint_and_never_forces_a_publish(side, tmp_path, monkeypatch):
    side()
    base = {"mode": "SHADOW", "feed_stale": False, "px_feed_stale": False, "breaker_tripped": False,
            "kill": False, "positions": {}, "today": {"orders": [], "trades": []}, "events": [],
            "rails": {"dip_rail": None}, "broker": dict(BROKER_OK, effective_mode="OFF")}
    doc_a = json.loads(json.dumps(base))
    doc_b = dict(json.loads(json.dumps(base)), next_trade=_nt(_cfg(tmp_path)))
    doc_c = dict(json.loads(json.dumps(base)),
                 next_trade=_nt(_cfg(tmp_path), _state(kill_done=True), feed_stale=True))
    assert doc_b["next_trade"] and doc_b["next_trade"] != doc_c["next_trade"]
    assert qe._publish_fingerprint(doc_a) == qe._publish_fingerprint(doc_b) == qe._publish_fingerprint(doc_c)
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 14, 10, 0, 0))
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    _, h, now = qe._should_publish({}, doc_a)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1030.0)    # +30 s, inside the interval
    assert qe._should_publish(state, doc_b)[0] is False
    assert qe._should_publish(state, doc_c)[0] is False


# ── 9. the size budget ───────────────────────────────────────────────────────────────────

def test_the_worst_case_block_is_under_3000_bytes_and_200_leaves(side, tmp_path, monkeypatch):
    long_text = "y" * 400
    doc = _sidecar()
    n, o = doc["legs"]["NOISE_382"], doc["legs"]["ORB_R6"]
    n["why"] = o["why"] = long_text
    n["next"].update(keel_src="fallback", keel_fb=long_text, branch=long_text,
                     may_change=["sq30", "sq60", "model"], trust=-0.123456, t_fast=-0.987654,
                     z=1.234567, size=4.123457, plugin=2.0, keel=2.061728)
    n["long"]["why"] = n["short"]["why"] = long_text
    n["exit_rule"] = o["exit_rule"] = long_text
    n["check"].update(preview=4.123457, actual=4.123457, board=4.123457, bar=long_text)
    for k in ("px", "vwap"):
        n[k] = 12345.67
    for k in ("trigger", "px", "rng", "risk", "stop_est", "target_est"):
        o[k] = 12345.67
    doc["host"] = long_text
    side(doc)
    # the adapter's per-leg limit under both sizes: each leg carries the longest send_block code
    monkeypatch.setitem(qe._ORDER_ADAPTER.cfg["rails"], "max_shares_per_leg", 5)
    nt = _nt(_cfg(tmp_path))     # every number populated: nothing refused
    assert nt["legs"]["NOISE"]["long"]["max_loss"] and nt["legs"]["ORB"]["max_loss"]
    assert nt["legs"]["NOISE"]["send_block"] == nt["legs"]["ORB"]["send_block"] == "broker_per_leg"
    # ... and the most blocks there can be (after the bell, every rail on), laid on the same block
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 10, 20, 16, 6, 0, tzinfo=qe._NY))
    st = _state(kill_done=True, breaker_tripped=True,
                dip_rail={"tripped_on": DAY, "blocks_until": "2026-10-21", "loss_usd": -812.0})
    worst = qe._build_next_trade(_cfg(tmp_path), st, True,
                                 {"broker": {"effective_mode": "OFF", "halted": True,
                                             "lease_ok_to_send": False, "daily_pnl": -1234.56}},
                                 DAY, log=NOOP)
    assert len(worst["blocks"]) == 5 and len(worst["send_blocks"]) == 4
    nt.update(blocks=worst["blocks"], send_blocks=worst["send_blocks"])
    size = len(json.dumps(nt, separators=(",", ":"), allow_nan=False))
    leaves = qe._fs_leaves(nt)
    print(f"worst-case next_trade block: {size} bytes, {leaves} leaves")
    assert size < 3000 and leaves < 200
    assert _no_nested_array(nt)
    # a failed leg carries its full 160-char error text (the engine then sends none of its
    # numbers; they are left in here, so this bounds it from above)
    o["status"] = "error"
    side(doc)
    err = _nt(_cfg(tmp_path))
    assert len(err["legs"]["ORB"]["why"]) == 160 and err["legs"]["ORB"]["sent"] is None
    err.update(blocks=worst["blocks"], send_blocks=worst["send_blocks"])
    assert len(json.dumps(err, separators=(",", ":"), allow_nan=False)) < 3000
    assert len(nt["legs"]["NOISE"]["why"]) == len(nt["legs"]["NOISE"]["branch"]) == 24


# ── 10. missing / bad sidecar, nt_notional, a failing build ──────────────────────────────

def test_no_sidecar_no_key_and_an_empty_cfg_does_not_crash(box, side, tmp_path):
    assert not side.path.exists()
    assert "next_trade" not in box(_cfg(tmp_path), _state())
    assert "next_trade" not in box({}, {"trading_day": DAY, "legs": {}})
    side()
    doc = box({}, {"trading_day": DAY, "legs": {}})
    nt = doc["next_trade"]
    assert nt["legs"]["NOISE"]["refused"] == "off" and "DIP" not in nt["legs"]
    assert nt["loss"]["limit"] == 0.0 and nt["loss"]["left"] is None


@pytest.mark.parametrize("raw", ["", "{not json", "[1, 2]", json.dumps(dict(_sidecar(), v=2)),
                                 json.dumps({k: v for k, v in _sidecar().items() if k != "v"})])
def test_a_bad_or_other_version_sidecar_gives_no_key(box, side, tmp_path, raw):
    side(raw=raw)
    assert "next_trade" not in box(_cfg(tmp_path), _state())


def test_nt_notional_sizing_gives_no_key(box, side, tmp_path):
    side()
    assert "next_trade" not in box(_cfg(tmp_path, size_mode="nt_notional"), _state())


def test_a_failing_build_still_gives_the_doc_and_logs_at_most_once_per_10_minutes(box, side, tmp_path,
                                                                                    monkeypatch):
    side()
    lines = []

    def boom(*a, **k):
        raise RuntimeError("bad leg")
    monkeypatch.setattr(qe, "_next_trade_orb", boom)
    clock = [5000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    doc = qe._build_doc(_cfg(tmp_path), _state(), False, 0.0, log=lines.append)
    assert "next_trade" not in doc and doc["today"]["breaker_input"] == -43.59
    qe._build_doc(_cfg(tmp_path), _state(), False, 0.0, log=lines.append)
    mine = [ln for ln in lines if "next-trade block skipped" in ln]
    assert mine == ["[qqq-exec] next-trade block skipped (RuntimeError: bad leg) -- the board shows "
                    "no next-trade line"]
    clock[0] += 601.0
    qe._build_doc(_cfg(tmp_path), _state(), False, 0.0, log=lines.append)
    mine = [ln for ln in lines if "next-trade block skipped" in ln]
    assert len(mine) == 2 and mine[1].endswith("[+1 more since the last line]")
    # and a raise straight out of _build_next_trade is caught by _build_doc itself
    monkeypatch.setattr(qe, "_build_next_trade", boom)
    assert "next_trade" not in qe._build_doc(_cfg(tmp_path), _state(), False, 0.0, log=NOOP)


def test_the_block_rides_the_doc_and_counts_toward_its_budget(box, side, tmp_path):
    side()
    doc = box(_cfg(tmp_path), _state())
    assert doc["next_trade"]["legs"]["NOISE"]["sent"] == 20
    assert doc["next_trade"]["at"] == doc["updated_at"]
    assert doc["next_trade"]["send_blocks"] == [], "the doc's own broker block"


# ── 11. the read memo ────────────────────────────────────────────────────────────────────

def test_the_sidecar_is_parsed_again_only_when_it_changes(side, monkeypatch):
    side()
    calls = []
    real = json.load

    def spy(f, *a, **k):
        calls.append(f.name)
        return real(f, *a, **k)
    monkeypatch.setattr(qe.json, "load", spy)
    a = qe._read_next_entry_cached()
    b = qe._read_next_entry_cached()
    assert a == b == _sidecar() and len(calls) == 1
    doc = _sidecar()
    doc["computed_at"] = "2026-10-20T10:45:31-04:00"
    side(doc)
    assert qe._read_next_entry_cached()["computed_at"] == "2026-10-20T10:45:31-04:00" and len(calls) == 2
    os.remove(side.path)
    assert qe._read_next_entry_cached() == {} and len(calls) == 2


# ── 12. conftest isolation ───────────────────────────────────────────────────────────────

def test_conftest_keeps_every_test_off_the_live_sidecar(box, tmp_path, monkeypatch):
    real = os.path.normcase(os.path.join(cs._paths()["state_dir"], "next_entry.json"))
    assert os.path.normcase(qe._next_entry_path()) != real
    assert not os.path.exists(qe._next_entry_path())
    seen = []
    real_stat = os.stat

    def stat(p, *a, **k):
        seen.append(os.path.normcase(str(p)))
        return real_stat(p, *a, **k)
    monkeypatch.setattr(qe.os, "stat", stat)
    doc = box(_cfg(tmp_path), _state())
    assert "next_trade" not in doc
    assert real not in seen and os.path.normcase(qe._next_entry_path()) in seen
