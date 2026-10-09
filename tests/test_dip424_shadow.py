"""tests/test_dip424_shadow.py -- DIP #424 ("KEEL DIP": run #424 = augur_strategies/NQDIP_1_1.py
at its validate champion) as two NO-ORDER shadow legs on the Webull paper box, MANAGER #108 GO
(2026-10-09): DIP_424K (+ KEEL v12 learned) and DIP_424F (constant size 1.245). The engine side:
api/dip_live.py (the live adapter) and api/cloud_signal.py (config, dispatch, per-slot ids,
the const KEEL mode). Everything runs on synthetic QQQ-shaped fixtures written into a temp home
(QQQ_1d.csv history + QQQ_5m.csv sessions, real session days); the real NQ master check skips
cleanly when the file is absent.

COVERS
  1. Config: the champion literal; ETF live params, no asset in KEEL's NQ training params;
     train cost 0.0 from 2010-06-07; const 1.245; shadow, no eod_flat/decide_at_close; the
     two legs appended after ENGUQ_335; the state file names the NOISE legs use.
  2. Trade ids: slot=None ids byte-identical for every CROWN/SHADOW leg; slot ids valid,
     parsed, distinct; a bad slot gives None.
  3. Keys: _entry_key/_rekey unchanged for slot-less trades; 7 trades on one bar -> 7 keys;
     a re-key never merges slots.
  4. Mechanism split: the union of single-mechanism runs is the all-on run (synthetic; plus the
     real NQ master, n = 3431, when EDGELOG_NQ_MASTER / augur_uploads has it).
  5. The file's own 5m-RTH aggregation equals the daily series run trade for trade.
  6. The probe: parity with the full-history truth at many cuts per mechanism, P = 32,
     closed trades identical with and without pads, CAP/IBS time-only exits forced inside the
     pads (two pads lose them), today's high/low/close never matter.
  7. build_daily_series: 5m overrides QQQ_1d, QQQ_1d fills older dates and holes, today
     needs its 09:30 bar, unfinished daily rows dropped, midnight stamps read as dates, a
     2:1-scaled daily file / a missing previous session / < 430 sessions -> None, a date's
     source never flips back.
  8. Trade dicts: entry/exit at the 09:30 bar at t[4]/t[5]; entry_bar is the 5m 09:30 bar;
     shares/slot/still_open; closed trades = NQDIP_1_1.py's own run, prices in points.
  9. Intraday invariance: the same trades from 09:35 to 16:00; an entry absent at 09:34:59,
     present at 09:35:05.
 10. step(): cold start SEED + seeded carries with slot ids; a 7-slot day = 7 ENTRY rows,
     7 ids; EXITs pair by id; reason text; a late sighting still emits, after the close it is
     skipped, a missed day is stale-skipped; not ready -> no SEED, the first SEED once
     QQQ_1d.csv appears; no row ever reaches the live ledger.
 11. KEEL (DIP_424K): scored on the 5m arrays at the 09:30 bar; one size for every slot; the
     EXIT reuses it; no state -> 1.0, no push.
 12. Const (DIP_424F): exactly 1.245 on ENTRY, EXIT and a seeded carry; invalid -> 1.0 + reason.
 13. Memo: the second leg does not recompute.
 14. The research files are byte-identical (LF sha256 pins).
"""
import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter

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
from api import dip_live as DL                      # noqa: E402
from api import market_calendar as mc               # noqa: E402
from api import trade_id as T                       # noqa: E402
from augur_engine.engine import run_backtest        # noqa: E402

QUIET = lambda *a, **k: None   # noqa: E731
LEGS = ("DIP_424K", "DIP_424F")
CHAMPION = {"cap_hold": 5, "cap_mult": 0.75, "cap_q": 0.35, "cost_bps": 2.0, "cost_pts_rt": 0.783,
            "dbl_n": 5, "gap_atr": 0.0, "gap_hold": 1, "ibs_exit": 1.0, "ibs_hold": 10,
            "ibs_thr": 0.25, "notional": 100000, "pb_ema": 10, "pb_hold": 30, "rsi_exit": 6,
            "rsi_len": 3, "rsi_thr": 45, "streak_hold": 4, "streak_n": 0, "trend_len": 400,
            "use_cap": True, "use_dbl": True, "use_gapdn": True, "use_ibs": True, "use_pb": True,
            "use_rsi": True, "use_streak": True}
MECHS = ["RSI", "DBL", "PB", "CAP", "IBS", "STREAK", "GAPDN"]
LIVE_PARAMS = cs.SHADOW_LEGS["DIP_424F"]["params"]


# ── synthetic fixtures ─────────────────────────────────────────────────────────────────────
def session_days(n, end):
    out, d = [], end
    while len(out) < n:
        if mc.is_session(d):
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


def walk_targets(days, seed=7, price=450.0):
    """[(date, o, h, l, c)] -- a drifting random walk with gaps: every mechanism trades."""
    rng = np.random.RandomState(seed)
    out, c_prev = [], price
    for d in days:
        o = c_prev * (1 + rng.normal(0, 0.004))
        c = o * (1 + rng.normal(0.0008, 0.011))
        h = max(o, c) * (1 + abs(rng.normal(0, 0.004)))
        lo = min(o, c) * (1 - abs(rng.normal(0, 0.004)))
        out.append((d, o, h, lo, c))
        c_prev = c
    return out


def crash_targets(days, crash_at, price=300.0):
    """A smooth uptrend (only STREAK trades, every other session) and ONE crash day: a gap
    down, a 5% range closing near its low -- all seven mechanisms signal at its close."""
    out, c_prev = [], price
    for i, d in enumerate(days):
        if i == crash_at:
            o = c_prev * 0.999
            h, lo = o * 1.001, o * 0.95
            c = lo * 1.004
        else:
            o = c_prev * 1.001
            c = o * 1.002
            h, lo = c * 1.0005, o * 0.9995
        out.append((d, o, h, lo, c))
        c_prev = c
    return out


def _epoch(d, hh=9, mm=30):
    return int(pd.Timestamp(f"{d.isoformat()} {hh:02d}:{mm:02d}", tz=cs.TZ).tz_convert("UTC").timestamp())


def session_bars(d, o, h, lo, c):
    """5m RTH bars for one session whose aggregate is exactly (o, h, lo, c): a piecewise-
    linear path o -> lo -> h -> c (or o -> h -> lo -> c on a down day) cut into bars."""
    nb = (DL._close_minutes(d) - 570) // 5
    knots = [o, lo, h, c] if c >= o else [o, h, lo, c]
    xs = [0, nb // 3, (2 * nb) // 3, nb]
    p = np.interp(np.arange(nb + 1), xs, knots)
    for x, k in zip(xs, knots):
        p[x] = k
    start = _epoch(d)
    opens, closes = p[:-1], p[1:]
    return pd.DataFrame({"time": start + 300 * np.arange(nb), "open": opens,
                         "high": np.maximum(opens, closes), "low": np.minimum(opens, closes),
                         "close": closes, "volume": 1000.0})


def write_home(root, targets, n5, drop_5m=(), no_1d=False, scale_1d=1.0, perturb_1d=0.0,
               keep_1d=None):
    """A temp EDGELOG home: QQQ_5m.csv = the last `n5` sessions of `targets` as 5m bars (minus
    `drop_5m` dates), QQQ_1d.csv = every target row stamped 00:00 ET (yfinance's convention),
    closes x (1 + perturb_1d) on the 5m dates, every price x scale_1d."""
    paths = cs._paths(home=str(root))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    five = [session_bars(*t) for t in targets[-n5:] if t[0] not in set(drop_5m)]
    pd.concat(five, ignore_index=True).to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"),
                                              index=False)
    if not no_1d:
        write_1d(paths, targets, n5, scale_1d, perturb_1d, keep_1d)
    return paths


