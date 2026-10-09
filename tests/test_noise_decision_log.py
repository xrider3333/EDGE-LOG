"""DECISION BARS (2026-10-05, NOISE lane audit / MANAGER #65) -- api/cloud_signal.py writes,
on every NOISE ENTRY/EXIT row, the bar the engine decided on (start/end, OHLCV), the session
VWAP, the noise band and the exact level the rule compared, read from NOISE_1_0.py's own
DECISION RECORD (return_decisions). Logging only.

Proved here:
  * the plugin: return_decisions changes no trade, pnl or metric (NOISE_1_0.py over every
    exit/stop mode, NOISE_1_8_CT304.py, NOISE_1_8_CT304H.py), and each record's comparison
    really holds at the bar it names;
  * the live step: replayed bar by bar on fixture bars WITH and WITHOUT the logging, every
    decision field of every row (event, side, times, prices, shares, size, trade id, reason)
    and every state.json leg record are identical -- only the dec_* columns differ;
  * the logged values are the bar / VWAP / band the rule used AT DECISION TIME: they match an
    independent recompute from the bars as they were then, and a later revision of the
    decision bar in the cache (the Webull failure this exists to catch) does not touch the
    row already written;
  * non-NOISE legs leave every dec_* column blank; an old-header ledger upgrades in place.
"""
import csv
import json
import os
import types

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs
from augur_engine.strategies import load_strategy


# ── fixture bars ─────────────────────────────────────────────────────────────────────────
def _bars(n_sessions, seed):
    """n_sessions of 78 five-minute RTH bars, a noisy random walk with real volume."""
    rng = np.random.default_rng(seed)
    days = [d for d in pd.bdate_range("2026-06-01", periods=n_sessions + 6)
            if d.strftime("%Y-%m-%d") not in ("2026-06-19", "2026-07-03")][:n_sessions]
    rows, px = [], 500.0
    for d in days:
        base = pd.Timestamp(f"{d.date()} 09:30", tz=cs.TZ)
        drift = rng.normal(0, 0.0015)
        for i in range(78):
            o = px
            c = o * (1 + drift + rng.normal(0, 0.0018))
            rows.append({"time": int((base + pd.Timedelta(minutes=5 * i)).tz_convert("UTC").timestamp()),
                         "open": o, "high": max(o, c) * (1 + abs(rng.normal(0, 0.0006))),
                         "low": min(o, c) * (1 - abs(rng.normal(0, 0.0006))), "close": c,
                         "volume": float(rng.integers(5000, 20000))})
            px = c
        px *= 1 + rng.normal(0, 0.004)
    return pd.DataFrame(rows)


NOISE_T_PARAMS = {"lookback": 5, "band_mult_long": 0.35, "band_mult_short": 0.35,
                  "exit_mode": "vwap", "stop_mode": "bandwidth", "stop_k": 1.0}


