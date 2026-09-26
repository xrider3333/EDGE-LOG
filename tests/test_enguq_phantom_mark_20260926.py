"""tools/enguq_phantom_mark_20260926.py -- WEBULL_GO_LIVE.md 3.7 item 3 (mark, don't delete,
the two ENGU-Q ghost trades). Every fixture value below is the real evidence quoted in that
tool's own docstring (box signals.csv / state.json / qqq_exec trades.csv, read via read-only
ssh/scp, 2026-09-26). This test never touches the box, $EDGELOG_HOME or any live file -- every
run works on a temp-dir copy of the live layout (tests/conftest.py's live_system_guard blocks a
real write there regardless).
"""
import csv
import json
import os
import sys
from zoneinfo import ZoneInfo
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import cloud_signal as cs                                          # noqa: E402
import tools.enguq_phantom_mark_20260926 as M                                # noqa: E402

NY = ZoneInfo("America/New_York")
# Outside 09:25-16:05 ET on any weekday -- see api.qqq_exec._in_market_window.
SAFE_NOW = datetime(2026, 9, 26, 22, 0, tzinfo=NY)

GHOST1, GHOST2 = M.GHOSTS

EXEC_HEADER = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px", "pnl",
              "nq_pnl_points", "exit_reason", "trade_id", "size"]


def _signals_row(emitted_at, event, ref_time, ref_price, trade_id, shares=139, reason=""):
    return {"emitted_at": emitted_at, "leg": M.GHOST_LEG, "event": event, "side": "long",
           "ref_time": ref_time, "ref_price": ref_price, "shares": shares, "reason": reason,
           "bar_source": "webull", "trade_id": trade_id, "size": "", "keel_size": ""}


def _filler_signals_rows(n):
    return [_signals_row(f"2026-09-{10 + i:02d}T09:30:00-04:00", "SEED", "", "", "")
           for i in range(n)]


def _base_signals_rows():
    return _filler_signals_rows(5) + [
        _signals_row(GHOST1["signals_emitted_at"], "ENTRY", GHOST1["entry_time"],
                    str(GHOST1["entry_px"]), GHOST1["trade_id"], shares=GHOST1["shares"]),
        _signals_row("2026-09-17T15:10:45.282610-04:00", "ENTRY", "2026-09-17T15:09:00-04:00",
                    "716.7405", "ENGUQ_335-20260917T190900Z-L", shares=139),
    ] + _filler_signals_rows(3) + [
        _signals_row(GHOST2["signals_emitted_at"], "ENTRY", GHOST2["entry_time"],
                    str(GHOST2["entry_px"]), GHOST2["trade_id"], shares=GHOST2["shares"]),
    ]


def _base_state():
    return {
        "generated_at": "2026-09-25T20:00:00-04:00",
        "legs": {
            M.GHOST_LEG: {
                "seeded": True, "key_format": "trade_id_v1",
                "trades": {
                    GHOST1["trade_id"]: {
                        "entry_time": GHOST1["entry_time"], "side": "long",
                        "entry_px": GHOST1["entry_px"], "shares": GHOST1["shares"],
                        "exit_emitted": False, "exit_time": None, "exit_px": None,
                        "skipped": None,
                    },
                    "ENGUQ_335-20260917T190900Z-L": {
                        "entry_time": "2026-09-17T15:09:00-04:00", "side": "long",
                        "entry_px": 716.7405, "shares": 139, "exit_emitted": True,
                        "exit_time": "2026-09-18T10:02:00-04:00", "exit_px": 717.1887,
                    },
                    GHOST2["trade_id"]: {
                        "entry_time": GHOST2["entry_time"], "side": "long",
                        "entry_px": GHOST2["entry_px"], "shares": GHOST2["shares"],
                        "exit_emitted": False, "exit_time": None, "exit_px": None,
                        "skipped": None,
                    },
                },
            },
            "ORB_R6": {"seeded": True, "trades": {}},
        },
    }