def write_1d(paths, targets, n5=0, scale_1d=1.0, perturb_1d=0.0, keep_1d=None):
    five_dates = {t[0] for t in targets[-n5:]} if n5 else set()
    rows = []
    for d, o, h, lo, c in targets:
        if keep_1d is not None and d not in keep_1d:
            continue
        k = 1.0 + (perturb_1d if d in five_dates else 0.0)
        rows.append((_epoch(d, 0, 0), o * scale_1d, h * scale_1d, lo * scale_1d,
                     c * k * scale_1d, 1e6))
    pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).to_csv(
        os.path.join(paths["ohlc_dir"], "QQQ_1d.csv"), index=False)


def at(d, hh, mm, ss=0):
    return pd.Timestamp(f"{d.isoformat()} {hh:02d}:{mm:02d}:{ss:02d}", tz=cs.TZ).to_pydatetime()


def five_arrays(paths, now):
    cfg = cs.SHADOW_LEGS["DIP_424F"]
    return cs.closed_arrays(cs.historical_bars("5m", paths), now, "5m", cs.leg_warmup_sessions(cfg))


def series_from(targets, last, junk_last=False):
    """build_daily_series' shape straight from `targets[:last + 1]` (no files): for the probe
    tests. junk_last: row `last`'s high/low/close replaced by nonsense (only its open counts)."""
    rows = targets[:last + 1]
    a = np.array([r[1:] for r in rows], float)
    if junk_last:
        o = a[-1, 0]
        a[-1, 1:] = (o * 1.3, o * 0.6, o * 0.7)
    dates = [r[0] for r in rows]
    arr = {"open": a[:, 0].copy(), "high": a[:, 1].copy(), "low": a[:, 2].copy(),
           "close": a[:, 3].copy(), "volume": np.ones(len(rows)),
           "day_id": np.arange(len(rows)), "index": DL._session_open_index(dates)}
    return {"arrays": arr, "dates": dates, "source": ["1d"] * len(rows), "first_bar": {},
            "L": last, "today": True}


def full_arrays(targets):
    return series_from(targets, len(targets) - 1)["arrays"]


def single(params, flag):
    p = dict(params, asset="ETF")
    for _m, f in cs.DIP_MECHS:
        p[f] = (f == flag)
    return p


WALK_DAYS = session_days(700, dt.date(2026, 10, 8))
WALK = walk_targets(WALK_DAYS)
CRASH_DAYS = session_days(470, dt.date(2026, 10, 8))
CRASH_AT = 466                       # 2026-10-05: STREAK is flat at its close -> 7 entries
CRASH = crash_targets(CRASH_DAYS, CRASH_AT)
D_CRASH, D_ENTRY, D_X1, D_X2 = (CRASH_DAYS[CRASH_AT + i] for i in range(4))


@pytest.fixture(autouse=True)
def _fresh_memo():
    DL._PROBE_MEMO.clear()
    yield
    DL._PROBE_MEMO.clear()


def _dip_legs(home):
    """The SHIPPED DIP legs, DIP_424K's KEEL pointed at `home` (no state there unless a test
    writes one)."""
    legs = {k: dict(cs.SHADOW_LEGS[k]) for k in LEGS}
    legs["DIP_424K"]["keel"] = dict(cs.SHADOW_LEGS["DIP_424K"]["keel"],
                                    **cs.keel_paths("DIP_424K", "v12", home=home))
    return legs


# ── 1. config ──────────────────────────────────────────────────────────────────────────────
def test_config_is_the_champion_and_the_two_legs_are_appended():
    assert cs.DIP_424_PARAMS == CHAMPION and "asset" not in cs.DIP_424_PARAMS
    assert cs.DIP_424_CONST_SIZE == 1.245
    assert [m for m, _f in cs.DIP_MECHS] == MECHS
    assert list(cs.SHADOW_LEGS)[-3:] == ["ENGUQ_335", "DIP_424K", "DIP_424F"]
    assert not set(LEGS) & set(cs.CROWN_LEGS)
    for key in LEGS:
        leg = cs.SHADOW_LEGS[key]
        assert leg["strategy"] == "NQDIP_1_1.py" and leg["timeframe"] == "5m"
        assert leg["runner"] == cs.DIP_RUNNER == "dip_daily"
        assert leg["params"] == dict(CHAMPION, asset="ETF")
        assert leg["warmup_sessions"] == cs.DIP_5M_ALL_SESSIONS
        assert cs.leg_warmup_sessions(leg) == cs.DIP_5M_ALL_SESSIONS
        assert leg["max_entry_age_sec"] == 390 * 60
        assert leg["shadow"] is True
        for flag in ("eod_flat", "decide_at_close", "resting_levels"):
            assert flag not in leg, (key, flag)
    k = cs.SHADOW_LEGS["DIP_424K"]["keel"]
    assert cs.keel_mode(k) == cs.KEEL_MODE_LEARNED and k["version"] == "v12"
    assert os.path.basename(k["state_path"]) == "DIP_424K_v12_state.joblib"
    assert os.path.basename(k["summary_path"]) == "DIP_424K_v12_summary.json"
    assert k["train"] == {"params": CHAMPION, "cost_pts": 0.0, "date_from": "2010-06-07"}
    assert "asset" not in k["train"]["params"]
    assert cs.SHADOW_LEGS["DIP_424F"]["keel"] == {"mode": "const", "size": 1.245}
    assert cs.keel_mode(cs.SHADOW_LEGS["DIP_424F"]["keel"]) == cs.KEEL_MODE_CONST


def test_the_mechanism_order_is_the_file_s_own():
    with open(os.path.join(ROOT, "augur_strategies", "NQDIP_1_1.py"), encoding="utf-8") as f:
        src = f.read()
    assert ('legs = [("RSI", use_rsi), ("DBL", use_dbl), ("PB", use_pb), ("CAP", use_cap),'
            in src.replace("\r\n", "\n"))
    assert [f for _m, f in cs.DIP_MECHS] == [f"use_{m.lower()}" for m in MECHS]


# ── 2. trade ids ───────────────────────────────────────────────────────────────────────────
def test_slotless_ids_are_byte_identical_for_every_leg():
    for leg in list(cs.CROWN_LEGS) + list(cs.SHADOW_LEGS):
        for side, code in (("long", "L"), ("short", "S")):
            want = f"{leg}-20260903T150000Z-{code}"
            assert T.make(leg, "2026-09-03T11:00:00-04:00", side) == want
            assert T.make(leg, "2026-09-03T11:00:00-04:00", side, slot=None) == want
            assert T.parse(want)["slot"] is None and T.is_valid(want)
    assert T.describe("NOISE_304-20260903T150000Z-L", cs._zi(cs.TZ)) == \
        "NOISE_304 long entered 2026-09-03 11:00 ET"


