"""tests/test_noise_forward_log.py -- the NOISE FORWARD LOG for Custom ML's pre-registered
forward test (docs/PREREG_noise_shadow_forward_2026-09-28.md): api/noise_forward.py writes one
decision-time row per NOISE signal into the shadow store; tools/noise_forward_log.py joins the
order adapter's fills onto it.

COVERS:
  1. The flags are the legs' own: at every trade the #382 and #422 plugins take on the
     synthetic series, the squeeze read at the decision bar gives exactly the size the plugin
     gave (all four on/off combinations occur, incl. a #382-only and a #422-only squeeze);
     sq60_on = keel_features' column; a Friday; an FOMC morning (and not after 14:00);
     the fixed tilt = ml_keel.fixed_tilt_sizes_v12 = compression_sizes(1.5, Friday 1.5, cap 3,
     FOMC 0.5 before 14:00).
  2. End to end through cloud_signal.step + run_shadow_step on one synthetic Friday: one row
     per primary entry, every multiplier equal to what the legs emitted (mult_check "ok"),
     both KEEL states' metadata, the engine commit; the live step's events, state.json and
     signals.csv byte-identical with the forward log on and off (and the shadow ledger too).
  3. build_rows: a shadow-only signal gets its own row, a primary entry waits for its shadow
     rows (grace) and is then written naming what is missing, a leg's wrong size is named,
     nothing is written twice, the log never back-fills before it went live.
  4. Shares: the book's rounding and per-leg clamp (= qqq_exec._sized_shares), config caps,
     defaults when the configs are unreadable.
  5. A failing writer never breaks the shadow tick (and logs rate-limited); it never pushes.
     One row that raises is logged once as a "row failed" stub, never blocks the rows after
     it and is not retried; --backfill rebuilds it. KEEL fallbacks are named, not scored.
     The engine commit is read from .git (plain repo, worktree, packed refs) with no git.
  6. The joiner on the real 2026-09-28 ledgers: today's four NOISE trades with their Webull
     fills, exit reasons and per-arm dollars; refused / skipped / open / shadow-only statuses
     and the total-cap check; what Webull did (a BLOCKED halt, a REFUSED 4xx, a CLOSE that
     never filled, a partial fill, OFF, UNKNOWN) as its own status with book-price dollars
     kept apart; an arm with no leg row or a diverging exit is not scored. With the
     scratchpad copy of that day's box files present, also the back-filled decision rows on
     the real bars (skips cleanly without it).
"""
import csv
import io
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import api.cloud_signal as cs                       # noqa: E402
from api import noise_forward as nf                 # noqa: E402
from api import qqq_exec as qe                      # noqa: E402
from augur_engine import ml_keel as K               # noqa: E402
import test_noise_422_shadow as T422               # noqa: E402  (synthetic 5m series + KEEL state)
import test_shadow_legs as TSL                      # noqa: E402  (synthetic home, legs, ticks)
import tools.noise_forward_log as nfl               # noqa: E402

QUIET = lambda *a, **k: None   # noqa: E731
CFG_382 = cs.CROWN_LEGS["NOISE_382"]
CFG_422 = cs.SHADOW_LEGS["NOISE_422_PLAIN"]
WARMUP = max(cs.leg_warmup_sessions(CFG_382), cs.leg_warmup_sessions(CFG_422))
FRIDAY = T422._DAYS[-1]
FOMC_DAY = "2026-09-16"


def _full_trades(cfg):
    """{entry_time: size} of the plugin's own full-history run over the synthetic series."""
    end = pd.Timestamp(f"{FRIDAY} 17:00", tz=cs.TZ).to_pydatetime()
    arr = cs.closed_arrays(T422._EPOCH, end, "5m", cs.leg_warmup_sessions(cfg))
    return {t["entry_time"]: t["size"] for t in cs.run_leg_trades(cfg, arr, leg_key="X")}


def _at(day, hhmm):
    return pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ).isoformat()


# ── 1. the flags are the legs' own ───────────────────────────────────────────────────────
def test_squeeze_at_the_decision_bar_gives_the_size_each_plugin_gave_at_every_trade():
    t382, t422 = _full_trades(CFG_382), _full_trades(CFG_422)
    assert t382 and set(t382) == set(t422), "#382 and #422 share one signal stream"
    combos = set()
    for entry_time in t382:
        arrays, eb, why = nf.decision_arrays(T422._EPOCH, entry_time, WARMUP)
        assert why is None and str(arrays["index"][eb].isoformat()) == entry_time
        on382, m382 = nf.plugin_squeeze(CFG_382, arrays, eb)
        on422, m422 = nf.plugin_squeeze(CFG_422, arrays, eb)
        assert m382 == t382[entry_time] and m422 == t422[entry_time], entry_time
        assert m382 == (2.0 if on382 else 1.0) and m422 == (1.75 if on422 else 1.0)
        combos.add((on382, on422))
    assert combos == {(True, True), (True, False), (False, True), (False, False)}, \
        "a #382-only and a #422-only squeeze must both be exercised"


def test_keel_flags_match_ml_keel_on_a_friday_and_an_fomc_morning():
    fixed_kw = dict(mult=1.5, dow={"4": 1.5}, cap=3.0, event={"mult": 0.5, "cut_hour": 14})
    seen = {"friday": 0, "fomc": 0, "not_fomc_after_14": 0, "sq_on": 0, "sq_off": 0}
    for day, times in ((FRIDAY, ("09:45", "10:30", "11:15", "12:00", "13:05", "14:40", "15:20")),
                       (FOMC_DAY, ("09:50", "10:35", "11:40", "13:55", "14:00", "15:10"))):
        for hhmm in times:
            arrays, eb, why = nf.decision_arrays(T422._EPOCH, _at(day, hhmm), WARMUP)
            assert why is None
            sq60, fri, fomc, tilt = nf.keel_flags(arrays, eb)
            F, names = K.keel_features(arrays)
            assert sq60 == bool(F[eb, names.index("sq60_on")] > 0), (day, hhmm)
            assert fri == (day == FRIDAY)
            assert fomc == (day == FOMC_DAY and int(hhmm[:2]) < 14), (day, hhmm)
            assert fomc == bool(K.pre_statement_mask(arrays, np.array([eb]), 14)[0])
            assert tilt == float(K.fixed_tilt_sizes_v12(arrays, [eb])[0])
            assert tilt == float(K.compression_sizes(arrays, [(eb, eb, 0.0)], **fixed_kw)[0])
            want = min((1.5 if sq60 else 1.0) * (1.5 if fri else 1.0), 3.0) * (0.5 if fomc else 1.0)
            assert tilt == pytest.approx(want, abs=1e-12)
            seen["friday"] += fri
            seen["fomc"] += fomc
            seen["not_fomc_after_14"] += (day == FOMC_DAY and not fomc)
            seen["sq_on" if sq60 else "sq_off"] += 1
    assert all(seen.values()), seen


def test_decision_arrays_refuse_an_entry_whose_signal_bar_is_missing():
    # 09:30 has no bar before it in the same session: the decision bar is not in the data
    arrays, eb, why = nf.decision_arrays(T422._EPOCH, _at(FRIDAY, "09:30"), WARMUP)
    assert arrays is None and eb is None and "signal bar missing" in why


# ── 2. end to end: live step + shadow step on one synthetic Friday ───────────────────────
def _offline(mp):
    def fake_fetch(tf, paths=None, log=print):
        return cs.historical_bars(tf, paths), "webull", True

    def boom(*a, **k):
        raise AssertionError("network touched")
    mp.setattr(cs, "fetch_and_merge", fake_fetch)
    mp.setattr(cs, "_fetch_webull", boom)
    mp.setattr(cs.qp, "_fetch_yf", boom)
    mp.setattr(cs, "_fetch_yf_daily", boom)
    mp.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)