def _stub_non_noise():
    """A non-NOISE leg (stands in for ORB / ENGU-Q): long at 10:00, out at 10:30, daily. It
    names no return_decisions, so its rows must leave every dec_* column blank."""
    mod = types.ModuleType("dec_log_non_noise_stub")
    mod.STRATEGY_NAME = "DEC_LOG_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        assert "return_decisions" not in kw
        o, c = np.asarray(opens, float), np.asarray(closes, float)
        log = []
        times = [t.strftime("%H:%M") for t in index]
        for i, hm in enumerate(times):
            if hm == "10:00":
                j = next((k for k in range(i, len(times)) if times[k] == "10:30"), None)
                if j is not None:
                    log.append((i, j, float(o[j] - o[i]), 1, float(o[i])))
                else:                               # still open: marked at the last close
                    log.append((i, len(c) - 1, float(c[-1] - o[i]), 1, float(o[i])))
        if not log:
            return None
        return {"trades": log if return_trades else None, "num_trades": len(log),
                "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "avg_pnl": 0, "wins": 0, "losses": 0}
    mod.run_backtest = run_backtest
    return mod


def _legs():
    return {
        # the real NOISE_1_0.py, a dense-trading geometry so a short tape proves something
        "NOISE_T": {"strategy": "NOISE_1_0.py", "timeframe": "5m", "warmup_sessions": 60,
                    "params": dict(NOISE_T_PARAMS), "decide_at_close": True, "eod_flat": True},
        # the same without the decide-at-close probe: ENTRY/EXIT found by the normal run
        "NOISE_T_LAG": {"strategy": "NOISE_1_0.py", "timeframe": "5m", "warmup_sessions": 60,
                        "params": dict(NOISE_T_PARAMS), "eod_flat": True},
        # the live crown's own file and params (NOISE_382), and the #422 shadow file
        "NOISE_382": dict(cs.CROWN_LEGS["NOISE_382"], keel=None),
        "NOISE_422_PLAIN": dict(cs.SHADOW_LEGS["NOISE_422_PLAIN"]),
        "STUB": {"strategy": _stub_non_noise(), "timeframe": "5m", "warmup_sessions": 60,
                 "params": {}},
    }


def _clean_legs():
    legs = _legs()
    for cfg in legs.values():
        if cfg.get("keel") is None:
            cfg.pop("keel", None)
    return legs


def _home(tmp_path, name, df):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    return paths


def _replay(paths, legs, df, n_sessions, after_tick=None, bar_sources=None):
    """Seed on the last bar before the window, then one step() per closed bar of the last
    `n_sessions` sessions. Returns every event, in order."""
    arrays = cs.build_arrays(df)
    idx = arrays["index"]
    days = sorted(set(idx.date))[-n_sessions:]
    bars = [ts for ts in idx if ts.date() in set(days)]
    cs.step(now=(bars[0] + pd.Timedelta(seconds=5)).to_pydatetime(), legs=legs, paths=paths,
            fetch=False, bar_sources=bar_sources)
    events = []
    for b in bars:
        now = (b + pd.Timedelta(seconds=300 + 10)).to_pydatetime()
        evs = cs.step(now=now, legs=legs, paths=paths, fetch=False, bar_sources=bar_sources)
        events.extend(evs)
        if after_tick:
            after_tick(b, evs)
    return events


def _ledger(paths):
    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
        f.seek(0)
        return header, list(csv.DictReader(f))


DF = None


def _df():
    global DF
    if DF is None:
        DF = _bars(60, seed=11)          # 60 sessions: the crown's lookback-40 band trades ~20
    return DF


# ── 1. the plugin: identical with and without the record; the record's rule holds ────────
def _run_plugin(fname, params, arrays, want):
    mod = load_strategy(fname)
    kw = dict(params)
    if want:
        kw["return_decisions"] = True
    return mod.run_backtest(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                            volumes=arrays["volume"], day_id=arrays["day_id"],
                            **({"index": arrays["index"]} if "CT304" in fname else {}),
                            return_trades=True, **kw)


def _check_rule(rec, o, h, l, c):
    """The comparison a record names must really hold at the bar it names."""
    i, lv = rec["bar"], rec["level"]
    rule = rec["rule"]
    checks = {"close>upper": lambda: c[i] > lv, "close<lower": lambda: c[i] < lv,
              "close<vwap": lambda: c[i] < lv, "close>vwap": lambda: c[i] > lv,
              "close<upper": lambda: c[i] < lv, "close>lower": lambda: c[i] > lv,
              "open<stop": lambda: o[i] < lv, "low<=stop": lambda: l[i] <= lv,
              "open>stop": lambda: o[i] > lv, "high>=stop": lambda: h[i] >= lv,
              "open<upper": lambda: o[i] < lv, "low<=upper": lambda: l[i] <= lv,
              "open>lower": lambda: o[i] > lv, "high>=lower": lambda: h[i] >= lv,
              "session_last_bar": lambda: lv is None}
    assert rule in checks, rule
    assert checks[rule](), (rule, rec)
    assert (rec["open"], rec["high"], rec["low"], rec["close"]) == (o[i], h[i], l[i], c[i])
    if rule in ("close<vwap", "close>vwap"):
        assert lv == rec["vwap"]
    if rule in ("close>upper", "close<upper"):
        assert lv == rec["upper"]
    if rule in ("close<lower", "close>lower"):
        assert lv == rec["lower"]


@pytest.mark.parametrize("params", [
    dict(NOISE_T_PARAMS),
    dict(NOISE_T_PARAMS, exit_mode="band", stop_mode="off"),
    dict(NOISE_T_PARAMS, exit_mode="boundary", stop_mode="fixed", stop_k=0.02),
    dict(NOISE_T_PARAMS, stop_mode="atr", stop_k=0.3, confirm_bars=2),
])
def test_noise_1_0_record_changes_nothing_and_its_rules_hold(params):
    arrays = cs.build_arrays(_df())
    off = _run_plugin("NOISE_1_0.py", params, arrays, False)
    on = _run_plugin("NOISE_1_0.py", params, arrays, True)
    assert "decisions" not in off
    dec = on.pop("decisions")
    assert on == off, "return_decisions must not change a single trade or metric"
    assert len(dec) == len(off["trades"]) >= 10
    o, h, l, c = (np.asarray(arrays[k], float) for k in ("open", "high", "low", "close"))
    for t, d in zip(off["trades"], dec):
        assert d["entry"]["bar"] == t[0] - 1                      # decided the bar before the fill
        _check_rule(d["entry"], o, h, l, c)
        _check_rule(d["exit"], o, h, l, c)
        assert d["exit"]["bar"] in (t[1], t[1] - 1)


@pytest.mark.parametrize("fname,params", [
    ("NOISE_1_8_CT304.py", cs.NOISE_382_PARAMS),
    ("NOISE_1_8_CT304H.py", cs.NOISE_422_PARAMS),
])
def test_noise_wrappers_forward_the_record_and_change_nothing(fname, params):
    arrays = cs.build_arrays(_df())
    off = _run_plugin(fname, params, arrays, False)
    on = _run_plugin(fname, params, arrays, True)
    assert off and off["num_trades"] >= 5, "fixture tape too quiet for the crown geometry"
    assert "decisions" not in off
    dec = on.pop("decisions")
    assert on == off
    assert len(dec) == len(off["trades"])
    assert cs._leg_accepts_return_decisions(fname)


def test_reflection_is_noise_only():
    assert cs._leg_accepts_return_decisions("NOISE_1_0.py")
    assert cs._leg_accepts_return_decisions(cs.CROWN_LEGS["NOISE_382"]["strategy"])
    for k in ("NOISE_422_PLAIN", "NOISE_422_FIXED", "NOISE_422_KEEL"):
        assert cs._leg_accepts_return_decisions(cs.SHADOW_LEGS[k]["strategy"])
    assert not cs._leg_accepts_return_decisions(cs.CROWN_LEGS["ORB_R6"]["strategy"])
    assert not cs._leg_accepts_return_decisions(cs.CROWN_LEGS["ENGUQ_335"]["strategy"])
    assert not cs._leg_accepts_return_decisions(_stub_non_noise())


# ── 2. the live step, replayed with and without the logging ─────────────────────────────
NON_DEC = [c for c in cs.SIGNAL_COLS if c not in cs.DECISION_COLS and c != "emitted_at"]


def _strip_state(state):
    s = json.loads(json.dumps(state, default=str))
    s.pop("generated_at", None)
    return s


def test_step_with_and_without_logging_decides_identically(tmp_path, monkeypatch):
    df = _df()
    runs = {}
    for flag in (False, True):
        monkeypatch.setattr(cs, "LOG_DECISION_BARS", flag)
        paths = _home(tmp_path, f"log_{flag}", df)
        events = _replay(paths, _clean_legs(), df, 3, bar_sources={"5m": "webull"})
        header, rows = _ledger(paths)
        runs[flag] = (events, rows, _strip_state(cs._load_state(paths)))
    (ev_off, rows_off, st_off), (ev_on, rows_on, st_on) = runs[False], runs[True]

    trade_rows = [r for r in rows_on if r["event"] in ("ENTRY", "EXIT")]
    by_leg = {k: [r for r in trade_rows if r["leg"] == k] for k in _legs()}
    assert len(by_leg["NOISE_T"]) >= 6 and by_leg["STUB"], "fixture too quiet to prove anything"
    assert len(by_leg["NOISE_T_LAG"]) >= 6
    assert by_leg["NOISE_382"] or by_leg["NOISE_422_PLAIN"], "no crown-file trade in the window"

    # every decision field of every row and the whole state is identical
    assert [{k: e.get(k, "") for k in NON_DEC} for e in ev_off] == \
           [{k: e.get(k, "") for k in NON_DEC} for e in ev_on]
    assert [{k: r[k] for k in NON_DEC} for r in rows_off] == [{k: r[k] for k in NON_DEC} for r in rows_on]
    assert st_off == st_on
    # off: every dec_* column blank everywhere
    assert all(r[c] == "" for r in rows_off for c in cs.DECISION_COLS)
    # on: every NOISE ENTRY/EXIT row has a full record; the stub, SEED rows: blank
    for r in rows_on:
        noise_trade = r["leg"].startswith("NOISE") and r["event"] in ("ENTRY", "EXIT")
        if noise_trade:
            blank = [c for c in cs.DECISION_COLS if r[c] == ""]
            allowed = {"dec_level"} if r["dec_rule"] == "session_last_bar" else set()
            assert set(blank) <= allowed, (r["leg"], r["event"], blank)
            assert r["dec_bar_source"] == r["bar_source"] == "webull"
        else:
            assert all(r[c] == "" for c in cs.DECISION_COLS), (r["leg"], r["event"])


def _vwap_at(df_day, k):
    tp = (df_day["high"] + df_day["low"] + df_day["close"]) / 3.0
    return float((tp * df_day["volume"]).iloc[:k + 1].sum() / df_day["volume"].iloc[:k + 1].sum())


def _noise_t_bands(df_upto, day, k):
    """NOISE_1_0's band at bar k of `day`, recomputed independently from the bars."""
    from augur_strategies import NOISE_1_0 as N   # pure helpers only
    arrays = cs.build_arrays(df_upto)
    did = arrays["day_id"]
    sb = N._session_bounds(did, len(did))
    o, c = np.asarray(arrays["open"], float), np.asarray(arrays["close"], float)
    sigma = N._sigma_matrix(o, c, sb, NOISE_T_PARAMS["lookback"])
    days = [arrays["index"][a].date() for a, _ in sb]
    si = days.index(day)
    a, _ = sb[si]
    prev_close = c[a - 1]
    ref_hi, ref_lo = max(o[a], prev_close), min(o[a], prev_close)
    return (ref_hi * (1 + NOISE_T_PARAMS["band_mult_long"] * sigma[si, k]),
            ref_lo * (1 - NOISE_T_PARAMS["band_mult_short"] * sigma[si, k]))


def _session_last_start(df, ts):
    """The start of the last bar of `ts`'s session in `df` (ET)."""
    t = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(cs.TZ)
    return t[t.dt.date == ts.date()].max()


def test_logged_values_are_what_the_rule_used_at_decision_time(tmp_path):
    """Each NOISE_T row's record equals the bar, VWAP and band recomputed independently from
    the bars AS THEY WERE at the tick that emitted it -- and revising the decision bar in the
    cache right after an ENTRY (Webull's late revision) leaves that row untouched, while a
    later row is logged from the revised bars it was in fact decided on."""
    orig = _df()
    paths = _home(tmp_path, "revise", orig)
    legs = {"NOISE_T": _legs()["NOISE_T"]}
    cache_csv = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    revised, tick_of = {}, {}
    nudge = {}

    def after_tick(b, evs):
        for e in evs:
            tick_of[(e["trade_id"], e["event"])] = b
        for e in evs:
            if e["event"] == "ENTRY" and not revised:
                # Webull revises the decision bar after the fact: the close moves 2.2c further
                # past the band (so the trade survives the re-run) and the volume halves
                t = int(pd.Timestamp(e["dec_bar_start"]).timestamp())
                d = 0.022 if e["side"] == "long" else -0.022
                cur = pd.read_csv(cache_csv)
                m = cur["time"] == t
                revised.update(t=t, tick=b, close=float(cur.loc[m, "close"].iloc[0]),
                               trade_id=e["trade_id"])
                nudge.update(d=d)
                cur.loc[m, "close"] += d
                cur.loc[m, "volume"] *= 0.5
                cur.to_csv(cache_csv, index=False)

    events = _replay(paths, legs, orig, 3, after_tick=after_tick)
    assert revised, "no ENTRY in the replay window"
    rows = [e for e in events if e["event"] in ("ENTRY", "EXIT")]
    assert len(rows) >= 6
    assert all(e["dec_bar_source"] == "cache" for e in rows)    # offline: no feed named

    revised_df = orig.copy()
    m = revised_df["time"] == revised["t"]
    revised_df.loc[m, "close"] += nudge["d"]
    revised_df.loc[m, "volume"] *= 0.5

    n_after = 0
    for e in rows:
        start = pd.Timestamp(e["dec_bar_start"]).tz_convert(cs.TZ)
        end = pd.Timestamp(e["dec_bar_end"]).tz_convert(cs.TZ)
        ref = pd.Timestamp(e["ref_time"]).tz_convert(cs.TZ)
        assert end - start == pd.Timedelta(minutes=5)
        # a VWAP / band close mid-session fills at the NEXT bar's open; on the session's
        # last bar it fills at that same bar's close (STEP C with is_last) -- same bar
        close_rule = e["dec_rule"] in ("close<vwap", "close>vwap", "close<upper", "close>lower")
        same_bar_close = close_rule and start == _session_last_start(orig, start)
        if e["event"] == "ENTRY" or (close_rule and not same_bar_close):
            assert end == ref, "decided at the close of the bar before the fill"
        else:
            assert start == ref, "a stop / boundary / last-bar exit is decided on its own bar"
        # the bars this row's tick read: the original cache up to (and including) the tick
        # that revised it, the revised cache after
        after = tick_of[(e["trade_id"], e["event"])] > revised["tick"]
        n_after += after
        source = revised_df if after else orig
        t = int(start.timestamp())
        upto = source[source["time"] <= t]
        day_rows = upto[pd.to_datetime(upto["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
                        == start.date()].reset_index(drop=True)
        k = len(day_rows) - 1
        bar = day_rows.iloc[k]
        assert (e["dec_open"], e["dec_high"], e["dec_low"], e["dec_close"]) == pytest.approx(
            (bar["open"], bar["high"], bar["low"], bar["close"]), rel=0, abs=1e-9)
        assert e["dec_volume"] == pytest.approx(bar["volume"])
        assert e["dec_vwap"] == pytest.approx(_vwap_at(day_rows, k), rel=1e-12)
        ub, lb = _noise_t_bands(upto, start.date(), k)
        assert e["dec_band_upper"] == pytest.approx(ub, rel=1e-12)
        assert e["dec_band_lower"] == pytest.approx(lb, rel=1e-12)
        want = {"close>upper": ub, "close<lower": lb, "close<vwap": e["dec_vwap"],
                "close>vwap": e["dec_vwap"]}
        if e["dec_rule"] in want:
            assert e["dec_level"] == pytest.approx(want[e["dec_rule"]], rel=1e-12)
    assert n_after >= 1, "no row decided after the revision -- the test proves only half"

    # the ENTRY whose bar was revised keeps the bar it was decided on, in the ledger too
    ent = next(e for e in events if e["event"] == "ENTRY" and e["trade_id"] == revised["trade_id"])
    assert ent["dec_close"] == revised["close"]
    final = pd.read_csv(cache_csv)
    assert float(final.loc[final["time"] == revised["t"], "close"].iloc[0]) != revised["close"]
    _, ledger_rows = _ledger(paths)
    led = next(r for r in ledger_rows if r["event"] == "ENTRY" and r["trade_id"] == revised["trade_id"])
    assert float(led["dec_close"]) == revised["close"], "the ledger keeps the decision-time bar"


# ── 3. header migration ─────────────────────────────────────────────────────────────────
def test_old_header_ledger_upgrades_and_keeps_its_rows(tmp_path):
    paths = cs._paths(home=str(tmp_path / "mig"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    old_cols = cs.SIGNAL_COLS[:cs.SIGNAL_COLS.index("target_px") + 1]
    with open(paths["signals_path"], "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=old_cols)
        w.writeheader()
        w.writerow({"emitted_at": "x", "leg": "ORB_R6", "event": "ENTRY", "side": "long",
                    "stop_px": "725.53", "target_px": "757.03"})
    ev = {"emitted_at": "y", "leg": "NOISE_382", "event": "ENTRY", "side": "short",
          "dec_bar_start": "2026-09-28T09:30:00-04:00", "dec_close": 735.66,
          "dec_vwap": 735.9, "dec_rule": "close<lower", "dec_level": 735.7,
          "dec_bar_source": "webull"}
    cs._append_signals([ev], paths)
    header, rows = _ledger(paths)
    assert header == cs.SIGNAL_COLS
    assert rows[0]["stop_px"] == "725.53" and all(rows[0][c] == "" for c in cs.DECISION_COLS)
    assert rows[1]["dec_close"] == "735.66" and rows[1]["dec_rule"] == "close<lower"
    assert rows[1]["dec_bar_source"] == "webull" and rows[1]["stop_px"] == ""


# ── 4. a bad record only blanks the dec_* columns -- logged, and never costs a trade ──────
def _noise_leg():
    return dict(_legs()["NOISE_T"])


def _decide(t):
    return {k: t[k] for k in ("side", "entry_time", "entry_px", "shares", "exit_time",
                              "exit_px", "still_open", "size", "entry_bar")}


@pytest.mark.parametrize("damage,expect_log", [
    (lambda d: d[:-1], "missing or misaligned"),                    # one record short
    (lambda d: None, "missing or misaligned"),                      # no records at all
    (lambda d: [{"entry": 5, "exit": 7}] * len(d), "rejected"),     # entry truthy, not a dict
    (lambda d: [dict(r, entry=dict(r["entry"], bar=r["entry"]["bar"] - 1)) for r in d],
     "rejected"),                                                   # entry bar off by one
    (lambda d: [dict(r, entry=dict(r["entry"], rule="close<lower" if r["entry"]["rule"]
                                   == "close>upper" else "close>upper")) for r in d],
     "rejected"),                                                   # wrong side
])
def test_bad_decision_records_blank_the_columns_and_say_so(monkeypatch, damage, expect_log):
    arrays = cs.build_arrays(_df())
    cfg = _noise_leg()
    good = cs.run_leg_trades(cfg, arrays, "NOISE_T", log=lambda m: None)
    assert len(good) >= 10 and all(t["decision"] is not None for t in good)
    real = cs.engine_run_backtest

    def damaged(*a, **kw):
        res = real(*a, **kw)
        res["decisions"] = damage(res["decisions"])
        return res

    monkeypatch.setattr(cs, "engine_run_backtest", damaged)
    logs = []
    bad = cs.run_leg_trades(cfg, arrays, "NOISE_T", log=logs.append)
    assert [_decide(t) for t in bad] == [_decide(t) for t in good], "a bad record changed a trade"
    assert all(t["decision"] is None for t in bad)
    assert any(expect_log in m for m in logs), logs


def test_trade_decision_never_raises():
    idx = cs.build_arrays(_df())["index"]
    for rec in ({"entry": 5}, {"entry": "x"}, {"entry": [1, 2]}, {"entry": {"bar": object()}},
                {"entry": {"bar": 9, "rule": "close>upper"}, "exit": 3}, 7, None):
        assert cs._trade_decision(rec, 10, 1, idx, len(idx), "5m") is None or \
            cs._trade_decision(rec, 10, 1, idx, len(idx), "5m")["exit"] is None