def test_slot_ids_are_valid_parsed_and_distinct():
    ids = [T.make("DIP_424K", "2026-10-06T09:30:00-04:00", "long", slot=m) for m in MECHS]
    assert ids[0] == "DIP_424K-20261006T133000Z-L-RSI"
    assert len(set(ids)) == 7 and all(T.is_valid(i) for i in ids)
    for m, i in zip(MECHS, ids):
        p = T.parse(i)
        assert (p["leg"], p["side"], p["slot"]) == ("DIP_424K", "long", m)
        assert p["entry_utc"] == dt.datetime(2026, 10, 6, 13, 30, tzinfo=dt.timezone.utc)
    assert T.describe(ids[5], cs._zi(cs.TZ)) == "DIP_424K long entered 2026-10-06 09:30 ET [STREAK]"
    for bad in ("rsi", "", "R-1", "TOOLONGSLOTNAME", "R SI", "RSİ", "RSI\n", "Rsi"):
        assert T.make("DIP_424K", "2026-10-06T09:30:00-04:00", "long", slot=bad) is None, bad
    assert T.parse("DIP_424K-20261006T133000Z-L-rsi") is None
    assert T.parse("DIP_424K-20261006T133000Z-L-") is None


# ── 3. keys ────────────────────────────────────────────────────────────────────────────────
def test_entry_keys_of_slotless_trades_are_unchanged_and_slots_never_merge():
    t = {"entry_time": "2026-10-06T09:30:00-04:00", "side": "long", "entry_px": 700.0}
    for leg in list(cs.CROWN_LEGS) + list(cs.SHADOW_LEGS):
        assert cs._entry_key(leg, t) == T.make(leg, t["entry_time"], "long")
    seven = [dict(t, slot=m) for m in MECHS]
    keys = [cs._entry_key("DIP_424F", x) for x in seven]
    assert len(set(keys)) == 7 and all(k.endswith("-" + m) for k, m in zip(keys, MECHS))
    # a pre-trade-id memory re-keyed: slot records keep 7 keys, a slot-less leg is as before
    legacy = {f"old{i}": {"entry_time": t["entry_time"], "side": "long", "slot": m,
                          "exit_emitted": False} for i, m in enumerate(MECHS)}
    st = {"trades": dict(legacy)}
    assert cs._rekey_recorded_trades("DIP_424F", st) == 0
    assert sorted(st["trades"]) == sorted(keys)
    plain = {"trades": {"a": {"entry_time": t["entry_time"], "side": "long"},
                        "b": {"entry_time": t["entry_time"], "side": "long"}}}
    assert cs._rekey_recorded_trades("NOISE_382", plain) == 1
    assert list(plain["trades"]) == [T.make("NOISE_382", t["entry_time"], "long")]


# ── 4. the mechanism split ─────────────────────────────────────────────────────────────────
def _trades(arr, params):
    res = run_backtest("NQDIP_1_1.py", arrays=arr, params=params, cost_pts=0.0, return_trades=True)
    return list((res or {}).get("trades") or [])


def test_union_of_single_mechanism_runs_is_the_all_on_run():
    arr = full_arrays(WALK)
    allon = _trades(arr, dict(LIVE_PARAMS))
    parts = []
    counts = {}
    for m, f in cs.DIP_MECHS:
        tr = _trades(arr, single(LIVE_PARAMS, f))
        counts[m] = len(tr)
        parts += tr
    assert Counter(map(tuple, allon)) == Counter(map(tuple, parts))
    assert all(counts[m] > 0 for m in MECHS), counts
    assert all(len(t) == 6 for t in allon)


def _nq_master():
    for p in (os.environ.get("EDGELOG_NQ_MASTER"),
              os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")):
        if p and os.path.exists(p):
            return p
    return None


@pytest.mark.skipif(_nq_master() is None, reason="no NQ 5m RTH no-adjust master on this machine "
                    "(set EDGELOG_NQ_MASTER)")
def test_real_nq_run_424_and_its_mechanism_split(monkeypatch):
    import augur_engine.data as _data
    path = _nq_master()
    monkeypatch.setattr(_data, "UPLOADS", os.path.dirname(os.path.abspath(path)))
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "0")
    arr = _data.load_master_arrays({"filename": os.path.basename(path)},
                                   date_from="2010-06-07", date_to="2026-08-24")
    allon = _trades(arr, dict(cs.DIP_424_PARAMS))
    assert len(allon) == 3431, "run #424's gate_validate.keel n_trades"
    parts = []
    for _m, f in cs.DIP_MECHS:
        p = dict(cs.DIP_424_PARAMS)
        for _m2, f2 in cs.DIP_MECHS:
            p[f2] = (f2 == f)
        parts += _trades(arr, p)
    assert Counter(map(tuple, allon)) == Counter(map(tuple, parts))


# ── 5. one bar per session ─────────────────────────────────────────────────────────────────
def test_the_files_own_5m_aggregation_equals_the_daily_series_run():
    rows = WALK[-450:]
    bars = pd.concat([session_bars(*t) for t in rows], ignore_index=True)
    a5 = cs.build_arrays(bars)
    run5 = _trades(a5, dict(LIVE_PARAMS))                    # asset ETF: the file aggregates
    rund = _trades(full_arrays(rows), dict(LIVE_PARAMS))
    idx5 = a5["index"]
    days = [r[0] for r in rows]
    assert run5 and len(run5) == len(rund)
    for t5, td in zip(sorted(run5, key=lambda t: (t[1], t[0], t[4])),
                      sorted(rund, key=lambda t: (t[1], t[0], t[4]))):
        assert idx5[t5[0]].date() == days[td[0]] and idx5[t5[1]].date() == days[td[1]]
        assert idx5[t5[0]].strftime("%H:%M") == "09:30"
        assert t5[4] == td[4] and t5[5] == td[5]
        assert t5[2] == pytest.approx(td[2], rel=1e-9)


# ── 6. the probe ───────────────────────────────────────────────────────────────────────────
def test_probe_pads_cover_the_longest_time_only_hold():
    assert DL.probe_pads(LIVE_PARAMS) == 32 == LIVE_PARAMS["pb_hold"] + 2
    a = series_from(WALK, 500)["arrays"]
    p = DL.probe_arrays(a, 5)
    assert len(p["close"]) == 506 and np.all(p["close"][-5:] == a["close"][-1] * 1000.0)
    assert np.all(p["open"][-5:] == p["high"][-5:]) and np.all(p["volume"][-5:] == 0)
    assert list(p["day_id"]) == list(range(506))
    assert (p["index"][-1] - a["index"][-1]) == pd.Timedelta(days=5)


