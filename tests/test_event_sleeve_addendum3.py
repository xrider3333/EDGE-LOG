"""EVENT SLEEVE ADDENDUM 3 (tools/event_sleeve_shadow.py): equal YEARLY risk per part - the sizing arithmetic, the re-drawn
harm bar, `constants --addendum 3` (built from Addendum 1's frozen file), and forward's choice of constants (Addendum 3
required). Synthetic inputs only: no house data (the data-sha block is stubbed), no network."""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import event_sleeve_shadow as S  # noqa: E402

COUNTS = {"A": 621, "B": 79, "C": 209}
SCALES1 = {"A": 1.406090, "B": 0.232735, "C": 0.690612}
SD1 = {"A": 711.19, "B": 4296.73, "C": 1447.99}
DATA = {"treasury_auctions_raw.json": "a" * 64, "nonequity_close.csv": "b" * 64, "ES_daily_rth.csv (rebal_scan cache)": "c" * 64}


@pytest.fixture(autouse=True)
def _keep_sys_path(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))


def _a1_file(d, counts=COUNTS, scales=SCALES1):
    """An addendum1_constants.json shaped like the frozen one (the fields Addendum 3 and forward read)."""
    os.makedirs(str(d), exist_ok=True)
    doc = dict(addendum=1, parts={p: dict(n_trades=counts[p], sd_usd=SD1[p], scale=scales[p]) for p in S.PARTS},
               harm=dict(threshold_risk_units=-8.274938), data_sha256=dict(DATA))
    path = os.path.join(str(d), S.CONSTANTS_FILE)
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
    return path


# ------------------------------------------------------------------ the sizing rule
def test_frozen_inputs_are_addendum_1s_posted_values():
    assert S.ADD1_FROZEN == {p: (COUNTS[p], SCALES1[p]) for p in S.PARTS}
    assert S.ADDENDUM3_REQUIRED is True and S.CONSTANTS3_FILE == "addendum3_constants.json"


def test_addendum3_sizing_gives_equal_yearly_risk_and_keeps_the_pooled_risk():
    z = S.addendum3_sizing(COUNTS, SCALES1)
    years = S.wf_years()
    N = sum(COUNTS.values()) / years
    assert z["years"] == years and z["N"] == pytest.approx(N) and z["N"] == pytest.approx(S.pooled_rate(list(COUNTS.values())))
    assert z["R_pooled"] == pytest.approx(1000.0 * math.sqrt(N))                     # Addendum 1's pooled yearly risk
    assert z["R_part"] == pytest.approx(z["R_pooled"] / math.sqrt(3.0))
    for p in S.PARTS:
        n = COUNTS[p] / years
        assert z["n"][p] == pytest.approx(n)
        assert z["u"][p] == pytest.approx(z["R_part"] / math.sqrt(n))
        assert z["scale"][p] == pytest.approx(SCALES1[p] * z["u"][p] / 1000.0)
        assert z["scale"][p] == pytest.approx(z["u"][p] / (1000.0 / SCALES1[p]))   # = u_p / SD_p
        assert z["share"][p] == pytest.approx(1.0 / 3.0)
        assert z["yearly_risk"][p] == pytest.approx(z["R_part"])
        assert z["share_addendum1"][p] == pytest.approx(COUNTS[p] / 909.0)
    assert sum(z["n"][p] * z["u"][p] ** 2 for p in S.PARTS) == pytest.approx(z["R_pooled"] ** 2)
    # the frequent part trades smaller, the rare one bigger
    assert z["u"]["A"] < 1000.0 < z["u"]["C"] < z["u"]["B"]


def test_addendum3_sizing_with_equal_rates_is_addendum_1():
    z = S.addendum3_sizing({"A": 300, "B": 300, "C": 300}, SCALES1)
    for p in S.PARTS:
        assert z["u"][p] == pytest.approx(1000.0) and z["scale"][p] == pytest.approx(SCALES1[p])


# ------------------------------------------------------------------ the harm bar
def test_addendum3_harm_with_equal_rates_reduces_to_addendum_1s_draws():
    z = S.addendum3_sizing({"A": 300, "B": 300, "C": 300}, SCALES1)
    a3, s3 = S.harm_threshold_a3(z["n"], z["u"], z["R_pooled"])
    a1, s1 = S.harm_threshold(z["N"])
    assert a3 == pytest.approx(a1, abs=1e-9)
    for k in ("mean", "median", "sd", "p1", "p10"):
        assert s3[k] == pytest.approx(s1[k], abs=1e-9)


