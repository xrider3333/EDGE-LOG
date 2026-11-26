"""tools/nq_box_topup.py (board 174): the box adds ONLY missing completed NQ 5m RTH bars after its
master's last bar, before the nightly KEEL build. No network: Yahoo is a stub frame."""
import importlib.util
import os

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "_nq_box_topup_under_test",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "nq_box_topup.py"))
T = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(T)


def _ts(day, hhmm):
    return int(pd.Timestamp("%s %s" % (day, hhmm), tz="US/Eastern").tz_convert("UTC").timestamp())


def _session(day, price=100.0, start="09:30", end="15:55"):
    t0, t1 = _ts(day, start), _ts(day, end)
    times = list(range(t0, t1 + 1, 300))
    n = len(times)
    return pd.DataFrame({"time": times, "open": [price] * n, "high": [price + 1] * n,
                         "low": [price - 1] * n, "close": [price] * n, "volume": [10] * n})


def _write_master(tmp_path, df, nl="\r\n"):
    p = tmp_path / "NOADJ_NQ_5m_RTH.csv"
    rows = ["time,open,high,low,close,volume,source"]
    for r in df.itertuples(index=False):
        rows.append("%d,%r,%r,%r,%r,%d,nt_hist" % (r.time, float(r.open), float(r.high),
                                                 float(r.low), float(r.close), r.volume))
    p.write_bytes((nl.join(rows) + nl).encode())
    return str(p)


NOW = _ts("2026-11-24", "18:15")


def test_add_only_existing_bytes_identical(tmp_path):
    p = _write_master(tmp_path, _session("2026-11-23"))
    before = open(p, "rb").read()
    # Yahoo disagrees on 11-23 (price 200) - those bars must NOT be rewritten.
    yahoo = pd.concat([_session("2026-11-23", 200.0), _session("2026-11-24", 101.0)])
    n = T.run(p, now_s=NOW, fetch=lambda: yahoo)
    assert n == 78
    after = open(p, "rb").read()
    assert after.startswith(before)
    df = pd.read_csv(p)
    assert len(df) == 156 and df["time"].is_monotonic_increasing
    assert set(df["source"].iloc[78:]) == {T.SOURCE_TAG}
    assert b"\r\n" in after[len(before):]          # keeps the file's line ending
    assert (df["close"].iloc[:78] == 100.0).all()


def test_forming_bar_and_open_session_skipped(tmp_path):
    p = _write_master(tmp_path, _session("2026-11-23"))
    before = open(p, "rb").read()
    yahoo = pd.concat([_session("2026-11-23"), _session("2026-11-24", end="14:00")])
    now = _ts("2026-11-24", "14:03")          # mid-session: 14:00 bar still forming
    assert T.run(p, now_s=now, fetch=lambda: yahoo) == 0
    assert open(p, "rb").read() == before


def test_new_bars_drops_forming_bar():
    yahoo = _session("2026-11-24")
    now = _ts("2026-11-24", "16:05")          # 15:55 bar closed but not settled; session not settled
    out, _ = T.new_bars(_ts("2026-11-23", "15:55"), yahoo, now)
    assert len(out) == 0
    out, _ = T.new_bars(_ts("2026-11-23", "15:55"), yahoo, NOW)
    assert len(out) == 78


def test_no_new_data_is_noop(tmp_path):
    p = _write_master(tmp_path, _session("2026-11-23"))
    before = open(p, "rb").read()
    assert T.run(p, now_s=NOW, fetch=lambda: _session("2026-11-23")) == 0
    assert T.run(p, now_s=NOW, fetch=lambda: None) == 0
    assert open(p, "rb").read() == before


def test_gap_appends_only_after_last_bar(tmp_path):
    # master ends 11-19; Yahoo only has 11-23 and 11-24 (gap 11-20 not available) -> add those, in order
    p = _write_master(tmp_path, _session("2026-11-19"))
    yahoo = pd.concat([_session("2026-11-24"), _session("2026-11-23")])
    assert T.run(p, now_s=NOW, fetch=lambda: yahoo) == 156
    df = pd.read_csv(p)
    assert df["time"].is_monotonic_increasing and df["time"].is_unique


def test_pc_push_same_day_is_noop_without_fetch(tmp_path):
    p = _write_master(tmp_path, pd.concat([_session("2026-11-23"), _session("2026-11-24")]))
    before = open(p, "rb").read()

    def boom():
        raise AssertionError("must not fetch when the PC already pushed today")
    assert T.run(p, now_s=NOW, fetch=boom) == 0
    assert open(p, "rb").read() == before


def test_eth_bars_filtered(tmp_path):
    p = _write_master(tmp_path, _session("2026-11-23"))
    yahoo = pd.concat([_session("2026-11-24", start="04:00", end="20:00")])
    assert T.run(p, now_s=_ts("2026-11-24", "21:00"), fetch=lambda: yahoo) == 78


