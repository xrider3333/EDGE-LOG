"""BOOK LOOKS r1 harness (tools/rocfrontier/r14_looks.py) - the accounting pieces on hand-checkable inputs, no box data.

The harness's own `smoke` runs the whole round on r11_risk.smoke's synthetic world and re-does the margin curve by brute force; these pin
the registered rules a result rests on: the ledger counting rule, the FWER arithmetic, the g* search (including 'no grid g reaches 0.05'),
the centring, the N-SIZE shift range, the calibration scale and g_adj, the past-pass judgement, and the refusal paths.
"""
import json
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "rocfrontier"))
import r14_looks as L  # noqa: E402
import r11_risk as R11  # noqa: E402

ROW = ("id", "date", "type", "candidate", "lb_ratio", "dup_of")


def _rows(*specs):
    """(id, date, type, candidate, lb_ratio, dup_of) -> ledger rows with every registered column present."""
    out = []
    for sp in specs:
        r = {c: "" for c in L.COLS}
        r.update(dict(zip(ROW, sp)))
        out.append(r)
    return out


def _csv(path, rows):
    L.write_smoke_ledger(path, [tuple(r[c] for c in L.COLS) for r in rows])


TINY = _rows(("R1", "2026-09-01", "REF", "#463 reference", "1.0", ""),
             ("L1", "2026-09-02", "SWAP", "#468 TTM seat", "0.99", ""),
             ("L2", "2026-09-03", "ADD", "#470 sleeve added", "1.02", ""),
             ("L3", "2026-09-04", "COMBO", "58d combo", "1.27", ""),
             ("L4", "2026-09-05", "SIZE", "V2 vol target", "1.57", ""),
             ("L5", "2026-09-06", "SIZE", "V2-500 ref 500", "1.46", ""),
             ("L6", "2026-09-07", "SWAP", "#468 TTM seat re-read", "0.99", "L1"),
             ("L7", "2026-09-08", "LANE", "TTM leg lockbox read", "", ""),
             ("L8", "2026-09-09", "LANE", "ORB leg lockbox read", "", "L7"),
             ("L9", "2026-09-10", "swap", "Q6 ORB #239 in the ORB seat", "1.021", ""))


def test_ledger_counting_rule_excludes_ref_and_dups_keeps_lane_apart_and_splits_size():
    K, looks = L.counts(TINY)
    assert (K["K_book"], K["K_size"], K["K_leg"], K["K_lane"]) == (6, 2, 4, 1)      # L1-L5 + L9 (type case-insensitive); L6 is a dup; LANE dup L8 out
    assert (K["n_ref"], K["n_dup"], K["n_other_type"], K["n_rows"]) == (1, 2, 0, 10)
    assert [r["id"] for r in looks] == ["L1", "L2", "L3", "L4", "L5", "L9"]
    assert L.find_row(TINY, "#468")["id"] == "L1"                                    # the non-dup row wins
    assert L.find_row(TINY, "Q6")["id"] == "L9" and L.find_row(TINY, "V2")["id"] == "L4" and L.find_row(TINY, "V2-500")["id"] == "L5"
    assert L.find_row(TINY, "Q4") is None
    assert L.ratio_of(TINY[1]) == pytest.approx(0.99)
    r = dict(TINY[1], lb_ratio="", lb_roc="150.0", ref_lb_roc="155.54")
    assert L.ratio_of(r) == pytest.approx(150.0 / 155.54)                            # falls back to the printed figures


def test_fwer_arithmetic_by_hand():
    assert L.fwer(0.5, 0.1, 2, 1) == pytest.approx(1 - 0.25 * 0.9)                  # 0.775
    assert L.fwer(0.0, 0.0, 156, 10) == 0.0
    assert L.fwer(0.00033, 0.0051, 156, 10) == pytest.approx(1 - (1 - 0.00033) ** 156 * (1 - 0.0051) ** 10)
    f = L.fwer(np.array([0.5, 0.0]), np.array([0.1, 0.0]), 2, 1)
    assert f[0] == pytest.approx(0.775) and f[1] == 0.0


