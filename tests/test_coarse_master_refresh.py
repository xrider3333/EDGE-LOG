"""The coarse masters (2m-60m): repairing a partial last bar, and when they refresh.

TWO THINGS ARE COVERED, both from the same 2026-09-30 owner GO via MANAGER.

1. REPAIRING A LAST ROW SAVED MID-BUCKET. A resampled master written while the market is
   open stores a bucket built from only the parent bars that had arrived. Nothing ever went
   back for it, so the partial bar was permanent. NOADJ_NQ_15m_RTH carried one from
   2026-06-30 10:45 ET - volume 5,270 against the parent's 16,244, because only 6 of its 15
   one-minute bars existed - and it failed the reproduction check on every run since, which
   correctly refused to append anything. That master stood still for three months.

   The repair must stay narrow: only the LAST row, and only when that row is provably a
   PREFIX of its own bucket. Anything else still stops the run, because a master we cannot
   rebuild from its parent is a master we do not understand.

2. WHEN THE REFRESH RUNS. Once an ET day after 17:25 (just behind the 17:20 refresh and
   push), plus once at runner start. Not every 30 minutes: nothing reads a 30m or 60m bar
   intraday, and rebuilding them each pass would rewrite millions of rows for no reader.
"""
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import augur_refresh  # noqa: E402
from tools import refresh_resampled_masters as rrm  # noqa: E402


def _parent(n=15, t0=1782830700, step=60):
    """A gap-free run of parent bars whose low keeps falling, so a prefix bucket and the
    full bucket genuinely differ on low, close and volume (as the real one did)."""
    rows = []
    for i in range(n):
        rows.append(dict(time=t0 + i * step, open=100.0 - i * 0.25, high=101.0 - i * 0.2,
                         low=99.0 - i * 0.5, close=100.5 - i * 0.3, volume=1000 + i))
    return pd.DataFrame(rows)


def _bucket_row(seg, t):
    b = rrm._bucket_from(seg)
    return pd.DataFrame([dict(time=t, **b)])


# ------------------------------------------------------------------ 1. the repair

def test_a_last_row_saved_mid_bucket_is_rebuilt_from_the_full_window():
    p = _parent()
    t = int(p["time"].iloc[0])
    existing = _bucket_row(p.iloc[:6], t)                 # saved after only 6 of 15 bars
    full = pd.concat([_bucket_row(p, t), _bucket_row(p, t + 900)], ignore_index=True)
    check = existing.merge(full, on="time", how="left", suffixes=("_old", "_new"))

    repaired, note = rrm.repair_partial_last_row(existing, full, p, check)
    assert repaired is not None, "a provable partial must be repairable"
    assert float(repaired["volume"].iloc[-1]) == pytest.approx(float(p["volume"].sum()))
    assert float(repaired["low"].iloc[-1]) == pytest.approx(float(p["low"].min()))
    assert float(repaired["close"].iloc[-1]) == pytest.approx(float(p["close"].iloc[-1]))


def test_the_repair_says_what_it_did_in_plain_english():
    """It must never be silent - a row rewritten without a word in the report is exactly
    the kind of thing nobody finds again."""
    p = _parent()
    t = int(p["time"].iloc[0])
    existing = _bucket_row(p.iloc[:6], t)
    full = pd.concat([_bucket_row(p, t), _bucket_row(p, t + 900)], ignore_index=True)
    check = existing.merge(full, on="time", how="left", suffixes=("_old", "_new"))
    _, note = rrm.repair_partial_last_row(existing, full, p, check)
    assert "6 of its 15 parent bars" in note
    assert "No earlier row was touched" in note


def test_a_wrong_row_that_is_NOT_a_prefix_is_refused():
    """Corruption must still stop the run. Only a row that looks exactly like an interrupted
    bucket is repairable; anything else means we cannot rebuild this master."""
    p = _parent()
    t = int(p["time"].iloc[0])
    existing = _bucket_row(p.iloc[:6], t)
    existing.loc[0, "high"] = 9999.0                      # not any prefix of this window
    full = pd.concat([_bucket_row(p, t), _bucket_row(p, t + 900)], ignore_index=True)
    check = existing.merge(full, on="time", how="left", suffixes=("_old", "_new"))
    repaired, note = rrm.repair_partial_last_row(existing, full, p, check)
    assert repaired is None and note is None