def test_addendum1_harm_bar_still_reproduces():
    thr, summ = S.harm_threshold(S.pooled_rate(list(COUNTS.values())))
    assert round(thr, 6) == -8.274938 and round(thr, 4) == -8.2749
    assert summ["p1"] == pytest.approx(-13.781790561193157) and summ["p10"] == pytest.approx(-5.596438912402769)


def test_addendum3_harm_is_deterministic_and_has_addendum_1s_mean():
    z = S.addendum3_sizing(COUNTS, SCALES1)
    a, sa = S.harm_threshold_a3(z["n"], z["u"], z["R_pooled"])
    b, sb = S.harm_threshold_a3(z["n"], z["u"], z["R_pooled"])
    assert a == b and sa == sb
    c, _ = S.harm_threshold_a3(z["n"], z["u"], z["R_pooled"], seed=S.HARM["seed"] + 1)
    assert c != a
    # the trade-weighted mean per trade is S / sqrt(N) risk units, as in Addendum 1
    assert sa["mean"] == pytest.approx(50 * 0.64 / math.sqrt(z["N"]), abs=0.15)
    assert -10.0 < a < -6.0 and sa["p1"] < a < sa["p10"]
    for p in S.PARTS:
        assert sa["trade_mix_probs"][p] == pytest.approx(COUNTS[p] / 909.0)
        assert sa["trade_mix_drawn"][p] == pytest.approx(COUNTS[p] / 909.0, abs=0.005)


def test_addendum3_harm_draw_order_is_as_documented():
    """Rebuild the bar by hand from one generator in the documented order: Sharpes, noise block, assignment uniforms."""
    z = S.addendum3_sizing(COUNTS, SCALES1)
    nd, nt = 500, 50
    rng = np.random.default_rng(7)
    sh = rng.normal(0.64, 0.30, size=nd)
    e = rng.standard_t(3.0, size=(nd, nt)) / math.sqrt(3.0)
    U = rng.random((nd, nt))
    nv = np.array([z["n"][p] for p in S.PARTS])
    cp = np.cumsum(nv / nv.sum())
    cp[-1] = 1.0
    k = np.searchsorted(cp, U, side="right")
    uv = np.array([z["u"][p] for p in S.PARTS])
    cum = (sh[:, None] * (z["R_pooled"] / (3.0 * nv))[k] + uv[k] * e).sum(axis=1) / 1000.0
    thr, summ = S.harm_threshold_a3(z["n"], z["u"], z["R_pooled"], n_draws=nd, seed=7)
    assert thr == pytest.approx(float(np.percentile(cum, 5.0)), abs=1e-12)
    assert summ["mean"] == pytest.approx(float(cum.mean()), abs=1e-12)