def test_probe_matches_the_full_history_truth_at_every_cut():
    """The truth: each mechanism alone over ALL 700 sessions (no pads). At a cut L every trade
    entered by L and closed by L is a closed trade of the probe, every trade entered by L that
    closes after it is an open position -- labels, bars and prices exact. 60+ sessions of tail
    after the last cut, so the truth sees every one of those positions close."""
    arr = full_arrays(WALK)
    truth = {m: _trades(arr, single(LIVE_PARAMS, f)) for m, f in cs.DIP_MECHS}
    n_open = n_closed = 0
    cuts = list(range(432, 640, 6))
    for L in cuts:
        got = DL.dip_positions(series_from(WALK, L, junk_last=True), LIVE_PARAMS)
        want = []
        for m, tr in truth.items():
            for t in tr:
                if t[0] > L:
                    continue
                if t[1] <= L:
                    want.append((m, t[0], t[1], t[4], t[5]))
                else:
                    want.append((m, t[0], None, t[4], None))
        assert sorted(got, key=str) == sorted(want, key=str), L
        n_open += sum(1 for g in got if g[2] is None)
        n_closed += sum(1 for g in got if g[2] is not None)
    assert n_open >= 40 and n_closed >= 200, (n_open, n_closed)
    seen = Counter(g[0] for L in cuts[-5:] for g in DL.dip_positions(series_from(WALK, L), LIVE_PARAMS))
    assert set(seen) == set(MECHS), seen


def test_closed_trades_are_the_plain_runs_own_and_today_s_hlc_never_matters():
    for L in (450, 517, 600):
        plain = []
        for m, f in cs.DIP_MECHS:
            plain += [(m, t[0], t[1], t[4], t[5])
                      for t in _trades(series_from(WALK, L)["arrays"], single(LIVE_PARAMS, f))]
        real = DL.dip_positions(series_from(WALK, L), LIVE_PARAMS)
        DL._PROBE_MEMO.clear()
        junk = DL.dip_positions(series_from(WALK, L, junk_last=True), LIVE_PARAMS)
        assert real == junk, L
        assert sorted(r for r in real if r[2] is not None) == sorted(plain), L


def test_cap_and_ibs_time_only_exits_are_forced_inside_the_pads_and_two_pads_lose_them():
    """CAP exits only by time (cap_hold 5) and IBS too (ibs_exit 1.0 can never be exceeded and
    a flat pad has IBS 0.5): with P = 32 pads a position entered on the last real session is
    still seen; with two pads it vanishes."""
    L = CRASH_AT + 1                  # the entry session: CAP and IBS filled at its open
    s = series_from(CRASH, L)
    for m in ("CAP", "IBS"):
        flag = dict(cs.DIP_MECHS)[m]
        full = DL.probe_arrays(s["arrays"], DL.probe_pads(LIVE_PARAMS))
        tr = [t for t in _trades(full, single(LIVE_PARAMS, flag)) if t[0] == L]
        assert len(tr) == 1 and L < tr[0][1] <= L + DL.probe_pads(LIVE_PARAMS), (m, tr)
        two = DL.probe_arrays(s["arrays"], 2)
        assert not [t for t in _trades(two, single(LIVE_PARAMS, flag)) if t[0] == L], m
    assert ("CAP", L, None) in [(g[0], g[1], g[2]) for g in DL.dip_positions(s, LIVE_PARAMS)]
    assert ("IBS", L, None) in [(g[0], g[1], g[2]) for g in DL.dip_positions(s, LIVE_PARAMS)]


def test_seven_mechanisms_fill_at_one_open_on_the_crash_fixture():
    pos = DL.dip_positions(series_from(CRASH, CRASH_AT + 1), LIVE_PARAMS)
    today = [g for g in pos if g[1] == CRASH_AT + 1]
    assert [g[0] for g in today] == MECHS and all(g[2] is None for g in today)
    assert all(g[3] == CRASH[CRASH_AT + 1][1] for g in today)


# ── 7. the daily series ───────────────────────────────────────────────────────────────────
def test_series_prefers_complete_5m_sessions_and_fills_the_rest_from_qqq_1d(tmp_path):
    hole = WALK_DAYS[-20]
    paths = write_home(tmp_path, WALK, 45, drop_5m=(hole,), perturb_1d=0.0002)
    now = at(WALK_DAYS[-10], 10, 0, 5)
    s, why = DL.build_daily_series(five_arrays(paths, now), now, paths, LIVE_PARAMS, log=QUIET)
    assert why is None and s["dates"][-1] == WALK_DAYS[-10] and s["today"] is True
    src = dict(zip(s["dates"], s["source"]))
    assert src[hole] == "1d" and src[WALK_DAYS[-11]] == "5m" and src[WALK_DAYS[-46]] == "1d"
    assert src[WALK_DAYS[-10]] == "5m_partial"
    by = {d: i for i, d in enumerate(s["dates"])}
    tgt = {t[0]: t for t in WALK}
    c = s["arrays"]["close"]
    assert c[by[WALK_DAYS[-11]]] == tgt[WALK_DAYS[-11]][4]                  # 5m, not the 1d close
    assert c[by[hole]] == pytest.approx(tgt[hole][4] * 1.0002, rel=1e-12)  # the 1d row
    assert c[by[WALK_DAYS[-46]]] == tgt[WALK_DAYS[-46]][4]
    assert s["arrays"]["open"][-1] == tgt[WALK_DAYS[-10]][1]
    assert s["cal"][0] == pytest.approx(0.0002, rel=1e-3) and s["cal"][1] == 0.0
    assert s["L"] == len(s["dates"]) - 1 == WALK_DAYS.index(WALK_DAYS[-10])
    assert [ts.strftime("%H:%M") for ts in s["arrays"]["index"][-3:]] == ["09:30"] * 3
    assert s["arrays"]["index"][-1].isoformat() == f"{WALK_DAYS[-10].isoformat()}T09:30:00-04:00"
    a = five_arrays(paths, now)
    for d, fb in s["first_bar"].items():
        assert a["index"][fb].date() == d and a["index"][fb].strftime("%H:%M") == "09:30"
    assert list(s["arrays"]["day_id"]) == list(range(len(s["dates"])))


def test_today_joins_only_with_its_0930_bar(tmp_path):
    day = WALK_DAYS[-10]
    paths = write_home(tmp_path, WALK, 45)
    s, _ = DL.build_daily_series(five_arrays(paths, at(day, 9, 34, 59)), at(day, 9, 34, 59), paths,
                                 LIVE_PARAMS, log=QUIET)
    assert s["dates"][-1] == WALK_DAYS[-11] and s["today"] is False
    s, _ = DL.build_daily_series(five_arrays(paths, at(day, 9, 35, 5)), at(day, 9, 35, 5), paths,
                                 LIVE_PARAMS, log=QUIET)
    assert s["dates"][-1] == day
    # today's bars but no 09:30 bar -> not ready (the REST tail fills it later)
    df = pd.read_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"))
    df[df["time"] != _epoch(day)].to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    now = at(day, 10, 0, 5)
    s, why = DL.build_daily_series(five_arrays(paths, now), now, paths, LIVE_PARAMS, log=QUIET)
    assert s is None and why[0] == "today_open"


def test_unfinished_daily_rows_are_dropped_and_midnight_stamps_are_dates(tmp_path):
    day = WALK_DAYS[-10]
    paths = write_home(tmp_path, WALK, 45)
    now = at(day, 10, 0, 5)
    rows = DL.daily_rows(paths, now)
    assert max(rows) == WALK_DAYS[-11], "today's and later rows are not finished sessions"
    assert rows[WALK_DAYS[-11]][3] == {t[0]: t for t in WALK}[WALK_DAYS[-11]][4]
    after = DL.daily_rows(paths, at(day, 16, 0, 1))
    assert max(after) == day
    # a duplicate stamp keeps the last row; a NaN / non-positive row is dropped
    df = pd.read_csv(os.path.join(paths["ohlc_dir"], "QQQ_1d.csv"))
    extra = df.iloc[[5, 6]].copy()
    extra.iloc[0, extra.columns.get_loc("close")] = 123.0
    extra.iloc[1, extra.columns.get_loc("open")] = float("nan")
    pd.concat([df, extra]).to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1d.csv"), index=False)
    rows = DL.daily_rows(paths, now)
    assert rows[WALK_DAYS[5]][3] == 123.0
    assert WALK_DAYS[6] in rows and rows[WALK_DAYS[6]][0] == WALK[6][1]