def test_history_is_never_rewritten_only_the_last_row():
    """If an EARLIER row is also disputed the file is not a mid-bucket save, and the strict
    check must win - repairing the tail would hide the real problem."""
    p = _parent(n=30)
    t0, t1 = int(p["time"].iloc[0]), int(p["time"].iloc[15])
    existing = pd.concat([_bucket_row(p.iloc[:15], t0), _bucket_row(p.iloc[15:21], t1)],
                         ignore_index=True)
    existing.loc[0, "close"] = 1.0                        # an earlier row is wrong too
    full = pd.concat([_bucket_row(p.iloc[:15], t0), _bucket_row(p.iloc[15:], t1),
                      _bucket_row(p.iloc[15:], t1 + 900)], ignore_index=True)
    check = existing.merge(full, on="time", how="left", suffixes=("_old", "_new"))
    assert rrm.repair_partial_last_row(existing, full, p, check)[0] is None


def test_the_real_nq_15m_row_is_the_case_this_was_written_for():
    """The numbers from the live master, so the fixture cannot drift away from the bug."""
    up = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_15m_RTH.csv")
    if not os.path.exists(up):
        pytest.skip("no NQ 15m master in this checkout")
    m = pd.read_csv(up)
    row = m[m["time"] == 1782830700]
    if not len(row):
        pytest.skip("the 2026-06-30 10:45 bucket is not this master's tail any more")
    assert float(row["volume"].iloc[0]) in (5270.0, 16244.0), (
        "either the unrepaired partial or the repaired full bucket - nothing else")


# --------------------------------------------------------------- 2. when it runs

def test_not_due_before_the_evening_cutoff(tmp_path):
    """Nothing reads a 30m bar intraday, so a midday pass must not rebuild them."""
    st = str(tmp_path / "state.json")
    for t in ("2026-09-30 09:35", "2026-09-30 13:00", "2026-09-30 17:24"):
        assert not augur_refresh.coarse_refresh_due(pd.Timestamp(t, tz="US/Eastern"), st)


def test_due_after_the_cutoff_when_it_has_not_run_today(tmp_path):
    st = str(tmp_path / "state.json")
    assert augur_refresh.coarse_refresh_due(pd.Timestamp("2026-09-30 17:26", tz="US/Eastern"), st)


def test_it_runs_once_a_day_not_once_a_pass(tmp_path):
    """The runner calls the refresh every pass; the second call of the evening must be a
    no-op, or a 30-minute cadence would rewrite millions of rows for no reader."""
    st = str(tmp_path / "state.json")
    evening = pd.Timestamp("2026-09-30 17:30", tz="US/Eastern")
    assert augur_refresh.coarse_refresh_due(evening, st)
    augur_refresh._mark_coarse_done(evening, st)
    assert not augur_refresh.coarse_refresh_due(evening, st)
    assert not augur_refresh.coarse_refresh_due(
        pd.Timestamp("2026-09-30 22:00", tz="US/Eastern"), st)
    # ...but the NEXT evening it is due again
    assert augur_refresh.coarse_refresh_due(
        pd.Timestamp("2026-10-01 17:30", tz="US/Eastern"), st)


def test_an_unreadable_state_file_means_not_run_today(tmp_path):
    """Failing to read the marker must cost one extra refresh, never skip one."""
    bad = tmp_path / "state.json"
    bad.write_text("{not json", encoding="utf-8")
    assert augur_refresh.coarse_refresh_due(
        pd.Timestamp("2026-09-30 17:30", tz="US/Eastern"), str(bad))


def test_the_marker_records_the_ET_day(tmp_path):
    st = str(tmp_path / "state.json")
    augur_refresh._mark_coarse_done(pd.Timestamp("2026-09-30 23:30", tz="US/Eastern"), st)
    assert json.load(open(st, encoding="utf-8"))["last_et_date"] == "2026-09-30"


def test_the_runner_forces_it_at_startup_only(monkeypatch):
    """`force` bypasses the day gate, which is how a freshly restarted fleet stops serving a
    stale coarse master. Every other pass goes through the gate."""
    calls = []
    monkeypatch.setattr(augur_refresh, "coarse_refresh_due", lambda *a, **k: calls.append("gated") or False)
    assert augur_refresh.run_coarse_refresh(force=False) == []
    assert calls == ["gated"], "a normal pass must consult the once-a-day gate"


def test_the_runner_calls_the_coarse_refresh_after_the_yahoo_one():
    """Order matters: the coarse masters are resampled FROM the 1m/5m parents, so refreshing
    them first would bake yesterday's tail into today's 30m bars."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    i_yahoo = src.index("changes = run_auto_refresh()")
    i_coarse = src.index("run_coarse_refresh(force=")
    assert i_yahoo < i_coarse
