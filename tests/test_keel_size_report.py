"""tests/test_keel_size_report.py -- tools/keel_size_report.py on a fixture day (MANAGER #76).

COVERS:
  1. A day from BEFORE the KEEL ENTRY EXTRAS deploy (the live ledger has no keel_* extra
     columns, no KEEL ENTRY log line): the branch is inferred from the state summary in
     effect AND the sizes -- below the shade line, KEEL's size equal to the fixed rule's is
     "fixed-only?" (shade needs a non-zero score; live #382's was 0 on the 10-05 state), a
     different one "shade?", none to compare "shade-line?" (never counted as fired); a
     state rebuilt since the day says "unknown" instead of guessing.
  2. A day AFTER it: the row's own keel_branch / keel_fixed_size win; a KEEL ENTRY log line
     (in a rotated .gz too) is read when the row has none.
  3. The offline recompute replays the leg's decision with the engine's own functions and
     gets the fixed-tilt size the engine computes at that entry bar; --rescore re-scores with
     the state in effect and names the branch the engine's own score took.
  4. The box pull is read-only (cat / grep / zcat / test only, BatchMode).
"""
import csv
import gzip
import json
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import api.cloud_signal as cs  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
from tools import keel_size_report as R  # noqa: E402

DAY = "2026-10-06"
OLD_COLS = cs.SIGNAL_COLS[:cs.SIGNAL_COLS.index("keel_branch")]     # before the deploy


def _write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _row(leg, hhmm, keel_size, **extra):
    t = f"{DAY}T{hhmm}:00-04:00"
    return dict({"emitted_at": t, "leg": leg, "event": "ENTRY", "side": "long",
                 "ref_time": t, "ref_price": 750.0, "shares": 133, "size": keel_size,
                 "keel_size": keel_size, "trade_id": f"{leg}-{hhmm}"}, **extra)


def _summary(home, leg, data_through, t_fast):
    d = os.path.join(home, "cloud_signal", "keel")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{leg}_v12_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"data_through": data_through, "t_fast_now": t_fast, "trust_now": 0.0,
                   "built_at": f"{data_through}T22:32:49+00:00"}, f)


def _home(tmp_path, data_through="2026-10-05"):
    home = str(tmp_path / "edgelog")
    f = R.home_files(home)
    _write_csv(f["live_signals"], OLD_COLS, [
        _row("NOISE_382", "10:05", 0.62),
        _row("NOISE_382", "11:30", 1.5),
        _row("ORB_R6", "10:35", 1.0),
        dict(_row("NOISE_382", "10:05", 0.62), event="EXIT"),
        _row("NOISE_382", "10:05", 1.0) | {"ref_time": "2026-10-05T10:05:00-04:00"},
    ])
    _write_csv(f["shadow_signals"], cs.SIGNAL_COLS, [
        _row("NOISE_422_KEEL", "10:05", 0.75, keel_branch="shade", keel_fixed_size=1.0,
             keel_t_fast=-1.23, keel_trust=0.0, keel_score=0.25),
        _row("NOISE_422_FIXED", "10:05", 1.0),
        _row("NOISE_422_PLAIN", "10:05", ""),
    ])
    _summary(home, "NOISE_382", data_through, -1.33)
    _summary(home, "NOISE_422_KEEL", data_through, -1.23)
    return home