def test_not_ready_guards(tmp_path):
    day = WALK_DAYS[-10]
    now = at(day, 10, 0, 5)
    # a 2:1-scaled daily file (a split the two files disagree on)
    p = write_home(tmp_path / "split", WALK, 45, scale_1d=0.5)
    s, why = DL.build_daily_series(five_arrays(p, now), now, p, LIVE_PARAMS, log=QUIET)
    assert s is None and why[0] == "cal_fail" and "bp" in why[1]
    # just inside / outside the tolerance
    p = write_home(tmp_path / "tol_in", WALK, 45, perturb_1d=cs.DIP_CAL_TOL * 0.9)
    assert DL.build_daily_series(five_arrays(p, now), now, p, LIVE_PARAMS, log=QUIET)[0] is not None
    p = write_home(tmp_path / "tol_out", WALK, 45, perturb_1d=cs.DIP_CAL_TOL * 1.1)
    assert DL.build_daily_series(five_arrays(p, now), now, p, LIVE_PARAMS, log=QUIET)[1][0] == "cal_fail"
    # the previous session in neither file
    prev = WALK_DAYS[-11]
    p = write_home(tmp_path / "prev", WALK, 45, drop_5m=(prev,),
                   keep_1d={t[0] for t in WALK} - {prev})
    s, why = DL.build_daily_series(five_arrays(p, now), now, p, LIVE_PARAMS, log=QUIET)
    assert s is None and why[0] == "prev_missing" and prev.isoformat() in why[1]
    # fewer than trend_len + 30 sessions
    p = write_home(tmp_path / "short", WALK[-429:], 45)
    s, why = DL.build_daily_series(five_arrays(p, now), now, p, LIVE_PARAMS, log=QUIET)
    assert s is None and why[0] == "short" and ">= 430" in why[1]
    # too few overlap sessions to check the scales
    p = write_home(tmp_path / "thin", WALK, 15)
    s, why = DL.build_daily_series(five_arrays(p, at(WALK_DAYS[-1], 10, 0, 5)),
                                   at(WALK_DAYS[-1], 10, 0, 5), p, LIVE_PARAMS, log=QUIET)
    assert s is None and why[0] == "cal_thin"
    # no QQQ_1d.csv at all (this PC): 45 sessions of 5m -> short
    p = write_home(tmp_path / "no1d", WALK, 45, no_1d=True)
    assert DL.build_daily_series(five_arrays(p, now), now, p, LIVE_PARAMS, log=QUIET)[1][0] == "short"


def test_a_dates_source_never_flips_back(tmp_path):
    paths = write_home(tmp_path, WALK, 45)
    seen = {}
    for day in WALK_DAYS[-12:]:
        for hh, mm in ((9, 35), (12, 0), (16, 0)):
            now = at(day, hh, mm, 5)
            s, _ = DL.build_daily_series(five_arrays(paths, now), now, paths, LIVE_PARAMS, log=QUIET)
            for d, src in zip(s["dates"], s["source"]):
                if d == day:
                    continue
                assert seen.setdefault(d, src) == src, (d, seen[d], src)
    assert s["dates"][0] == WALK_DAYS[0], "the series start is fixed"