def _exec_row(entry_ts, entry_px, exit_px, pnl, trade_id=""):
    return {"leg": M.EXEC_LEG, "entry_ts": entry_ts, "exit_ts": "2026-09-17 16:00:04",
           "side": "long", "shares": "10", "entry_px": str(entry_px), "exit_px": str(exit_px),
           "pnl": str(pnl), "nq_pnl_points": "", "exit_reason": "EOD", "trade_id": trade_id,
           "size": ""}


def _base_exec_rows():
    return [
        _exec_row("2026-09-16 09:31:00", 700.0, 701.0, "1.0"),                       # filler
        _exec_row(GHOST1["exec_entry_ts"], GHOST1["exec_entry_px"], "nan", "nan"),    # ghost 1
        _exec_row(GHOST2["exec_entry_ts"], GHOST2["exec_entry_px"], "740.89", "-2.35",
                 trade_id=GHOST2["trade_id"]),                                       # ghost 2
        _exec_row("2026-09-24 12:18:25", 739.3817, "741.345", "19.63"),              # filler
    ]


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "edgelog_home"
    paths = cs._paths(home=str(h))
    _write_csv(paths["signals_path"], cs.SIGNAL_COLS, _base_signals_rows())
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        json.dump(_base_state(), f, indent=2)
    exec_path = M._exec_trades_path(str(h))
    _write_csv(exec_path, EXEC_HEADER, _base_exec_rows())
    return {"home": str(h), "paths": paths, "exec_path": exec_path}


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """Finding 5: every --apply test below runs the tool's real psutil scan of THIS machine's
    processes. A real api.qqq_exec --serve/--once or cloud_signal --loop/--once/--live-paths
    process on the dev PC (or a sibling worktree) would make the --apply tests fail for a
    reason that has nothing to do with the tool under test. Default every test to a clean
    process list; test_apply_refuses_with_a_running_cloud_signal_process and
    test_apply_refuses_with_a_running_qqq_exec_process below override this per-test to prove
    the checks still work."""
    monkeypatch.setattr(M, "_running_live_writer_cmdlines", lambda: [])
    monkeypatch.setattr(M, "_running_qqq_exec_cmdlines", lambda: [])


def _read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_state(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 1. dry run writes nothing, but names both ghosts in all three files ────────────────────────
def test_dry_run_writes_nothing(home):
    sig_before = open(home["paths"]["signals_path"], "rb").read()
    state_before = open(home["paths"]["state_path"], "rb").read()
    exec_before = open(home["exec_path"], "rb").read()

    out = []
    rc = M.run_mark(home=home["home"], apply_=False, now=SAFE_NOW, log=out.append)
    text = "\n".join(out)

    assert rc == 0, text
    assert open(home["paths"]["signals_path"], "rb").read() == sig_before
    assert open(home["paths"]["state_path"], "rb").read() == state_before
    assert open(home["exec_path"], "rb").read() == exec_before
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)
    assert not os.path.exists(os.path.join(home["paths"]["state_dir"], "corrections.log"))
    for g in (GHOST1, GHOST2):
        assert g["trade_id"] in text
    assert "DRY RUN" in text