# ------------------------------------------------------------------ constants --addendum 3
def test_constants_a3_writes_its_file_from_addendum_1s(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(S, "data_shas", lambda: dict(DATA))
    a1 = _a1_file(tmp_path)
    a1_bytes = open(a1, "rb").read()
    doc = S.mode_constants_a3(out_dir=str(tmp_path))
    out = capsys.readouterr().out
    path = os.path.join(str(tmp_path), S.CONSTANTS3_FILE)
    assert os.path.exists(path) and open(a1, "rb").read() == a1_bytes            # Addendum 1's file is only read
    with open(path) as f:
        got = json.load(f)
    z = S.addendum3_sizing(COUNTS, SCALES1)
    thr, _ = S.harm_threshold_a3(z["n"], z["u"], z["R_pooled"])
    assert got["addendum"] == 3 and got["supersedes"]["sha256"] == S.sha256_file(a1)
    assert got["harm"]["threshold_risk_units"] == round(thr, 6) and got["harm"]["seed"] == 20261011
    assert got["data_sha256"] == DATA and got["data_sha256_same_as_addendum1"] is True
    for p in S.PARTS:
        assert got["parts"][p]["scale"] == round(z["scale"][p], 6)
        assert got["parts"][p]["u_usd"] == pytest.approx(z["u"][p])
        assert got["parts"][p]["yearly_risk_share"] == pytest.approx(1.0 / 3.0)
    assert got["risk"]["R_pooled_usd"] == pytest.approx(z["R_pooled"]) and got["risk"]["R_part_usd"] == pytest.approx(z["R_part"])
    assert doc["parts"] == got["parts"]
    assert "CLOSE threshold (5th percentile): %.4f" % thr in out and "written " in out
    # a second run leaves the frozen file alone
    before = open(path, "rb").read()
    S.mode_constants_a3(out_dir=str(tmp_path))
    assert "left unchanged" in capsys.readouterr().out and open(path, "rb").read() == before


def test_constants_a3_refuses_without_or_with_a_changed_addendum_1(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "data_shas", lambda: dict(DATA))
    with pytest.raises(SystemExit, match="Addendum 1"):
        S.mode_constants_a3(out_dir=str(tmp_path))
    _a1_file(tmp_path, scales=dict(SCALES1, B=0.2327))
    with pytest.raises(SystemExit, match="not Addendum 1's frozen file"):
        S.mode_constants_a3(out_dir=str(tmp_path))
    _a1_file(tmp_path, counts=dict(COUNTS, C=210))
    with pytest.raises(SystemExit, match="not Addendum 1's frozen file"):
        S.mode_constants_a3(out_dir=str(tmp_path))
    assert not os.path.exists(os.path.join(str(tmp_path), S.CONSTANTS3_FILE))


def test_cli_routes_addendum_3(monkeypatch):
    seen = []
    monkeypatch.setattr(S, "mode_constants", lambda force=False: seen.append(("a1", force)))
    monkeypatch.setattr(S, "mode_constants_a3", lambda force=False: seen.append(("a3", force)))
    assert S.main(["constants"]) == 0 and S.main(["constants", "--addendum", "3"]) == 0
    assert S.main(["constants", "--addendum", "3", "--force"]) == 0
    assert seen == [("a1", False), ("a3", False), ("a3", True)]


# ------------------------------------------------------------------ forward: which constants
def test_forward_constants_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "data_shas", lambda: dict(DATA))
    with pytest.raises(SystemExit, match="constants"):
        S.forward_constants(str(tmp_path))
    a1 = _a1_file(tmp_path)
    with pytest.raises(SystemExit, match="Addendum 3 sizing is required"):
        S.forward_constants(str(tmp_path))
    path, doc = S.forward_constants(str(tmp_path), required=False)               # the switch off: Addendum 1's file
    assert path == a1 and doc["addendum"] == 1
    S.mode_constants_a3(out_dir=str(tmp_path))
    path, doc = S.forward_constants(str(tmp_path))
    assert os.path.basename(path) == S.CONSTANTS3_FILE and doc["addendum"] == 3


def test_forward_refuses_on_addendum_1_constants_alone(tmp_path):
    _a1_file(tmp_path)
    with pytest.raises(SystemExit, match="addendum3_constants.json missing"):
        S.mode_forward("2026-10-14", out_dir=str(tmp_path))
    assert not os.path.exists(os.path.join(str(tmp_path), "forward_status.json"))


def test_forward_records_the_constants_file_and_sha(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(S, "data_shas", lambda: dict(DATA))
    _a1_file(tmp_path)
    S.mode_constants_a3(out_dir=str(tmp_path))
    capsys.readouterr()
    monkeypatch.setattr(S, "forward_feeds", lambda out_dir: {"yahoo": None, "auctions": None})
    monkeypatch.setattr(S, "part_plan", lambda p, feeds, since, out_dir, today: S._refused_plan("stub data", "stub refusal"))
    S.mode_forward("2026-10-14", out_dir=str(tmp_path))
    out = capsys.readouterr().out
    p3 = os.path.join(str(tmp_path), S.CONSTANTS3_FILE)
    sha = S.sha256_file(p3)
    with open(p3) as f:
        c3 = json.load(f)
    with open(os.path.join(str(tmp_path), "forward_status.json")) as f:
        st = json.load(f)
    assert st["constants_file"] == S.CONSTANTS3_FILE and st["constants_sha256"] == sha and st["constants_addendum"] == 3
    assert st["scales"] == {p: c3["parts"][p]["scale"] for p in S.PARTS}
    assert st["harm_threshold_risk_units"] == c3["harm"]["threshold_risk_units"]
    assert "constants: %s (addendum 3) sha256 %s" % (S.CONSTANTS3_FILE, sha) in out
    assert all(st["parts"][p]["status"] == "REFUSED" for p in S.PARTS)
    T = pd.read_csv(os.path.join(str(tmp_path), "forward_trades.csv"))
    assert len(T) == 0
