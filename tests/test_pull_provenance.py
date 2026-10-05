r"""Pull provenance (augur_engine/pull_provenance.py, 2026-10-05).

WHAT IT IS FOR. Alpaca computes `adjustment=split` AT QUERY TIME and corrects its own history:
GE's daily bar for 2021-07-30 came back 12.95 at ~15:45 and 103.60 at ~17:20 the same afternoon.
A cache is therefore a photograph of the vendor on the day it was pulled, and a result cannot be
reproduced without knowing which photograph it used. These tests pin the three properties that
make the record worth having:

  - the hash depends on the BARS and nothing else - not on row order, not on pandas' dtype
    choices. A hash that moved when pandas was upgraded would report every cache as changed and
    teach everyone to ignore the warning, which is worse than having none;
  - a changed vendor answer is recognisable, and a changed REQUESTED WINDOW is not reported as
    one (that would be noise burying the real thing);
  - nothing here can break a pull. A six-hour download must not fail because its receipt could
    not be filed.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import pull_provenance as prov  # noqa: E402


@pytest.fixture(autouse=True)
def _own_home(monkeypatch, tmp_path):
    """Never the real C:\\EdgeLog\\state - conftest's live-system guard blocks that write and
    fails the test, which is the correct outcome."""
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    return tmp_path


def _df(n=5, base=100.0, start=1_600_000_000, step=60):
    return pd.DataFrame({
        "time": [start + i * step for i in range(n)],
        "open": [base + i for i in range(n)],
        "high": [base + i + 0.5 for i in range(n)],
        "low": [base + i - 0.5 for i in range(n)],
        "close": [base + i + 0.25 for i in range(n)],
        "volume": [1000 + i for i in range(n)],
    })


# ═══════════════════════════════════════════════════ the hash
def test_the_same_bars_hash_the_same():
    assert prov.content_hash(_df()) == prov.content_hash(_df())


def test_row_order_does_not_change_the_hash():
    """The vendor's paging order is not part of the data."""
    a = _df(8)
    b = a.iloc[::-1].reset_index(drop=True)
    assert prov.content_hash(a) == prov.content_hash(b)


def test_a_changed_price_changes_the_hash():
    a = _df()
    b = _df()
    b.loc[2, "close"] = b.loc[2, "close"] + 0.01
    assert prov.content_hash(a) != prov.content_hash(b)


def test_a_changed_volume_changes_the_hash():
    a = _df()
    b = _df()
    b.loc[1, "volume"] = int(b.loc[1, "volume"]) + 1
    assert prov.content_hash(a) != prov.content_hash(b)


def test_a_missing_bar_changes_the_hash():
    a = _df(6)
    b = a.drop(index=3).reset_index(drop=True)
    assert prov.content_hash(a) != prov.content_hash(b)


def test_the_hash_does_not_depend_on_the_dtype_pandas_chose():
    """THE ONE THAT PROTECTS THE WARNING'S CREDIBILITY. pandas 3 changed the datetime
    resolution; a hash that moved with the library would mark every cache changed."""
    a = _df()
    b = _df()
    b["time"] = b["time"].astype("int32")
    b["volume"] = b["volume"].astype("float64")
    b["open"] = b["open"].astype("float32").astype("float64")
    assert prov.content_hash(a) == prov.content_hash(b)


def test_extra_columns_are_ignored():
    """A caller's own annotations are not the vendor's answer."""
    a = _df()
    b = _df()
    b["symbol"] = "GE"
    b["note"] = "re-pulled"
    assert prov.content_hash(a) == prov.content_hash(b)


def test_an_empty_frame_has_its_own_stable_hash():
    assert prov.content_hash(pd.DataFrame()) == prov.content_hash(pd.DataFrame())
    assert prov.content_hash(pd.DataFrame()) != prov.content_hash(_df())


def test_an_unusable_frame_does_not_raise():
    """A hash is a receipt, not a validator."""
    h = prov.content_hash(pd.DataFrame({"nope": [1, 2]}))
    assert isinstance(h, str) and h.startswith("sha256:")


