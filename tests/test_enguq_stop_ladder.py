"""NT8 paper stop ladder (stop-loss overlay row 6, 2026-10-31).

augur_strategies/ENGUQ_1M_ETH_R2_1_0.py gains a runtime-only `return_levels` keyword: with
return_trades=True the result carries out["levels"], one row per trade (ORB_3_6.py's
_levels_row shape) plus "steps" -- the initial stop, then every bar the stop MOVED (breakeven,
trail), capped at _LEVELS_MAX_STEPS. api/paper.py's run_shadow asks every file that names the
keyword for it and _extract_trades hangs stop_px / target_px / stops [{t, px, reason}] on the
trade; _emit writes them to the paper_trades doc and api/paper_bundle.py carries them to the
board.

Coverage:
  1. inert: the result with return_levels (interpreted walk) is byte-identical to the
     interpreted walk without it, and within the compiled-vs-interpreted parity tolerance of
     the compiled default (tests/test_fastloop_parity.py's own bar).
  2. the ladder: first step = initial stop = entry - stop_mult x risk; stops never move down;
     a breakeven step sits at the entry; the cap keeps the first and the last step.
  3. paper: _extract_trades attaches the three keys from an aligned levels list and nothing
     when the file logs no stop; misaligned levels attach nothing; the bundle keeps them.
"""
import importlib.util
import os
import pickle

import pytest

from augur_engine.engine import run_backtest
from augur_engine import fastloop
import api.paper as paper
import api.paper_bundle as pb

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")