# ── 2. apply marks exactly the two ghosts, everything else byte-identical ─────────────────────
# EXEC_HEADER (above) has no 'note' column -- matching api/qqq_exec.py's real TRADE_COLS as of
# this writing (finding 3) -- so this tool must NOT write qqq_exec/trades.csv at all: it backs
# up and rewrites only signals.csv and state.json, and records the two exec rows' identity
# (leg, entry_ts, entry_px) in corrections.log instead of a note column.
def test_apply_marks_exactly_the_two_ghosts(home):
    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 0, "\n".join(out)

    sig_bak = home["paths"]["signals_path"] + M.BACKUP_SUFFIX
    st_bak = home["paths"]["state_path"] + M.BACKUP_SUFFIX
    exec_bak = home["exec_path"] + M.BACKUP_SUFFIX
    assert os.path.exists(sig_bak) and os.path.exists(st_bak)
    assert not os.path.exists(exec_bak), (
        "no note column exists -- trades.csv must never be backed up or written")

    rows = _read_rows(home["paths"]["signals_path"])
    bak_rows = _read_rows(sig_bak)
    assert len(rows) == len(bak_rows), "no row may ever be deleted"

    ghost_positions = {r["trade_id"]: i for i, r in enumerate(rows) if r["trade_id"] in
                       (GHOST1["trade_id"], GHOST2["trade_id"])}
    for g in (GHOST1, GHOST2):
        i = ghost_positions[g["trade_id"]]
        assert rows[i]["event"] == "VOID_ENTRY"
        assert rows[i]["reason"].startswith(M.GHOST_REASON)
        for col in cs.SIGNAL_COLS:
            if col in ("event", "reason"):
                continue
            assert rows[i][col] == bak_rows[i][col], f"{g['trade_id']} field {col} must be untouched"
    # the REAL trade that follows the first ghost must be completely unaffected
    real_row = next(r for r in rows if r["trade_id"] == "ENGUQ_335-20260917T190900Z-L")
    assert real_row["event"] == "ENTRY"
    # every other row is byte-identical to the backup
    for i in range(len(rows)):
        if i in ghost_positions.values():
            continue
        assert rows[i] == bak_rows[i], f"row {i} must be byte-identical to the backup"

    state = _read_state(home["paths"]["state_path"])
    bak_state = _read_state(st_bak)
    for g in (GHOST1, GHOST2):
        rec = state["legs"][M.GHOST_LEG]["trades"][g["trade_id"]]
        assert rec["ghost"] is True
        assert rec["ghost_reason"].startswith(M.GHOST_NOTE)
        # never fabricated: exit_emitted/exit_time/exit_px are exactly what they were
        assert rec["exit_emitted"] is False
        assert rec["exit_time"] is None and rec["exit_px"] is None
        assert rec["entry_px"] == g["entry_px"] and rec["shares"] == g["shares"]
    real_rec = state["legs"][M.GHOST_LEG]["trades"]["ENGUQ_335-20260917T190900Z-L"]
    assert real_rec == bak_state["legs"][M.GHOST_LEG]["trades"]["ENGUQ_335-20260917T190900Z-L"]
    assert state["legs"]["ORB_R6"] == bak_state["legs"]["ORB_R6"]
    assert M.MARKER_KEY in state["repairs"]

    # trades.csv itself is completely untouched, since it never had a note column to write
    # into (finding 3): no header change, same rows.
    exec_rows = _read_rows(home["exec_path"])
    assert "note" not in exec_rows[0].keys()
    assert exec_rows == _base_exec_rows(), "qqq_exec/trades.csv must be byte-for-byte untouched"

    corr_log = os.path.join(home["paths"]["state_dir"], "corrections.log")
    log_text = open(corr_log, encoding="utf-8").read()
    assert GHOST1["trade_id"] in log_text and GHOST2["trade_id"] in log_text
    # the exec rows' identity is recorded in the log in place of a note column
    assert GHOST1["exec_entry_ts"] in log_text and str(GHOST1["exec_entry_px"]) in log_text
    assert GHOST2["exec_entry_ts"] in log_text and str(GHOST2["exec_entry_px"]) in log_text
    assert "NOT written" in log_text


# ── 3. idempotent: applying twice changes nothing the second time ─────────────────────────────
def test_apply_twice_is_idempotent(home):
    out1 = []
    assert M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out1.append) == 0

    sig_after_1 = open(home["paths"]["signals_path"], "rb").read()
    state_after_1 = open(home["paths"]["state_path"], "rb").read()
    exec_after_1 = open(home["exec_path"], "rb").read()

    out2 = []
    rc2 = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out2.append)
    assert rc2 == 0
    assert "nothing to mark" in "\n".join(out2)
    assert open(home["paths"]["signals_path"], "rb").read() == sig_after_1
    assert open(home["paths"]["state_path"], "rb").read() == state_after_1
    assert open(home["exec_path"], "rb").read() == exec_after_1