def _write_book_configs(home, base=10, per_leg=60, total=80):
    os.makedirs(os.path.join(home, "qqq_exec"), exist_ok=True)
    os.makedirs(os.path.join(home, "webull_orders"), exist_ok=True)
    with open(os.path.join(home, "qqq_exec", "config.json"), "w", encoding="utf-8") as f:
        json.dump({"shares": {"ORB": 10, "NOISE": base}, "max_shares_per_leg": per_leg}, f)
    with open(os.path.join(home, "webull_orders", "config.json"), "w", encoding="utf-8") as f:
        json.dump({"mode": "PAPER", "rails": {"max_shares_per_leg": per_leg,
                                              "max_total_position_shares": total}}, f)


def _drive(root, forward_log, mp, ticks=30):
    mp.setattr(cs, "NOISE_FORWARD_LOG", forward_log)
    paths = TSL._make_home(root)
    home = paths["home"]
    _write_book_configs(home)
    T422._write_keel_state(home, "NOISE_382")          # a real KEEL score on the primary too
    live, shadow = TSL._live_legs(home), TSL._shadow_legs(home)
    live_events, shadow_events = [], []
    for now in TSL._ticks(ticks):
        live_events += cs.step(now=now, legs=live, paths=paths, fetch=True)
        shadow_events += cs.run_shadow_step(now=now, fetch=True, live_legs=live, shadow_legs=shadow,
                                            live_paths=paths, log=QUIET)
    return {"paths": paths, "live": live_events, "shadow": shadow_events}


@pytest.fixture(scope="module")
def drives(tmp_path_factory):
    """Both drives run once for the module; every patch is undone before the tests read
    the files they left behind."""
    mp = pytest.MonkeyPatch()
    try:
        _offline(mp)
        sent = []
        mp.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
        on = _drive(tmp_path_factory.mktemp("fwd_on"), True, mp)
        off = _drive(tmp_path_factory.mktemp("fwd_off"), False, mp)
        on["sent"] = sent
    finally:
        mp.undo()
    return {"on": on, "off": off}


def _strip_clock(rows):
    return [{k: v for k, v in r.items() if k != "emitted_at"} for r in rows]


def test_live_step_is_byte_identical_with_the_forward_log_on_and_off(drives):
    a, b = drives["on"], drives["off"]
    assert a["live"] and _strip_clock(a["live"]) == _strip_clock(b["live"])
    with open(a["paths"]["state_path"], "rb") as fa, open(b["paths"]["state_path"], "rb") as fb:
        assert fa.read() == fb.read(), "live state.json must not change by one byte"
    assert _strip_clock(TSL._ledger_rows(a["paths"]["signals_path"])) == \
        _strip_clock(TSL._ledger_rows(b["paths"]["signals_path"]))
    # the shadow legs are untouched by it too
    assert _strip_clock(a["shadow"]) == _strip_clock(b["shadow"])
    sa, sb = cs.shadow_paths(a["paths"]), cs.shadow_paths(b["paths"])
    with open(sa["state_path"], "rb") as fa, open(sb["state_path"], "rb") as fb:
        assert fa.read() == fb.read()
    assert os.path.exists(nf.forward_log_path(sa)) and not os.path.exists(nf.forward_log_path(sb))
    assert drives["on"]["sent"] == [], "nothing pages the owner"