# ── 8. trade dicts ─────────────────────────────────────────────────────────────────────────
def test_trade_dicts_fill_at_the_0930_bar_and_match_the_file_s_own_run(tmp_path):
    paths = write_home(tmp_path, WALK, 45)
    day = WALK_DAYS[-3]
    now = at(day, 11, 0, 5)
    a = five_arrays(paths, now)
    trades = cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424F"], a, "DIP_424F", now, paths, QUIET)
    assert trades
    L = WALK_DAYS.index(day)
    truth = []
    for m, f in cs.DIP_MECHS:
        truth += [(m,) + tuple(t) for t in _trades(full_arrays(WALK), single(LIVE_PARAMS, f))]
    closed = {(t["slot"], t["entry_time"], t["exit_time"], t["entry_px"], t["exit_px"])
              for t in trades if not t["still_open"]}
    want = {(m, DL._session_open_index([WALK_DAYS[t[0]]])[0].isoformat(),
             DL._session_open_index([WALK_DAYS[t[1]]])[0].isoformat(), round(t[4], 4), round(t[5], 4))
            for (m, *t) in truth if t[1] <= L and t[1] >= L - cs.DIP_DIFF_SESSIONS + 1}
    assert closed == want and len(closed) >= 10
    tgt = {t[0]: t for t in WALK}
    for t in trades:
        d_in = dt.date.fromisoformat(t["entry_time"][:10])
        assert t["entry_time"].endswith("T09:30:00-04:00") and t["side"] == "long"
        assert t["entry_px"] == round(tgt[d_in][1], 4), "the 09:30 open = the backtest fill"
        assert t["shares"] == int(cs.NOTIONAL_PER_LEG // t["entry_px"]) and t["size"] == 1.0
        assert t["slot"] in MECHS and t["entry_note"].startswith(f"slot={t['slot']}; decided at the ")
        if t["entry_bar"] is not None:
            assert a["index"][t["entry_bar"]].isoformat() == t["entry_time"]
        else:
            assert d_in < WALK_DAYS[-45], "only a session older than the 5m cache has no bar"
        if t["still_open"]:
            assert t["exit_time"] is None and t["exit_px"] is None
        else:
            d_out = dt.date.fromisoformat(t["exit_time"][:10])
            assert t["exit_time"].endswith("T09:30:00-04:00")
            assert t["exit_px"] == round(tgt[d_out][1], 4)
            assert t["exit_note"] == (f"slot={t['slot']}; decided at the "
                                      f"{WALK_DAYS[WALK_DAYS.index(d_out) - 1].isoformat()} close, "
                                      f"filled at the {d_out.isoformat()} 09:30 open")
    assert all(t["entry_time"] >= trades[0]["entry_time"] for t in trades)


# ── 9. intraday invariance ─────────────────────────────────────────────────────────────────
def _no_note(trades):
    return [{k: v for k, v in t.items() if k != "entry_note"} for t in trades]


def test_the_trade_list_is_the_same_all_session_and_today_s_entries_appear_at_0935(tmp_path):
    paths = write_home(tmp_path, CRASH, 30)
    cfg = cs.SHADOW_LEGS["DIP_424F"]
    base = None
    for hh, mm, ss in ((9, 35, 5), (10, 30, 5), (12, 55, 5), (15, 55, 5), (16, 0, 5)):
        DL._PROBE_MEMO.clear()           # recomputed every time: invariance, not the memo
        now = at(D_ENTRY, hh, mm, ss)
        tr = cs.run_dip_leg_trades(cfg, five_arrays(paths, now), "DIP_424F", now, paths, QUIET)
        if base is None:
            base = _no_note(tr)
        assert _no_note(tr) == base, (hh, mm)
    assert sorted(t["slot"] for t in base if t["entry_time"].startswith(D_ENTRY.isoformat())) == sorted(MECHS)
    now = at(D_ENTRY, 9, 34, 59)
    early = cs.run_dip_leg_trades(cfg, five_arrays(paths, now), "DIP_424F", now, paths, QUIET)
    assert early is not None
    assert not [t for t in early if t["entry_time"].startswith(D_ENTRY.isoformat())]


# ── 10. step() ─────────────────────────────────────────────────────────────────────────────
def _rows(path):
    import csv
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _crash_run(tmp_path, legs=None, keel_state=False):
    """SEED at the crash day's 17:00, then 09:35:05 / 12:00:05 on each later session."""
    paths = write_home(tmp_path, CRASH, 30)
    legs = legs or _dip_legs(paths["home"])
    if keel_state:
        legs["DIP_424K"]["keel"] = _write_keel_state(paths["home"])
    seed = cs.step(now=at(D_CRASH, 17, 0), legs=legs, paths=paths, fetch=False)
    by_day = {}
    for d in (D_ENTRY, D_X1, D_X2):
        ev = []
        for hh, mm in ((9, 35), (12, 0)):
            ev += cs.step(now=at(d, hh, mm, 5), legs=legs, paths=paths, fetch=False)
        by_day[d] = ev
    return paths, legs, seed, by_day


def test_a_seven_slot_day_through_step(tmp_path):
    paths, legs, seed, by_day = _crash_run(tmp_path)
    assert sorted(e["leg"] for e in seed) == sorted(LEGS)
    assert all(e["event"] == "SEED" and "open_at_seed=none" in e["reason"] for e in seed)
    tgt = {t[0]: t for t in CRASH}
    for leg in LEGS:
        ent = [e for e in by_day[D_ENTRY] if e["leg"] == leg]
        assert [e["event"] for e in ent] == ["ENTRY"] * 7
        ids = [e["trade_id"] for e in ent]
        assert ids == [T.make(leg, f"{D_ENTRY.isoformat()}T09:30:00-04:00", "long", slot=m) for m in MECHS]
        for e, m in zip(ent, MECHS):
            assert e["ref_time"] == f"{D_ENTRY.isoformat()}T09:30:00-04:00"
            assert e["ref_price"] == round(tgt[D_ENTRY][1], 4)
            assert e["reason"] == (f"slot={m}; decided at the {D_CRASH.isoformat()} close; filled at "
                                   f"the {D_ENTRY.isoformat()} 09:30 open (the backtest fill, ref_price "
                                   f"= that open); first seen 09:35 ET (a session is first seen at "
                                   f"its 09:30 bar's close, 09:35)")
        # D_X1: STREAK exits at the 09:30 open (decided at the entry day's up close)
        x1 = [e for e in by_day[D_X1] if e["leg"] == leg]
        assert [(e["event"], e["trade_id"]) for e in x1] == [("EXIT", ids[5])]
        assert x1[0]["ref_time"] == f"{D_X1.isoformat()}T09:30:00-04:00"
        assert x1[0]["ref_price"] == round(tgt[D_X1][1], 4)
        assert x1[0]["reason"] == (f"strategy_exit; slot=STREAK; decided at the {D_ENTRY.isoformat()} "
                                   f"close, filled at the {D_X1.isoformat()} 09:30 open")
        # D_X2: GAPDN out (gap_hold 1), STREAK back in -- a new id on the same slot
        x2 = [(e["event"], e["trade_id"]) for e in by_day[D_X2] if e["leg"] == leg]
        assert ("EXIT", ids[6]) in x2
        assert ("ENTRY", T.make(leg, f"{D_X2.isoformat()}T09:30:00-04:00", "long", slot="STREAK")) in x2
        assert len(x2) == 2
    st = json.load(open(cs._paths(home=paths["home"])["state_path"], encoding="utf-8"))
    rec = st["legs"]["DIP_424F"]["trades"][ids[0].replace("DIP_424K", "DIP_424F")]
    assert rec["slot"] == "RSI" and rec["exit_emitted"] is False
    # the ledger: one ENTRY per id, EXITs pair by id, the ids parse with their slots
    rows = _rows(paths["signals_path"])
    for leg in LEGS:
        ents = {r["trade_id"] for r in rows if r["leg"] == leg and r["event"] == "ENTRY"}
        exits = {r["trade_id"] for r in rows if r["leg"] == leg and r["event"] == "EXIT"}
        assert len(ents) == 8 and exits <= ents and len(exits) == 2
        assert {T.parse(i)["slot"] for i in ents} == set(MECHS)


def test_dip_rows_never_reach_the_live_ledger(tmp_path, monkeypatch):
    live = write_home(tmp_path, CRASH, 30)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)
    legs = _dip_legs(live["home"])
    events = []
    for now in (at(D_CRASH, 17, 0), at(D_ENTRY, 9, 35, 5), at(D_X1, 9, 35, 5)):
        events += cs.run_shadow_step(now=now, fetch=False, live_legs=cs.CROWN_LEGS,
                                     shadow_legs=legs, live_paths=live, log=QUIET)
    assert [e for e in events if e["event"] == "ENTRY"]
    assert not os.path.exists(live["signals_path"]), "the live ledger is never written"
    assert not os.path.exists(live["state_path"])
    sp = cs.shadow_paths(live)
    assert {r["leg"] for r in _rows(sp["signals_path"])} == set(LEGS)


def _seed_day_with_open_positions():
    """A walk session (inside the 5m window) holding >= 2 open positions, at least one of
    which closes by the fixture's last session."""
    last = len(WALK_DAYS) - 1
    closed_by_end = {(g[0], g[1]) for g in DL.dip_positions(series_from(WALK, last), LIVE_PARAMS)
                     if g[2] is not None}
    for i in range(len(WALK_DAYS) - 14, len(WALK_DAYS) - 4):
        opens = [g for g in DL.dip_positions(series_from(WALK, i), LIVE_PARAMS) if g[2] is None]
        if len(opens) >= 2 and any((g[0], g[1]) in closed_by_end for g in opens):
            return i
    raise AssertionError("fixture has no seed day with two open positions")