def test_g_star_is_the_smallest_grid_margin_at_or_under_the_level_or_beyond_the_grid():
    assert len(L.GRID) == 201 and L.GRID[0] == 0.0 and L.GRID[-1] == 1.0 and L.GRID[1] == 0.005
    F = np.linspace(0.3, 0.0, 201)                                                   # monotone down the grid
    i = int(np.flatnonzero(F <= 0.05)[0])
    assert L.g_star(F, 0.05) == float(L.GRID[i]) and F[i] <= 0.05 < F[i - 1]
    assert L.g_star(F, 0.025) >= L.g_star(F, 0.05) >= L.g_star(F, 0.10)
    assert L.g_star(np.full(201, 0.2)) is None and L.gfmt(None) == "> 1.0"            # no grid g reaches 0.05 -> reported as > 1.0
    assert L.g_star(np.zeros(201)) == 0.0 and L.gfmt(0.215) == "0.215"


def test_centring_gives_the_median_draw_zero_excess_and_counts_passes_at_the_margin():
    v = np.array([120.0, 150.0, 155.0, 160.0, 400.0, -5.0, np.nan])
    med = float(np.nanmedian(v[np.isfinite(v)][:5]))                                 # 155
    e = L.excess(v, med)
    assert e[2] == 0.0 and e[3] == pytest.approx(math.log(160 / 155)) and e[5] == -np.inf and e[6] == -np.inf
    ok = np.ones(len(v), bool)
    cnt = L.pass_centred(e, ok)
    assert cnt[0] == 3                                                                # at g = 0: the median draw and the two above it
    assert cnt[int(round(0.03 / 0.005))] == 2 and cnt[-1] == 1                         # 160/155 = +3.2 %; 400/155 passes even g = 1.0
    ok[2] = False                                                                    # the Sortino clause fails for the median draw
    assert L.pass_centred(e, ok)[0] == 2
    assert L.pass_centred(e, np.ones(len(v), bool), prem=L.WF_PREM)[0] == 1          # the WF clause keeps its 5 % premium at g = 0
    assert np.all(L.excess(v, -1.0) == -np.inf)                                      # a non-positive median: nothing can pass (flagged by the counts)


def test_size_shifts_run_over_250_to_n_minus_250_inclusive():
    ks = L.shifts(4179)
    assert ks[0] == 250 and ks[-1] == 4179 - 250 and len(ks) == 4179 - 499 == 3680
    cnt = L.pass_uncentred(np.array([155.54, 160.0, 200.0, np.nan]), np.array([4.2, 4.0, 4.5, 4.5]), L.LB_BAR)
    assert cnt[0] == 2 and cnt[int(round(0.05 / 0.005))] == 1 and cnt[-1] == 0        # read as printed: 160 fails Sortino 4.150; 200 = +28.6 %


def test_calibration_scale_and_adjusted_margin_use_max_of_one_and_r():
    e = np.random.default_rng(1).normal(0, 0.10, 40000)
    c = L.calibration([1.05, 0.95, 1.10, 0.90, 1.00], e)
    assert c["n_real"] == 5 and c["n_null"] == 40000
    assert c["sd_real"] == pytest.approx(float(np.std(np.log([1.05, 0.95, 1.10, 0.90, 1.00]), ddof=1)))
    assert c["r"] == pytest.approx(c["sd_real"] / c["sd_null"]) and 0.5 <= c["r"] <= 2.0 and not c["flag"]
    assert L.g_adj(0.2, 0.7) == pytest.approx(0.2)                                   # never scaled down
    assert L.g_adj(0.2, 1.6) == pytest.approx(0.32)                                  # scaled up to the real swaps' spread
    assert L.g_adj(None, 1.6) is None and L.g_adj(0.2, float("nan")) == pytest.approx(0.2)
    assert L.calibration([1.05, 0.95], np.full(40000, 0.0))["flag"]                  # sd_null 0 -> r undefined -> flagged
    assert L.calibration([2.0, 0.5], e)["flag"]                                      # r far above 2.0 -> flagged