def test_one_row_per_primary_entry_with_every_multiplier_equal_to_the_legs(drives):
    d = drives["on"]
    sp = cs.shadow_paths(d["paths"])
    rows = nf.read_csv_rows(nf.forward_log_path(sp))
    with open(nf.forward_log_path(sp), encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == nf.COLS
    prim = [e for e in d["live"] if e["leg"] == "NOISE_382" and e["event"] == "ENTRY"]
    assert prim, "the synthetic Friday must give the primary at least one entry"
    assert [r["signal_id"] for r in rows] == [e["trade_id"] for e in prim]
    assert {r["row_type"] for r in rows} == {"primary"}
    shadow = {(e["leg"], e["ref_time"]): e for e in d["shadow"] if e["event"] == "ENTRY"}
    for r, e in zip(rows, prim):
        assert r["mult_check"] == "ok", r["mult_check"]
        assert r["log_version"] == nf.LOG_VERSION and r["side"] == e["side"]
        assert r["entry_bar_time"] == e["ref_time"] == r["signal_bar_close"]
        assert pd.Timestamp(r["signal_bar_start"]) == pd.Timestamp(e["ref_time"]) - pd.Timedelta(minutes=5)
        assert r["decide_at_close"] == "1" and r["friday"] == "1"
        assert float(r["m_382keel"]) == e["size"] and float(r["keel382_size"]) == e["keel_size"]
        assert float(r["m_382plain"]) == pytest.approx(e["size"] / e["keel_size"], rel=1e-12)
        p, fx, kl = (shadow[(k, e["ref_time"])] for k in nf.ARM_LEGS)
        assert float(r["m_422plain"]) == p["size"]
        assert float(r["m_422fixed"]) == pytest.approx(fx["size"], rel=1e-12)
        assert float(r["fixed_tilt"]) == fx["keel_size"]
        assert float(r["m_422keel"]) == kl["size"] and float(r["keel422_size"]) == kl["keel_size"]
        assert r["shadow_trade_ids"].split(";") == [p["trade_id"], fx["trade_id"], kl["trade_id"]]
        for a in nf.ARMS:
            assert int(r[f"sh_{a}"]) == min(qe._sized_shares(10, float(r[f"m_{a}"])), 60)
        for leg in ("382", "422"):
            assert r[f"keel{leg}_version"] == "v12" and r[f"keel{leg}_seed"] == str(K.SEED)
            assert r[f"keel{leg}_data_through"] == str(T422._DAYS[-2])
            assert int(r[f"keel{leg}_trades"]) > 0
        assert r["keel382_fallback"] == "" and r["keel422_fallback"] == "", "both KEEL states scored"
        assert r["engine_commit"] == nf.engine_commit()
        assert (r["base_shares"], r["max_shares_per_leg"], r["max_total_shares"]) == ("10", "60", "80")
        assert r["note"] == ""
    hb = json.load(open(sp["heartbeat_path"], encoding="utf-8"))
    assert hb["ok"] is True


# ── 3. build_rows: shadow-only, grace, mismatches, no duplicates ─────────────────────────
def _sig(leg, hhmm, side, size, keel_size="", day=FRIDAY, reason="decide_at_close: x"):
    ref = _at(day, hhmm)
    return {"emitted_at": ref, "leg": leg, "event": "ENTRY", "side": side, "ref_time": ref,
            "ref_price": "700.0", "reason": reason, "size": size, "keel_size": keel_size,
            "trade_id": cs._trade_id.make(leg, ref, side)}


def _ctx(tmp_path):
    return nf.context({"NOISE_382": CFG_382}, {"NOISE_422_PLAIN": CFG_422},
                      nf.book_caps(str(tmp_path / "none1"), str(tmp_path / "none2")))


def _true_sizes(hhmm, day=FRIDAY):
    arrays, eb, _ = nf.decision_arrays(T422._EPOCH, _at(day, hhmm), WARMUP)
    m382 = nf.plugin_squeeze(CFG_382, arrays, eb)[1]
    m422 = nf.plugin_squeeze(CFG_422, arrays, eb)[1]
    return m382, m422, nf.keel_flags(arrays, eb)[3]


def test_build_rows_shadow_only_grace_mismatch_and_no_duplicates(tmp_path):
    m382, m422, tilt = _true_sizes("10:15")
    primary = [_sig("NOISE_382", "10:15", "short", m382 * 1.25, 1.25),
               _sig("NOISE_382", "13:30", "long", _true_sizes("13:30")[0], 1.0)]
    shadow = [_sig("NOISE_422_PLAIN", "10:15", "short", m422),
              _sig("NOISE_422_FIXED", "10:15", "short", m422 * tilt, tilt),
              _sig("NOISE_422_KEEL", "10:15", "short", m422 * 0.8, 0.8),
              # the #422 legs took a trade the primary did not
              _sig("NOISE_422_PLAIN", "11:05", "long", _true_sizes("11:05")[1]),
              # 13:30: only a KEEL row, with the WRONG plugin part
              _sig("NOISE_422_KEEL", "13:30", "long", 2.5 * 1.25, 1.25)]
    bars = lambda: T422._EPOCH          # noqa: E731
    ctx = _ctx(tmp_path)
    # at 13:32 the 13:30 entry is still inside its grace: held, the rest written
    now = pd.Timestamp(f"{FRIDAY} 13:32", tz=cs.TZ).to_pydatetime()
    rows, pending = nf.build_rows(primary, shadow, bars, now, ctx, set(), str(FRIDAY))
    assert pending == 1
    assert [(r["row_type"], r["signal_id"]) for r in rows] == [
        ("primary", primary[0]["trade_id"]), ("shadow_only", shadow[3]["trade_id"])]
    ok, only = rows
    assert ok["mult_check"] == "ok", ok["mult_check"]
    assert float(ok["m_382keel"]) == pytest.approx(m382 * 1.25) and float(ok["m_422keel"]) == pytest.approx(m422 * 0.8)
    assert "no NOISE_382 entry" in only["mult_check"] and only["m_382keel"] == ""
    assert only["sh_382keel"] == "" and only["shadow_trade_ids"] == shadow[3]["trade_id"]
    # past the grace: written, naming what is missing and what is wrong
    later = now + pd.Timedelta(minutes=15).to_pytimedelta()
    rows2, pending2 = nf.build_rows(primary, shadow, bars, later, ctx,
                                    {r["signal_id"] for r in rows}, str(FRIDAY))
    assert pending2 == 0 and len(rows2) == 1
    chk = rows2[0]["mult_check"]
    assert "no NOISE_422_PLAIN row" in chk and "no NOISE_422_FIXED row" in chk
    assert "NOISE_422_KEEL plugin size 2.5" in chk
    # nothing twice, and nothing from before the log's first day
    logged = {r["signal_id"] for r in rows + rows2}
    assert nf.build_rows(primary, shadow, bars, later, ctx, logged, str(FRIDAY)) == ([], 0)
    tomorrow = (pd.Timestamp(FRIDAY) + pd.Timedelta(days=3)).date().isoformat()
    assert nf.build_rows(primary, shadow, bars, later, ctx, set(), tomorrow) == ([], 0)


def test_since_date_for_never_back_fills_before_the_log_went_live():
    today = pd.Timestamp("2026-10-05").date()
    assert nf.since_date_for([], today) == "2026-10-05"
    assert nf.since_date_for([{"entry_bar_time": "2026-10-02T10:15:00-04:00"}], today) == "2026-10-02"
    assert nf.since_date_for([{"entry_bar_time": "2026-09-29T10:15:00-04:00"}], today) == "2026-09-30"


# ── 4. shares ────────────────────────────────────────────────────────────────────────────
def test_sized_shares_are_the_books_rounding_and_per_leg_clamp():
    for m in (1.0, 1.25, 1.5, 1.75, 2.0, 2.625, 0.04, 0.5, 3.5, 5.25):
        assert nf.sized_shares(10, m, 0) == qe._sized_shares(10, m), m
    assert nf.sized_shares(10, 1.75, 60) == 18
    assert nf.sized_shares(10, 5.25, 60) == 52, "52.5 rounds half to even, exactly as the book does"
    assert nf.sized_shares(10, 7.0, 60) == 60, "clamped at the per-leg cap"
    assert nf.sized_shares(10, 7.0, 20) == 20
    assert nf.sized_shares(10, 0.04, 60) == 1 and nf.sized_shares(0, 2.0, 60) == 0
    assert nf.sized_shares(10, None, 60) is None


def test_book_caps_read_the_configs_and_default_when_unreadable(tmp_path):
    home = str(tmp_path)
    _write_book_configs(home, base=12, per_leg=40, total=70)
    q = os.path.join(home, "qqq_exec", "config.json")
    o = os.path.join(home, "webull_orders", "config.json")
    assert nf.book_caps(q, o) == (12, 40, 70, "")
    base, per_leg, total, note = nf.book_caps(str(tmp_path / "x.json"), str(tmp_path / "y.json"))
    assert (base, per_leg, total) == (10, 60, 80)
    assert "qqq_exec config" in note and "webull_orders rails" in note
    assert nf._book_config_paths(cs._paths(home=home)) == (q, o)


def test_book_caps_take_the_smaller_per_leg_cap_of_qqq_exec_and_the_rails(tmp_path):
    home = str(tmp_path)
    _write_book_configs(home, per_leg=60)
    q = os.path.join(home, "qqq_exec", "config.json")
    o = os.path.join(home, "webull_orders", "config.json")

    def rails(per_leg):
        with open(o, "w", encoding="utf-8") as f:
            json.dump({"mode": "PAPER", "rails": {"max_shares_per_leg": per_leg,
                                                  "max_total_position_shares": 80}}, f)
    rails(50)
    assert nf.book_caps(q, o)[1] == 50, "the rail refuses past 50, so no leg holds more"
    rails(70)
    assert nf.book_caps(q, o)[1] == 60, "qqq_exec clamps at 60 first"
    rails(0)
    assert nf.book_caps(q, o)[1] == 60, "an unset rail leaves qqq_exec's clamp"


def test_keel_fallback_names_why_a_one_was_not_a_score(tmp_path, monkeypatch):
    home = str(tmp_path)
    entry = _at(FRIDAY, "10:15")
    kp = dict(version="v12", **cs.keel_paths("NOISE_382", "v12", home=home))
    monkeypatch.setattr(cs, "_KEEL_STATE_CACHE", {})
    # a fallback is always exactly 1.0: any other keel_size is a real score, nothing checked
    assert nf.keel_fallback(kp, entry, 1.3) == "" and nf.keel_fallback(kp, entry, "") == ""
    assert nf.keel_fallback(None, entry, 1.0) == ""
    assert nf.keel_fallback(dict(mode="fixed", version="v12"), entry, 1.0) == ""
    assert nf.keel_fallback(kp, entry, 1.0) == "keel state unavailable (no state file)"
    assert nf.keel_fallback(dict(version="v12"), entry, 1.0) == "keel config has no state_path"
    cfg = T422._write_keel_state(home, "NOISE_382")
    assert "not loaded in this process" in nf.keel_fallback(cfg, entry, 1.0)
    state, _summary = cs._load_keel_state(cfg["state_path"], cfg["summary_path"])  # the leg's load
    assert state is not None
    arrays, _eb, _why = nf.decision_arrays(T422._EPOCH, entry, WARMUP)
    assert nf.keel_fallback(cfg, entry, 1.0) == "" == nf.keel_fallback(cfg, entry, 1.0, arrays), \
        "a loaded, fresh, matching state: a 1.0 is a real score (zero trust)"
    later = (pd.Timestamp(str(FRIDAY)) + pd.Timedelta(days=14)).date().isoformat()
    assert nf.keel_fallback(cfg, _at(later, "10:15"), 1.0).startswith("keel state stale: ")
    hit = cs._KEEL_STATE_CACHE[cfg["state_path"]]
    monkeypatch.setitem(cs._KEEL_STATE_CACHE, cfg["state_path"],
                        (hit[0], dict(hit[1], feature_names=["not_a_feature"]), hit[2]))
    assert nf.keel_fallback(cfg, entry, 1.0, arrays) == "keel feature columns do not match the state"


def test_one_failing_row_is_logged_once_and_never_blocks_the_rest(tmp_path, monkeypatch):
    paths = TSL._make_home(tmp_path)
    sp = cs.shadow_paths(paths)
    primary = [_sig("NOISE_382", "10:15", "short", _true_sizes("10:15")[0], 1.0),
               _sig("NOISE_382", "13:30", "long", _true_sizes("13:30")[0], 1.0)]
    cs._append_signals(primary, paths)
    real, calls = nf._row, []

    def flaky(row_type, sid, *a, **k):
        calls.append(sid)
        if sid == primary[0]["trade_id"]:
            raise ValueError("synthetic bad row")
        return real(row_type, sid, *a, **k)
    monkeypatch.setattr(nf, "_row", flaky)
    monkeypatch.setattr(nf, "_MEMO", {"key": None, "pending": 0})
    live = {"NOISE_382": dict(CFG_382, keel=dict(version="v12", **cs.keel_paths(
        "NOISE_382", "v12", home=paths["home"])))}
    now = pd.Timestamp(f"{FRIDAY} 15:00", tz=cs.TZ).to_pydatetime()
    assert nf.forward_log_tick(now, paths, sp, live, {}, log=QUIET) == 2
    bad, good = nf.read_csv_rows(nf.forward_log_path(sp))
    assert (bad["signal_id"], good["signal_id"]) == (primary[0]["trade_id"], primary[1]["trade_id"])
    assert bad["mult_check"] == "row failed: ValueError: synthetic bad row"
    assert (bad["entry_bar_time"], bad["side"], bad["m_382plain"]) == (primary[0]["ref_time"], "short", "")
    assert good["m_382plain"] != "" and "row failed" not in good["mult_check"]
    # the stub counts as logged: a new ledger line makes the tick look again, and it is not retried
    cs._append_signals([_sig("NOISE_382", "14:40", "short", _true_sizes("14:40")[0], 1.0)], paths)
    n_calls = len(calls)
    assert nf.forward_log_tick(now + pd.Timedelta(minutes=30).to_pytimedelta(), paths, sp, live, {},
                               log=QUIET) == 1
    assert calls[n_calls:] == [cs._trade_id.make("NOISE_382", _at(FRIDAY, "14:40"), "short")]
    # --backfill rebuilds the stub from the ledgers and the bars; the stub is replaced
    monkeypatch.setattr(nf, "_row", real)
    table = nfl.decision_rows(nfl.input_paths(paths["home"]), backfill=True, now=now)
    by = {r["signal_id"]: r for r in table}
    assert len(table) == 3 and by[bad["signal_id"]]["row_source"] == "backfill"
    assert by[bad["signal_id"]]["m_382plain"] != ""
    assert by[good["signal_id"]]["row_source"] == "forward_log"


def test_engine_commit_is_read_from_git_files_with_no_subprocess(tmp_path, monkeypatch):
    import subprocess
    want = subprocess.run(["git", "rev-parse", "HEAD"], cwd=nf.ROOT, capture_output=True,
                          text=True).stdout.strip()
    assert nf.git_head_sha() == want
    sha_a, sha_b = "a" * 40, "b" * 40
    # a linked worktree: .git is a file, its branch ref lives in the common dir's packed-refs
    common = tmp_path / "main.git"
    wt_git = common / "worktrees" / "wt"
    wt_git.mkdir(parents=True)
    (wt_git / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
    (common / "packed-refs").write_text(f"# pack-refs with: peeled\n{sha_b} refs/heads/feature\n",
                                        encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {wt_git.as_posix()}\n", encoding="utf-8")
    assert nf.git_head_sha(str(wt)) == sha_b
    # a plain repo with a loose ref, and a detached HEAD
    repo = tmp_path / "repo"
    (repo / ".git" / "refs" / "heads").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo / ".git" / "refs" / "heads" / "main").write_text(sha_a + "\n", encoding="utf-8")
    assert nf.git_head_sha(str(repo)) == sha_a
    (repo / ".git" / "HEAD").write_text(sha_b + "\n", encoding="utf-8")
    assert nf.git_head_sha(str(repo)) == sha_b
    assert nf.git_head_sha(str(tmp_path / "nothing")) == ""
    # engine_commit never starts git when the files answer
    monkeypatch.setattr(nf, "_COMMIT", [])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("git ran")))
    assert nf.engine_commit() == want


