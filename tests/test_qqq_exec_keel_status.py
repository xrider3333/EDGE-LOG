"""tests/test_qqq_exec_keel_status.py -- api/qqq_exec.py's _build_keel_status (item D,
2026-09-25): "trained through" must mean the DATA, not the last NQ #382 trade.

Before this fix, `trained_through` was always summary['last_nq_session'] -- the date
of the last NQ trade the KEEL state was fitted on (augur_engine/ml_keel.py's own
field). On a quiet day with no trade at all, the web tab kept showing an older date
even though the state's underlying data (tools/keel_live_state.py's nightly rebuild)
was fully current through today. Fixed by adding a separate 'data_through' field (the
ET date of the last BAR used -- see tests/test_keel_live_state.py) that
_build_keel_status now prefers, falling back to last_nq_session for an old summary
written before this fix shipped, and separately publishing 'last_trade_session' (never
dropped -- still meaningful on its own).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe          # noqa: E402
from api import cloud_signal as cs      # noqa: E402


def _write_summary(tmp_path, **fields):
    path = tmp_path / "summary.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fields, f)
    return str(path)


def _crown_legs(summary_path, version="v12"):
    return {
        "NOISE_382": {
            "strategy": "NOISE_1_8_CT304.py",
            "keel": {"version": version, "state_path": "unused.joblib",
                     "summary_path": summary_path},
        },
    }


def test_trained_through_prefers_data_through_over_last_nq_session(tmp_path, monkeypatch):
    summary_path = _write_summary(tmp_path, version="v12", n_trades=10,
                                  last_nq_session="2026-09-20", data_through="2026-09-24")
    monkeypatch.setattr(cs, "CROWN_LEGS", _crown_legs(summary_path))

    out = qe._build_keel_status(log=lambda *a, **k: None)

    assert out["NOISE"]["trained_through"] == "2026-09-24"
    assert out["NOISE"]["last_trade_session"] == "2026-09-20"
    assert out["NOISE"]["n_trades"] == 10
    assert out["NOISE"]["version"] == "v12"


def test_trained_through_falls_back_to_last_nq_session_for_an_old_summary(tmp_path, monkeypatch):
    """A summary written before item D shipped has no 'data_through' key at all."""
    summary_path = _write_summary(tmp_path, version="v12", n_trades=10,
                                  last_nq_session="2026-09-20")
    monkeypatch.setattr(cs, "CROWN_LEGS", _crown_legs(summary_path))

    out = qe._build_keel_status(log=lambda *a, **k: None)

    assert out["NOISE"]["trained_through"] == "2026-09-20"
    assert out["NOISE"]["last_trade_session"] == "2026-09-20"


def test_trained_through_falls_back_when_data_through_is_null(tmp_path, monkeypatch):
    """A summary that DOES have the key but with a null value (e.g. the ET-date
    lookup itself failed at build time, see tools/keel_live_state.py's build()) must
    fall back exactly like a missing key -- `or`, not a bare .get()."""
    summary_path = _write_summary(tmp_path, version="v12", n_trades=3,
                                  last_nq_session="2026-09-20", data_through=None)
    monkeypatch.setattr(cs, "CROWN_LEGS", _crown_legs(summary_path))

    out = qe._build_keel_status(log=lambda *a, **k: None)

    assert out["NOISE"]["trained_through"] == "2026-09-20"


def test_leg_without_keel_block_is_skipped(monkeypatch):
    monkeypatch.setattr(cs, "CROWN_LEGS", {"NOISE_382": {"strategy": "NOISE_1_8_CT304.py"}})
    out = qe._build_keel_status(log=lambda *a, **k: None)
    assert out == {}


def test_missing_summary_file_is_skipped_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "CROWN_LEGS", _crown_legs(str(tmp_path / "missing.json")))
    out = qe._build_keel_status(log=lambda *a, **k: None)
    assert out == {}


def test_no_crown_legs_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(cs, "CROWN_LEGS", {})
    assert qe._build_keel_status(log=lambda *a, **k: None) == {}
