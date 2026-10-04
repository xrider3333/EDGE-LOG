"""tools/repair_10s_from_replay.py - merging a Tick Replay sidecar into the 10s capture file.

Everything runs on synthetic CSVs under tmp_path; nothing under C:\\EdgeLog is read or written.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import repair_10s_from_replay as R  # noqa: E402

HEADER = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n"
T0 = 1_790_900_000          # a multiple of 10


def _row(i, vol=20, delta=0, buy=0, sell=0, ticks=0, rt=3, close=100.5):
    return f"{T0 + 10 * i},100,101,99,{close},{vol},{delta},{buy},{sell},{ticks},{rt}\n"


def _bar(dt_, *f):
    return str(T0 + dt_) + "," + ",".join(str(x) for x in f) + chr(10)


def _write(path, rows, header=HEADER, eol="\n"):
    data = header + "".join(rows)
    if eol != "\n":
        data = data.replace("\n", eol)
    with open(path, "wb") as fh:
        fh.write(data.encode())
    return path


def _lines(path):
    with open(path, "rb") as fh:
        return fh.read().decode().replace("\r\n", "\n").split("\n")[1:-1]


@pytest.fixture
def paths(tmp_path, monkeypatch):
    # the tool's production default must never be where a test points
    monkeypatch.setattr(R, "DEFAULT_OHLC_DIR", str(tmp_path / "ohlc"))
    d = tmp_path / "ohlc"
    (d / "replay").mkdir(parents=True)
    monkeypatch.setattr(R, "_hook_before_final_check", None)
    monkeypatch.setattr(R, "_hook_before_replace", None)
    return d / "NQ_10s.csv", d / "replay" / "NQ_10s_replay.csv", d / "_backups"


def _run(master, side, backups, **kw):
    s, bad = R.read_sidecar(str(side))
    return R.update_file(str(master), s, str(backups), sleep=lambda *_: None, **kw)


def test_repairs_rt3_and_zero_flow_and_leaves_rt0_1_2_alone(paths):
    master, side, backups = paths
    keep0 = _row(0, delta=4, buy=12, sell=8, ticks=15, rt=0)
    keep1 = _row(1, delta=-6, buy=7, sell=13, ticks=20, rt=1)
    keep2 = _row(2, delta=2, buy=11, sell=9, ticks=18, rt=2)
    _write(master, [keep0, keep1, keep2,
                    _row(3, rt=3),                       # no ticks, live
                    _row(4, rt=0),                       # history pass with Tick Replay off: zero flow
                    _row(5, rt=1)])                      # a flagged-live row that really carries zero flow
    # the sidecar disagrees with rows 0-2 on purpose: they must not move
    _write(side, [_row(0, delta=99, buy=99, sell=0, ticks=9, rt=4), _row(1, delta=99, buy=99, sell=0, ticks=9, rt=4),
                  _row(2, delta=99, buy=99, sell=0, ticks=9, rt=4),
                  _row(3, delta=6, buy=13, sell=7, ticks=21, rt=4),
                  _row(4, delta=-2, buy=9, sell=11, ticks=14, rt=4),
                  _row(5, delta=0, buy=10, sell=10, ticks=12, rt=4)])
    st = _run(master, side, backups)
    got = _lines(master)
    assert got[:3] == [keep0.strip(), keep1.strip(), keep2.strip()]
    assert got[3] == f"{T0 + 30},100,101,99,100.5,20,6,13,7,21,4"
    assert got[4] == f"{T0 + 40},100,101,99,100.5,20,-2,9,11,14,4"
    assert got[5].endswith(",0,10,10,12,4")
    assert st["repaired"] == 3 and st["skip_has_flow"] == 3 and st["wrote"]


def test_ohlcv_replaced_only_when_master_volume_is_zero(paths):
    master, side, backups = paths
    _write(master, [_bar(0, 1, 2, 0.5, 10.5, 0, 0, 0, 0, 0, 3), _bar(10, 100, 101, 99, 100.5, 20, 0, 0, 0, 0, 3)])
    _write(side, [_bar(0, 10, 11, 9, 10.5, 8, 2, 5, 3, 6, 4), _bar(10, 100, 101.5, 98, 100.5, 25, 1, 13, 12, 9, 4)])
    _run(master, side, backups)
    got = _lines(master)
    assert got[0] == f"{T0},10,11,9,10.5,8,2,5,3,6,4"            # empty master bar: replayed bar taken whole
    assert got[1] == f"{T0 + 10},100,101,99,100.5,20,1,13,12,9,4"  # real volume: master OHLCV kept, flow replaced


def test_price_mismatch_is_skipped(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3, close=100.5)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4, close=180.5)])      # another contract
    st = _run(master, side, backups)
    assert st["skip_price"] == 1 and st["repaired"] == 0 and not st["wrote"]
    assert _lines(master) == [_row(0, rt=3).strip()]


def test_sidecar_bar_without_ticks_repairs_nothing(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, rt=4)])
    st = _run(master, side, backups)
    assert st["skip_no_ticks"] == 1 and not st["wrote"]
    assert not backups.exists()                                    # no change -> no backup either


def test_inserts_missing_bars_in_time_order(paths):
    master, side, backups = paths
    a, d = _row(0, delta=1, buy=3, sell=2, ticks=4, rt=1), _row(3, delta=1, buy=3, sell=2, ticks=4, rt=1)
    _write(master, [a, d])
    _write(side, [_row(1, delta=2, buy=8, sell=6, ticks=9, rt=4),                 # traded, has ticks
                  _row(2, delta=0, rt=4),                                         # traded, replay saw no tick
                  f"{T0 + 25},100,101,99,100.5,0,0,0,0,0,4\n",                    # zero volume: a real zero
                  _row(4, delta=-1, buy=4, sell=5, ticks=6, rt=4)])               # after the master's last bar
    st = _run(master, side, backups)
    got = _lines(master)
    assert [int(x.split(",")[0]) for x in got] == [T0, T0 + 10, T0 + 20, T0 + 25, T0 + 30, T0 + 40]
    assert got[1].endswith(",2,8,6,9,4")
    assert got[2].endswith(",0,0,0,0,3")            # unknown flow stays flagged rt=3
    assert got[3].endswith(",0,0,0,0,4")
    assert got[0] == a.strip() and got[4] == d.strip()
    assert st["inserted"] == 4 and st["inserted_unknown_flow"] == 1


def test_never_deletes_and_keeps_malformed_lines(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3), "garbage,line\n", _row(1, delta=1, buy=3, sell=2, ticks=4, rt=1)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    before = _lines(master)
    _run(master, side, backups)
    after = _lines(master)
    assert len(after) == len(before)
    assert "garbage,line" in after and after[2] == before[2]


def test_idempotent_second_run_changes_nothing(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3), _row(2, rt=1, delta=1, buy=3, sell=2, ticks=4)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4), _row(1, delta=2, buy=8, sell=6, ticks=9, rt=4)])
    st1 = _run(master, side, backups)
    snap = master.read_bytes()
    st2 = _run(master, side, backups)
    assert st1["wrote"] and st1["repaired"] == 1 and st1["inserted"] == 1
    assert not st2["wrote"] and st2["repaired"] == 0 and st2["inserted"] == 0
    assert master.read_bytes() == snap


def test_dry_run_writes_nothing(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4), _row(1, delta=1, buy=2, sell=1, ticks=3, rt=4)])
    snap = master.read_bytes()
    st = _run(master, side, backups, dry_run=True)
    assert st["repaired"] == 1 and st["inserted"] == 1 and not st["wrote"]
    assert master.read_bytes() == snap and not backups.exists()
    assert not os.path.exists(str(master) + ".repair.tmp")


def test_backup_is_a_dated_copy_of_the_original(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    orig = master.read_bytes()
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    st = _run(master, side, backups)
    assert os.path.basename(st["backup"]).startswith("NQ_10s.csv.pre-repair-")
    assert open(st["backup"], "rb").read() == orig


def test_crlf_master_keeps_crlf(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)], eol="\r\n")
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4), _row(1, delta=1, buy=2, sell=1, ticks=3, rt=4)])
    _run(master, side, backups)
    raw = master.read_bytes()
    assert raw.count(b"\r\n") == 3 and raw.count(b"\n") == 3


def test_refuses_when_the_result_would_have_fewer_rows(paths, monkeypatch):
    master, side, backups = paths
    _write(master, [_row(0, rt=3), _row(1, rt=1, delta=1, buy=3, sell=2, ticks=4)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    snap = master.read_bytes()
    real = R.merge_bytes

    def lossy(raw, *a, **k):
        new, st = real(raw, *a, **k)
        return new.rsplit(b"\n", 2)[0] + b"\n", st            # drop the last row
    monkeypatch.setattr(R, "merge_bytes", lossy)
    with pytest.raises(R.Refused):
        _run(master, side, backups)
    assert master.read_bytes() == snap
    assert not os.path.exists(str(master) + ".repair.tmp")


def test_refuses_unsorted_master_and_runaway_insert(paths):
    master, side, backups = paths
    _write(master, [_row(2, rt=1, delta=1, buy=3, sell=2, ticks=4), _row(1, rt=1, delta=1, buy=3, sell=2, ticks=4)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    with pytest.raises(R.Refused):
        _run(master, side, backups)
    _write(master, [_row(0, rt=1, delta=1, buy=3, sell=2, ticks=4)])
    _write(side, [_row(i, delta=6, buy=13, sell=7, ticks=21, rt=4) for i in range(1, 6)])
    with pytest.raises(R.Refused):
        _run(master, side, backups, max_insert=3)


def test_row_appended_mid_merge_is_carried_over(paths, monkeypatch):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    late = _row(5, delta=1, buy=3, sell=2, ticks=4, rt=1)
    fired = []

    def append_once(path):
        if not fired:
            fired.append(1)
            with open(path, "ab") as fh:
                fh.write(late.encode())
    monkeypatch.setattr(R, "_hook_before_final_check", append_once)
    st = _run(master, side, backups)
    got = _lines(master)
    assert got[0].endswith(",6,13,7,21,4") and got[-1] == late.strip() and len(got) == 2
    assert st["wrote"]


def test_row_appended_after_the_last_check_is_healed(paths, monkeypatch):
    """The residual window: an append lands between the final check and os.replace."""
    if not hasattr(os, "link"):
        pytest.skip("no hard links")
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    lost = _row(5, delta=1, buy=3, sell=2, ticks=4, rt=1)
    newer = _row(6, delta=2, buy=4, sell=2, ticks=5, rt=1)
    fired = []

    def append_late(path):
        if not fired:
            fired.append(1)
            with open(path, "ab") as fh:
                fh.write(lost.encode())
    monkeypatch.setattr(R, "_hook_before_replace", append_late)
    st = _run(master, side, backups)
    # the indicator keeps appending to the NEW file afterwards
    with open(master, "ab") as fh:
        fh.write(newer.encode())
    got = _lines(master)
    assert got[0].endswith(",6,13,7,21,4")
    assert lost.strip() in got and newer.strip() in got
    assert [int(x.split(",")[0]) for x in got] == sorted(int(x.split(",")[0]) for x in got)
    assert st["healed"] == 1 and st.get("healed_ok")
    assert not os.path.exists(str(master) + ".premerge")


def test_a_locked_replace_waits_and_retries(paths, monkeypatch):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    real = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("sharing violation")
        return real(src, dst)
    monkeypatch.setattr(R.os, "replace", flaky)
    st = _run(master, side, backups)
    assert st["wrote"] and len(calls) == 2 and _lines(master)[0].endswith(",6,13,7,21,4")
    assert len(list(backups.glob("*"))) == 1                     # retries do not pile up backups


def test_bad_sidecar_header_is_rejected(paths):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    side.write_text("time,open\n1,2\n")
    with pytest.raises(R.BadInput):
        R.read_sidecar(str(side))


def test_summary_reports_counts_reach_and_et(paths):
    master, side, backups = paths
    t_edt = 1_790_900_000                                        # inside US daylight time
    _write(master, [f"{t_edt},100,101,99,100.5,20,0,0,0,0,3\n"])
    _write(side, [f"{t_edt - 10},100,101,99,100.5,20,1,3,2,4,4\n", f"{t_edt},100,101,99,100.5,20,6,13,7,21,4\n"])
    st = _run(master, side, backups)
    text = R.summarize("NQ", st, 0, False, str(side))
    assert "bars repaired: 1" in text and "bars inserted: 1" in text
    assert "reach (oldest sidecar bar): 2026-10-01" in text and " ET" in text
    assert R._et_str(1_790_900_000).endswith("ET")


def test_main_dry_run_on_copies_exits_zero_and_defaults_never_used(paths, capsys):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    snap = master.read_bytes()
    rc = R.main(["--sym", "NQ", "--ohlc-dir", str(master.parent), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0 and "DRY RUN" in out and "bars repaired: 1" in out
    assert master.read_bytes() == snap
    rc = R.main(["--sym", "ES", "--ohlc-dir", str(master.parent), "--dry-run"])      # no ES files
    assert rc == 3


def test_main_real_run_writes_and_second_run_is_a_noop(paths, capsys):
    master, side, backups = paths
    _write(master, [_row(0, rt=3)])
    _write(side, [_row(0, delta=6, buy=13, sell=7, ticks=21, rt=4)])
    assert R.main(["--sym", "NQ", "--ohlc-dir", str(master.parent)]) == 0
    assert _lines(master)[0].endswith(",6,13,7,21,4")
    capsys.readouterr()
    assert R.main(["--sym", "NQ", "--ohlc-dir", str(master.parent)]) == 0
    assert "nothing to change" in capsys.readouterr().out