# ── 1. before the deploy ─────────────────────────────────────────────────────────────────
def test_before_the_deploy_never_calls_shade_from_the_state_alone(tmp_path):
    """Below the shade line with no fixed size to compare: 'shade-line?', not fired."""
    home = _home(tmp_path)
    rows, summaries, line = R.build_report(home, DAY, recompute=False)
    by = {(r["leg"], r["time"][11:16]): r for r in rows}
    assert set(by) == {("NOISE_382", "10:05"), ("NOISE_382", "11:30"),
                       ("NOISE_422_KEEL", "10:05"), ("NOISE_422_FIXED", "10:05")}
    live = by[("NOISE_382", "10:05")]
    assert live["branch"] == "shade-line?" and live["src"] == "state"
    assert by[("NOISE_382", "11:30")]["branch"] == "shade-line?"
    assert live["t_fast"] == pytest.approx(-1.33) and live["keel_size"] == pytest.approx(0.62)
    shadow = by[("NOISE_422_KEEL", "10:05")]
    assert shadow["branch"] == "shade" and shadow["src"] == "row"
    assert shadow["fixed_logged"] == pytest.approx(1.0)
    assert by[("NOISE_422_FIXED", "10:05")]["branch"] == "fixed-leg"
    # review 10-05: a fixed-mode leg's used size IS the fixed rule's size
    assert by[("NOISE_422_FIXED", "10:05")]["fixed_logged"] == pytest.approx(1.0)
    assert line.startswith(f"{DAY} NOISE_382: shade branch fired on 0 of 2 entries")
    assert "inferred" in line
    assert "2 below the shade line with no fixed size" in line
    assert "shade on 1 of 1" in line
    text = R.format_report(rows, summaries, line, DAY)
    assert "VERDICT:" in text and "in effect on" in text and "NOISE_382" in text


def test_below_the_shade_line_the_sizes_decide_shade_or_fixed_only(tmp_path):
    """The 10-06 case: the state in effect is below the line (t_fast -1.33) but live #382's
    model score is 0, so KEEL's size equals the fixed rule's -- 'fixed-only?', and the verdict
    must not say shade fired. A size that differs is 'shade?'."""
    home = _home(tmp_path)
    f = R.home_files(home)
    _write_csv(f["live_signals"], cs.SIGNAL_COLS, [
        _row("NOISE_382", "10:05", 1.0, keel_fixed_size=1.0),
        _row("NOISE_382", "11:30", 1.5, keel_fixed_size=1.5),
    ])
    rows, _s, line = R.build_report(home, DAY, recompute=False)
    br = {r["time"][11:16]: r["branch"] for r in rows if r["leg"] == "NOISE_382"}
    assert br == {"10:05": "fixed-only?", "11:30": "fixed-only?"}
    assert line.startswith(f"{DAY} NOISE_382: shade branch fired on 0 of 2 entries")
    assert "KEEL sized every entry the same as the fixed rule would" in line
    assert "below the shade line with no fixed size" not in line

    _write_csv(f["live_signals"], cs.SIGNAL_COLS, [
        _row("NOISE_382", "10:05", 1.0, keel_fixed_size=1.0),
        _row("NOISE_382", "11:30", 0.62, keel_fixed_size=1.5),
    ])
    rows, _s, line = R.build_report(home, DAY, recompute=False)
    br = {r["time"][11:16]: r["branch"] for r in rows if r["leg"] == "NOISE_382"}
    assert br == {"10:05": "fixed-only?", "11:30": "shade?"}
    assert "shade branch fired on 1 of 2" in line
    assert "KEEL sized 0.62 where the fixed rule would size 1.5" in line


def test_a_state_rebuilt_since_the_day_is_not_guessed_from(tmp_path):
    home = _home(tmp_path, data_through=DAY)
    rows, _s, line = R.build_report(home, DAY, recompute=False)
    live = [r for r in rows if r["leg"] == "NOISE_382"]
    assert all(r["branch"] == "unknown" and "rebuilt since" in r["note"] for r in live)
    assert "branch not known on 2" in line


def test_shade_line_not_crossed_reads_fixed_only_or_trust_by_the_sizes(tmp_path):
    home = _home(tmp_path)
    _summary(home, "NOISE_382", "2026-10-05", 0.2)              # above the -0.5 line
    f = R.home_files(home)
    _write_csv(f["live_signals"], cs.SIGNAL_COLS, [
        _row("NOISE_382", "10:05", 1.5, keel_fixed_size=1.5),
        _row("NOISE_382", "11:30", 1.2, keel_fixed_size=1.0),
    ])
    rows, _s, line = R.build_report(home, DAY, recompute=False)
    br = {r["time"][11:16]: r["branch"] for r in rows if r["leg"] == "NOISE_382"}
    assert br == {"10:05": "fixed-only?", "11:30": "trust?"}
    assert "fired on 0 of 2" in line and "KEEL sized 1.2 where the fixed rule would size 1" in line


