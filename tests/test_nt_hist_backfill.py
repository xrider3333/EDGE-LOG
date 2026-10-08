"""tools/nt_hist_backfill.py - the Python half of the EdgeLogHistFetch add-on (2026-10-08)."""
import os

from tools import nt_hist_backfill as H

HDR = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n"


def _row(t, vol, flow, rt):
    b = flow / 2
    return f"{t},1,1,1,1,{vol},0,{b},{b},{1 if flow else 0},{rt}\n"


def _capture(tmp_path, rows):
    d = tmp_path / "ohlc"
    d.mkdir(exist_ok=True)
    (d / "NQ_10s.csv").write_text(HDR + "".join(rows))
    (d / "ES_10s.csv").write_text(HDR)
    return d


def test_holes_groups_no_split_rows_into_runs(tmp_path):
    base = 1_790_000_000
    rows = [_row(base + 10 * i, 5, 10, 1) for i in range(5)]
    rows += [_row(base + 100 + 10 * i, 5, 0, 3) for i in range(30)]          # one hole of 30 rows
    rows += [_row(base + 1000 + 10 * i, 5, 10, 1) for i in range(5)]
    rows += [_row(base + 5000 + 10 * i, 0, 0, 3) for i in range(30)]         # no volume: not a hole
    d = _capture(tmp_path, rows)
    got = H.holes(str(d / "NQ_10s.csv"), base + 6000)
    assert got == [(base + 100, base + 390, 30)]


def test_queue_is_idempotent_and_names_the_front_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "EL", str(tmp_path))
    base = int(1_791_400_000)                                                  # 2026-10-07
    d = _capture(tmp_path, [_row(base + 10 * i, 5, 0, 3) for i in range(20)])
    made = H.queue(now_ts=base + 3600, ohlc_dir=str(d), log=lambda m: None)
    assert len(made) == 1
    req = H._read_req(os.path.join(H.qdir(), made[0] + ".req"))
    assert req["instrument"] == "NQ 12-26" and req["kind"] == "ticks10s" and req["sym"] == "NQ"
    assert H.queue(now_ts=base + 3600, ohlc_dir=str(d), log=lambda m: None) == []


def test_merge_runs_each_done_request_once(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "EL", str(tmp_path))
    os.makedirs(H.qdir())
    out = tmp_path / "side.csv"
    out.write_text(HDR)
    with open(os.path.join(H.qdir(), "NQ_x_20.done"), "w") as f:
        f.write(f"instrument=NQ 12-26\nkind=ticks10s\nsym=NQ\nout={out}\n# result=done 3 rows\n")
    calls = []
    run = lambda argv: calls.append(argv) or 0
    assert H.merge(ohlc_dir=str(tmp_path), log=lambda m: None, run=run) == ["NQ_x_20"]
    assert calls[0][:2] == ["--master", os.path.join(str(tmp_path), "NQ_10s.csv")]
    assert H.merge(ohlc_dir=str(tmp_path), log=lambda m: None, run=run) == []
    assert len(calls) == 1