def test_past_pass_is_judged_at_the_k_in_force_then_and_now():
    looks = L.counts(TINY)[1]
    row = L.find_row(TINY, "58d")
    kt = L.k_then(looks, row)
    assert kt == {"K_book": 3, "K_leg": 3, "K_size": 0}                                # L1, L2, L3 dated on or before it
    assert L.k_then(looks, L.find_row(TINY, "Q6")) == {"K_book": 6, "K_leg": 4, "K_size": 2}
    assert L.judge(1.273, 0.20) is True and L.judge(1.273, 0.30) is False and L.judge(1.273, None) is False
    assert L.judge(2.5, None) is None and L.judge(float("nan"), 0.1) is None
    # the margin a K-look read must carry: with p_leg(g) falling down the grid, more looks then means a smaller margin then
    p_leg = np.maximum(0.0, 0.05 - L.GRID * 0.5) ** 1 * 2                             # 0.10 at g = 0, 0 from g = 0.10
    p_size = np.zeros(201)
    g_then = L.g_star(L.fwer(p_leg, p_size, kt["K_leg"], kt["K_size"]))
    g_now = L.g_star(L.fwer(p_leg, p_size, 4, 2))
    assert g_now >= g_then > 0


def test_refusals_no_ready_tbd_ledger_and_a_changed_prereg(tmp_path, monkeypatch):
    probe = tmp_path / "prereg.txt"
    probe.write_text("the plan\r\nline two\r\n")
    sha = R11.sha_lf(str(probe))
    assert L.check_prereg(str(probe), sha) == sha                                     # CRLF-insensitive
    with pytest.raises(SystemExit):
        L.check_prereg(str(probe), "0" * 64)
    with pytest.raises(SystemExit):
        L.check_prereg(str(probe), "TBD")
    probe.write_text("the plan\nline two\naddendum\n")
    with pytest.raises(SystemExit):
        L.check_prereg(str(probe), sha)                                              # the plan changed after it was registered
    led = tmp_path / "ledger.csv"
    _csv(str(led), TINY)
    monkeypatch.setattr(L, "LEDGER", str(led))
    monkeypatch.setattr(L, "LEDGER_SHA", "TBD")
    monkeypatch.setattr(L, "SMOKE_TBD_OK", False)
    with pytest.raises(SystemExit) as ex:
        L.check_ledger()
    assert ex.value.code == 2                                                        # 'ledger not yet registered'
    with pytest.raises(SystemExit) as ex:
        L.ledger()
    assert ex.value.code == 2
    monkeypatch.setattr(L, "LEDGER_SHA", "0" * 64)
    with pytest.raises(SystemExit):
        L.check_ledger()
    monkeypatch.setattr(L, "LEDGER_SHA", R11.sha_lf(str(led)))
    assert L.check_ledger() == L.LEDGER_SHA
    # run(): the registered prereg and ledger in place, but no READY
    monkeypatch.setattr(L, "PREREG", str(probe))
    monkeypatch.setattr(L, "PREREG_SHA", R11.sha_lf(str(probe)))
    monkeypatch.setattr(L, "OUT", str(tmp_path / "out"))
    with pytest.raises(SystemExit, match="parity has not passed"):
        L.run()
    # a READY from another prereg / ledger is refused before any record is touched
    os.makedirs(L.OUT)
    with open(L._ready_path(), "w") as f:
        f.write(json.dumps({"records": {}, "prereg_sha256": "0" * 64, "ledger_sha256": L.LEDGER_SHA}))
    with pytest.raises(SystemExit, match="prereg changed"):
        L.run()
    with open(L._ready_path(), "w") as f:
        f.write(json.dumps({"records": {}, "prereg_sha256": L.PREREG_SHA, "ledger_sha256": "0" * 64}))
    with pytest.raises(SystemExit, match="ledger changed"):
        L.run()
    monkeypatch.setattr(L, "LEDGER_SHA", "TBD")
    with pytest.raises(SystemExit) as ex:
        L.run()
    assert ex.value.code == 2


def test_the_registered_prereg_sha_is_the_file_in_the_repo():
    got = R11.sha_lf(L.PREREG)
    assert got == L.PREREG_SHA, (f"PREREG_LOOKS_R1.txt hashes to {got}, r14_looks.PREREG_SHA is {L.PREREG_SHA} - an addendum landed? "
                                 "re-hash and update PREREG_SHA (and LEDGER_SHA with it) in the same commit")
    assert L.LEDGER_SHA == "TBD" or len(L.LEDGER_SHA) == 64