# ── 2. after the deploy: the log line ────────────────────────────────────────────────────
def test_reads_keel_entry_log_lines_from_rotated_gz_logs(tmp_path):
    home = _home(tmp_path, data_through=DAY)
    logs = R.home_files(home)["logs_dir"]
    os.makedirs(logs, exist_ok=True)
    ev = {"leg": "NOISE_382", "ref_time": f"{DAY}T10:05:00-04:00", "side": "long",
          "keel_size": 0.62, "keel_fixed_size": 1.5, "keel_branch": "shade",
          "keel_t_fast": -1.33, "keel_trust": 0.0, "keel_score": 0.38, "size": 0.62,
          "trade_id": "NOISE_382-x"}
    with gzip.open(os.path.join(logs, "cloud_signal.log.2.gz"), "wt", encoding="utf-8") as f:
        f.write("[cloud-signal] something else\n" + cs.keel_entry_log_line(ev) + " DIFFERS\n")
    rows, _s, line = R.build_report(home, DAY, recompute=False)
    r = [x for x in rows if x["leg"] == "NOISE_382" and x["time"].endswith("10:05:00-04:00")][0]
    assert r["src"] == "log" and r["branch"] == "shade"
    assert r["t_fast"] == pytest.approx(-1.33) and r["score"] == pytest.approx(0.38)
    assert r["fixed_logged"] == pytest.approx(1.5)
    assert "KEEL sized 0.62 where the fixed rule would size 1.5" in line