# ═══════════════════════════════════════════════════ what a record holds
def test_a_record_says_when_and_what_and_how_much():
    r = prov.record("ge", "1Day", "2021-07-01", "2021-08-31", _df(7))
    assert r["symbol"] == "GE", "the symbol is normalised so GE and ge are one series"
    assert r["rows"] == 7
    assert r["requested_start"] == "2021-07-01" and r["requested_end"] == "2021-08-31"
    assert r["pulled_at"].endswith("Z"), "a pull time with no timezone is not evidence"
    assert r["content_hash"].startswith("sha256:")
    assert r["first_bar"] < r["last_bar"]


def test_the_record_lands_on_disk_as_one_json_line():
    prov.record("GE", "1Day", "a", "b", _df())
    with open(prov.manifest_path(), encoding="utf-8") as fh:
        lines = [l for l in fh.read().splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["symbol"] == "GE"


def test_the_adjustment_is_part_of_the_series_identity():
    """A split-adjusted pull and a raw one SHOULD differ; treating them as one series would
    report that difference as a vendor revision every single time."""
    assert prov.series_key("GE", "1Day", "split") != prov.series_key("GE", "1Day", "raw")
    prov.record("GE", "1Day", "a", "b", _df(), adjustment="split")
    prov.record("GE", "1Day", "a", "b", _df(9), adjustment="raw")
    assert len(prov.history("GE", "1Day", "split")) == 1
    assert len(prov.history("GE", "1Day", "raw")) == 1


def test_an_empty_pull_is_still_recorded():
    """"The vendor returned nothing on this day" is as much a photograph as a full one, and it is
    what you want on record when a symbol quietly stops coming back."""
    r = prov.record("ZZZZ", "1Day", "a", "b", pd.DataFrame())
    assert r["rows"] == 0
    assert prov.latest("ZZZZ", "1Day")["rows"] == 0


def test_history_is_newest_first_even_within_one_second():
    """NO SLEEP ON PURPOSE. Three pulls inside the same second used to tie on the timestamp and
    order arbitrarily, so "the latest pull" - which is what compare_to_fresh asks for - was a
    coin flip. The stamp now carries microseconds and ties fall back to position in the
    append-only file, which is the true order.
    """
    for n in (3, 4, 5):
        prov.record("GE", "1Day", "a", "b", _df(n))
    rows = prov.history("GE", "1Day")
    assert [r["rows"] for r in rows] == [5, 4, 3], [r["rows"] for r in rows]
    assert prov.latest("GE", "1Day")["rows"] == 5


def test_trim_keeps_the_newest_when_every_pull_shares_a_second():
    for n in range(1, prov.KEEP_PER_SERIES + 4):
        prov.record("GE", "1Day", "a", "b", _df(n))
    prov.trim()
    rows = prov.history("GE", "1Day")
    assert len(rows) == prov.KEEP_PER_SERIES
    assert rows[0]["rows"] == prov.KEEP_PER_SERIES + 3, "it threw away the newest"


# ═══════════════════════════════════════════════════ did the vendor change its mind?
def test_a_revised_answer_for_the_same_window_is_reported():
    """The GE case, in miniature: one window, two pulls, different content."""
    prov.record("GE", "1Day", "2021-07-01", "2021-08-31", _df(5, base=12.95))
    prov.record("GE", "1Day", "2021-07-01", "2021-08-31", _df(5, base=103.60))
    pairs = prov.changed_between_pulls("GE", "1Day")
    assert len(pairs) == 1
    older, newer = pairs[0]
    assert older["content_hash"] != newer["content_hash"]


def test_two_identical_pulls_are_not_reported_as_a_change():
    prov.record("GE", "1Day", "a", "b", _df())
    prov.record("GE", "1Day", "a", "b", _df())
    assert prov.changed_between_pulls("GE", "1Day") == []


def test_a_different_WINDOW_is_not_reported_as_a_vendor_change():
    """A longer window naturally returns more bars. Calling that a revision would bury the real
    thing in noise - this is the false positive that would make the tool useless."""
    prov.record("GE", "1Day", "2021-07-01", "2021-08-31", _df(5))
    prov.record("GE", "1Day", "2021-01-01", "2021-12-31", _df(250))
    assert prov.changed_between_pulls("GE", "1Day") == []


# ═══════════════════════════════════════════════════ comparing a cache with a fresh pull
def test_an_unchanged_series_says_so():
    prov.record("GE", "1Day", "a", "b", _df())
    verdict, msg = prov.compare_to_fresh(_df(), "GE", "1Day")
    assert verdict == "same", msg


def test_a_changed_series_says_cache_differs_from_a_fresh_pull():
    prov.record("GE", "1Day", "a", "b", _df(5, base=12.95))
    verdict, msg = prov.compare_to_fresh(_df(5, base=103.60), "GE", "1Day")
    assert verdict == "differs"
    assert "cache differs from a fresh pull" in msg, msg
    assert "RE-PULL" in msg, "it must say what to do, not just that something is wrong"
    assert "QUERY TIME" in msg, "and why, or it reads as a loader bug"


def test_a_series_never_pulled_is_unknown_not_clean():
    verdict, msg = prov.compare_to_fresh(_df(), "NEVER", "1Day")
    assert verdict == "unknown"
    assert "nothing to compare" in msg


# ═══════════════════════════════════════════════════ it must never break a pull
def test_a_manifest_that_cannot_be_written_does_not_raise(monkeypatch):
    monkeypatch.setattr(prov.os, "makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "nope")))
    assert prov.record("GE", "1Day", "a", "b", _df()) is not None, \
        "the caller still gets its record even when nothing could be filed"


def test_a_lock_it_cannot_take_skips_the_write_rather_than_tearing_the_file(monkeypatch):
    """FAIL OPEN, BUT DO NOT WRITE UNLOCKED. A torn line would corrupt the record for everybody;
    a missing line costs this one receipt. Same rule as the rate limiter's fail-open path, which
    had exactly this bug and touched shared state anyway."""
    import contextlib
    from augur_engine import alpaca_rate

    @contextlib.contextmanager
    def never_got(*a, **k):
        yield False

    monkeypatch.setattr(alpaca_rate, "_lock", never_got)
    prov.record("GE", "1Day", "a", "b", _df())
    assert prov.read_all() == [], "it wrote without the lock"


def test_a_damaged_line_does_not_make_the_rest_unreadable():
    prov.record("GE", "1Day", "a", "b", _df())
    with open(prov.manifest_path(), "a", encoding="utf-8") as fh:
        fh.write("{this is not json\n")
    prov.record("INTC", "1Day", "a", "b", _df())
    syms = {r["symbol"] for r in prov.read_all()}
    assert syms == {"GE", "INTC"}


def test_reading_a_manifest_that_does_not_exist_is_empty_not_an_error():
    assert prov.read_all(os.path.join("no", "such", "file.jsonl")) == []
    assert prov.latest("GE", "1Day") is None


def test_describe_handles_nothing():
    assert "no recorded pull" in prov.describe(None)


# ═══════════════════════════════════════════════════ housekeeping
def test_trim_keeps_the_newest_per_series():
    import time as _t
    for i in range(prov.KEEP_PER_SERIES + 6):
        prov.record("GE", "1Day", "a", "b", _df(i + 1))
        _t.sleep(0.001)
    removed = prov.trim()
    assert removed == 6
    assert len(prov.history("GE", "1Day")) == prov.KEEP_PER_SERIES


def test_trim_does_not_mix_series():
    prov.record("GE", "1Day", "a", "b", _df())
    prov.record("INTC", "1Day", "a", "b", _df())
    assert prov.trim() == 0
    assert len(prov.read_all()) == 2


# ═══════════════════════════════════════════════════ where the hook lives
def test_fetch_bars_records_every_pull_including_an_empty_one():
    """RECORDED IN fetch_bars, NOT IN upsert_master. TTM, TBIS and the ROC-frontier harnesses
    pull straight into their own research caches and never reach the library path, so a receipt
    filed only there would miss exactly the pulls that matter - the limitation the split guard
    shipped with."""
    src = open(os.path.join(ROOT, "tools", "import_alpaca_stocks.py"), encoding="utf-8").read()
    body = src[src.index("def fetch_bars"):src.index("def rth_filter")]
    assert body.count("pull_provenance.record(") == 2, \
        "both the empty-result path and the normal one must file a receipt"


def test_the_hash_is_computed_on_the_deduplicated_sorted_frame():
    """fetch_bars de-duplicates and sorts before returning; the receipt must describe what the
    caller actually gets, not the raw paged rows."""
    src = open(os.path.join(ROOT, "tools", "import_alpaca_stocks.py"), encoding="utf-8").read()
    body = src[src.index("def fetch_bars"):src.index("def rth_filter")]
    i_dedup = body.index("drop_duplicates")
    i_record = body.rindex("pull_provenance.record(")
    assert i_dedup < i_record