# ── 4. a mismatch refuses and writes nothing ────────────────────────────────────────────────
def test_mismatch_refuses(home):
    rows = _read_rows(home["paths"]["signals_path"])
    for r in rows:
        if r["trade_id"] == GHOST1["trade_id"]:
            r["ref_price"] = "999.99"          # no longer matches the evidence
    _write_csv(home["paths"]["signals_path"], cs.SIGNAL_COLS, rows)
    sig_before = open(home["paths"]["signals_path"], "rb").read()
    state_before = open(home["paths"]["state_path"], "rb").read()

    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)

    assert rc != 0
    assert "REFUSED" in "\n".join(out)
    assert open(home["paths"]["signals_path"], "rb").read() == sig_before
    assert open(home["paths"]["state_path"], "rb").read() == state_before
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)


# ── 4b. an unparseable shares value classifies as a mismatch instead of crashing (finding 6) ───
def test_unparseable_shares_is_a_mismatch_not_a_crash(home):
    state = _read_state(home["paths"]["state_path"])
    state["legs"][M.GHOST_LEG]["trades"][GHOST1["trade_id"]]["shares"] = "one-thirty-nine"
    with open(home["paths"]["state_path"], "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    out = []
    rc = M.run_mark(home=home["home"], apply_=False, now=SAFE_NOW, log=out.append)
    assert rc == 2, "\n".join(out)
    assert "REFUSED" in "\n".join(out)


# ── 4c. a float-formatted shares value ("139.0") still matches -- int(float(...)), not a crash ─
def test_float_formatted_shares_still_matches(home):
    state = _read_state(home["paths"]["state_path"])
    state["legs"][M.GHOST_LEG]["trades"][GHOST1["trade_id"]]["shares"] = "139.0"
    with open(home["paths"]["state_path"], "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    out = []
    rc = M.run_mark(home=home["home"], apply_=False, now=SAFE_NOW, log=out.append)
    assert rc == 0, "\n".join(out)
    assert "state.json=match" in "\n".join(out)


# ── 5. inside market hours refuses --apply (dry run still fine) ───────────────────────────────
def test_apply_inside_market_hours_refuses(home):
    inside = datetime(2026, 9, 28, 10, 30, tzinfo=NY)   # a Monday, 10:30 ET
    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=inside, log=out.append)
    assert rc == 2
    assert "REFUSED" in "\n".join(out)
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)


# ── 6. a fresh live-writer heartbeat refuses --apply ───────────────────────────────────────────
def test_apply_refuses_with_a_fresh_heartbeat(home):
    # cs._live_writer_age_sec compares the heartbeat's ts against the REAL wall clock
    # (datetime.now), not against `now`/SAFE_NOW -- unlike qqq_exec's own state.json check in
    # test 9 below, which this tool judges against `now` itself via _qqq_exec_state_age_sec.
    # Stamping with SAFE_NOW (2026-09-26 22:00 ET) would read as "fresh" only until the real
    # clock passes SAFE_NOW + LIVE_WRITER_FRESH_SEC, after which this test would start failing
    # for a reason that has nothing to do with the tool (finding 1). Stamp with the real "now"
    # instead so the heartbeat is fresh by construction, on any day this test happens to run.
    hb_path = home["paths"]["heartbeat_path"]
    os.makedirs(os.path.dirname(hb_path), exist_ok=True)
    with open(hb_path, "w", encoding="utf-8") as f:
        json.dump({"ts": datetime.now(NY).isoformat(), "note": ""}, f)   # real "now" -- looks live

    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 2
    assert "REFUSED" in "\n".join(out)
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)


# ── 7. never deletes a row, never touches a P&L field, even mid-apply ─────────────────────────
def test_never_touches_pnl_fields(home):
    exec_before = _read_rows(home["exec_path"])
    out = []
    assert M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append) == 0
    exec_after = _read_rows(home["exec_path"])
    assert len(exec_after) == len(exec_before), "never delete a qqq_exec row"
    for before, after in zip(exec_before, exec_after):
        assert before["entry_px"] == after["entry_px"]
        assert before["exit_px"] == after["exit_px"]
        assert before["pnl"] == after["pnl"]