FN = "ENGUQ_1M_ETH_R2_1_0.py"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parity_fixture():
    """tests/test_fastloop_parity.py's own tape and cases (tests/ is not a package)."""
    spec = importlib.util.spec_from_file_location("_fastloop_parity_fx", os.path.join(ROOT, "tests", "test_fastloop_parity.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._bars, m.CASES


_bars, CASES = _parity_fixture()
PARAMS = [p for f, p in CASES if f == FN]


def _run(params, arrays, **extra):
    return run_backtest(FN, arrays=arrays, params=dict(params, **extra), cost_pts=0.0,
                        return_trades=True)


def _blob(res):
    res = dict(res or {})
    res.pop("levels", None)
    return pickle.dumps(res)


def _cap():
    spec = importlib.util.spec_from_file_location("_enguq_r2_cap", os.path.join(ROOT, "augur_strategies", FN))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._LEVELS_MAX_STEPS


# ── 1. inert ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("params", PARAMS)
def test_return_levels_is_byte_identical_to_the_interpreted_walk(params):
    arrays = _bars()
    os.environ["EDGELOG_NO_FASTLOOP"] = "1"
    try:
        slow = _run(params, arrays)
    finally:
        os.environ.pop("EDGELOG_NO_FASTLOOP", None)
    with_levels = _run(params, arrays, return_levels=True)
    assert slow and len(slow["trades"]) > 5
    assert _blob(slow) == _blob(with_levels)
    assert "levels" not in slow and len(with_levels["levels"]) == len(with_levels["trades"])


@pytest.mark.skipif(not fastloop.HAVE_NUMBA, reason="numba not installed")
@pytest.mark.parametrize("params", PARAMS)
def test_return_levels_matches_the_compiled_default_within_parity(params):
    arrays = _bars()
    fast = _run(params, arrays)
    lv = _run(params, arrays, return_levels=True)
    assert len(fast["trades"]) == len(lv["trades"])
    for a, b in zip(fast["trades"], lv["trades"]):
        assert int(a[0]) == int(b[0]) and int(a[1]) == int(b[1])
        assert abs(float(a[2]) - float(b[2])) < 1e-12 and abs(float(a[4]) - float(b[4])) < 1e-12


# ── 2. the ladder ────────────────────────────────────────────────────────────────────────
def test_ladder_starts_at_the_initial_stop_and_only_ever_rises():
    arrays = _bars()
    params = PARAMS[0]
    cap = _cap()
    r = _run(params, arrays, return_levels=True)
    rows = r["levels"]
    assert rows and all(isinstance(x, dict) for x in rows)
    saw_be = saw_trail = False
    for t, lv in zip(r["trades"], rows):
        assert lv["entry_bar"] == int(t[0]) and lv["side"] == 1 and lv["entry"] == float(t[4])
        assert lv["target"] is None and lv["trail"] is True and lv["partial"] is False
        assert lv["stop"] == pytest.approx(lv["entry"] - params["stop_mult"] * lv["risk"])
        steps = lv["steps"]
        assert steps[0] == {"bar": lv["entry_bar"], "px": lv["stop"], "reason": "initial"}
        assert len(steps) <= cap
        pxs = [s["px"] for s in steps]
        assert pxs == sorted(pxs), "a long's stop never moves down"
        bars = [s["bar"] for s in steps]
        assert bars == sorted(bars) and all(int(t[0]) < b <= int(t[1]) for b in bars[1:])
        for s in steps[1:]:
            assert s["reason"] in ("breakeven", "trail")
            if s["reason"] == "breakeven":
                saw_be = True
                assert s["px"] == pytest.approx(lv["entry"])
                assert lv["be_bar"] is not None and lv["be_bar"] <= s["bar"]
            else:
                saw_trail = True
        if lv.get("steps_dropped"):
            assert len(steps) == cap
    assert saw_be and saw_trail, "the fixture must exercise both kinds of move"


# ── 3. paper ─────────────────────────────────────────────────────────────────────────────
def _leg():
    return {"key": "ENGUQ_335", "strategy": FN, "instrument": "NQ", "timeframe": "1m",
            "session": "eth", "mult": 20.0}


def test_extract_trades_attaches_the_ladder_only_where_the_engine_logged_one():
    arrays = _bars()
    r = _run(PARAMS[0], arrays, return_levels=True)
    raw = r["trades"]
    levels = paper._levels_by_entry(r, raw)
    assert set(levels) == {int(t[0]) for t, lv in zip(raw, r["levels"]) if lv}
    trades = paper._extract_trades(_leg(), arrays, [(t, 1.0) for t in raw], levels=levels)
    assert trades and all("stops" in t for t in trades)
    t0, lv0 = trades[0], r["levels"][0]
    assert t0["stop_px"] == lv0["stop"] and t0["target_px"] is None
    assert t0["stops"][0]["px"] == lv0["stop"] and t0["stops"][0]["reason"] == "initial"
    assert t0["stops"][0]["t"] == t0["entry_dt"].isoformat()       # the entry bar's own time
    assert len(t0["stops"]) == len(lv0["steps"])
    # no levels -> no keys (an old file, or a misaligned list)
    plain = paper._extract_trades(_leg(), arrays, [(t, 1.0) for t in raw])
    assert all("stops" not in t and "stop_px" not in t for t in plain)
    assert paper._levels_by_entry({"levels": r["levels"][:-1]}, raw) == {}
    assert paper._levels_by_entry({}, raw) == {}


def test_paper_sees_the_keyword_on_the_files_that_name_it():
    assert paper._leg_accepts_return_levels(FN)
    assert paper._leg_accepts_return_levels("NOISE_1_0.py")
    assert paper._leg_accepts_return_levels("NOISE_1_1_NBHD.py")
    assert paper._leg_accepts_return_levels("NOISE_1_8_CT304H.py")
    assert not paper._leg_accepts_return_levels("NQDIP_1_1.py")       # no stop by design
    assert not paper._leg_accepts_return_levels("no_such_file.py")


def test_bundle_carries_the_ladder():
    doc = {"leg": "ENGUQ_335", "stop_px": 100.0, "target_px": None,
           "stops": [{"t": "2026-10-30T09:31:00-04:00", "px": 100.0, "reason": "initial"},
                     {"t": "2026-10-30T10:02:00-04:00", "px": 101.5, "reason": "breakeven"}]}
    row = pb.encode_row("pt_x", doc)
    back = dict(zip(pb.FIELDS, row))
    assert back["stop_px"] == 100.0 and back["stops"] == doc["stops"] and back["target_px"] is None
    assert back["id"] == "pt_x"