def test_cold_start_carries_open_positions_as_seeded_entries_with_slot_ids(tmp_path):
    i = _seed_day_with_open_positions()
    day = WALK_DAYS[i]
    paths = write_home(tmp_path, WALK, 45)
    legs = _dip_legs(paths["home"])
    seed = cs.step(now=at(day, 12, 0, 5), legs=legs, paths=paths, fetch=False)
    open_now = [g for g in DL.dip_positions(series_from(WALK, i), LIVE_PARAMS) if g[2] is None]
    for leg in LEGS:
        ev = [e for e in seed if e["leg"] == leg]
        assert ev[0]["event"] == "SEED" and "carried as an open would-be trade" in ev[0]["reason"]
        carried = ev[1:]
        assert len(carried) == len(open_now)
        for e, g in zip(carried, open_now):
            when = f"{WALK_DAYS[g[1]].isoformat()}T09:30:00-04:00"
            assert e["event"] == "ENTRY" and e["ref_time"] == when
            assert e["trade_id"] == T.make(leg, when, "long", slot=g[0])
            assert e["reason"].startswith(cs.SEEDED_REASON_TAG) and f"(slot={g[0]})" in e["reason"]
            assert e["ref_price"] == round(g[3], 4)
        n_hist = int(ev[0]["reason"].split("absorbed ")[1].split(" ")[0])
        assert n_hist <= 7 * cs.DIP_DIFF_SESSIONS, "only the last sessions' trades are absorbed"
    k = [e for e in seed if e["leg"] == "DIP_424K" and e["event"] == "ENTRY"]
    f = [e for e in seed if e["leg"] == "DIP_424F" and e["event"] == "ENTRY"]
    assert all(e["size"] == 1.0 and e["keel_size"] == "" for e in k), "KEEL never scores a seed"
    assert all(e["size"] == 1.245 and e["keel_size"] == 1.245 for e in f), "const is a rule"
    # a restart is not a second cold start, and the carried trades' EXITs follow by id
    again = cs.step(now=at(day, 12, 0, 5), legs=legs, paths=paths, fetch=False)
    assert again == []
    later = []
    for d in WALK_DAYS[i + 1:]:
        later += cs.step(now=at(d, 9, 35, 5), legs=legs, paths=paths, fetch=False)
    exits = {e["trade_id"] for e in later if e["event"] == "EXIT"}
    assert {e["trade_id"] for e in carried if T.parse(e["trade_id"])["leg"] == "DIP_424F"} & exits


def test_late_sighting_emits_after_close_and_missed_day_skip(tmp_path):
    # late: first tick at 13:00 of the entry day -> still emitted (no order; the fill is the open)
    paths = write_home(tmp_path / "late", CRASH, 30)
    legs = _dip_legs(paths["home"])
    cs.step(now=at(D_CRASH, 17, 0), legs=legs, paths=paths, fetch=False)
    ev = cs.step(now=at(D_ENTRY, 13, 0, 5), legs=legs, paths=paths, fetch=False)
    assert len([e for e in ev if e["event"] == "ENTRY"]) == 14
    # after the close: first seen at 16:00:30 -> recorded silently, after_close
    paths = write_home(tmp_path / "close", CRASH, 30)
    cs.step(now=at(D_CRASH, 17, 0), legs=legs, paths=paths, fetch=False)
    ev = cs.step(now=at(D_ENTRY, 16, 0, 30), legs=legs, paths=paths, fetch=False, post_close=True)
    assert [e for e in ev if e["event"] == "ENTRY"] == []
    st = json.load(open(paths["state_path"], encoding="utf-8"))
    assert st["legs"]["DIP_424F"]["after_close_skipped"] == 7
    # its EXIT is suppressed with it the next morning
    ev = cs.step(now=at(D_X1, 9, 35, 5), legs=legs, paths=paths, fetch=False)
    assert [e for e in ev if e["event"] == "EXIT"] == []
    # a missed session: no 5m bars for the entry day -> QQQ_1d fills it next morning, stale
    paths = write_home(tmp_path / "missed", CRASH, 30, drop_5m=(D_ENTRY,))
    cs.step(now=at(D_CRASH, 17, 0), legs=legs, paths=paths, fetch=False)
    ev = cs.step(now=at(D_X1, 9, 35, 5), legs=legs, paths=paths, fetch=False)
    assert [e for e in ev if e["event"] == "ENTRY"] == []
    st = json.load(open(paths["state_path"], encoding="utf-8"))
    assert st["legs"]["DIP_424F"]["stale_skipped"] == 7


def test_not_ready_writes_no_seed_until_qqq_1d_appears(tmp_path):
    paths = write_home(tmp_path, CRASH, 30, no_1d=True)
    legs = _dip_legs(paths["home"])
    logs = []
    ev = cs.step(now=at(D_ENTRY, 9, 35, 5), legs=legs, paths=paths, fetch=False)
    assert ev == []
    st = json.load(open(paths["state_path"], encoding="utf-8"))
    assert not any(st["legs"][k].get("seeded") for k in LEGS)
    assert cs.run_dip_leg_trades(legs["DIP_424F"], five_arrays(paths, at(D_ENTRY, 9, 40, 5)),
                                 "DIP_424F", at(D_ENTRY, 9, 40, 5), paths, logs.append) is None
    write_1d(paths, CRASH)
    ev = cs.step(now=at(D_ENTRY, 9, 40, 5), legs=legs, paths=paths, fetch=False)
    assert sorted(e["event"] for e in ev if e["leg"] == "DIP_424F") == ["ENTRY"] * 7 + ["SEED"]
    assert all(cs.SEEDED_REASON_TAG in e["reason"] for e in ev if e["event"] == "ENTRY")


def test_history_window_line(tmp_path, monkeypatch):
    paths = write_home(tmp_path, CRASH, 30)
    legs = _dip_legs(paths["home"])
    now = at(D_X2, 12, 0, 5)
    ln = DL.history_line("DIP_424F", legs["DIP_424F"], paths, now=now)
    assert "-- READY (needs >= 430)" in ln and "NOT READY" not in ln
    assert "470 session(s) (29 from 5m, 440 from QQQ_1d.csv, 1 partial 5m;" in ln
    p2 = write_home(tmp_path / "pc", CRASH, 30, no_1d=True)
    ln = DL.history_line("DIP_424F", legs["DIP_424F"], p2, now=now)
    assert "NOT READY" in ln and ">= 430" in ln
    # log_history_windows routes a DIP leg to that line (never the 5m session count)
    monkeypatch.setattr(DL, "history_line", lambda key, cfg, paths, now=None: f"LINE {key}")
    lines = []
    cs.log_history_windows(legs=legs, paths=paths, log=lines.append)
    assert lines == ["LINE DIP_424K", "LINE DIP_424F"]


# ── 11. KEEL (DIP_424K) ────────────────────────────────────────────────────────────────────
def _write_keel_state(home):
    """A real fitted KEEL v12 state (tests/test_noise_422_shadow.py's builder) under
    DIP_424K's file names, its summary dated the crash day (one session before the entry)."""
    import test_noise_422_shadow as T422
    kp = T422._write_keel_state(home, leg_key="DIP_424K")
    with open(kp["summary_path"], encoding="utf-8") as f:
        summ = json.load(f)
    summ["data_through"] = summ["last_nq_session"] = D_CRASH.isoformat()
    with open(kp["summary_path"], "w", encoding="utf-8") as f:
        json.dump(summ, f)
    return dict(cs.SHADOW_LEGS["DIP_424K"]["keel"], **kp)


def test_keel_scores_the_0930_bar_once_for_every_slot_and_the_exit_reuses_it(tmp_path):
    paths, legs, _seed, by_day = _crash_run(tmp_path, keel_state=True)
    ent = [e for e in by_day[D_ENTRY] if e["leg"] == "DIP_424K"]
    assert len(ent) == 7
    ks = {e["keel_size"] for e in ent}
    assert len(ks) == 1 and isinstance(ent[0]["keel_size"], float) and ent[0]["keel_size"] > 0
    assert all(e["size"] == e["keel_size"] for e in ent)
    assert all(e["keel_branch"] not in ("", "fallback-1.0") for e in ent), "a real score"
    # the score IS the state's own at the entry session's 09:30 bar of the 5m arrays
    now = at(D_ENTRY, 9, 35, 5)
    a = five_arrays(paths, now)
    bar = [i for i, ts in enumerate(a["index"]) if ts.isoformat() == ent[0]["ref_time"]]
    want, diag = cs._keel_size_for_entry(legs["DIP_424K"]["keel"], a, bar[0], ent[0]["ref_time"])
    assert isinstance(diag, dict) and want == ent[0]["keel_size"]
    x1 = [e for e in by_day[D_X1] if e["leg"] == "DIP_424K" and e["event"] == "EXIT"]
    assert len(x1) == 1 and x1[0]["size"] == ent[0]["size"] and x1[0]["keel_size"] == ent[0]["keel_size"]