# ── 8. if trades.csv ALREADY has a note column (e.g. api/qqq_exec.py's TRADE_COLS grows one
#      later), the tool still writes it -- finding 3's fix only forbids ADDING the column ───────
def test_apply_writes_note_when_column_already_present(home, tmp_path):
    header_with_note = EXEC_HEADER + ["note"]
    _write_csv(home["exec_path"], header_with_note, _base_exec_rows())

    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 0, "\n".join(out)

    exec_bak = home["exec_path"] + M.BACKUP_SUFFIX
    assert os.path.exists(exec_bak), "a pre-existing note column IS backed up and written"
    rows = _read_rows(home["exec_path"])
    ghost1_row = next(r for r in rows if r["entry_ts"] == GHOST1["exec_entry_ts"])
    ghost2_row = next(r for r in rows if r["entry_ts"] == GHOST2["exec_entry_ts"])
    assert ghost1_row["note"].startswith(M.GHOST_NOTE)
    assert ghost2_row["note"].startswith(M.GHOST_NOTE)
    filler_rows = [r for r in rows if r["entry_ts"] not in
                  (GHOST1["exec_entry_ts"], GHOST2["exec_entry_ts"])]
    assert all(r.get("note", "") == "" for r in filler_rows)


# ── 9. edgelog-qqq-exec itself must also be idle before --apply (finding 4) ───────────────────
def test_apply_refuses_with_a_fresh_qqq_exec_state(home):
    """A concurrent qqq_exec write between this tool's read and its os.replace could lose a
    ledger row -- --apply must also refuse while edgelog-qqq-exec looks freshly active, not
    only while cloud_signal does. Freshness is judged against `now` (SAFE_NOW), NOT the real
    wall clock -- so the file's mtime is set relative to SAFE_NOW, exactly like the fixed
    heartbeat timestamps in test 6 above."""
    qe_state_path = os.path.join(os.path.dirname(home["exec_path"]), "state.json")
    with open(qe_state_path, "w", encoding="utf-8") as f:
        json.dump({"_last_tick_wall": None}, f)   # content is irrelevant -- mtime is the signal
    fresh = SAFE_NOW.timestamp() - 10   # 10s "old" relative to SAFE_NOW -- well inside FRESH_SEC
    os.utime(qe_state_path, (fresh, fresh))

    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 2
    assert "REFUSED" in "\n".join(out)
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)


def test_apply_allows_a_stale_qqq_exec_state(home):
    """A qqq_exec state.json that has not been touched recently (relative to SAFE_NOW) reads
    as stopped/idle -- apply proceeds exactly as before this fixture existed."""
    qe_state_path = os.path.join(os.path.dirname(home["exec_path"]), "state.json")
    with open(qe_state_path, "w", encoding="utf-8") as f:
        json.dump({"_last_tick_wall": None}, f)
    stale = SAFE_NOW.timestamp() - (cs.LIVE_WRITER_FRESH_SEC + 60)
    os.utime(qe_state_path, (stale, stale))

    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 0, "\n".join(out)


# ── 11. the process-scan guards themselves still refuse on a real hit (finding 5) ──────────────
def test_apply_refuses_with_a_running_cloud_signal_process(home, monkeypatch):
    monkeypatch.setattr(M, "_running_live_writer_cmdlines",
                        lambda: ["pid 4242: python -u -c 'from api.cloud_signal import "
                                "cloud_signal_thread; cloud_signal_thread()'"])
    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 2
    assert "REFUSED" in "\n".join(out)
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)


def test_apply_refuses_with_a_running_qqq_exec_process(home, monkeypatch):
    monkeypatch.setattr(M, "_running_qqq_exec_cmdlines",
                        lambda: ["pid 4343: python -m api.qqq_exec --serve"])
    out = []
    rc = M.run_mark(home=home["home"], apply_=True, now=SAFE_NOW, log=out.append)
    assert rc == 2
    assert "REFUSED" in "\n".join(out)
    assert not os.path.exists(home["paths"]["signals_path"] + M.BACKUP_SUFFIX)
