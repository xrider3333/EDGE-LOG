"""ENGU-Q RTH r1 harness gate: the search space must be able to EXPRESS the cells it is
compared against, and every declared fence must be self-consistent.

Why this test exists, stated plainly because it has now caught the same defect three times:
an Auto-Validate walks an int or float knob as `min + step*k`. A setting that does not land on
that lattice can never be evaluated, so a round that compares its winner against such a cell is
comparing against something the search could not have found. Round 62 nearly shipped this.
STRATEGY-BEATING's review (#67, L1) caught it in the draft's `tl_len` and `atr_len`. And this
test caught it a THIRD time in `stop_mult`, because the draft and the review both checked the
crown FILE's defaults while run #335's own champion settings are different numbers - 1.2 is not
on a 0.25 lattice. Checking the file's defaults is not checking the run.

So this test pins BOTH reference cells:
  - the crown file's defaults (ENGUQ_1M_ETH_R2_1_0.py), which the parity run uses, and
  - run #335's saved champion settings, which are what the house means by "the crown".
"""
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTH = os.path.join(HERE, "augur_strategies", "ENGUQ_RTH_1_0.py")
R2 = os.path.join(HERE, "augur_strategies", "ENGUQ_1M_ETH_R2_1_0.py")

# Run #335's SAVED champion settings, read off the stored run doc
# (C:\EdgeLog\_anatomy_cache\runs\335.json -> best_params; data_source db_noadj_eth,
# 2010-06-07..2026-06-30, cost 0.533). Transcribed here so the test does not depend on a
# path outside the repo.
RUN335 = {
    "buf_atr": 0.4, "tl_len": 238, "trail_frac": 4.0, "ema_len": 1340, "atr_len": 28,
    "act_R": 2.5, "breakeven_R": 1.0, "limit_atr": 0.1, "er_len": 100, "stop_mult": 1.2,
    "regime_len": 5, "min_brk": 1.4, "vol_mult": 0.0, "er_th": 0.0,
}


def _load(path):
    spec = importlib.util.spec_from_file_location("s_" + os.path.basename(path), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rth():
    return _load(RTH)


@pytest.fixture(scope="module")
def r2():
    return _load(R2)


def _on_lattice(value, lo, hi, step):
    """True when value is reachable as lo + step*k, k a non-negative integer, within [lo, hi].

    Compared with a tolerance rather than for equality: the lattice is built by repeated float
    addition, so 0.5 + 0.1*11 is not exactly 1.6 in binary floating point.
    """
    if step in (None, 0):
        return lo <= value <= hi
    if not (lo - 1e-9 <= value <= hi + 1e-9):
        return False
    k = round((value - lo) / step)
    return k >= 0 and abs(lo + step * k - value) <= max(1e-9, abs(step) * 1e-6)


def test_every_default_is_on_its_own_lattice(rth):
    """A knob whose own default is unreachable is a fence that contradicts itself."""
    bad = []
    for name, spec in rth.DEFAULT_PARAMS.items():
        if spec.get("type") not in ("int", "float"):
            continue
        if not _on_lattice(spec["default"], spec["min"], spec["max"], spec.get("step")):
            bad.append((name, spec["default"], spec["min"], spec["max"], spec.get("step")))
    assert not bad, "defaults off their own lattice: %r" % (bad,)


@pytest.mark.parametrize("cell_name", ["crown_file_defaults", "run_335_champion"])
def test_reference_cells_are_reachable(rth, r2, cell_name):
    """The two cells this round is judged against must both be expressible by the search.

    This is the gate that matters: it is not enough for the new file to run: a comparison
    against a cell outside the lattice is a comparison the search could never have won or lost.
    """
    cell = ({k: v["default"] for k, v in r2.DEFAULT_PARAMS.items()}
            if cell_name == "crown_file_defaults" else RUN335)
    bad = []
    for name, value in cell.items():
        spec = rth.DEFAULT_PARAMS.get(name)
        assert spec is not None, "%s is missing from the RTH file entirely" % name
        if spec.get("type") not in ("int", "float"):
            continue
        if not _on_lattice(value, spec["min"], spec["max"], spec.get("step")):
            bad.append("%s=%s not on %s..%s step %s"
                       % (name, value, spec["min"], spec["max"], spec.get("step")))
    assert not bad, "%s unreachable: %s" % (cell_name, "; ".join(bad))


def test_the_two_nq_floors_are_searchable_and_hold_their_nq_values(rth):
    """L3: the floors that caused Q36's 308-against-1,194 trade count must be knobs, and their
    lattices must still contain the NQ values so parity is exact."""
    for name, nq_value in (("risk_floor", 0.50), ("atr_floor", 0.25)):
        spec = rth.DEFAULT_PARAMS.get(name)
        assert spec is not None, name + " is not exposed as a knob"
        assert spec["min"] == 0.0, name + " must reach 0 = off"
        assert _on_lattice(nq_value, spec["min"], spec["max"], spec["step"]), \
            "%s cannot reach its hard-coded NQ value %s" % (name, nq_value)
        assert spec["default"] == nq_value, \
            "%s default must be the NQ value so an unparameterised call is parity" % name


def test_the_efficiency_gate_threshold_is_searchable(rth):
    """L2: the gate reads `if float(er_th) > 0`, so at 0.0 er_len does nothing. The threshold
    has to be in the space or er_len is a dead knob being searched."""
    spec = rth.DEFAULT_PARAMS["er_th"]
    assert spec["max"] >= 0.5 and spec["min"] == 0.0
    assert spec["step"] <= 0.05


def test_regime_len_includes_off_and_one_session(rth):
    """Pin 1: ONE fence, 0..20 step 1 - it holds 0 = off and the crown's 10, and on a 390-bar
    tape each block is exactly one session."""
    spec = rth.DEFAULT_PARAMS["regime_len"]
    assert (spec["min"], spec["max"], spec["step"]) == (0, 20, 1)


def test_the_compiled_walk_is_not_reachable_from_this_file(rth):
    """The compiled transcription hard-codes BOTH floors and takes no parameter for either, so
    a compiled run would silently return NQ-floored trades whatever the search chose. The
    dispatch must be absent from the source, not merely unused."""
    src = open(RTH, encoding="utf-8").read()
    # the CALL, not the word - the file explains in a comment why the dispatch is gone
    msg = "the compiled dispatch is back; it ignores the new floors"
    assert "_fl.engu_walk(" not in src, msg
    assert "max(0.25, 0.5)" not in src, "a hard-coded NQ risk floor survived the patch"


def test_the_search_space_is_not_pinned(rth):
    """A file whose numeric knobs all have min == max records one config and the runner refuses
    it. The owner's rule is a FULL search space."""
    numeric = [s for s in rth.DEFAULT_PARAMS.values() if s.get("type") in ("int", "float")]
    assert numeric and any(s["min"] != s["max"] for s in numeric)