# ── 5. a failing writer never breaks the tick; it never pushes ───────────────────────────
def test_a_failing_forward_log_never_breaks_the_shadow_tick(tmp_path, monkeypatch):
    _offline(monkeypatch)
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", True)
    paths = TSL._make_home(tmp_path)
    live, shadow = TSL._live_legs(paths["home"]), TSL._shadow_legs(paths["home"])
    monkeypatch.setattr(nf, "_ERR", {"last_logged": 0.0, "suppressed": 0})
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("synthetic forward-log failure")
    monkeypatch.setattr(nf, "_tick", boom)
    logs, events = [], []
    for now in TSL._ticks(3):
        events += cs.run_shadow_step(now=now, fetch=True, live_legs=live, shadow_legs=shadow,
                                     live_paths=paths, log=logs.append)
    sp = cs.shadow_paths(paths)
    assert len(calls) == 4 and events, "the shadow legs still ran every tick"
    assert json.load(open(sp["heartbeat_path"], encoding="utf-8"))["ok"] is True
    fails = [m for m in logs if "NOISE forward log failed" in m]
    assert len(fails) == 1 and nf._ERR["suppressed"] == 3, fails
    assert not os.path.exists(nf.forward_log_path(sp))


def test_forward_log_tick_never_pushes_even_on_a_cloud_host(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    paths = TSL._make_home(tmp_path)
    sp = cs.shadow_paths(paths)
    cs._append_signals([_sig("NOISE_382", "10:15", "short", 1.0, 1.0)], paths)
    now = pd.Timestamp(f"{FRIDAY} 11:00", tz=cs.TZ).to_pydatetime()
    live = {"NOISE_382": dict(CFG_382, keel=dict(version="v12", **cs.keel_paths(
        "NOISE_382", "v12", home=paths["home"])))}
    assert nf.forward_log_tick(now, paths, sp, live, {}, log=QUIET) == 1
    assert sent == []
    rows = nf.read_csv_rows(nf.forward_log_path(sp))
    assert len(rows) == 1 and "no NOISE_422_PLAIN row" in rows[0]["mult_check"]
    assert rows[0]["keel382_seed"] == "" and rows[0]["keel382_data_through"] == ""
    # no KEEL state on this home: the 1.0 the leg emitted is named as the fallback it was
    assert rows[0]["keel382_fallback"] == "keel state unavailable (no state file)"
    # a repeat tick with nothing new writes nothing
    assert nf.forward_log_tick(now, paths, sp, live, {}, log=QUIET) == 0
    # no primary leg in the live legs (a stub run): a no-op
    assert nf.forward_log_tick(now, paths, sp, {"ORB_R6": {}}, {}, log=QUIET) == 0


# ── 6. the joiner on the real 2026-09-28 ledgers ─────────────────────────────────────────
# Verbatim 09-28 rows from the box (pulled that evening): the primary's four trades, ORB's
# (other open shares) and ENGU-Q's.
SIGNALS_0928 = """emitted_at,leg,event,side,ref_time,ref_price,shares,reason,bar_source,trade_id,size,keel_size
2026-09-28T10:15:06.335667-04:00,NOISE_382,ENTRY,short,2026-09-28T10:15:00-04:00,735.6599,135,"decide_at_close: decided at the close of the 10:10 bar, priced at that close",webull,NOISE_382-20260928T141500Z-S,2.0,1.0
2026-09-28T11:40:06.494936-04:00,NOISE_382,EXIT,short,2026-09-28T11:40:00-04:00,735.695,135,"strategy_exit; decide_at_close: decided at the close of the 11:35 bar, priced at that close",webull,NOISE_382-20260928T141500Z-S,2.0,1.0
2026-09-28T11:45:06.325321-04:00,NOISE_382,ENTRY,short,2026-09-28T11:45:00-04:00,734.45,136,"decide_at_close: decided at the close of the 11:40 bar, priced at that close",webull,NOISE_382-20260928T154500Z-S,1.0,1.0
2026-09-28T12:00:06.908622-04:00,NOISE_382,EXIT,short,2026-09-28T12:00:00-04:00,735.63,136,"strategy_exit; decide_at_close: decided at the close of the 11:55 bar, priced at that close",webull,NOISE_382-20260928T154500Z-S,1.0,1.0
2026-09-28T12:05:07.087236-04:00,NOISE_382,ENTRY,short,2026-09-28T12:05:00-04:00,735.31,135,"decide_at_close: decided at the close of the 12:00 bar, priced at that close",webull,NOISE_382-20260928T160500Z-S,1.0,1.0
2026-09-28T12:10:06.982898-04:00,NOISE_382,EXIT,short,2026-09-28T12:10:00-04:00,735.62,136,"strategy_exit; decide_at_close: decided at the close of the 12:05 bar, priced at that close",webull,NOISE_382-20260928T160500Z-S,1.0,1.0
2026-09-28T12:15:07.014219-04:00,NOISE_382,ENTRY,short,2026-09-28T12:15:00-04:00,735.465,135,"decide_at_close: decided at the close of the 12:10 bar, priced at that close",webull,NOISE_382-20260928T161500Z-S,1.0,1.0
2026-09-28T12:20:05.758344-04:00,NOISE_382,EXIT,short,2026-09-28T12:20:00-04:00,736.88,135,"strategy_exit; decide_at_close: decided at the close of the 12:15 bar, priced at that close",webull,NOISE_382-20260928T161500Z-S,1.0,1.0
"""
ORDERS_0928 = """ts_et,leg,action,side,shares,nq_px,qqq_px,px_source,reason,latency_s,signal_source,size,shares_wanted,after_close_s
2026-09-28 10:15:11,NOISE,ENTER,short,20,,735.6499,engine_webull,signal entry,11.159,engine,2.0,20,11.159
2026-09-28 10:50:06,ORB,ENTER,short,10,,732.32,engine_webull,signal entry,306.654,engine,1.0,10,6.654
2026-09-28 11:40:09,NOISE,EXIT,short,20,,735.705,engine_webull,signal exit,9.715,engine,2.0,20,9.715
2026-09-28 11:45:09,NOISE,ENTER,short,10,,734.44,engine_webull,signal entry,9.091,engine,1.0,10,9.091
2026-09-28 12:00:08,NOISE,EXIT,short,10,,735.64,engine_webull,signal exit,8.503,engine,1.0,10,8.503
2026-09-28 12:05:08,NOISE,ENTER,short,10,,735.3,engine_webull,signal entry,8.57,engine,1.0,10,8.57
2026-09-28 12:10:09,NOISE,EXIT,short,10,,735.63,engine_webull,signal exit,9.12,engine,1.0,10,9.12
2026-09-28 12:15:09,NOISE,ENTER,short,10,,735.455,engine_webull,signal entry,9.064,engine,1.0,10,9.064
2026-09-28 12:20:09,NOISE,EXIT,short,10,,736.89,engine_webull,signal exit,9.816,engine,1.0,10,9.816
2026-09-28 15:59:01,ORB,EXIT,short,10,,736.76,live_stream,EOD (px: live_stream),,engine,1.0,10,
"""
BROKER_0928 = """ts_et,leg,intent,side,shares,signal_id,client_order_id,mode,ok,sent,shadow_px,broker_fill_px,slippage,reason,duplicate,host_id,outcome
2026-09-28 10:15:11,NOISE,OPEN,SHORT,20,qxNOISE38220260928T141500ZSO,qxNOISE38220260928T141500ZSO,PAPER,True,True,735.6499,735.87,0.2201,,False,edgelog,OK
2026-09-28 11:40:09,NOISE,CLOSE,BUY,20,qxNOISE38220260928T141500ZSC,qxNOISE38220260928T141500ZSC,PAPER,True,True,735.705,735.57,-0.135,,False,edgelog,OK
2026-09-28 11:45:09,NOISE,OPEN,SHORT,10,qxNOISE38220260928T154500ZSO,qxNOISE38220260928T154500ZSO,PAPER,True,True,734.44,734.35,-0.09,,False,edgelog,OK
2026-09-28 12:00:08,NOISE,CLOSE,BUY,10,qxNOISE38220260928T154500ZSC,qxNOISE38220260928T154500ZSC,PAPER,True,True,735.64,735.68,0.04,,False,edgelog,OK
2026-09-28 12:05:08,NOISE,OPEN,SHORT,10,qxNOISE38220260928T160500ZSO,qxNOISE38220260928T160500ZSO,PAPER,True,True,735.3,735.15,-0.15,,False,edgelog,OK
2026-09-28 12:10:09,NOISE,CLOSE,BUY,10,qxNOISE38220260928T160500ZSC,qxNOISE38220260928T160500ZSC,PAPER,True,True,735.63,735.73,0.1,,False,edgelog,OK
2026-09-28 12:15:09,NOISE,OPEN,SHORT,10,qxNOISE38220260928T161500ZSO,qxNOISE38220260928T161500ZSO,PAPER,True,True,735.455,735.57,0.115,,False,edgelog,OK
2026-09-28 12:20:10,NOISE,CLOSE,BUY,10,qxNOISE38220260928T161500ZSC,qxNOISE38220260928T161500ZSC,PAPER,True,True,736.89,736.74,-0.15,,False,edgelog,OK
"""
TRADES_0928 = """leg,entry_ts,exit_ts,side,shares,entry_px,exit_px,pnl,nq_pnl_points,exit_reason,nt_entry_exec_id,nt_entry_ts,nt_entry_px,nt_exit_exec_id,nt_exit_ts,nt_exit_px,nt_qty,ratio_at_entry,ratio_at_exit,nt_reconstructed,nt_mult,nt_notional_usd,shadow_notional_usd,notional_ratio,signal_source,trade_id,size,shares_wanted,keel_size
NOISE,2026-09-28 10:15:11,2026-09-28 11:40:09,short,20,735.6499,735.705,-1.1,,signal exit,,,,,,,,41.17517575599396,41.17517575599396,,,,14713.0,,engine,NOISE_382-20260928T141500Z-S,2.0,20,1.0
NOISE,2026-09-28 11:45:09,2026-09-28 12:00:08,short,10,734.44,735.64,-12.0,,signal exit,,,,,,,,41.17517575599396,41.17517575599396,,,,7344.4,,engine,NOISE_382-20260928T154500Z-S,1.0,10,1.0
NOISE,2026-09-28 12:05:08,2026-09-28 12:10:09,short,10,735.3,735.63,-3.3,,signal exit,,,,,,,,41.17517575599396,41.17517575599396,,,,7353.0,,engine,NOISE_382-20260928T160500Z-S,1.0,10,1.0
NOISE,2026-09-28 12:15:09,2026-09-28 12:20:10,short,10,735.455,736.89,-14.35,,signal exit,,,,,,,,41.17517575599396,41.17517575599396,,,,7354.55,,engine,NOISE_382-20260928T161500Z-S,1.0,10,1.0
ORB,2026-09-28 10:50:06,2026-09-28 15:59:01,short,10,732.32,736.76,-44.4,,EOD (px: live_stream),,,,,,,,41.17517575599396,41.17517575599396,,,,7323.2,,engine,ORB_R6-20260928T144500Z-S,1.0,10,
ENGUQ,2026-09-28 12:33:38,2026-09-28 15:59:01,long,10,738.0395,736.66,-13.8,,EOD (px: live_stream),,,,,,,,41.17517575599396,41.17517575599396,,,,7380.39,,engine,ENGUQ_335-20260928T163200Z-L,1.0,10,
"""
# The four decision rows, as the forward log would hold them (multipliers from the joiner's
# back-fill on that day's real bars -- see the scratchpad test below).
M_0928 = {"NOISE_382-20260928T141500Z-S": (2.0, 1.75), "NOISE_382-20260928T154500Z-S": (1.0, 1.0),
          "NOISE_382-20260928T160500Z-S": (1.0, 1.0), "NOISE_382-20260928T161500Z-S": (1.0, 1.0)}
# per trade: (Webull entry fill, Webull exit fill, per-share P&L short)
FILLS_0928 = {"NOISE_382-20260928T141500Z-S": (735.87, 735.57, 0.30),
              "NOISE_382-20260928T154500Z-S": (734.35, 735.68, -1.33),
              "NOISE_382-20260928T160500Z-S": (735.15, 735.73, -0.58),
              "NOISE_382-20260928T161500Z-S": (735.57, 736.74, -1.17)}


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _shadow_0928():
    """The three #422 legs' ENTRY/EXIT rows for the day's four signals: same bars, sides and
    prices as the primary's (the legs did not exist that day; this is what they would log)."""
    out = []
    for r in csv.DictReader(io.StringIO(SIGNALS_0928)):
        entry_ref = next(e["ref_time"] for e in csv.DictReader(io.StringIO(SIGNALS_0928))
                         if e["trade_id"] == r["trade_id"] and e["event"] == "ENTRY")
        for leg in nf.ARM_LEGS:
            out.append(dict(r, leg=leg, trade_id=cs._trade_id.make(leg, entry_ref, r["side"])))
    return out


def _csv_text(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _home_0928(tmp_path, extra_decisions=(), state=None, shadow_edit=None, broker_edit=None):
    """A home holding the day's ledgers and the four decision rows. `shadow_edit(rows)` /
    `broker_edit(rows)` may change the #422 legs' signal rows / broker_orders.csv rows
    (lists of dicts) before they are written."""
    home = str(tmp_path / "home")
    paths = nfl.input_paths(home)
    _write(paths["signals"], SIGNALS_0928)
    _write(paths["orders"], ORDERS_0928)
    broker = list(csv.DictReader(io.StringIO(BROKER_0928)))
    _write(paths["broker_orders"], _csv_text(broker_edit(broker) if broker_edit else broker))
    _write(paths["trades"], TRADES_0928)
    _write(paths["exec_state"], json.dumps(state or {"legs": {}, "events": []}))
    shadow = _shadow_0928()
    shadow = shadow_edit(shadow) if shadow_edit else shadow
    _write(paths["shadow_signals"], _csv_text(shadow))
    rows = []
    for sid, (m382, m422) in M_0928.items():
        e = next(r for r in csv.DictReader(io.StringIO(SIGNALS_0928))
                 if r["trade_id"] == sid and r["event"] == "ENTRY")
        ids = {s["leg"]: s["trade_id"] for s in shadow
               if s["event"] == "ENTRY" and s["ref_time"] == e["ref_time"]}
        r = {c: "" for c in nf.COLS}
        r.update({"log_version": nf.LOG_VERSION, "row_type": "primary", "signal_id": sid,
                  "side": e["side"], "entry_bar_time": e["ref_time"], "base_shares": 10,
                  "max_shares_per_leg": 60, "max_total_shares": 80,
                  "shadow_trade_ids": ";".join(ids[k] for k in nf.ARM_LEGS if k in ids),
                  "m_382plain": m382, "m_422plain": m422, "m_422fixed": m422,
                  "m_382keel": float(e["size"]), "m_422keel": m422})
        for a in nf.ARMS:
            r[f"sh_{a}"] = nf.sized_shares(10, float(r[f"m_{a}"]), 60)
        rows.append(r)
    nf.append_rows(paths["forward_log"], rows + list(extra_decisions))
    return paths


def test_joiner_gives_the_four_0928_noise_trades_with_their_webull_fills(tmp_path):
    paths = _home_0928(tmp_path)
    out = nfl.build_table(paths)
    assert [r["signal_id"] for r in out] == list(M_0928)
    for r in out:
        sid = r["signal_id"]
        e_fill, x_fill, pps = FILLS_0928[sid]
        assert r["row_source"] == "forward_log" and r["primary_status"] == "filled", r
        assert r["primary_status_detail"] == "" and r["exit_divergence"] == "" == r["arms_not_scored"]
        assert r["entry_fill_px"] == e_fill and r["exit_fill_px"] == x_fill
        assert r["entry_broker_outcome"] == r["exit_broker_outcome"] == "OK"
        assert r["entry_broker_sent_ts_et"][:10] == "2026-09-28"
        assert r["entry_filled_shares"] == r["exit_filled_shares"] == int(r["entry_shares"])
        assert r["pnl_per_share"] == pytest.approx(pps)
        assert r["pnl_per_share_book"] == pytest.approx(
            (float(r["exit_shadow_px"]) - float(r["entry_shadow_px"])) * -1.0)
        assert r["exit_reason"] == "signal exit" and r["entry_capped"] == 0
        assert r["entry_shares"] == r["entry_shares_wanted"] == ("20" if sid.endswith("141500Z-S") else "10")
        m382, m422 = M_0928[sid]
        assert r["pnl_usd_382plain"] == pytest.approx(pps * 10 * m382)
        assert r["pnl_usd_422plain"] == pytest.approx(pps * 10 * m422)
        assert r["pnl_usd_422plain_capped"] == pytest.approx(pps * nf.sized_shares(10, m422, 60))
        assert r["exit_signal_time"] and r["exit_signal_price"]
    first = out[0]
    assert first["other_open_shares"] == 0, "ORB entered at 10:50, after NOISE's 10:15"
    assert out[1]["other_open_shares"] == 10, "ORB's 10 shares were open at 11:45"
    assert first["pnl_usd_382keel"] == pytest.approx(6.0)
    assert first["pnl_usd_422plain_capped"] == pytest.approx(0.30 * 18)
    assert first["pnl_usd_382keel_book"] == pytest.approx(-0.0551 * 10 * 2.0), "book prices, apart"
    assert first["entry_broker_sent_ts_et"] == "2026-09-28 10:15:11"
    assert first["exit_broker_sent_ts_et"] == "2026-09-28 11:40:09"
    # the CLI writes the same table
    out_csv = str(tmp_path / "table.csv")
    assert nfl.main(["--home", os.path.dirname(os.path.dirname(paths["orders"])), "--out", out_csv]) == 0
    got = list(csv.DictReader(open(out_csv, encoding="utf-8", newline="")))
    assert list(got[0]) == nfl.JOIN_COLS and len(got) == 4


def test_joiner_statuses_refused_skipped_open_shadow_only_and_the_total_cap(tmp_path):
    def decision(hhmm, side, m, row_type="primary", leg="NOISE_382"):
        ref = f"2026-09-28T{hhmm}:00-04:00"
        r = {c: "" for c in nf.COLS}
        r.update({"row_type": row_type, "signal_id": cs._trade_id.make(leg, ref, side), "side": side,
                  "entry_bar_time": ref, "base_shares": 10, "max_total_shares": 80,
                  "m_382keel": m, "sh_382keel": nf.sized_shares(10, m, 60)})
        return r
    refused = decision("13:00", "long", 1.0)
    skipped = decision("13:30", "short", 1.0)
    opened = decision("14:00", "long", 1.0)
    shadow_only = decision("14:30", "long", 1.0, "shadow_only", "NOISE_422_PLAIN")
    capped = decision("11:00", "short", 7.0)     # 60 shares + ORB's 10 + ... past the 80 total?
    state = {"legs": {"NOISE": {"trade_id": opened["signal_id"], "entry_ts": "2026-09-28 14:00:08",
                                "shares_total": 10, "shares_wanted": 10, "entry_px": 736.1}},
             "events": [{"ts_et": "2026-09-28 13:30:06", "kind": "entry_leg_busy",
                         "text": "NOISE entry signal for " + cs._trade_id.describe(
                             skipped["signal_id"], nfl._tz()) + " while ... ; not taken"}]}
    paths = _home_0928(tmp_path, extra_decisions=[refused, skipped, opened, shadow_only, capped],
                       state=state)
    with open(paths["orders"], "a", encoding="utf-8", newline="") as f:
        f.write("2026-09-28 13:00:09,NOISE,ENTER,long,10,,,,REFUSED -- breaker/feed/kill blocked,"
                "9.0,engine,1.0,10,\n")
    with open(paths["broker_orders"], "a", encoding="utf-8", newline="") as f:
        oid = "qx" + nfl._alnum(opened["signal_id"]) + "O"
        f.write(f"2026-09-28 14:00:08,NOISE,OPEN,BUY,10,{oid},{oid},PAPER,True,True,736.1,736.2,"
                "0.1,,False,edgelog,OK\n")
    # a second leg holding 15 shares at 11:00 puts the 60-share arm past the 80 total
    with open(paths["trades"], "a", encoding="utf-8", newline="") as f:
        f.write("ENGUQ,2026-09-28 10:30:00,2026-09-28 11:30:00,long,15,1,1,0,,x"
                + "," * 19 + "\n")
    by = {r["signal_id"]: r for r in nfl.build_table(paths)}
    assert by[refused["signal_id"]]["primary_status"] == "refused"
    assert "breaker/feed/kill" in by[refused["signal_id"]]["primary_status_detail"]
    assert by[skipped["signal_id"]]["primary_status"] == "skipped"
    assert "entry_leg_busy" in by[skipped["signal_id"]]["primary_status_detail"]
    op = by[opened["signal_id"]]
    assert op["primary_status"] == "open" and op["entry_shares"] == 10 and op["pnl_per_share"] == ""
    assert op["entry_fill_px"] == 736.2 and op["pnl_per_share_book"] == ""
    assert by[shadow_only["signal_id"]]["primary_status"] == "n/a"
    cp = by[capped["signal_id"]]
    assert cp["primary_status"] == "no_order_found"
    assert cp["other_open_shares"] == 25, "ORB 10 (from 10:50) + the 15-share leg"
    assert cp["total_cap_refused_arms"] == "382keel", "60 + 25 > 80: the order rail would refuse it"
    assert by["NOISE_382-20260928T141500Z-S"]["total_cap_refused_arms"] == ""


def _broker(rows, sid, intent, **kw):
    """Change trade `sid`'s OPEN ("O") or CLOSE ("C") broker_orders.csv row in place."""
    want = "qx" + nfl._alnum(sid) + intent
    row = next(r for r in rows if r["signal_id"] == want)
    row.update(kw)
    return rows


T1, T2, T3, T4 = list(M_0928)


def test_joiner_classifies_what_webull_did_and_scores_only_real_fills(tmp_path):
    def edit(rows):
        # T2: the OPEN blocked by a reconcile halt, so its CLOSE had nothing to close
        _broker(rows, T2, "O", mode="BLOCKED", ok="False", sent="False", broker_fill_px="",
                slippage="", outcome="BLOCKED",
                reason="halted: reconcile mismatch: believed -10 QQQ, broker 0")
        _broker(rows, T2, "C", mode="BLOCKED", ok="False", sent="False", broker_fill_px="",
                slippage="", outcome="BLOCKED",
                reason="nothing to close at the broker for leg 'NOISE': no position this adapter sent")
        # T3: Webull refused the OPEN outright (a 4xx)
        _broker(rows, T3, "O", ok="False", sent="True", broker_fill_px="", slippage="",
                outcome="REFUSED",
                reason="ServerException: HTTP Status: 417 -- short sale not allowed")
        # T4: the CLOSE was accepted but never filled
        _broker(rows, T4, "C", broker_fill_px="", slippage="",
                reason="gave up waiting for a fill price")
        return rows
    oid = "qx" + nfl._alnum(T1) + "O"
    state = {"legs": {}, "events": [{"ts_et": "2026-09-28 10:16:30", "kind": "broker",
                                     "text": f"QQQ BROKER OPEN NOISE: Webull reports PARTIALLY_FILLED "
                                             f"for order {oid} -- 15 of 20 share(s) filled; the "
                                             f"adapter's books now count only the filled shares"}]}
    by = {r["signal_id"]: r for r in nfl.build_table(_home_0928(tmp_path, state=state,
                                                                 broker_edit=edit))}
    one, two, three, four = by[T1], by[T2], by[T3], by[T4]
    assert one["primary_status"] == "filled"
    assert (one["entry_broker_shares"], one["entry_filled_shares"], one["exit_filled_shares"]) == (20, 15, 20)
    assert one["pnl_per_share"] == pytest.approx(0.30)
    # a BLOCKED halt: never sent -- no Webull dollars, the book's in their own columns
    assert two["primary_status"] == "broker_blocked"
    assert two["primary_status_detail"].startswith("halt: halted: reconcile mismatch")
    assert two["entry_broker_outcome"].startswith("BLOCKED: halted") and two["entry_broker_sent_ts_et"] == ""
    assert two["entry_fill_px"] == "" and two["pnl_per_share"] == ""
    for a in nf.ARMS:
        assert two[f"pnl_usd_{a}"] == "" == two[f"pnl_usd_{a}_capped"], a
    assert two["pnl_per_share_book"] == pytest.approx(-1.2)
    assert two["pnl_usd_382plain_book"] == pytest.approx(-12.0)
    assert two["pnl_usd_422plain_book"] == pytest.approx(-12.0)
    # a Webull 4xx
    assert three["primary_status"] == "broker_refused"
    assert three["primary_status_detail"].startswith("http_4xx: ServerException: HTTP Status: 417")
    assert three["entry_broker_sent_ts_et"] == "2026-09-28 12:05:08" and three["pnl_usd_382keel"] == ""
    # an entry that filled and a CLOSE that never did
    assert four["primary_status"] == "exit_fill_pending"
    assert four["primary_status_detail"] == "exit sent and accepted, no Webull fill price captured yet"
    assert four["entry_fill_px"] == 735.57 and four["exit_fill_px"] == ""
    assert four["pnl_per_share"] == "" and four["pnl_usd_382plain"] == ""
    assert four["pnl_per_share_book"] == pytest.approx(-1.435)


def test_broker_side_verdicts_and_reason_kinds():
    ok = dict(mode="PAPER", ok="True", sent="True", outcome="OK", shares="10")
    assert nfl.broker_side([])["verdict"] == "none"
    assert nfl.broker_side([dict(ok, broker_fill_px="")])["verdict"] == "fill_pending"
    assert nfl.broker_side([dict(ok, mode="OFF", sent="False", broker_fill_px="")])["verdict"] == "off"
    unknown = dict(ok, ok="False", outcome="UNKNOWN", reason="ReadTimeout: timed out")
    assert nfl.broker_side([unknown])["verdict"] == "unknown"
    blocked = dict(ok, mode="BLOCKED", ok="False", sent="False", outcome="BLOCKED",
                   reason="halted: reconcile mismatch")
    # a blocked OPEN re-sent once the halt cleared, and filled: filled at the re-send's price
    got = nfl.broker_side([blocked, dict(ok, broker_fill_px="701.5", ts_et="2026-09-28 10:16:00")])
    assert (got["verdict"], got["fill_px"], got["sent_ts"]) == ("filled", 701.5, "2026-09-28 10:16:00")
    # a CLOSE remainder re-sent after a partial: one share-weighted price, the counts added
    got = nfl.broker_side([dict(ok, broker_fill_px="700.0", signal_id="qxAC"),
                           dict(ok, broker_fill_px="702.0", signal_id="qxACR1", shares="4")],
                          [{"text": "Webull reports CANCELLED for order qxAC -- 6 of 10 share(s) filled"}])
    assert (got["filled"], got["shares"], got["fill_px"]) == (10, 14, pytest.approx(700.8))
    # a row from before the outcome column existed
    assert nfl.broker_side([{"mode": "BLOCKED", "ok": "False", "sent": "False"}])["verdict"] == "blocked"
    kinds = {"halted: kill file present at /x": "halt",
             "projected total position 90 exceeds max_total_position_shares 80": "total_cap",
             "qty 70 exceeds max_shares_per_leg 60": "per_leg_cap",
             "daily loss limit hit (-210.00 <= -200.0)": "daily_loss",
             "outside session window 09:30-16:00 NY": "session_window",
             "leg 'NOISE' already has an open position (one_open_position_per_leg)": "one_open_position",
             "lease unverifiable: firestore read timed out": "lease",
             "host 'oracle' holds a fresh lease (12 s old)": "lease",
             "no PAPER client (mode PAPER)": "no_client",
             "ServerException: HTTP Status: 417 bad": "http_4xx",
             "ServerException: HTTP 503": "http_503", "something else": "other",
             "ServerException: HTTP Status: 417 Please check the order quantity": "http_4xx",
             "Please retry later": "other"}
    for text, kind in kinds.items():
        assert nfl.reason_kind(text) == kind, text


def test_joiner_blanks_an_arm_whose_leg_is_missing_or_exits_elsewhere(tmp_path):
    def edit(rows):
        out = []
        for r in rows:
            entry = nf._trade_id.parse(r["trade_id"])["entry_utc"]
            stamp = entry.strftime("%H%M")
            if r["leg"] == nf.FIXED_LEG and stamp == "1545":
                continue                         # T2: the fixed leg never traded it
            if r["leg"] == nf.KEEL_LEG and stamp == "1605" and r["event"] == "EXIT":
                continue                         # T3: the KEEL leg is still open
            if r["leg"] == nf.KEEL_LEG and stamp == "1415" and r["event"] == "EXIT":
                r = dict(r, ref_time="2026-09-28T11:45:00-04:00", ref_price="734.45")
            if r["leg"] == nf.PLAIN_LEG and stamp == "1615" and r["event"] == "EXIT":
                r = dict(r, ref_price="736.90")   # T4: the same bar, another price
            out.append(r)
        return out
    by = {r["signal_id"]: r for r in nfl.build_table(_home_0928(tmp_path, shadow_edit=edit))}
    one, two, three, four = by[T1], by[T2], by[T3], by[T4]
    assert one["exit_divergence"] == ("NOISE_422_KEEL exit bar 2026-09-28T11:45:00-04:00 vs "
                                      "2026-09-28T11:40:00-04:00, price 734.45 vs 735.695")
    assert one["arms_not_scored"] == "422keel: exit divergence"
    assert one["pnl_usd_422keel"] == "" == one["pnl_usd_422keel_capped"] == one["pnl_usd_422keel_book"]
    assert one["pnl_usd_422plain"] == pytest.approx(0.30 * 10 * 1.75)
    assert two["exit_divergence"] == "" and two["arms_not_scored"] == "422fixed: no NOISE_422_FIXED row"
    assert two["pnl_usd_422fixed"] == "" and two["pnl_usd_422plain"] != ""
    assert three["exit_divergence"].startswith("NOISE_422_KEEL has no exit (primary exited")
    assert three["pnl_usd_422keel"] == "" and three["pnl_usd_382keel"] != ""
    assert four["exit_divergence"] == "NOISE_422_PLAIN exit price 736.90 vs 736.88"
    assert four["arms_not_scored"] == "422plain: exit divergence"


def test_the_nightly_pull_copies_the_forward_log_where_the_joiner_reads_it(tmp_path):
    import tools.pull_box_ledgers as pbl
    rel = "cloud_signal/shadow/" + nf.FORWARD_LOG_FILENAME
    assert rel in pbl.FILES
    home = str(tmp_path)
    assert nfl.input_paths(home)["forward_log"] == os.path.join(home, *rel.split("/"))
    assert (nf.forward_log_path(cs.shadow_paths(cs._paths(home=home)))
            == nfl.input_paths(home)["forward_log"])


# ── the real 09-28 box files in the session scratchpad (skips when wiped) ────────────────
PARITY_0928 = os.environ.get("EDGELOG_PARITY_0928_DIR") or os.path.join(
    os.environ.get("TEMP", ""), "claude", "C--Users-xride-OneDrive-Desktop",
    "ca3282b4-bb88-4797-ab00-ad2cf71b02b3", "scratchpad", "parity0928")
_HAS_PARITY = all(os.path.exists(os.path.join(PARITY_0928, f)) for f in
                  ("QQQ_5m.csv", "signals.csv", "orders.csv", "broker_orders.csv", "trades.csv",
                   "state.json"))


@pytest.mark.skipif(not _HAS_PARITY, reason="no scratchpad copy of the 2026-09-28 box files")
def test_backfill_on_the_real_0928_bars_matches_the_live_sizes_and_the_422_plugin(tmp_path):
    P = PARITY_0928
    paths = nfl.input_paths(str(tmp_path / "nohome"), signals=os.path.join(P, "signals.csv"),
                            ohlc_dir=P, keel_dir=P, orders=os.path.join(P, "orders.csv"),
                            trades=os.path.join(P, "trades.csv"),
                            broker_orders=os.path.join(P, "broker_orders.csv"),
                            exec_state=os.path.join(P, "state.json"))
    out = nfl.build_table(paths, since="2026-09-28", backfill=True)
    assert [r["signal_id"] for r in out] == list(M_0928)
    # the #422 plugin's own sizes on the same bars (the shadow legs did not exist that day)
    df = cs.historical_bars("5m", {"ohlc_dir": P})
    end = pd.Timestamp("2026-09-28 12:25", tz=cs.TZ).to_pydatetime()
    arr = cs.closed_arrays(df, end, "5m", cs.leg_warmup_sessions(CFG_422))
    sizes_422 = {t["entry_time"]: t["size"] for t in cs.run_leg_trades(CFG_422, arr, leg_key="X")}
    for r in out:
        m382, m422 = M_0928[r["signal_id"]]
        assert r["row_source"] == "backfill" and r["primary_status"] == "filled"
        assert float(r["m_382plain"]) == m382 == float(r["leg_m_382plain"])
        assert float(r["m_422plain"]) == m422 == sizes_422[r["entry_bar_time"]]
        assert "m_382plain" not in r["mult_check"], "the live #382 size is the flag's"
        assert (str(r["friday"]), str(r["fomc_pre14"]), str(r["decide_at_close"])) == ("0", "0", "1")
        assert str(r["keel382_data_through"]) == "2026-09-25" and str(r["keel382_trades"]) == "4861"
        e_fill, x_fill, pps = FILLS_0928[r["signal_id"]]
        assert r["entry_fill_px"] == e_fill and r["pnl_per_share"] == pytest.approx(pps)
