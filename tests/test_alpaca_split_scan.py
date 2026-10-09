"""tools/alpaca_split_scan.py: the missed-split scan over research caches (TBIS data QA, 2026-10-04).

Pins the three schemas the caches use and the two decisions that matter: a whole-ratio gap whose
volume moves the other way IS flagged (GE's 1-for-8, 2021-08-02), a 2x news jump on rising volume
is NOT (with the volume test on), and files named *raw* are skipped as unadjusted by design.
No network, synthetic frames only.
"""
import importlib.util
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("_split_scan", os.path.join(ROOT, "tools", "alpaca_split_scan.py"))
scan_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan_mod)


def _intraday(days, prices, vols):
    """Two 10-minute regular-session bars a day (09:30, 15:50 ET)."""
    rows = []
    for d, p, v in zip(days, prices, vols):
        for hhmm in ("09:30", "15:50"):
            ts = pd.Timestamp(f"{d} {hhmm}", tz="US/Eastern")
            rows.append(dict(time=int(ts.timestamp()), open=p, high=p, low=p, close=p, volume=v))
    return pd.DataFrame(rows)


DAYS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2021-07-06", periods=40)]


def test_reverse_split_flagged_and_news_jump_not(tmp_path):
    # GE-like: price x8 on day 20, volume / 8 -> a split the feed missed
    ge = _intraday(DAYS, [13.0] * 20 + [104.0] * 20, [8e6] * 20 + [1e6] * 20)
    ge.to_csv(tmp_path / "GE.csv.gz", index=False)
    # news: price x2 on day 20 on HIGHER volume -> ordinary news, not a split
    nw = _intraday(DAYS, [10.0] * 20 + [20.0] * 20, [1e6] * 20 + [3e6] * 20)
    nw.to_csv(tmp_path / "NEWS_30m_split_rth.csv", index=False)
    flags, skipped, scanned = scan_mod.scan(str(tmp_path))
    assert scanned == 2 and not skipped
    assert [(f[1], f[2], f[4]) for f in flags] == [("GE", DAYS[20], "8:1")]
    # price-only (the strict write-guard rule) also flags the news jump
    flags_p, _, _ = scan_mod.scan(str(tmp_path), require_volume=False)
    assert sorted(f[1] for f in flags_p) == ["GE", "NEWS"]


def test_daily_and_multi_symbol_schemas(tmp_path):
    daily = pd.DataFrame({"date": DAYS, "open": [50.0] * 20 + [25.0] * 20, "close": [50.0] * 20 + [25.0] * 20,
                          "volume": [1e6] * 20 + [2e6] * 20})           # a 2:1 forward split left unadjusted
    daily.to_csv(tmp_path / "XYZ_1Day_split.csv", index=False)
    multi = pd.DataFrame({"symbol": ["AAA"] * 40 + ["BBB"] * 40, "date": DAYS * 2,
                          "o": [10.0] * 40 + [4.0] * 20 + [16.0] * 20, "c": [10.0] * 40 + [4.0] * 20 + [16.0] * 20,
                          "v": [1e6] * 40 + [4e6] * 20 + [1e6] * 20})     # BBB 1-for-4 reverse
    multi.to_parquet(tmp_path / "daily_split.parquet")
    flags, skipped, scanned = scan_mod.scan(str(tmp_path))
    assert scanned == 2 and not skipped
    got = sorted((f[1], f[2], f[4]) for f in flags)
    assert got == [("BBB", DAYS[20], "4:1"), ("XYZ", DAYS[20], "1:2")]


def test_raw_files_skipped_and_unknown_schema_reported(tmp_path):
    ge = _intraday(DAYS, [13.0] * 20 + [104.0] * 20, [8e6] * 20 + [1e6] * 20)
    ge.to_csv(tmp_path / "GE_1Day_raw.csv", index=False)
    pd.DataFrame({"symbol": ["A"], "name": ["x"]}).to_csv(tmp_path / "assets.csv", index=False)
    flags, skipped, scanned = scan_mod.scan(str(tmp_path))
    assert scanned == 0 and flags == []
    reasons = dict((os.path.basename(p), why) for p, why in skipped)
    assert reasons["GE_1Day_raw.csv"] == "raw by design"
    assert "assets.csv" in reasons
    flags_raw, _, _ = scan_mod.scan(str(tmp_path), include_raw=True)
    assert [f[1] for f in flags_raw] == ["GE"]


def test_daily_rows_stamped_at_midnight_are_scanned(tmp_path):
    """Alpaca 1D masters carry time = 00:00 ET; without a re-stamp the regular-session window sees
    no session and the scan passes a missed split silently."""
    mid = [int(pd.Timestamp(d, tz="US/Eastern").timestamp()) for d in DAYS]
    f = pd.DataFrame({"time": mid, "open": [13.0] * 20 + [104.0] * 20, "close": [13.0] * 20 + [104.0] * 20,
                      "volume": [8e6] * 20 + [1e6] * 20})
    f.to_csv(tmp_path / "master_ge1d.csv", index=False)
    flags, skipped, scanned = scan_mod.scan(str(tmp_path))
    assert scanned == 1 and [(x[2], x[4]) for x in flags] == [(DAYS[20], "8:1")]
