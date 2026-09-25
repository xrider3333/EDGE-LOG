"""tools/cloud_signal_repair_20260914.py.

Covers docs/CLOUD_SIGNAL_REPAIR_20260914.md (item 1: the 2026-09-14 replay-contaminated rows
8-12 + legs.NOISE_304) and WEBULL_PAPER_TODO.md #4 (the one 2026-09-21 duplicate NOISE_304
ENTRY row), on a temp-dir copy of the live layout -- never the owner's real EDGELOG_HOME
(tests/conftest.py's live_system_guard blocks any write there regardless).

Fixture shape: 7 filler rows (unrelated leg, never touched) + the 5 item-1 rows (data rows
8-12, exactly as docs/CLOUD_SIGNAL_REPAIR_20260914.md's evidence table gives them) + the 2
item-4 duplicate rows (the ledger's last two rows, as WEBULL_PAPER_TODO.md #4 describes them).
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import cloud_signal as cs                              # noqa: E402
from api import qqq_exec as qe                                  # noqa: E402
from tools import cloud_signal_repair_20260914 as R              # noqa: E402

NY = ZoneInfo("America/New_York")
# Any date/time after 16:05 ET satisfies "outside the 09:25-16:05 weekday window" regardless
# of which weekday it lands on -- see api.qqq_exec._in_market_window.
SAFE_NOW = datetime(2026, 9, 25, 22, 0, tzinfo=NY)
LATER_SAFE_NOW = datetime(2026, 9, 26, 22, 0, tzinfo=NY)


def _row(emitted_at, leg, event, side="", ref_time="", ref_price="", shares="", reason="",
        bar_source="webull", trade_id="", size="", keel_size=""):
    return {"emitted_at": emitted_at, "leg": leg, "event": event, "side": side,
           "ref_time": ref_time, "ref_price": ref_price, "shares": shares, "reason": reason,
           "bar_source": bar_source, "trade_id": trade_id, "size": size, "keel_size": keel_size}


# Exactly the docs/CLOUD_SIGNAL_REPAIR_20260914.md evidence table -- rows 8-12.
ITEM1_FIXTURE_ROWS = [
    _row("2026-09-14T00:55:21.008295-04:00", "NOISE_304", "SEED",
        reason="cold start: absorbed 3 historical trade(s) without emitting; open_at_seed=none"),
    _row("2026-09-14T00:55:22.286878-04:00", "NOISE_304", "ENTRY", side="long",
        ref_time="2026-09-03T09:40:00-04:00", ref_price="712.78", reason=""),
    _row("2026-09-14T00:55:23.555021-04:00", "NOISE_304", "EXIT", side="long",
        ref_time="2026-09-03T10:05:00-04:00", ref_price="711.275", reason="strategy_exit"),
    _row("2026-09-14T00:55:25.724420-04:00", "NOISE_304", "ENTRY", side="long",
        ref_time="2026-09-03T11:00:00-04:00", ref_price="713.5699", reason=""),
    _row("2026-09-14T09:31:00.324783-04:00", "NOISE_304", "EXIT", side="long",
        ref_time="2026-09-03T15:55:00-04:00", ref_price="717.61", reason="strategy_exit"),
]

# WEBULL_PAPER_TODO.md #4's evidence: the same NOISE_304 ENTRY signalled twice, ~0.65s apart.
ITEM4_TRADE_ID = "NOISE_304-20260921T134000Z-L"
ITEM4_FIXTURE_ROWS = [
    _row("2026-09-21T09:45:09.410000-04:00", "NOISE_304", "ENTRY", side="long",
        ref_time="2026-09-21T09:40:00-04:00", ref_price="729.81", reason="",
        trade_id=ITEM4_TRADE_ID),
    _row("2026-09-21T09:45:10.060000-04:00", "NOISE_304", "ENTRY", side="long",
        ref_time="2026-09-21T09:40:00-04:00", ref_price="729.81", reason="",
        trade_id=ITEM4_TRADE_ID),
]


def _filler_rows(n):
    return [_row(f"2026-08-{20 + i:02d}T09:30:00-04:00", "ORB_R6", "SEED",
                reason=f"cold start: absorbed {i} historical trade(s) without emitting; "
                       f"open_at_seed=none")
           for i in range(n)]


def _write_signals(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def _base_state():
    return {
        "generated_at": "2026-09-24T16:00:00-04:00",
        "bar_source": {"5m": {"source": "webull"}},
        "legs": {
            "NOISE_304": {
                "seeded": True, "key_format": "trade_id_v1", "stale_skipped": 3,
                "trades": {
                    "NOISE_304-20260903T134000Z-L": {
                        "entry_time": "2026-09-03T09:40:00-04:00", "side": "long",
                        "entry_px": 712.78, "shares": 140, "exit_emitted": True,
                        "exit_time": "2026-09-03T10:05:00-04:00", "exit_px": 711.275},
                    "NOISE_304-20260903T150000Z-L": {
                        "entry_time": "2026-09-03T11:00:00-04:00", "side": "long",
                        "entry_px": 713.5699, "shares": 140, "exit_emitted": True,
                        "exit_time": "2026-09-03T15:55:00-04:00", "exit_px": 717.61},
                },
            },
            "ORB_R6": {"seeded": True, "trades": {}, "stale_skipped": 28},
            "ENGUQ_335": {"seeded": True, "trades": {}, "stale_skipped": 1},
        },
    }


@pytest.fixture
def home(tmp_path):
    """A temp EDGELOG_HOME whose cloud_signal/signals.csv + state.json reproduce the live
    layout both docs describe: 7 filler rows, then rows 8-12 (item 1), then the last-two-rows
    duplicate (item 4)."""
    h = tmp_path / "edgelog_home"
    paths = cs._paths(home=str(h))
    rows = _filler_rows(7) + ITEM1_FIXTURE_ROWS + ITEM4_FIXTURE_ROWS
    _write_signals(paths["signals_path"], cs.SIGNAL_COLS, rows)
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        json.dump(_base_state(), f, indent=2)
    return paths


def _read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_state(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 1. dry run writes nothing ───────────────────────────────────────────────────────────────
def test_dry_run_writes_nothing(home):
    sig_before = open(home["signals_path"], "rb").read()
    state_before = open(home["state_path"], "rb").read()
    out = []
    rc = R.run_repair(home=home["home"], apply_=False, now=SAFE_NOW, log=out.append)
    text = "\n".join(out)

    assert rc == 0
    assert open(home["signals_path"], "rb").read() == sig_before, "dry run must not touch signals.csv"
    assert open(home["state_path"], "rb").read() == state_before, "dry run must not touch state.json"
    assert not os.path.exists(home["signals_path"] + R.BACKUP_SUFFIX)
    assert not os.path.exists(home["state_path"] + R.BACKUP_SUFFIX)
    assert not os.path.exists(os.path.join(home["state_dir"], "corrections.log"))

    # exactly rows 8-12 and the one legs.NOISE_304 key, per WEBULL_PAPER_TODO.md item 1 step 3
    for n in (8, 9, 10, 11, 12):
        assert f"row {n} " in text, f"dry run must list row {n}"
    assert "legs.NOISE_304" in text
    # the item-4 duplicate (row 14) and its confirmation check
    assert "row 14 " in text
    assert "item 4 check: confirmed" in text
    assert "DRY RUN" in text


# ── 2. apply relabels exactly those rows and writes backups ────────────────────────────────
def test_apply_relabels_exactly_and_writes_backups(home):
    out = []
    rc = R.run_repair(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 0, "\n".join(out)

    sig_bak = home["signals_path"] + R.BACKUP_SUFFIX
    st_bak = home["state_path"] + R.BACKUP_SUFFIX
    assert os.path.exists(sig_bak) and os.path.exists(st_bak)

    rows = _read_rows(home["signals_path"])
    bak_rows = _read_rows(sig_bak)
    assert len(rows) == len(bak_rows) == 14, "same row count as the backup -- never delete a row"

    # rows 8-12 (index 7-11) -> VOID_*, reason prefixed, nothing else on those rows changed
    assert [rows[i]["event"] for i in range(7, 12)] == [
        "VOID_SEED", "VOID_ENTRY", "VOID_EXIT", "VOID_ENTRY", "VOID_EXIT"]
    for i in range(7, 11):
        assert rows[i]["reason"].startswith("void 20260914: written into the live ledger")
    assert rows[11]["reason"].startswith("void 20260914: live EXIT of the replay's")
    for i in range(7, 12):
        for col in cs.SIGNAL_COLS:
            if col in ("event", "reason"):
                continue
            assert rows[i][col] == bak_rows[i][col], f"row {i+1} field {col} must be untouched"

    # item 4: the LATER of the two duplicate ENTRY rows is voided, the earlier one kept live
    assert rows[12]["event"] == "ENTRY" and rows[12]["emitted_at"] == ITEM4_FIXTURE_ROWS[0]["emitted_at"]
    assert rows[13]["event"] == "VOID_ENTRY" and rows[13]["emitted_at"] == ITEM4_FIXTURE_ROWS[1]["emitted_at"]
    assert rows[13]["reason"].startswith("void 20260921: duplicate signal")

    # every OTHER row is byte-identical to the backup, whole-row
    for i in range(len(rows)):
        if i in (7, 8, 9, 10, 11, 13):
            continue
        assert rows[i] == bak_rows[i], f"row {i+1} must be byte-identical to the backup"

    state = _read_state(home["state_path"])
    assert "NOISE_304" not in state["legs"], "legs.NOISE_304 must be removed"
    assert "20260914_replay_contamination" in state["repairs"]
    assert "20260921_duplicate_entry" in state["repairs"]
    bak_state = _read_state(st_bak)
    assert state["legs"]["ORB_R6"] == bak_state["legs"]["ORB_R6"], "ORB_R6 must be untouched"
    assert state["legs"]["ENGUQ_335"] == bak_state["legs"]["ENGUQ_335"], "ENGUQ_335 must be untouched"

    corr_log = os.path.join(home["state_dir"], "corrections.log")
    assert os.path.exists(corr_log)
    log_text = open(corr_log, encoding="utf-8").read()
    assert "item 1" in log_text and "item 4" in log_text
    assert "NOISE_304-20260903T134000Z-L" in log_text, "the removed leg object must be logged verbatim"


# ── 3. a mismatch refuses ───────────────────────────────────────────────────────────────────
def test_mismatch_refuses(home):
    rows = _read_rows(home["signals_path"])
    rows[8]["ref_price"] = "999.99"          # row 9 (index 8) no longer matches the spec
    _write_signals(home["signals_path"], cs.SIGNAL_COLS, rows)
    sig_before = open(home["signals_path"], "rb").read()
    state_before = open(home["state_path"], "rb").read()

    out = []
    rc = R.run_repair(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)

    assert rc != 0
    assert "REFUSED" in "\n".join(out)
    assert open(home["signals_path"], "rb").read() == sig_before
    assert open(home["state_path"], "rb").read() == state_before
    assert not os.path.exists(home["signals_path"] + R.BACKUP_SUFFIX)
    assert not os.path.exists(home["state_path"] + R.BACKUP_SUFFIX)


def test_state_mismatch_refuses(home):
    """legs.NOISE_304 missing from state.json while the rows are still original -- a mixture
    the spec says a human must look at, never guessed past."""
    state = _read_state(home["state_path"])
    del state["legs"]["NOISE_304"]
    with open(home["state_path"], "w", encoding="utf-8") as f:
        json.dump(state, f)

    out = []
    rc = R.run_repair(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc != 0
    assert "REFUSED" in "\n".join(out)
    assert not os.path.exists(home["signals_path"] + R.BACKUP_SUFFIX)


def test_item4_extra_damage_refuses(home):
    """A third row matching the duplicate's identity -- section 4's 'only damage' check must
    catch this and refuse, even though rows 8-12 and the pair's own shape still look fine."""
    rows = _read_rows(home["signals_path"])
    extra = dict(ITEM4_FIXTURE_ROWS[1])
    extra["emitted_at"] = "2026-09-21T09:45:10.900000-04:00"
    rows.append(extra)
    _write_signals(home["signals_path"], cs.SIGNAL_COLS, rows)

    out = []
    rc = R.run_repair(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc != 0
    text = "\n".join(out)
    assert "REFUSED" in text
    assert not os.path.exists(home["signals_path"] + R.BACKUP_SUFFIX)


# ── 4. apply twice is a no-op the second time ───────────────────────────────────────────────
def test_apply_twice_is_a_noop(home):
    out1 = []
    rc1 = R.run_repair(home=home["home"], apply_=True, now=SAFE_NOW, log=out1.append)
    assert rc1 == 0

    sig_after_first = open(home["signals_path"], "rb").read()
    state_after_first = open(home["state_path"], "rb").read()
    corr_log = os.path.join(home["state_dir"], "corrections.log")
    log_after_first = open(corr_log, encoding="utf-8").read()
    bak_mtime = os.path.getmtime(home["signals_path"] + R.BACKUP_SUFFIX)

    out2 = []
    rc2 = R.run_repair(home=home["home"], apply_=True, now=LATER_SAFE_NOW, log=out2.append)
    assert rc2 == 0
    assert "nothing to repair" in "\n".join(out2)

    assert open(home["signals_path"], "rb").read() == sig_after_first
    assert open(home["state_path"], "rb").read() == state_after_first
    assert open(corr_log, encoding="utf-8").read() == log_after_first, "must not append twice"
    assert os.path.getmtime(home["signals_path"] + R.BACKUP_SUFFIX) == bak_mtime, "must not re-backup"

    # dry run after a full apply also reads as a no-op
    out3 = []
    assert R.run_repair(home=home["home"], apply_=False, now=LATER_SAFE_NOW, log=out3.append) == 0
    assert "nothing to repair" in "\n".join(out3)


# ── 5. the qqq_exec reader ignores the VOID rows (real parsing function) ───────────────────
def test_qqq_exec_reader_ignores_void_rows(home, monkeypatch):
    rc = R.run_repair(home=home["home"], apply_=True, now=SAFE_NOW, log=lambda *_: None)
    assert rc == 0

    monkeypatch.setattr(cs, "DEFAULT_PATHS", home)
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"

    # the adapter already consumed the 7 filler rows; rows 8-14 are new to it
    state = {"legs": {}, "engine_cursor": 7}
    kept_entry_emitted = datetime.fromisoformat(ITEM4_FIXTURE_ROWS[0]["emitted_at"])
    now = kept_entry_emitted + timedelta(seconds=5)   # well inside ENGINE_CONSUME_STALE_SEC
    events = qe._consume_engine_signals(state, cfg, now, log=lambda *_: None)

    assert state["engine_cursor"] == 14, "every row, void or not, must still be marked consumed"
    # none of the five voided 2026-09-14 rows, and none of the voided 2026-09-21 duplicate,
    # ever reach the adapter as an actionable event
    assert all(e["ref_time"] != "2026-09-03T09:40:00-04:00" for e in events)
    assert all(e["ref_time"] != "2026-09-03T15:55:00-04:00" for e in events)
    noise_921 = [e for e in events if e.get("trade_id") == ITEM4_TRADE_ID]
    assert len(noise_921) == 1, f"exactly the one kept ENTRY must reach the adapter, got {noise_921}"
    assert noise_921[0]["event"] == "ENTRY" and noise_921[0]["ref_price"] == pytest.approx(729.81)