def test_keel_with_no_state_sizes_one_and_never_pushes(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print, **k: sent.append(msg))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    paths, legs, _seed, by_day = _crash_run(tmp_path)
    assert not os.path.exists(legs["DIP_424K"]["keel"]["state_path"])
    ent = [e for e in by_day[D_ENTRY] if e["leg"] == "DIP_424K"]
    assert len(ent) == 7 and all(e["keel_size"] == 1.0 and e["size"] == 1.0 for e in ent)
    assert all(e["keel_branch"] == "fallback-1.0" for e in ent)
    assert sent == []
    a = five_arrays(paths, at(D_ENTRY, 9, 35, 5))
    bar = [i for i, ts in enumerate(a["index"]) if ts.isoformat() == ent[0]["ref_time"]][0]
    assert cs._keel_size_for_entry(legs["DIP_424K"]["keel"], a, bar, ent[0]["ref_time"]) ==         (1.0, "keel state unavailable")
    assert cs._push_allowed(legs["DIP_424K"], True) is False, "a shadow leg never pages"


# ── 12. const (DIP_424F) ───────────────────────────────────────────────────────────────────
def test_const_size_is_exactly_1_245_on_entry_and_exit(tmp_path):
    _paths, _legs, _seed, by_day = _crash_run(tmp_path)
    ent = [e for e in by_day[D_ENTRY] if e["leg"] == "DIP_424F"]
    assert len(ent) == 7 and all(e["size"] == 1.245 and e["keel_size"] == 1.245 for e in ent)
    assert all("keel_branch" not in e for e in ent), "no learned extras on a const leg"
    x1 = [e for e in by_day[D_X1] if e["leg"] == "DIP_424F" and e["event"] == "EXIT"]
    assert x1 and x1[0]["size"] == 1.245 and x1[0]["keel_size"] == 1.245


def test_const_mode_contract():
    good = {"mode": "const", "size": 1.245}
    assert cs._keel_size_for_entry(good, None, None, None) == (1.245, {"mode": "const", "size": 1.245})
    assert cs._keel_fallback_reason(good, at(D_ENTRY, 10, 0)) is None
    for bad in (5.0, 0.0, -1.0, float("nan"), float("inf"), "x", None):
        k = {"mode": "const", "size": bad}
        size, why = cs._keel_size_for_entry(k, None, 3, "2026-10-06T09:30:00-04:00")
        assert size == 1.0 and isinstance(why, str) and why.startswith("keel const size invalid")
        assert cs._keel_fallback_reason(k, at(D_ENTRY, 10, 0)).startswith("keel const size invalid")
        assert cs._keel_fallback_is_real(cs._keel_fallback_reason(k, at(D_ENTRY, 10, 0)))
    assert cs._keel_size_for_entry({"mode": "CONST", "size": "1.5"}, None, None, None)[0] == 1.5
    assert cs._seed_carry_sizes({"keel": good}, {"size": 1.0}) == (1.245, 1.245)
    assert cs._seed_carry_sizes({"keel": {"version": "v12", "mode": "fixed"}}, {"size": 1.0}) == (1.0, "")
    assert cs._seed_carry_sizes({}, {"size": 1.75}) == (1.75, "")


# ── 13. memo ───────────────────────────────────────────────────────────────────────────────
def test_the_second_leg_and_later_bars_do_not_recompute(tmp_path, monkeypatch):
    paths = write_home(tmp_path, CRASH, 30)
    calls = []
    real = cs.engine_run_backtest
    monkeypatch.setattr(cs, "engine_run_backtest", lambda *a, **k: calls.append(1) or real(*a, **k))
    now = at(D_ENTRY, 9, 35, 5)
    a = five_arrays(paths, now)
    k = cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424K"], a, "DIP_424K", now, paths, QUIET)
    assert len(calls) == 7
    f = cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424F"], a, "DIP_424F", now, paths, QUIET)
    assert len(calls) == 7 and _no_note(k) == _no_note(f)
    later = at(D_ENTRY, 14, 0, 5)
    cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424F"], five_arrays(paths, later), "DIP_424F", later,
                          paths, QUIET)
    assert len(calls) == 7, "a session's later bars change nothing the probe reports"
    nxt = at(D_X1, 9, 35, 5)
    cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424F"], five_arrays(paths, nxt), "DIP_424F", nxt,
                          paths, QUIET)
    assert len(calls) == 14


def test_a_broken_trade_shape_fails_the_tick_closed(tmp_path, monkeypatch):
    paths = write_home(tmp_path, CRASH, 30)
    now = at(D_ENTRY, 9, 35, 5)
    a = five_arrays(paths, now)
    monkeypatch.setattr(cs, "engine_run_backtest",
                        lambda *a_, **k: {"trades": [(400, 401, 1.0, 1, 1.0)]})
    logs = []
    assert cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424F"], a, "DIP_424F", now, paths, logs.append) is None
    got = cs.leg_decision_trades(cs.SHADOW_LEGS["DIP_424F"], a, "DIP_424F", "5m", now, paths,
                                 False, log=QUIET)
    assert got[0] is None and got[1] is a
    # a short trade, or a long not filled at the session open, fails it closed too
    for bad in ((400, 401, 1.0, -1, 1.0, 1.0), (400, 401, 1.0, 1, 1.0, 1.0)):
        DL._PROBE_MEMO.clear()
        monkeypatch.setattr(cs, "engine_run_backtest", lambda *a_, b=bad, **k: {"trades": [b]})
        assert cs.run_dip_leg_trades(cs.SHADOW_LEGS["DIP_424F"], a, "DIP_424F", now, paths,
                                     QUIET) is None


def test_a_dip_leg_never_reaches_run_leg_trades(tmp_path, monkeypatch):
    paths = write_home(tmp_path, CRASH, 30)
    monkeypatch.setattr(cs, "run_leg_trades", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("run_leg_trades called for a DIP leg")))
    ev = []
    for now in (at(D_CRASH, 17, 0), at(D_ENTRY, 9, 35, 5)):
        ev += cs.step(now=now, legs=_dip_legs(paths["home"]), paths=paths, fetch=False)
    assert len([e for e in ev if e["event"] == "ENTRY"]) == 14


# ── 14. the research files are byte-identical ──────────────────────────────────────────────
@pytest.mark.parametrize("rel, sha", [
    ("augur_strategies/NQDIP_1_1.py", "114a0b542d5cbd0472c1ef8675970f120fc3a3cdb5f63dacc0aab6a8e611a514"),
    ("augur_engine/ml_keel.py", "0b4dc36d488fe6db51a56a8e5011d51a29f91fe04a61df6059758796cee202e9"),
])
def test_research_files_are_unchanged(rel, sha):
    with open(os.path.join(ROOT, rel), "rb") as f:
        assert hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest() == sha