# ── 3. the offline recompute + rescore, on a stub leg ────────────────────────────────────
def _stub_leg(keel_cfg):
    mod = types.ModuleType("keel_report_stub")
    mod.STRATEGY_NAME = "KEEL_REPORT_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        idx = pd.DatetimeIndex(index)
        n = len(closes)
        trades = [(i, min(i + 2, n - 1), float(closes[min(i + 2, n - 1)] - closes[i]), 1,
                   float(closes[i]))
                  for i in range(n) if idx[i].hour == 10 and idx[i].minute == 5]
        return {"trades": trades if return_trades else None, "num_trades": len(trades),
                "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "avg_pnl": 0, "wins": 0, "losses": 0}
    mod.run_backtest = run_backtest
    return {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 2,
            "keel": keel_cfg}


def _bars(home):
    rng = np.random.RandomState(5)
    rows, px = [], 700.0
    for day in ("2026-10-02", "2026-10-05", DAY):           # Fri, Mon, Tue
        base = pd.Timestamp(f"{day} 09:30:00", tz=cs.TZ)
        for i in range(78):
            t = base + pd.Timedelta(minutes=5 * i)
            o = px
            px += rng.normal(0, 0.6)
            rows.append({"time": int(t.tz_convert("UTC").timestamp()), "open": o,
                         "high": max(o, px) + 0.2, "low": min(o, px) - 0.2, "close": px,
                         "volume": 1000.0})
    d = R.home_files(home)["ohlc_dir"]
    os.makedirs(d, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(d, "QQQ_5m.csv"), index=False)
    return df


def test_recompute_and_rescore_match_the_engine_at_the_entry_bar(tmp_path, monkeypatch):
    from test_cloud_signal_keel_extras import _leaning_state, _base_state
    home = str(tmp_path / "edgelog")
    epoch_df = _bars(home)
    _a, state = _base_state()
    _a, lean = _leaning_state(float(state["t_fast_now"]) + 0.01)     # shade fires
    import joblib
    kd = R.home_files(home)["keel_dir"]
    os.makedirs(kd, exist_ok=True)
    joblib.dump(lean, os.path.join(kd, "NOISE_STUB_v12_state.joblib"))
    _summary(home, "NOISE_STUB", "2026-10-05", float(state["t_fast_now"]))
    live_cfg = {"version": "v12", "state_path": os.path.join(kd, "NOISE_STUB_v12_state.joblib"),
                "summary_path": os.path.join(kd, "NOISE_STUB_v12_summary.json")}
    cfg = _stub_leg(live_cfg)
    monkeypatch.setattr(R, "keel_legs", lambda: {"NOISE_STUB": (cfg, "live")})

    # what the engine computes for the 10:05 entry, decided when that bar closed
    now = pd.Timestamp(f"{DAY} 10:10:06", tz=cs.TZ).to_pydatetime()
    arrays = cs.closed_arrays(epoch_df, now, "5m", 2)
    trades = cs.run_leg_trades(cfg, arrays, leg_key="NOISE_STUB")
    t = [x for x in trades if x["entry_time"].startswith(f"{DAY}T10:05")][0]
    want_fixed, _ = cs._keel_fixed_size_for_entry({"version": "v12", "mode": "fixed"},
                                                  arrays, t["entry_bar"])
    want_ks, want_diag = cs._keel_size_for_entry(live_cfg, arrays, t["entry_bar"],
                                                 t["entry_time"])
    _write_csv(R.home_files(home)["live_signals"], OLD_COLS,
               [_row("NOISE_STUB", "10:05", want_ks)])

    rows, _s, line = R.build_report(home, DAY, rescore=True)
    assert len(rows) == 1
    r = rows[0]
    assert r["fixed_recomputed"] == pytest.approx(want_fixed)
    assert r["branch"] == "shade (rescored)" and r["src"] == "rescore"
    assert r["t_fast"] == pytest.approx(want_diag["t_fast"])
    assert r["score"] == pytest.approx(want_diag["z"])
    assert r["note"] == ""                                     # rescored size == the size used
    assert "shade branch fired on 1 of 1" in line

    # without --rescore: the same day is inferred from the summary AND the sizes -- the
    # shade branch really sized this entry away from the fixed rule, so "shade?"
    assert abs(want_ks - want_fixed) > R.SIZE_TOL, "fixture: shade must change the size"
    rows, _s, _l = R.build_report(home, DAY)
    assert rows[0]["branch"] == "shade?" and rows[0]["fixed_recomputed"] == pytest.approx(want_fixed)


def test_cli_rescores_by_default(monkeypatch, tmp_path):
    seen = []

    def fake_build(home, date, rescore=False, recompute=True, log=print):
        seen.append(rescore)
        return [], {}, f"{date}: no KEEL-sized NOISE entries."
    monkeypatch.setattr(R, "build_report", fake_build)
    home = str(tmp_path / "edgelog")
    assert R.main(["--date", DAY, "--home", home]) == 0
    assert R.main(["--date", DAY, "--home", home, "--no-rescore"]) == 0
    assert R.main(["--date", DAY, "--home", home, "--rescore"]) == 0
    assert seen == [True, False, True]


# ── 4. the box pull is read-only ─────────────────────────────────────────────────────────
def test_box_pull_only_reads(tmp_path):
    calls = []

    class Res:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake(cmd, **kw):
        calls.append(cmd)
        return Res()
    missing = R.pull_from_box(DAY, str(tmp_path / "pull"), rescore=True, run_cmd=fake)
    assert missing == []
    assert calls and all("BatchMode=yes" in c for c in calls)
    remote = " ".join(c[-1] for c in calls).replace("2>/dev/null", "")
    for word in (" rm ", " mv ", " cp ", ">", "sed -i", "tee ", "truncate", "chmod"):
        assert word not in remote, word
    assert "keel_size_diffs" not in remote
    assert "NOISE_382_v12_state.joblib" in remote and "NOISE_422_FIXED" not in remote