def test_fetch_error_never_raises(tmp_path):
    p = _write_master(tmp_path, _session("2026-11-23"))

    def bad():
        raise RuntimeError("network down")
    assert T.run(p, now_s=NOW, fetch=bad) == 0
    assert T.main(["--nq-file", str(tmp_path / "missing.csv")]) == 0


def test_keel_state_unit_tops_up_first_and_never_blocks():
    unit = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "deploy", "cloud", "edgelog-keel-state.service")
    lines = [ln.strip() for ln in open(unit, encoding="utf-8") if not ln.strip().startswith("#")]
    pre = [ln for ln in lines if ln.startswith("ExecStartPre=")]
    assert pre == ["ExecStartPre=-__EDGELOG_VENV__/bin/python -u tools/nq_box_topup.py "
                   "--nq-file __EDGELOG_HOME__/nq/NOADJ_NQ_5m_RTH.csv"]
    assert lines.index(pre[0]) < [i for i, ln in enumerate(lines) if ln.startswith("ExecStart=")][0]


def test_holiday_and_half_day_bars_skipped(tmp_path):
    # 11-26 Thanksgiving (CME short session), 11-27 half day: both left for the PC push, and
    # nothing after them is added either (no hole in the master)
    p = _write_master(tmp_path, _session("2026-11-25"))
    before = open(p, "rb").read()
    yahoo = pd.concat([_session("2026-11-25"), _session("2026-11-26", 90.0, end="12:55"),
                       _session("2026-11-27", 91.0, end="13:10"), _session("2026-11-30", 92.0)])
    assert T.run(p, now_s=_ts("2026-11-30", "18:15"), fetch=lambda: yahoo) == 0
    assert open(p, "rb").read() == before


def test_full_days_after_pc_filled_half_day_added(tmp_path):
    p = _write_master(tmp_path, pd.concat([_session("2026-11-25"), _session("2026-11-27", end="13:10")]))
    yahoo = pd.concat([_session("2026-11-27", end="13:10"), _session("2026-11-30", 92.0),
                       _session("2026-12-01", 93.0, end="12:00")])
    assert T.run(p, now_s=_ts("2026-12-01", "18:15"), fetch=lambda: yahoo) == 78


def test_pc_push_mid_run_not_overwritten(tmp_path):
    p = _write_master(tmp_path, _session("2026-11-23"))
    pc = _session("2026-11-23")

    def fetch():
        # a PC push lands while the top-up is pulling Yahoo
        _write_master(tmp_path, pd.concat([pc, _session("2026-11-24", 150.0)]))
        return pd.concat([_session("2026-11-23"), _session("2026-11-24", 101.0)])

    n = T.run(p, now_s=NOW, fetch=fetch)
    assert n == 0
    df = pd.read_csv(p)
    assert len(df) == 156 and (df["close"].iloc[78:] == 150.0).all()
    assert set(df["source"]) == {"nt_hist"}
    assert not [f for f in os.listdir(tmp_path) if f.startswith(".topup_")]


def test_roll_guard_cut_mid_day_adds_no_partial_day(tmp_path, monkeypatch):
    p = _write_master(tmp_path, _session("2026-11-23"))
    before = open(p, "rb").read()
    cut = _ts("2026-11-24", "12:00")
    monkeypatch.setattr(T.R.roll_guard, "split_tv_frame",
                        lambda df, after_time, root: (df[df["time"] < cut].reset_index(drop=True), None))
    yahoo = pd.concat([_session("2026-11-23"), _session("2026-11-24", 101.0)])
    assert T.run(p, now_s=NOW, fetch=lambda: yahoo) == 0
    assert open(p, "rb").read() == before


def test_spike_after_feed_hole_held_back(tmp_path):
    # 11-24 has a 15-min hole at 15:00 then a bar opening 5 pct off: nothing from that day lands,
    # and the guard trims at the spike even when the full-day filter is bypassed.
    p = _write_master(tmp_path, _session("2026-11-23"))
    before = open(p, "rb").read()
    d = _session("2026-11-24")
    d = d[~d["time"].isin([_ts("2026-11-24", "15:00"), _ts("2026-11-24", "15:05")])].copy()
    d.loc[d["time"] == _ts("2026-11-24", "15:10"), "open"] = 105.0
    assert T.run(p, now_s=NOW, fetch=lambda: d) == 0
    assert open(p, "rb").read() == before
    orig = T._full_sessions_only
    T._full_sessions_only = lambda df: df
    try:
        out, note = T.new_bars(_ts("2026-11-23", "15:55"), d, NOW, prev_close=100.0)
    finally:
        T._full_sessions_only = orig
    assert int(out["time"].max()) == _ts("2026-11-24", "14:55") and "jumps" in note


def test_overnight_gap_is_not_a_spike():
    # 09:30 open 5 pct above the prior 15:55 close is a real gap (hole > 55 min), not a spike.
    d = _session("2026-11-24", 105.0)
    out, note = T.new_bars(_ts("2026-11-23", "15:55"), d, NOW, prev_close=100.0)
    assert len(out) == 78 and note is None
