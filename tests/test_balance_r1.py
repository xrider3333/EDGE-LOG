"""BALANCE r1 Stage A harness (tools/balance_r1_stageA.py; docs/PREREG_balance_r1_2026-10-06.md section 12).

SYNTHETIC data only: every path the harness would read is either never reached or pointed at tmp_path; no master,
crown file, R / L / RES file or the open-bar cache is read. Proved here:
  * the band and VWAP re-typed from NOISE_1_0 equal its own decision records (1e-9) at every decision bar, for
    _FROZEN-style settings and for the band twins, on NQ-like and ES-like fixtures, and the #304-eligible first break
    + 1 is NOISE_1_0's first entry on every session (gates exercised);
  * the classifier reads only bars stamped <= 11:55 (by STAMP, also with missing early bars); no look-ahead under
    perturbation after random cut bars; warm-up and roll sessions are never traded and still feed the next band;
  * the stretch geometry, next-open fills, the live-band stop, the VWAP target, OPP-BREAK, STOP over TARGET, the
    15:55 flat, re-entry only after a TARGET, the last-fill knob;
  * the zero overlap with a #304 entry on a synthetic stop-then-#304-entry session; held intervals;
  * the cut guards; the statistics; null determinism; the three-way split; the Auto-Validate lattice (8 configs).
"""
import json
import math
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import augur_engine.auto  # noqa: F401  (bind the worktree's engine before the harness extends sys.path)
import augur_engine.data  # noqa: F401
import augur_engine.engine  # noqa: F401
import augur_engine.strategies  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import balance_r1_stageA as BAL  # noqa: E402
import power_line as PL  # noqa: E402

TZ = "US/Eastern"
HM = 570 + 5 * np.arange(78)


# ------------------------------------------------------------------ fixtures
def _arrays(n_sessions, seed, px0=500.0, start="2024-01-02", drop=None, half=None, sd=0.0018, drift_sd=0.0015):
    """load_master_arrays-shaped dict: n_sessions of 5m RTH bars (tz-aware ET index), a noisy walk with volume; each
    session carries a per-bar drift drawn with SD drift_sd (0 = a driftless walk: many balance days)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n_sessions)
    rows, px = [], px0
    for si, d in enumerate(days):
        base = pd.Timestamp("%s 09:30" % d.date(), tz=TZ)
        drift = rng.normal(0, drift_sd)
        nb = 39 if (half and si in half) else 78
        for i in range(nb):
            o = px
            c = o * (1 + drift + rng.normal(0, sd))
            hi = max(o, c) * (1 + abs(rng.normal(0, 0.0006)))
            lo = min(o, c) * (1 - abs(rng.normal(0, 0.0006)))
            vol = float(rng.integers(5000, 20000))
            px = c
            if drop and i in drop.get(si, ()):
                continue
            rows.append((base + pd.Timedelta(minutes=5 * i), o, hi, lo, c, vol))
        px *= 1 + rng.normal(0, 0.004)
    ix = pd.DatetimeIndex([r[0] for r in rows])
    a = np.array([r[1:] for r in rows], float)
    return {"open": a[:, 0].copy(), "high": a[:, 1].copy(), "low": a[:, 2].copy(), "close": a[:, 3].copy(),
            "volume": a[:, 4].copy(), "day_id": pd.factorize(pd.Series(ix).dt.date)[0].astype("int64"), "index": ix}


def _copy(A):
    return {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in A.items()}


@pytest.fixture(scope="module")
def P_small():
    P = BAL.frozen()                       # the real _FROZEN dict, read from NOISE_1_8_CT304.py (code, not data)
    return dict(P, lookback=5, band_mult_long=0.35, band_mult_short=0.35)


def _flat_last(A, P, sig_k=None, c_s=None):
    """Rebuild the LAST session flat at its 09:30 open (huge volume) so VWAP = O0; its bands depend only on prior
    sessions and that open, so they can be read before the afternoon closes are set."""
    A = _copy(A)
    S0 = BAL.build_bands(A, P)
    si = S0.ns - 1
    a, m = int(S0.a[si]), int(S0.m[si])
    O0 = A["open"][a]
    for arr in ("open", "high", "low", "close"):
        A[arr][a:a + m] = O0
    A["volume"][a:a + m] = 1e6
    return A, a, m, O0


def _sess():
    o, c = np.full(78, 100.0), np.full(78, 100.0)
    return o, c, np.full(78, 110.0), np.full(78, 90.0), np.full(78, 100.0)


# ------------------------------------------------------------------ band and VWAP parity with NOISE_1_0's records
@pytest.mark.parametrize("px0,sd,seed", [(15000.0, 0.0018, 5), (4000.0, 0.0012, 9)])   # NQ-like, ES-like
def test_band_parity_and_eligible_first_break(P_small, px0, sd, seed):
    A = _arrays(120, seed, px0=px0, sd=sd, drop={70: [1]}, half={75})
    S = BAL.build_bands(A, P_small)
    brk, bs = BAL.raw_break(S)
    elig = BAL.eligible_first_break(S, bs, P_small)
    tr = BAL.run_304(A, P_small, S)
    assert len(tr) > 50
    nb, mx = BAL.band_parity(S, tr)
    assert nb == 2 * len(tr) and mx <= 1e-9
    assert BAL.eligible_parity(S, elig, tr) == S.ns
    # the gates were exercised: a vol-skipped session and a short-blocked session each had a raw break at k <= m-2
    vol_blk = [si for si in range(S.ns) if not S.warm[si] and S.vol_pct[si] >= 95
               and (bs[S.a[si] + 1:S.a[si] + S.m[si] - 1] != 0).any()]
    sh_blk = [si for si in range(S.ns) if not S.warm[si] and S.dt_pos[si] <= 0.2
              and (bs[S.a[si] + 1:S.a[si] + S.m[si] - 1] == -1).any()]
    assert vol_blk and sh_blk
    assert all(elig[si] < 0 for si in vol_blk)


@pytest.mark.parametrize("lb", [3, 5, 8])
def test_band_twins_built_with_their_own_settings(P_small, lb):
    A = _arrays(90, 21, px0=15000.0)
    Pt = BAL.twin_params(P_small, lb)
    assert (Pt["band_mult_long"], Pt["band_mult_short"], Pt["lookback"]) == (1.0, 1.0, lb)
    St = BAL.build_bands(A, Pt)
    assert St.warm[:lb].all() and not St.warm[lb:].any()
    assert np.isnan(St.UB[:St.a[lb]]).all() and np.isfinite(St.UB[St.a[lb]:]).all()
    tr = BAL.run_304(A, Pt, St)
    nb, mx = BAL.band_parity(St, tr)
    assert nb == 2 * len(tr) > 0 and mx <= 1e-9
    _, bs = BAL.raw_break(St)
    BAL.eligible_parity(St, BAL.eligible_first_break(St, bs, Pt), tr)


def test_twin_bands_differ_from_the_frozen_band(P_small):
    A = _arrays(40, 3)
    S1 = BAL.build_bands(A, P_small)
    S2 = BAL.build_bands(A, BAL.twin_params(P_small, P_small["lookback"]))
    k = np.isfinite(S1.UB)
    assert not np.allclose(S1.UB[k], S2.UB[k]) and np.allclose(S1.V[k], S2.V[k], equal_nan=True)


def test_parity_mismatch_aborts(P_small):
    A = _arrays(60, 4)
    S = BAL.build_bands(A, P_small)
    tr = BAL.run_304(A, P_small, S)
    tr = tr.assign(signal_date=pd.Timestamp("2020-01-02"))          # put them in WF for trade_parity
    f = pd.DataFrame({"entry": tr.entry_stamp, "exit": tr.exit_stamp, "side": tr.side, "unit_usd": 1.0})
    f["entry"] = pd.Timestamp("2020-01-02 10:00")
    with pytest.raises(SystemExit, match="#304 parity"):
        BAL.trade_parity(tr, f.iloc[:-1])
    g = f.copy()
    g["side"] = -g["side"]
    with pytest.raises(SystemExit, match="differs"):
        BAL.trade_parity(tr, g)
    bad = BAL.build_bands(A, P_small)
    bad.UB = bad.UB + 1e-6
    with pytest.raises(SystemExit, match="band parity"):
        BAL.band_parity(bad, tr)


# ------------------------------------------------------------------ the classifier and look-ahead
def test_classifier_noon_cut_by_stamp(P_small):
    A = _arrays(30, 2)
    A, a, m, O0 = _flat_last(A, P_small)
    S = BAL.build_bands(A, P_small)
    si = S.ns - 1
    k1155, k1200 = int(np.flatnonzero(S.hm[a:a + m] == 715)[0]), int(np.flatnonzero(S.hm[a:a + m] == 720)[0])
    trading = S.has1555 & ~S.warm
    assert BAL.classify(S, trading, BAL.raw_break(S)[0])[si]
    for k, want in ((k1155, False), (k1200, True)):
        B = _copy(A)
        B["close"][a + k] = S.UB[a + k] * 1.01
        B["high"][a + k] = B["close"][a + k]
        Sb = BAL.build_bands(B, P_small)
        assert BAL.raw_break(Sb)[0][a + k]
        assert bool(BAL.classify(Sb, trading, BAL.raw_break(Sb)[0])[si]) == want
    rng = np.random.default_rng(1)                                      # anything stamped >= 12:00 never changes it
    for _ in range(5):
        B = _copy(A)
        j = a + np.flatnonzero(S.hm[a:a + m] >= 720)
        f = 1 + rng.normal(0, 0.05, len(j))
        for arr in ("open", "close"):
            B[arr][j] = B[arr][j] * f
        B["high"][j] = np.maximum(B["open"][j], B["close"][j]) * 1.01
        B["low"][j] = np.minimum(B["open"][j], B["close"][j]) * 0.99
        Sb = BAL.build_bands(B, P_small)
        assert BAL.raw_break(Sb)[0][j].any()
        assert BAL.classify(Sb, trading, BAL.raw_break(Sb)[0])[si]


def test_noon_cut_by_stamp_with_missing_early_bars(P_small):
    A = _arrays(30, 2, drop={29: [1]})                                  # the last session lacks its 09:35 bar
    A, a, m, O0 = _flat_last(A, P_small)
    S = BAL.build_bands(A, P_small)
    assert m == 77 and S.hm[a + 29] == 720                             # positional k = 29 is the 12:00 bar
    B = _copy(A)
    B["close"][a + 29] = S.UB[a + 29] * 1.01
    Sb = BAL.build_bands(B, P_small)
    brk = BAL.raw_break(Sb)[0]
    assert brk[a + 29]
    assert BAL.classify(Sb, Sb.has1555 & ~Sb.warm, brk)[S.ns - 1]      # a positional k <= 29 rule would say no


def test_no_lookahead_perturbation(P_small):
    # a driftless walk with wide bands: dozens of BALANCE days, TARGET / STOP / FLAT exits and re-entries (the fixture
    # is asserted non-trivial, so the signal, fill, exit and re-entry paths are all perturbed)
    P = dict(P_small, band_mult_long=1.5, band_mult_short=1.5)
    A = _arrays(100, 3, drift_sd=0.0)
    S = BAL.build_bands(A, P)
    brk, _ = BAL.raw_break(S)
    tr_mask = S.has1555 & ~S.warm
    bal = BAL.classify(S, tr_mask, brk)
    fs = {t: BAL.first_signals(S, bal, brk, t)[0] for t in (0.5, 2 / 3)}
    sim = BAL.simulate(S, bal, 0.5, 0.533, 20.0, 1.533)
    assert bal.sum() >= 15 and len(sim) >= 20 and (sim.order >= 2).any()
    assert {BAL.TARGET, BAL.STOP} <= set(sim.exit_reason)
    rng = np.random.default_rng(11)
    re = sim[sim.order >= 2]
    sim = sim.assign(dec_i=np.where(sim.close_exit, sim.exit_i, sim.exit_i - 1))   # the bar whose close decides the exit
    cuts = list(rng.integers(int(S.a[8]), S.n - 5, size=8))
    cuts += list(re["fill_i"].iloc[:2]) + list(re["sig_i"].iloc[:2] - 1) + list(sim["sig_i"].iloc[[3, 10]])
    for r in (BAL.TARGET, BAL.STOP):                                     # cut AT an exit decision: its fill is perturbed
        cuts += list(sim[(sim.exit_reason == r) & ~sim.close_exit]["dec_i"].iloc[:2])
    keyc = ["sig_i", "fill_i", "exit_i", "side", "entry", "exit_reason", "order"]
    ncmp, nre, ndec = 0, 0, 0
    for cutb in cuts:
        cutb = int(cutb)
        B = _copy(A)
        j = np.arange(cutb + 1, S.n)
        f = 1 + rng.normal(0, 0.02, len(j))
        B["open"][j] *= f
        B["close"][j] *= 1 + rng.normal(0, 0.02, len(j))
        B["high"][j] = np.maximum(B["open"][j], B["close"][j]) * 1.002
        B["low"][j] = np.minimum(B["open"][j], B["close"][j]) * 0.998
        # volume over five orders of magnitude, so one bar after the cut can drag the cumulative VWAP (a VWAP peek
        # then changes a decision at the cut)
        B["volume"][j] = rng.integers(1, 50000, len(j)) * 10.0 ** rng.integers(0, 5, len(j))
        S2 = BAL.build_bands(B, P)
        brk2, _ = BAL.raw_break(S2)
        u = slice(0, cutb + 1)
        for x1, x2 in ((S.UB, S2.UB), (S.LB, S2.LB), (S.V, S2.V)):
            np.testing.assert_array_equal(x1[u], x2[u])
        np.testing.assert_array_equal(brk[u], brk2[u])
        bal2 = BAL.classify(S2, tr_mask, brk2)
        for si in range(S.ns):
            noon = S.a[si] + np.flatnonzero(S.hm[S.a[si]:S.b[si]] <= 715)
            if len(noon) and noon[-1] <= cutb:
                assert bal[si] == bal2[si]
        for t in (0.5, 2 / 3):
            f2 = BAL.first_signals(S2, bal2, brk2, t)[0]
            for si in range(S.ns):
                if 0 <= fs[t][si] <= cutb or 0 <= f2[si] <= cutb:
                    assert fs[t][si] == f2[si]
        sim2 = BAL.simulate(S2, bal2, 0.5, 0.533, 20.0, 1.533)
        k1 = sim[sim.sig_i <= cutb][["sig_i", "side"]].to_numpy()
        k2 = sim2[sim2.sig_i <= cutb][["sig_i", "side"]].to_numpy()
        np.testing.assert_array_equal(k1, k2)
        # a trade whose exit is DECIDED at or before the cut (the close that signals it) has the same signal, fill,
        # entry, exit bar, reason and order; once its exit bar is at or before the cut, the exit price matches too
        sim2 = sim2.assign(dec_i=np.where(sim2.close_exit, sim2.exit_i, sim2.exit_i - 1))
        d1 = sim[sim.dec_i <= cutb].reset_index(drop=True)
        d2 = sim2[sim2.dec_i <= cutb].reset_index(drop=True)
        pd.testing.assert_frame_equal(d1[keyc], d2[keyc])
        done = (d1.exit_i <= cutb).to_numpy()
        np.testing.assert_array_equal(d1["exit"].to_numpy()[done], d2["exit"].to_numpy()[done])
        ncmp += len(d1)
        nre += int((d1.order >= 2).sum())
        ndec += int((~done).sum())
    assert ncmp >= 20 and nre >= 1 and ndec >= 2                         # the comparisons were not vacuous


def test_warmup_sessions_never_trading_or_balance():
    A = _arrays(45, 6)
    P = BAL.frozen()
    S = BAL.build_bands(A, P)
    brk, _ = BAL.raw_break(S)
    roll = np.zeros(S.ns, bool)
    t = BAL.trading_mask(S, roll)
    assert S.warm[:40].all() and not S.warm[40:].any()
    assert not t[:40].any() and t[40:].all()
    assert not BAL.classify(S, t, brk)[:40].any()
    assert np.isnan(S.UB[:S.a[40]]).all() and np.isnan(S.V[:S.a[40]]).all()
    assert (BAL.first_signals(S, BAL.classify(S, t, brk), brk, 0.5)[0][:40] == -1).all()


def test_first_signal_is_exit_independent(P_small):
    A = _arrays(80, 8)
    S = BAL.build_bands(A, P_small)
    brk, _ = BAL.raw_break(S)
    bal = BAL.classify(S, S.has1555 & ~S.warm, brk)
    assert bal.sum() >= 5
    for t in (0.5, 2 / 3):
        idx, sd = BAL.first_signals(S, bal, brk, t)
        tr = BAL.simulate(S, bal, t, 0.533, 20.0, 1.533)
        first = tr[tr.order == 1].set_index("si")
        for si in np.flatnonzero(bal):
            if si in first.index:
                assert idx[si] == first.loc[si, "sig_i"] and sd[si] == first.loc[si, "side"]
            else:
                assert idx[si] == -1


# ------------------------------------------------------------------ rolls
def test_load_rolls_ignores_not_a_roll_and_cuts(tmp_path):
    p = tmp_path / "rolls_NQ.csv"
    pd.DataFrame({"root": "NQ", "old": ["A", "B", "C", "D"], "new": ["B", "C", "D", "E"],
                  "switch_et": ["2024-01-03 20:00", "2024-01-06 18:00", "2024-01-10 20:00", "2025-07-10 20:00"],
                  "offset_pts": [10.0, 20.0, 30.0, 40.0],
                  "kind": ["mid_session", "reopen", "not_a_roll", "mid_session"]}).to_csv(p, index=False)
    r = BAL.load_rolls("NQ", str(p))
    assert list(r["switch_et"].dt.strftime("%Y-%m-%d")) == ["2024-01-03", "2024-01-06"]


def test_roll_sessions_never_traded_and_still_feed_the_next_band(P_small):
    A = _arrays(30, 12)
    S = BAL.build_bands(A, P_small)
    sw = pd.DataFrame({"switch_et": pd.to_datetime(["2024-01-24 20:00", "2024-01-27 18:00", "2024-02-01 11:30"]),
                       "offset_pts": [5.0, 6.0, 7.0], "kind": "mid_session", "old": "x", "new": "y"})
    roll, notes = BAL.roll_sessions(S, sw)
    got = [d.strftime("%Y-%m-%d") for _, _, d, _ in notes]
    assert got == ["2024-01-25", "2024-01-29", "2024-02-02"]           # first session whose first bar is after the switch
    assert roll.sum() == 3
    t = BAL.trading_mask(S, roll)
    assert not t[roll].any()
    brk, _ = BAL.raw_break(S)
    bal = BAL.classify(S, t, brk)
    assert not bal[roll].any()
    tr = BAL.simulate(S, bal, 0.5, 0.533, 20.0, 1.533)
    assert not tr.si.isin(np.flatnonzero(roll)).any()
    NZ = BAL.noise_mod()
    for j in np.flatnonzero(roll):
        nxt = j + 1
        assert S.prev_close[nxt] == S.c[S.b[j] - 1]                      # the roll session's last close is prev_close
        sig = NZ._sigma_matrix(S.o, S.c, S.bounds, 5)
        a, m = S.a[nxt], S.m[nxt]
        ref_hi = max(S.o[a], S.c[S.b[j] - 1])
        np.testing.assert_array_equal(S.UB[a:a + m], ref_hi * (1.0 + 0.35 * sig[nxt, :m]))
    S_noroll = BAL.build_bands(A, P_small)                               # bands never depend on the roll flags
    np.testing.assert_array_equal(S.UB, S_noroll.UB)


# ------------------------------------------------------------------ stretch geometry
def test_stretch_geometry():
    x, E, side, D = BAL.stretch([105, 95, 100], [100, 100, 100], [110, 110, 110], [90, 90, 90])
    assert x[0] == 0.5 and E[0] == 110 and side[0] == -1 and D[0] == 10
    assert x[1] == 0.5 and E[1] == 90 and side[1] == 1 and D[1] == 10
    assert np.isnan(x[2]) and side[2] == 0                              # C == V: no signal
    # denominator <= 0 (short: UB == V; long: LB == V), a NaN close, a NaN band
    x, _, side, _ = BAL.stretch([106, 94, np.nan, 105], [105, 95, 100, 100], [105, 110, 110, np.nan],
                                [90, 95, 90, 90])
    assert np.isnan(x).all() and not side.any()
    x, _, side, _ = BAL.stretch([106], [105], [104], [90])                # UB below V
    assert np.isnan(x[0]) and side[0] == 0
    x, _, _, _ = BAL.stretch([104, 110], [100, 100], [110, 110], [90, 90])
    assert (x <= 1).all()                                                # no raw break -> x <= 1
    x, _, _, _ = BAL.stretch([102], [100], [103], [90])
    assert x[0] == 2 / 3 and x[0] >= 8 / 12                              # 2/3 inclusive
    assert 6 / 12 == 0.5 and 8 / 12 == 2 / 3


def test_x_exactly_half_signals_B1_and_two_thirds_signals_B2():
    o, c, UB, LB, V = _sess()
    c[29] = 105.0
    assert BAL.sim_session(o, c, UB, LB, V, HM, True, 6 / 12)[0]["sig_k"] == 29
    assert BAL.sim_session(o, c, UB, LB, V, HM, True, 8 / 12) == []
    o, c, UB, LB, V = _sess()
    UB[:] = 103.0
    c[29] = 102.0
    assert BAL.sim_session(o, c, UB, LB, V, HM, True, 8 / 12)[0]["sig_k"] == 29


# ------------------------------------------------------------------ fills, exits, re-entry
def test_next_open_fills_and_first_fill_noon():
    o, c, UB, LB, V = _sess()
    c[18:30] = 106.0
    o[30] = 106.5
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    t = tr[0]
    assert (t["sig_k"], t["fill_k"], t["sig_hm"], t["fill_hm"], t["side"], t["entry"]) == (29, 30, 715, 720, -1, 106.5)
    assert t["reason"] == BAL.TARGET and t["exit_k"] == 31 and t["exit"] == o[31] and t["gross"] == 6.5
    assert len(tr) == 1


def test_last_fill_1530_and_the_last_fill_knob():
    o, c, UB, LB, V = _sess()
    c[71] = 106.0                                                        # 15:25 signal -> 15:30 fill
    t = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert len(t) == 1 and t[0]["sig_hm"] == 925 and t[0]["fill_hm"] == 930
    o, c, UB, LB, V = _sess()
    c[72] = 106.0                                                        # a 15:30 signal is ignored
    assert BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5) == []
    assert BAL.sig_last_for(360) == 925 and BAL.sig_last_for(330) == 895
    o, c, UB, LB, V = _sess()
    c[71] = 106.0
    assert BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5, sig_last=BAL.sig_last_for(330)) == []
    c[65] = 106.0
    t = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5, sig_last=BAL.sig_last_for(330))
    assert t[0]["sig_hm"] == 895 and t[0]["fill_hm"] == 900


def test_stop_is_the_live_band_and_nan_never_stops():
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:40] = 103.0
    UB[40:] = 104.0                                                      # the band at bar j, not the one at entry
    c[40] = 105.0
    c[50] = 106.0                                                        # no re-entry after a STOP
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert len(tr) == 1 and tr[0]["reason"] == BAL.STOP and tr[0]["exit_k"] == 41 and tr[0]["exit"] == o[41]
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:40] = 103.0
    UB[40] = np.nan
    c[40] = 1000.0
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert tr[0]["reason"] == BAL.TARGET and tr[0]["exit_k"] == 42      # bar 41 (c = 100 = V) is the target


def test_target_close_at_vwap_next_open_and_lows_are_not_an_input():
    import inspect
    assert not {"l", "low", "lows", "h", "high"} & set(inspect.signature(BAL.sim_session).parameters)
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:35] = 101.0                                                     # above VWAP: no exit, whatever the lows did
    c[35] = 100.0                                                        # equality exits
    o[36] = 99.5
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert tr[0]["reason"] == BAL.TARGET and tr[0]["exit_k"] == 36 and tr[0]["exit"] == 99.5


def test_opp_break_and_opposite_band_target_close_the_day():
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:40] = 103.0
    V[40], c[40] = 88.0, 89.0                                            # below LB, not through V (V outside the band)
    c[50] = 106.0
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert len(tr) == 1 and tr[0]["reason"] == BAL.OPP and tr[0]["exit_k"] == 41 and not tr[0]["opp_band"]
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:40] = 103.0
    c[40] = 85.0                                                         # below LB and through V
    c[50] = 106.0
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert len(tr) == 1 and tr[0]["reason"] == BAL.TARGET and tr[0]["opp_band"]


def test_stop_beats_target_on_the_same_bar():
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:40] = 103.0
    V[40], c[40] = 120.0, 115.0                                          # above UB and at / below V
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert tr[0]["reason"] == BAL.STOP


def test_flat_at_1555_close():
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:] = 103.0
    t = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)[0]
    assert (t["reason"], t["exit_k"], t["exit"], t["exit_hm"], t["held_end_hm"], t["close_exit"]) == (
        BAL.FLAT, 77, 103.0, 955, 960, True)
    c[77] = 111.0                                                        # a stop signalled at 15:55 exits at that close
    t = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)[0]
    assert (t["reason"], t["exit"], t["held_end_hm"]) == (BAL.STOP, 111.0, 960)


def test_reentry_only_after_a_target():
    o, c, UB, LB, V = _sess()
    c[29], o[30] = 106.0, 106.0
    c[30:35] = 103.0
    c[35] = 94.0                                                         # short TARGET and a long stretch: no signal here
    c[36] = 94.0                                                         # the exit's fill bar: the earliest re-signal
    tr = BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5)
    assert len(tr) == 2
    assert tr[0]["reason"] == BAL.TARGET and tr[0]["exit_k"] == 36
    assert (tr[1]["sig_k"], tr[1]["fill_k"], tr[1]["side"], tr[1]["order"]) == (36, 37, 1, 2)
    o, c, UB, LB, V = _sess()                                            # a post-noon break while flat closes the day
    c[40] = 111.0
    c[50] = 106.0
    assert BAL.sim_session(o, c, UB, LB, V, HM, True, 0.5) == []
    o, c, UB, LB, V = _sess()                                            # not BALANCE -> nothing
    c[29] = 106.0
    assert BAL.sim_session(o, c, UB, LB, V, HM, False, 0.5) == []


# ------------------------------------------------------------------ the zero overlap with a #304 entry
@pytest.mark.parametrize("kb", [48, 76])
def test_zero_overlap_stop_then_304_entry(P_small, kb):
    """kb 48: a 13:30 break. kb 76: a 15:50 break (#304's last entry bar, k = m-2) - BALANCE's STOP fills at the 15:55
    OPEN and its held interval ends there (held_end = exit stamp 15:55, not 16:00), while #304 fills at that open and is
    flattened at the 15:55 close (file row 15:55 / 15:55 -> [15:55, 16:00)): the held intervals touch, never overlap."""
    A = _arrays(30, 7)
    A, a, m, O0 = _flat_last(A, P_small)
    S0 = BAL.build_bands(A, P_small)
    UB = S0.UB[a:a + m]
    ks = 42                                                              # 13:00 signal
    c_s = O0 + 0.8 * (UB[ks:kb].min() - O0)
    A["close"][a + ks] = A["high"][a + ks] = c_s
    A["volume"][a + ks:a + m] = 1.0
    for arr in ("open", "high", "low", "close"):
        A[arr][a + ks + 1:a + kb] = c_s
    c_b = UB[kb] * 1.001
    A["open"][a + kb], A["low"][a + kb] = c_s, c_s
    A["close"][a + kb] = A["high"][a + kb] = c_b
    for arr in ("open", "high", "low", "close"):
        A[arr][a + kb + 1:a + m] = c_b
    S = BAL.build_bands(A, P_small)
    np.testing.assert_array_equal(S.UB[a:a + m], UB)                     # bands do not depend on today's closes
    assert S.x[a + ks] >= 0.5 and S.side[a + ks] == -1
    brk, _ = BAL.raw_break(S)
    bal = BAL.classify(S, S.has1555 & ~S.warm, brk)
    assert bal[S.ns - 1]
    tr = BAL.simulate(S, bal, 0.5, 0.533, 20.0, 1.533)
    t = tr[tr.si == S.ns - 1].iloc[0]
    assert t.exit_reason == BAL.STOP and t.side == -1
    n304 = BAL.run_304(A, P_small, S)
    e = n304[n304.si == S.ns - 1].iloc[0]
    assert e.side == 1 and e.entry_stamp == t.exit_stamp == S.ts[a + kb + 1]
    assert t.held_end == t.exit_stamp and not t.close_exit                # a next-open exit ends at its fill
    if kb == m - 2:
        assert e.exit_stamp == e.entry_stamp and e.exit_stamp.strftime("%H:%M") == "15:55"
        assert t.exit_stamp.strftime("%H:%M") == "15:55"
    crown = BAL.crown_intervals(pd.DataFrame({"entry": [e.entry_stamp], "exit": [e.exit_stamp], "side": [e.side]}))
    ov, _ = BAL.overlap(tr[tr.si == S.ns - 1], {"NOISE422": crown})
    assert ov.loc[ov.crown == "NOISE422", "overlap_minutes"].iloc[0] == 0
    with pytest.raises(SystemExit, match="must be 0"):                   # a non-zero NOISE overlap is a bug
        BAL.overlap(tr[tr.si == S.ns - 1], {"NOISE382": [(t.fill_stamp, t.exit_stamp + pd.Timedelta(minutes=5), 1)]})


# ------------------------------------------------------------------ held intervals
def test_held_minutes_half_open_and_1555_close():
    d = pd.Timestamp("2024-03-04")
    hm, n = BAL.held_minutes([(d + pd.Timedelta(hours=10), d + pd.Timedelta(hours=10, minutes=30), 1)], [d])
    held = np.flatnonzero(hm[d])
    assert held[0] == 30 and held[-1] == 59 and len(held) == 30 and n == 0
    nz = pd.DataFrame({"entry": [d + pd.Timedelta(hours=15)], "exit": [d + pd.Timedelta(hours=15, minutes=55)], "side": [-1]})
    iv = BAL.crown_intervals(nz)
    assert iv[0][1] == d + pd.Timedelta(hours=16)
    hm, _ = BAL.held_minutes(iv, [d])
    assert hm[d][389] == -1 and hm[d][329] == 0 and hm[d][330] == -1
    hm, n = BAL.held_minutes([(d + pd.Timedelta(hours=10), d + pd.Timedelta(hours=11), 1),
                              (d + pd.Timedelta(hours=10, minutes=30), d + pd.Timedelta(hours=11), -1)], [d])
    assert n == 1 and hm[d][65] == 2 and hm[d][35] == 1 and hm[d][90] == 0


def test_crown_stamps_converted_and_multiday_fill(tmp_path):
    p = tmp_path / "ENGUQ335_raw_trades.csv"
    pd.DataFrame({"entry_time": ["2020-01-02 15:00:00-05:00", "2020-07-01 08:30:00-04:00"],
                  "exit_time": ["2020-01-06 10:00:00-05:00", "2020-07-01 09:45:00-04:00"],
                  "side": ["long", "short"], "pnl_usd": [100.0, -50.0], "size": [1.0, 2.0], "stage": "WF"}).to_csv(p, index=False)
    df = BAL.load_crown("ENGUQ335", str(p))
    assert df["entry"].dt.tz is None and str(df["entry"][0]) == "2020-01-02 15:00:00"
    assert str(df["exit"][1]) == "2020-07-01 09:45:00" and df["unit_usd"].tolist() == [100.0, -25.0]
    days = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06", "2020-07-01"])
    hm, _ = BAL.held_minutes(BAL.crown_intervals(df, close_end=False), days)
    a, b, c, d = (hm[x] for x in days)
    assert np.flatnonzero(a)[0] == 330 and (a[330:] == 1).all() and (b == 1).all()
    assert (c[:30] == 1).all() and not c[30:].any()
    assert (d[:15] == -1).all() and not d[15:].any()                     # pre-RTH minutes do not count
    q = tmp_path / "ORB314_raw_trades.csv"
    pd.DataFrame({"entry_time": ["2020-01-02 09:40:00-05:00"], "exit_time": ["2020-01-02 15:55:00-05:00"],
                  "side": ["short"], "pnl_usd": [10.0], "size": [1.0], "stage": "WF"}).to_csv(q, index=False)
    o = BAL.load_crown("ORB314", str(q))
    assert BAL.crown_intervals(o)[0][1] == pd.Timestamp("2020-01-02 16:00")


def test_ttm_interval_adds_30_minutes():
    ix = pd.date_range("2024-03-04 09:30", periods=13, freq="30min", tz=TZ)
    iv = BAL.ttm_intervals([(1, 4, 2.5, -1, 5000.0, 5002.5)], ix)
    assert iv == [(pd.Timestamp("2024-03-04 10:00"), pd.Timestamp("2024-03-04 12:00"), -1)]


# ------------------------------------------------------------------ cut guards
def test_master_with_a_bar_after_the_cut_aborts(monkeypatch):
    A = _arrays(3, 1, start="2025-06-26")
    assert BAL.naive(A["index"])[-1].date() == pd.Timestamp("2025-06-30").date()
    monkeypatch.setattr(BAL, "find_master", lambda *a, **k: {"id": 37, "filename": "NOADJ_NQ_5m_RTH.csv",
                                                             "source": "db_noadj_rth"})
    monkeypatch.setattr(BAL, "load_master_arrays", lambda m, date_from=None, date_to=None: A)
    with pytest.raises(SystemExit) as e:
        BAL.load_master("NQ")
    assert str(e.value) == "a bar after 2025-06-29 is in memory - abort" == BAL.CUT_MSG
    ok = _arrays(3, 1, start="2025-06-24")
    monkeypatch.setattr(BAL, "load_master_arrays", lambda m, date_from=None, date_to=None: ok)
    assert BAL.load_master("NQ") is ok
    monkeypatch.setattr(BAL, "find_master", lambda *a, **k: {"id": 61, "filename": "ADJ_NQ_5m_RTH.csv",
                                                             "source": "db_noadj_rth"})
    with pytest.raises(SystemExit, match="expected id 37"):
        BAL.load_master("NQ")


def test_crown_rows_after_the_cut_are_dropped(tmp_path):
    p = tmp_path / "NOISE422_raw_trades.csv"
    pd.DataFrame({"entry_time": ["2025-06-27 10:05:00", "2025-06-30 10:05:00"],
                  "exit_time": ["2025-06-27 15:55:00", "2025-06-30 11:00:00"], "side": ["long", "short"],
                  "pnl_usd": [1.0, 2.0], "size": [1.0, 1.0], "stage": "WF"}).to_csv(p, index=False)
    assert len(BAL.load_crown("NOISE422", str(p))) == 1
    q = tmp_path / "ENGUQ335_raw_trades.csv"
    pd.DataFrame({"entry_time": ["2025-06-27 15:00:00-04:00", "2025-06-26 10:00:00-04:00"],
                  "exit_time": ["2025-06-30 10:00:00-04:00", "2025-06-26 11:00:00-04:00"], "side": ["long", "long"],
                  "pnl_usd": [1.0, 2.0], "size": [1.0, 1.0], "stage": "WF"}).to_csv(q, index=False)
    df = BAL.load_crown("ENGUQ335", str(q))
    assert len(df) == 1 and str(df["entry"][0]) == "2025-06-26 10:00:00"
    bad = tmp_path / "NOISE382_raw_trades.csv"
    pd.DataFrame({"entry_time": ["2024-01-02 09:25:00"], "exit_time": ["2024-01-02 10:00:00"], "side": ["long"],
                  "pnl_usd": [1.0], "size": [1.0], "stage": "WF"}).to_csv(bad, index=False)
    with pytest.raises(SystemExit, match="outside 09:30-15:55"):
        BAL.load_crown("NOISE382", str(bad))


def test_daily_requires_every_session_on_the_index():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    tr = pd.DataFrame({"session": pd.DatetimeIndex(["2024-01-02", "2024-01-02", "2024-01-04"]), "net_usd": [1.0, 2.0, 3.0]})
    with pytest.raises(SystemExit, match="not on the day index"):
        BAL.daily(tr, idx)
    np.testing.assert_array_equal(BAL.daily(tr.iloc[:2], idx).to_numpy(), [3.0, 0.0])


# ------------------------------------------------------------------ statistics
def test_roc30_equals_r11_stats():
    rng = np.random.default_rng(4)
    dates = pd.bdate_range("2016-07-01", periods=700)
    x = rng.normal(40, 900, 700)
    years = (dates[-1] - dates[0]).days / 365.25
    st = BAL.R11.stats(x, dates)
    assert abs(PL.roc30(x[None, :], years)[0] - st["roc"]) < 1e-9
    assert abs(BAL.own(x, dates)["roc"] - st["roc"]) < 1e-12


def test_t_rsum_years_window():
    tr = pd.DataFrame({"session": pd.DatetimeIndex(["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04",
                                                    "2024-01-05"]), "net_usd": [0.5, 0.5, 2.0, 3.0, 4.0]})
    assert abs(BAL.t_stat(tr) - 2.5 / (np.std([1, 2, 3, 4], ddof=1) / 2)) < 1e-12
    x = np.array([5.0, -1.0, 10.0, 3.0, 7.0, 2.0])
    inR = np.array([1, 1, 1, 1, 1, 0], bool)
    assert BAL.r_sum(x, inR) == 24.0 and BAL.r_sum_ex3(x, inR) == 2.0   # [-1, 3] are left after the 3 best
    b = pd.DatetimeIndex(["2016-06-30", "2016-07-01", "2017-06-30", "2017-07-01", "2025-06-29"])
    y = BAL.july_june(np.array([100.0, 1.0, 2.0, 4.0, 8.0]), b)
    assert y[0] == 3.0 and y[1] == 4.0 and y[-1] == 8.0 and len(y) == 9
    b = pd.DatetimeIndex(["2020-02-14", "2020-02-15", "2020-04-30", "2020-05-01"])
    assert BAL.ex_window(np.array([1.0, 10.0, 100.0, 1000.0]), b, *BAL.X20) == 1001.0
    assert BAL.pf(np.array([3.0, -1.0, -2.0])) == 1.0


def test_event_path_marks_and_freezes():
    tr = pd.DataFrame({"R0": [2.0], "beyond": [False], "marks": [[(5, 1.0), (10, 2.0)]], "exit_min": [15],
                       "gross_pts": [3.0]})
    ep = BAL.event_path(tr)
    assert ep[0] == 0.0 and ep[1] == 0.5 and ep[2] == 1.0 and (ep[3:] == 1.5).all()


# ------------------------------------------------------------------ null and power determinism
def test_null_draw_order_and_seed():
    rng = np.random.default_rng(20261006)
    want = [(rng.choice([-1, 1], size=3), rng.choice([-1, 1], size=5)) for _ in range(2)]
    got = list(BAL.null_coins([3, 5], draws=2))
    for (d, coins), (w1, w2) in zip(got, want):
        np.testing.assert_array_equal(coins[0], w1)
        np.testing.assert_array_equal(coins[1], w2)
    np.testing.assert_array_equal(got[0][1][0], BAL.power_coin(3))      # the first B1 draw = the power coin


def test_family_null_deterministic():
    rng = np.random.default_rng(2)
    nd = 300
    cells = [("B1", rng.normal(30, 300, 120), rng.integers(0, nd, 120)),
             ("B2", rng.normal(30, 300, 60), rng.integers(0, nd, 60))]
    inR = rng.random(nd) < 0.3
    a = BAL.family_null(cells, nd, inR, 1.2, 10.66, draws=50)
    b = BAL.family_null(cells, nd, inR, 1.2, 10.66, draws=50)
    assert a["p95"] == b["p95"] and a["sd_rsum_B1"] == b["sd_rsum_B1"]
    c = BAL.family_null(cells, nd, inR, 1.2, 10.66, draws=50, seed=7)
    assert c["p95"] != a["p95"]
    coins = next(BAL.null_coins([120, 60], draws=1))[1]                   # draw 1 recomputed by hand
    x = np.bincount(cells[0][2], weights=coins[0] * cells[0][1] - 10.66, minlength=nd)
    assert abs(a["maxima"]["max_rsum"][0] - max(x[inR].sum(), np.bincount(
        cells[1][2], weights=coins[1] * cells[1][1] - 10.66, minlength=nd)[inR].sum())) < 1e-6


def test_mode_guards(monkeypatch):
    monkeypatch.setattr(BAL, "MODE", "counts")
    with pytest.raises(RuntimeError, match="forbidden in --counts"):
        BAL.simulate(None, np.zeros(0, bool), 0.5, 0.533, 20.0, 1.533)
    monkeypatch.setattr(BAL, "MODE", "power")
    with pytest.raises(RuntimeError, match="real run"):
        BAL.book_add(np.zeros(3), None, None, None, 1.0)


# ------------------------------------------------------------------ the 13 bars and the verdict (section 8)
def _cell(**kw):
    c = SimpleNamespace(st={"roc": 6.0}, rs=100.0, rs3=50.0, pf=1.2, n=500, years=8.994, yrs=[1.0] * 6 + [-1.0] * 3,
                        t=2.5, stress=10.0, net=1000.0, best_day=100.0, best_trade=50.0, x11=500.0, early_net=10.0)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


_P95 = {"rsum": 99.0, "t": 2.2, "roc": 3.0}


def _fails(c, other=1.0, p95=None):
    bs = BAL.bars13(c, other, p95 or _P95)
    assert [r[0] for r in bs] == list(range(1, 14))
    return {no for no, _, ok, _ in bs if not ok}


def test_bars13_thresholds_one_bar_at_a_time():
    assert _fails(_cell()) == set()
    n50 = int(math.ceil(50 * 8.994))                                      # 450 trades = 50.03 a year
    assert _fails(_cell(st={"roc": 5.0}, pf=1.05, n=n50, t=2.0), p95={"rsum": 99.0, "t": 1.9, "roc": 0.0}) == set()
    assert _fails(_cell(yrs=[1.0] * 6 + [0.0] * 3)) == set()             # 6 of 9 years, inclusive
    one = {1: (dict(st={"roc": 4.99}), None), 2: (dict(rs=0.0), {"rsum": -10.0, "t": 2.2, "roc": 3.0}),
           3: (dict(rs3=0.0), None), 4: (dict(rs=99.0), None), 5: (dict(pf=1.049), None), 6: (dict(n=n50 - 1), None),
           7: (dict(yrs=[1.0] * 5 + [-1.0] * 4), None), 8: (dict(t=1.99), {"rsum": 99.0, "t": 1.0, "roc": 3.0}),
           9: (dict(stress=0.0), None), 10: (dict(best_trade=1000.0), None), 11: (dict(x11=0.0), None),
           12: (dict(early_net=0.0), None)}
    for bar, (kw, p95) in one.items():
        assert _fails(_cell(**kw), p95=p95) == {bar}, bar
    assert _fails(_cell(t=2.2)) == {8}                                    # t must be ABOVE the null p95 (strict)
    assert _fails(_cell(n=99)) == {6}
    assert _fails(_cell(), other=0.0) == {13}


def test_stage_verdict_by_bar_number_and_the_av_default():
    ok, c6, c56 = BAL.bars13(_cell(), 1.0, _P95), BAL.bars13(_cell(n=99), 1.0, _P95), BAL.bars13(_cell(n=99, pf=1.0), 1.0, _P95)
    assert BAL.stage_verdict({"B1": ok, "B2": c6}) == (["B1"], ["B2"])
    assert BAL.stage_verdict({"B1": c56, "B2": c6}) == ([], ["B2"])
    assert BAL.stage_verdict({"B1": c56, "B2": c56}) == ([], [])
    assert BAL.stage_verdict({"B1": c6, "B2": ok}) == (["B2"], ["B1"])
    shuffled = list(reversed(c6))                                         # read by number, not by position
    assert BAL.stage_verdict({"B1": shuffled, "B2": c56}) == ([], ["B1"])
    with pytest.raises(SystemExit, match="bars 1..13"):
        BAL.stage_verdict({"B1": ok[:12], "B2": ok})
    assert BAL.av_space_for("B2")["stretch_12ths"]["default"] == 8
    assert BAL.av_space_for("B1")["stretch_12ths"]["default"] == 6
    assert BAL.av_space_for(None)["stretch_12ths"]["default"] is None
    assert BAL.AV_SPACE["stretch_12ths"]["default"] == 6 and BAL.av_space_for("B2")["last_fill_min"]["default"] == 360


def test_fragile_is_a_twin_sign_flip(monkeypatch):
    monkeypatch.setattr(BAL, "MODE", "run")
    monkeypatch.setattr(BAL, "print_cell", lambda *a, **k: None)
    tw = lambda *nets: [("twin%d" % (20 * (i + 1)), 20 * (i + 1), None, SimpleNamespace(net=v)) for i, v in enumerate(nets)]
    assert not BAL.twin_rows(SimpleNamespace(net=10.0), tw(5.0, 1.0, 0.5))
    assert BAL.twin_rows(SimpleNamespace(net=10.0), tw(5.0, 0.0, 0.5))      # one above 0 and the other not
    assert not BAL.twin_rows(SimpleNamespace(net=0.0), tw(-3.0, 0.0, -1.0))
    assert BAL.twin_rows(SimpleNamespace(net=-1.0), tw(-3.0, 2.0, -1.0))


@pytest.mark.filterwarnings("ignore:Degrees of freedom:RuntimeWarning", "ignore:invalid value:RuntimeWarning")
def test_family_null_identity_coin_reproduces_the_real_cell(monkeypatch):           # 1 draw: its null SD is NaN
    """Bars 4 and 8 compare a cell with null draws; a draw whose coins are all +1 (the real sides: gross is signed)
    must give exactly the cell's own ROC, t and R-sum."""
    bdays = pd.bdate_range("2016-07-01", periods=400)
    rng = np.random.default_rng(23)
    sess = pd.DatetimeIndex(np.sort(rng.choice(bdays.to_numpy(), 150)))  # repeats: several trades a session
    g = rng.normal(0.8, 12, 150)
    tr = pd.DataFrame({"session": sess, "gross_pts": g, "net_usd": 20 * g - 20 * 0.533})
    x = BAL.daily(tr, bdays).to_numpy()
    inR = rng.random(400) < 0.3
    years = (bdays[-1] - bdays[0]).days / 365.25
    di = bdays.get_indexer(sess)
    monkeypatch.setattr(BAL, "null_coins", lambda sizes, draws=1, seed=0: iter([(0, [np.ones(k, int) for k in sizes])]))
    nl = BAL.family_null([("B1", 20 * g, di), ("B2", 20 * g, di)], len(bdays), inR, years, 20 * 0.533, draws=1)
    mx = nl["maxima"].iloc[0]
    assert abs(mx.max_rsum - BAL.r_sum(x, inR)) < 1e-6
    assert abs(mx.max_t - BAL.t_stat(tr)) < 1e-9
    assert abs(mx.max_roc - BAL.own(x, bdays)["roc"]) < 1e-9
    assert nl["p95"]["t"] == mx.max_t and nl["p95"]["rsum"] == mx.max_rsum


def test_book_add_and_power_match_the_house_functions(monkeypatch, capsys):
    monkeypatch.setattr(BAL, "MODE", "run")
    HH = BAL.HH
    bdays = pd.bdate_range("2016-07-01", periods=600)
    rng = np.random.default_rng(17)
    B = pd.Series(rng.normal(150, 900, 600), index=bdays)
    L = B + 0.264 * pd.Series(rng.normal(20, 400, 600), index=bdays)
    years = (bdays[-1] - bdays[0]).days / 365.25
    x = np.where(rng.random(600) < 0.3, rng.normal(30, 400, 600), 0.0)
    rows, _ = BAL.book_add(x, B, L, bdays, years)
    capsys.readouterr()
    hh_ok = HH.book_report(x, B, years, "X")
    out = capsys.readouterr().out
    got = {(lab, base): (s, roc, so, p5, ok) for lab, base, s, roc, so, p5, ok in rows}
    for hlab, key in (("VOL scale", "c"), ("$30k own DD (twin)", "$30k twin")):
        s, roc, so, p5, _ = got[(key, "#463")]
        assert ("at %-18s (x%.3f NQ): ROC@30k %.2f  Sortino %.3f  bootstrap p5 %+.1f" % (hlab, s, roc, so, p5)) in out
    assert got[("c", "#463")][4] == hh_ok
    # power(): the coin leg on a synthetic schedule against HH.power_lines (#463 base) and the same lines on L
    sess = pd.DatetimeIndex(np.sort(rng.choice(bdays.to_numpy(), 300)))
    ent = rng.normal(15000, 50, 300)
    wf = pd.DataFrame({"session": sess, "entry": ent, "exit": ent + rng.normal(0, 15, 300)})
    pw = BAL.power(wf, B, L, bdays, years)
    coin = BAL.power_coin(len(wf))
    xc = BAL.daily(wf.assign(net_usd=coin * (wf["exit"] - wf["entry"]) * 20.0 - 20.0 * 0.533), bdays).to_numpy()
    capsys.readouterr()
    HH.power_lines(xc, B, years)
    out = capsys.readouterr().out
    for hlab, k, s in (("VOL scale (primary)", "book_c", pw["c"]), ("$30k own drawdown (twin)", "book_twin", pw["twin"])):
        r = pw["lines"][k]
        assert ("%-26s x%.3f NQ: SD of the book-add lead %.1f points; 5%% line %.1f; 80%% line %.1f" % (
            hlab, s, r["sd"], r["line_5pct"], r["line_80pct"])) in out
    xv, c = HH.vol_scaled(xc, B, bdays)
    assert c == pw["c"] and PL.power_line(L.to_numpy() + xv, L.to_numpy(), years) == pw["lines"]["line_c"]


# ------------------------------------------------------------------ constants, the index assert, the warm-up assert
def test_cost_curve_per_instrument_and_bar_constants():
    for inst in ("NQ", "ES"):
        cc = dict(BAL.COST_CURVE[inst])
        assert cc["gross 0"] == 0.0 and cc["house"] == BAL.INST[inst]["cost"]
        assert cc["+2 ticks a side"] == BAL.INST[inst]["stress"]
        assert abs(cc["+1 tick a side"] - (cc["house"] + 0.5)) < 1e-12   # 0.25-point ticks on both
        assert [v for _, v in BAL.COST_CURVE[inst]] == sorted(v for _, v in BAL.COST_CURVE[inst])
    assert abs(dict(BAL.COST_CURVE["NQ"])["MNQ"] - BAL.R11.MICRO_RT["NQ"] / 2.0) < 1e-12   # $ a micro RT / $ a point
    assert abs(dict(BAL.COST_CURVE["ES"])["MES"] - BAL.R11.MICRO_RT["ES"] / 5.0) < 1e-12
    assert BAL.LINE_BAR == (126.86, 3.916) and BAL.BOOK_REF_BARS == (98.50, 3.816)


def test_every_wf_balance_date_must_be_on_the_index():
    dates = pd.DatetimeIndex(["2016-06-30", "2016-07-01", "2016-07-05", "2016-07-06"])
    ctx = SimpleNamespace(inst="NQ", S=SimpleNamespace(dates=dates), balance=np.array([True, True, True, False]))
    idx = pd.DatetimeIndex(["2016-07-01", "2016-07-05"])
    assert BAL.assert_balance_on_index(ctx, idx) == 2                   # an EARLY day is not checked against WF
    ctx.balance[3] = True                                                # a BALANCE day with no trade, off the index
    with pytest.raises(SystemExit, match="not on #463's day index"):
        BAL.assert_balance_on_index(ctx, idx)


def test_prepare_asserts_the_40_session_warmup(monkeypatch, P_small):
    A = _arrays(60, 6)
    sw = pd.DataFrame({"switch_et": pd.to_datetime(pd.Series([], dtype=str)), "offset_pts": pd.Series([], dtype=float),
                       "kind": pd.Series([], dtype=str), "old": pd.Series([], dtype=str), "new": pd.Series([], dtype=str)})
    monkeypatch.setattr(BAL, "load_master", lambda inst, *a, **k: A)
    monkeypatch.setattr(BAL, "load_rolls", lambda inst, path=None: sw.copy())
    monkeypatch.setattr(BAL, "N_WF_SWITCHES", 0)
    ctx = BAL.prepare("NQ", BAL.frozen())
    assert ctx.S.warm[:40].all() and not ctx.S.warm[40:].any() and not (ctx.trading | ctx.balance)[:40].any()
    with pytest.raises(SystemExit, match="warm-up"):
        BAL.prepare("NQ", P_small)                                       # lookback 5 is not the frozen 40 sessions


def test_day_groups_coloss_vs_L_reads_line_csv(capsys):
    d = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"])
    wf = pd.DataFrame({"session": d, "net_usd": [-100.0, -300.0, 50.0]})
    sp = pd.DataFrame({"date": d, "si": [0, 1, 2], "group": ["BREAK-LOSS", "QUIET", "QUIET"],
                       "sub": ["BREAK-LOSS VWAP", BAL.SUBS[0], BAL.SUBS[0]], "exit_304": ["VWAP", "", ""],
                       "unit_304": [-5.0, 0.0, 0.0], "L": [0.0] * 3, "inR": [True, False, False]})
    W = SimpleNamespace(L=pd.Series([5.0, -5.0, 1.0], index=d), line=pd.Series([-5.0, 5.0, 1.0], index=d),
                        inR=pd.Series([True, False, False], index=d))
    BAL.day_groups(wf, sp, W)
    row = [r for r in capsys.readouterr().out.splitlines() if "co-loss share (all WF days)" in r][0]
    assert "vs #304 0.250 $ / 0.500 count; vs L 0.250 $ / 0.500 count" in row    # W.L would give 0.750


# ------------------------------------------------------------------ the three-way split
def _split_world(P_small):
    A = _arrays(80, 8)
    S = BAL.build_bands(A, P_small)
    S.dt_pos = S.dt_pos.copy()
    S.vol_pct = S.vol_pct.copy()
    sis = [60, 61, 62, 63, 64]
    bal = np.zeros(S.ns, bool)
    bal[sis] = True
    bs = np.zeros(S.n, int)
    a, m = S.a, S.m
    bs[a[61] + m[61] - 1] = 1                                           # last bar only
    bs[a[62] + 50] = -1                                                 # short break blocked by skip_bot_short
    S.dt_pos[62] = 0.1
    S.vol_pct[62] = np.nan
    tr = pd.DataFrame({"si": [63, 64, 64], "entry_idx": [a[63] + 40, a[64] + 40, a[64] + 60],
                       "signal_idx": [a[63] + 39, a[64] + 39, a[64] + 59], "unit_usd": [100.0, -50.0, 300.0],
                       "exit_rule": ["session_last_bar", "close<vwap", "high>=stop"]})
    L = pd.Series(np.linspace(500, -500, S.ns), index=S.dates)        # negative on the five BALANCE days
    inR = pd.Series(np.arange(S.ns) % 2 == 0, index=S.dates)
    return S, bal, bs, tr, L, inR


def test_split3_groups_subsplit_and_share(P_small):
    S, bal, bs, tr, L, inR = _split_world(P_small)
    sp = BAL.split3(S, bal, bs, tr, L, inR, P_small)
    g = dict(zip(sp.si, sp["sub"]))
    assert g == {60: BAL.SUBS[0], 61: BAL.SUBS[2], 62: BAL.SUBS[1], 63: "BREAK-WIN", 64: "BREAK-LOSS VWAP"}
    q = sp[sp.group == "QUIET"]
    assert q["sub"].isin(BAL.SUBS[:3]).sum() == len(q) == 3
    assert sp.set_index("si").loc[64, "unit_304"] == 250.0
    rows, share = BAL.coloss_table(sp)
    allL = sp.L[sp.L < 0].sum()
    blL = sp.L[(sp.L < 0) & (sp.group == "BREAK-LOSS")].sum()
    assert allL < 0 and np.isclose(share, blL / allL) and 0 < share < 1
    assert rows[-1][1] == 5 and rows[-1][6] == 0.0                     # session-level #304 losing $: 64 nets +250


def test_split3_unexplained_block_and_early_signal_abort(P_small):
    S, bal, bs, tr, L, inR = _split_world(P_small)
    bs[S.a[62] + 50] = 1                                                # a LONG break that no gate blocks
    S.vol_pct[62] = 10.0
    with pytest.raises(SystemExit, match="do not explain"):
        BAL.split3(S, bal, bs, tr, L, inR, P_small)
    S, bal, bs, tr, L, inR = _split_world(P_small)
    tr.loc[0, "signal_idx"] = S.a[63] + 10                              # a #304 signal before 12:00 on a BALANCE day
    with pytest.raises(SystemExit, match="before 12:00"):
        BAL.split3(S, bal, bs, tr, L, inR, P_small)
    assert [BAL.exit_class(r) for r in ("close>vwap", "open<stop", "session_last_bar")] == ["VWAP", "STOP", "FLAT"]


# ------------------------------------------------------------------ Auto-Validate lattice (AMENDMENT 0 item 6)
def test_auto_validate_lattice_reaches_all_8_configs():
    from augur_engine.auto import _auto_space_from_params, _RandomSampler
    space = _auto_space_from_params(BAL.AV_SPACE)
    assert space == {"stretch_12ths": ("int", 6, 9, 1), "last_fill_min": ("int", 330, 360, 30)}
    sm = _RandomSampler(space, seed=42)
    seen = {(p["stretch_12ths"], p["last_fill_min"]) for p in (sm.ask() for _ in range(400))}
    assert seen == {(s, lf) for s in (6, 7, 8, 9) for lf in (330, 360)}
    assert {s for s, _ in seen} >= {6, 8}                                # both Stage A cells are on the lattice
    assert BAL.sig_last_for(360) == BAL.SIG_LAST


# ------------------------------------------------------------------ prereg pinning
_TEXT = "# T\n## AMENDMENT 0\nx\n## 3. Rules\nr\n## 4. Counts\nc\n## 6. Null\nn\n## 7. O\no\n## 8. Bars\nb\n## 9. D\nd\n"


def test_prereg_sections_and_check(tmp_path):
    sec = BAL.prereg_sections(_TEXT)
    assert sec == {3: "## 3. Rules\nr", 6: "## 6. Null\nn", 8: "## 8. Bars\nb"}
    p = tmp_path / "p.md"
    p.write_text(_TEXT, encoding="utf-8")
    h = BAL.prereg_hashes(str(p))
    ok = BAL.prereg_check(str(p), go_sha=h["sha256_lf"], sec_sha=h["sections_3_6_8_sha256"])
    assert not ok["whole_file_changed_since_go"]
    p.write_text(_TEXT + "## AMENDMENT 1\nnew counts\n", encoding="utf-8")          # an amendment elsewhere: reported
    ok = BAL.prereg_check(str(p), go_sha=h["sha256_lf"], sec_sha=h["sections_3_6_8_sha256"])
    assert ok["whole_file_changed_since_go"]
    p.write_text(_TEXT.replace("## 6. Null\nn", "## 6. Null\nn2"), encoding="utf-8")
    with pytest.raises(SystemExit, match="sections 3, 6 or 8 changed"):
        BAL.prereg_check(str(p), go_sha=h["sha256_lf"], sec_sha=h["sections_3_6_8_sha256"])


def test_pinned_sections_hash_matches_the_prereg_in_this_checkout():
    assert BAL.prereg_hashes()["sections_3_6_8_sha256"] == BAL.PREREG_SECTIONS_SHA


# ------------------------------------------------------------------ the loaders on synthetic files (pins patched to the fixtures)
def _sha(p):
    import hashlib
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def test_load_R_and_episodes(tmp_path, monkeypatch):
    bdays = pd.bdate_range("2024-01-02", periods=60)
    inR = np.zeros(60, bool)
    eps = [(bdays[3], bdays[7]), (bdays[20], bdays[22])]
    for s, e in eps:
        inR[(bdays >= s) & (bdays <= e)] = True
    rp = tmp_path / "residual_days.csv"
    pd.DataFrame({"date": bdays.strftime("%Y-%m-%d"), "in_R": inR}).to_csv(rp, index=False)
    ap = tmp_path / "a2.json"
    ap.write_text(json.dumps({"line_episodes": [[str(s.date()), str(e.date())] for s, e in eps], "c_res": 0.264}))
    monkeypatch.setattr(BAL, "RESID_SHA", _sha(rp))
    monkeypatch.setattr(BAL, "R_DAYS", int(inR.sum()))
    monkeypatch.setattr(BAL, "R_EPIS", 2)
    r, got, _ = BAL.load_R(bdays, str(rp), str(ap))
    assert r.sum() == 8 and got == eps
    ap.write_text(json.dumps({"line_episodes": [[str(bdays[3].date()), str(bdays[6].date())],
                                                [str(bdays[20].date()), str(bdays[22].date())]], "c_res": 0.264}))
    with pytest.raises(SystemExit, match="union"):
        BAL.load_R(bdays, str(rp), str(ap))
    monkeypatch.setattr(BAL, "RESID_SHA", "0" * 64)
    with pytest.raises(SystemExit, match="sha256"):
        BAL.load_R(bdays, str(rp), str(ap))
    ep = tmp_path / "episodes.csv"
    pd.DataFrame({"start": ["2024-01-05", "2024-02-01"], "end": ["2024-01-10", "2024-02-02"]}).to_csv(ep, index=False)
    monkeypatch.setattr(BAL, "DD_EPIS", 2)
    monkeypatch.setattr(BAL, "DD_DAYS", 6)
    e2, mask = BAL.load_episodes(bdays, str(ep))
    assert len(e2) == 2 and mask.sum() == 6
    pd.DataFrame({"start": ["2025-06-27"], "end": ["2025-07-02"]}).to_csv(ep, index=False)
    with pytest.raises(SystemExit, match="after 2025-06-29"):
        BAL.load_episodes(bdays, str(ep))


def test_load_L_pins_and_parity(tmp_path, monkeypatch):
    bdays = pd.bdate_range("2016-07-01", periods=300)
    rng = np.random.default_rng(3)
    B = pd.Series(np.round(rng.normal(100, 800, 300), 2), index=bdays)
    RES = np.round(rng.normal(10, 300, 300), 6)
    rp = tmp_path / "res.csv"
    pd.DataFrame({"date": bdays.strftime("%Y-%m-%d"), "book_mtm": B.to_numpy(), "RES": RES, "RAW": RES}).to_csv(rp, index=False)
    L = B.to_numpy() + 0.264 * RES
    lp = tmp_path / "line.csv"
    pd.DataFrame({"date": bdays.strftime("%Y-%m-%d"), "line": L, "book": B.to_numpy(), "res_c": 0.264 * RES}).to_csv(lp, index=False)
    st = BAL.own(L, bdays)
    monkeypatch.setattr(BAL, "RES_SHA", _sha(rp))
    monkeypatch.setattr(BAL, "LINE_FACTS", (st["roc"], st["sort"]))
    Lg, R, line, st2, dmax = BAL.load_L(B, str(rp), str(lp))
    assert np.allclose(Lg.to_numpy(), L) and dmax == 0.0 and abs(st2["roc"] - st["roc"]) < 1e-12
    monkeypatch.setattr(BAL, "LINE_FACTS", (st["roc"] + 1.0, st["sort"]))
    with pytest.raises(SystemExit, match="L PARITY FAILED"):
        BAL.load_L(B, str(rp), str(lp))
    monkeypatch.setattr(BAL, "LINE_FACTS", (st["roc"], st["sort"]))
    with pytest.raises(SystemExit, match="differs from #463 .* over the house \\$1"):
        BAL.load_L(B + 5.0, str(rp), str(lp))
    # one tolerance on #463 vs the file's book (the house $1): a 40-cent gap on one row (another build window) passes,
    # L is built on B, and line.csv is checked against the RES file's own columns to the cent
    B2 = B.copy()
    B2.iloc[100] += 0.40
    Lg, _, line, _, dmax = BAL.load_L(B2, str(rp), str(lp))
    assert abs(dmax - 0.40) < 1e-9 and abs(Lg.iloc[100] - (L[100] + 0.40)) < 1e-9 and np.allclose(line.to_numpy(), L)
    bad = pd.read_csv(lp)
    bad.loc[5, "book"] += 0.02
    bad.to_csv(lp, index=False)
    with pytest.raises(SystemExit, match="line.csv book is not the RES file's book_mtm"):
        BAL.load_L(B, str(rp), str(lp))
    bad.loc[5, "book"] -= 0.02
    bad.loc[7, "line"] += 0.02
    bad.to_csv(lp, index=False)
    with pytest.raises(SystemExit, match="line.csv line is not book_mtm"):
        BAL.load_L(B, str(rp), str(lp))


def test_index_checks_on_the_real_calendar_shape(monkeypatch):
    bd = pd.bdate_range("2016-07-01", "2025-06-27")
    sund = pd.date_range("2016-07-03", "2025-06-29", freq="W-SUN")[-280:]
    idx = bd.union(sund)
    v = np.full(len(idx), 100.0)
    v[(idx >= "2020-03-03") & (idx <= "2020-03-27")] = -3000.0
    monkeypatch.setattr(BAL, "N_INDEX", len(idx))
    bdays, years, n = BAL.index_checks(pd.Series(v, index=idx))
    assert n == 280 and abs(years - 8.994) < 5e-4
    v[(idx >= "2022-05-02") & (idx <= "2022-07-29")] = -3000.0          # a deeper drawdown elsewhere aborts
    with pytest.raises(SystemExit, match="worst WF drawdown"):
        BAL.index_checks(pd.Series(v, index=idx))


def test_disperse_coverage_and_terciles(tmp_path):
    days = pd.bdate_range("2024-01-02", periods=80)
    rng = np.random.default_rng(9)
    rows = []
    for d in days:
        for s in ("S%d" % i for i in range(5)):
            for hm, col in ((570, "o"), (595, "c")):
                if d == days[70] and s in ("S3", "S4") and hm == 595:
                    continue                                              # 3 of 6 members: under the 80% guard
                t = (pd.Timestamp(d.date()).tz_localize(TZ) + pd.Timedelta(minutes=hm)).tz_convert("UTC")
                px = 100 * (1 + rng.normal(0, 0.01)) if hm == 595 else 100.0
                rows.append({"symbol": s, "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px, "c": px,
                             "day": d.strftime("%Y-%m-%d")})
    rows.append({"symbol": "S0", "t": "2025-07-01T13:30:00Z", "o": 1.0, "c": 1.0, "day": "2025-07-01"})   # after the cut
    ob = tmp_path / "open_bars.csv"
    pd.DataFrame(rows).to_csv(ob, index=False)
    nd = tmp_path / "ndx.csv"
    pd.DataFrame({"ticker": ["S%d" % i for i in range(6)], "from": "2024-01-01", "to": ""}).to_csv(nd, index=False)
    lab, dropped = BAL.disperse(str(ob), str(nd))
    assert dropped == 1 and days[70] not in lab.index and lab.index.max() <= BAL.CUT
    assert (lab.iloc[:60] == "unlabelled").all() and lab.iloc[60:].isin(["low", "mid", "high"]).all()
    o = pd.DataFrame(rows[:-1])
    o = o[o.t.str.endswith(("14:30:00Z", "13:30:00Z"))].set_index(["day", "symbol"])["o"]
    c = pd.DataFrame(rows[:-1])
    c = c[c.t.str.endswith(("14:55:00Z", "13:55:00Z"))].set_index(["day", "symbol"])["c"]
    disp = (c / o.reindex(c.index) - 1).groupby(level=0).std(ddof=1)
    disp = disp[[d != days[70].strftime("%Y-%m-%d") for d in disp.index]]
    v = disp.to_numpy()
    p = 100 * np.mean(v[:65] < v[65])
    want = "low" if p < 33.3 else ("mid" if p < 66.7 else "high")
    assert lab.iloc[65] == want


def _tercile(p):
    return "low" if p < 33.3 else ("mid" if p < 66.7 else "high")


def test_disperse_window_is_the_prior_sessions(tmp_path, monkeypatch):
    """The rank window is the prior N SESSIONS (a guard-dropped day is a session without a value), not the prior N kept
    days; the minimum counts values inside that window."""
    days = pd.bdate_range("2024-01-02", periods=35)
    rng = np.random.default_rng(10)
    rows, ret = [], {}
    for d in days:
        r = []
        for s in ("S%d" % i for i in range(5)):
            c = 100 * (1 + rng.normal(0, 0.01))
            for hm, px in ((570, 100.0), (595, c)):
                if d == days[20] and s in ("S3", "S4") and hm == 595:
                    continue                                              # 3 of 5 members: under the 80% guard
                t = (pd.Timestamp(d.date()).tz_localize(TZ) + pd.Timedelta(minutes=hm)).tz_convert("UTC")
                rows.append({"symbol": s, "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px, "c": px,
                             "day": d.strftime("%Y-%m-%d")})
            r.append(c / 100.0 - 1.0)
        ret[d] = float(np.std(r, ddof=1))
    ob = tmp_path / "open_bars.csv"
    pd.DataFrame(rows).to_csv(ob, index=False)
    nd = tmp_path / "ndx.csv"
    pd.DataFrame({"ticker": ["S%d" % i for i in range(5)], "from": "2024-01-01", "to": ""}).to_csv(nd, index=False)
    monkeypatch.setattr(BAL, "DISP_WIN", 10)
    monkeypatch.setattr(BAL, "DISP_MIN", 9)
    lab, dropped = BAL.disperse(str(ob), str(nd))
    assert dropped == 1 and days[20] not in lab.index and len(lab) == 34
    v21 = ret[days[21]]
    prior = [ret[days[i]] for i in range(11, 20)]                       # sessions 11..20; 20 has no value
    assert lab[days[21]] == _tercile(100 * np.mean(np.array(prior) < v21))
    assert lab[days[10]] == _tercile(100 * np.mean(np.array([ret[days[i]] for i in range(10)]) < ret[days[10]]))
    monkeypatch.setattr(BAL, "DISP_MIN", 10)                             # 9 values in the window: unlabelled
    lab, _ = BAL.disperse(str(ob), str(nd))
    assert lab[days[21]] == "unlabelled" and lab[days[30]] == "unlabelled" and lab[days[31]] != "unlabelled"


# ------------------------------------------------------------------ offline smoke: every mode's code path on a SYNTHETIC world
def _smoke_world(monkeypatch, tmp_path):
    """Every loader replaced by synthetic data (no master, crown, R / L / RES, roll or open-bar file is read) -> W."""
    monkeypatch.setattr(BAL, "MODE", None)
    monkeypatch.setattr(BAL, "CACHE", str(tmp_path / "cache"))
    A = {"NQ": _arrays(230, 31, px0=5000.0, start="2016-01-04", half={150}),
         "ES": _arrays(230, 32, px0=2000.0, start="2016-01-04", sd=0.0014)}
    P = BAL.frozen()
    last = BAL.naive(A["NQ"]["index"])[-1].normalize()
    bdays = pd.bdate_range(BAL.WF0, last)
    rng = np.random.default_rng(5)
    B = pd.Series(rng.normal(150, 900, len(bdays)), index=bdays)
    RES = pd.Series(rng.normal(20, 400, len(bdays)), index=bdays)
    L = B + BAL.RES_W * RES
    inR = pd.Series(np.zeros(len(bdays), bool), index=bdays)
    R_eps = [(bdays[10], bdays[25]), (bdays[60], bdays[70])]
    for s, e in R_eps:
        inR[(bdays >= s) & (bdays <= e)] = True
    D_eps = [(bdays[30], bdays[40])]
    S0 = BAL.build_bands(A["NQ"], P)
    t0 = BAL.run_304(A["NQ"], P, S0)
    noise = pd.DataFrame({"entry": t0.entry_stamp, "exit": t0.exit_stamp, "side": t0.side,
                          "pnl_usd": 20 * t0.raw_pts - 10.66, "size": 1.0})
    noise["unit_usd"] = noise.pnl_usd
    days = BAL.naive(A["NQ"]["index"]).normalize().unique()
    orb = pd.DataFrame({"entry": days + pd.Timedelta(minutes=580), "exit": days + pd.Timedelta(minutes=660), "side": 1})
    enq = pd.DataFrame({"entry": days[::2] + pd.Timedelta(minutes=480), "exit": days[::2] + pd.Timedelta(minutes=900),
                        "side": -1})
    crowns = {"NOISE422": noise, "NOISE382": noise, "ORB314": orb, "ENGUQ335": enq}
    sw = pd.DataFrame({"switch_et": pd.to_datetime(["2016-03-10 20:00", "2016-09-08 20:00", "2016-11-03 20:00"]),
                       "offset_pts": [-1.5, 3.0, 4.0], "kind": "mid_session", "old": "a", "new": "b"})
    n_wf = int(((t0.signal_date >= BAL.WF0) & (t0.signal_date <= BAL.WF1)).sum())
    monkeypatch.setattr(BAL, "N_PARITY", n_wf)
    monkeypatch.setattr(BAL, "N_WF_SWITCHES", 2)
    monkeypatch.setattr(BAL, "load_master", lambda inst, *a, **k: A[inst])
    monkeypatch.setattr(BAL, "load_rolls", lambda inst, path=None: sw.copy())
    monkeypatch.setattr(BAL, "load_crown", lambda name, path=None: crowns[name].copy())
    monkeypatch.setattr(BAL.HH, "book", lambda: (B, {"roc": 93.81, "sort": 3.816}))
    monkeypatch.setattr(BAL, "index_checks", lambda b: (bdays, (bdays[-1] - bdays[0]).days / 365.25, 0))
    monkeypatch.setattr(BAL, "load_L", lambda b: (L, RES, L.copy(), {"roc": 120.82, "sort": 3.916}, 0.0))
    monkeypatch.setattr(BAL, "load_R", lambda b: (inR, R_eps, {}))
    monkeypatch.setattr(BAL, "load_episodes", lambda b: (D_eps, np.asarray((bdays >= D_eps[0][0]) & (bdays <= D_eps[0][1]))))
    monkeypatch.setattr(BAL, "book_leg_dailies", lambda b, BB: {k: B * w for k, w in
                                                                (("ORB", 0.3), ("ENGUQ", 0.3), ("TTM", 0.2), ("NOISE", 0.2))})
    monkeypatch.setattr(BAL, "disperse", lambda *a, **k: (pd.Series(np.resize(["low", "mid", "high"], len(bdays)),
                                                                     index=bdays), 0))
    monkeypatch.setattr(BAL, "ttm_trades", lambda: [])
    monkeypatch.setattr(BAL, "sha_bytes", lambda p: "synthetic")
    W = BAL.setup()
    assert W.par["matched"] == n_wf and W.par["max_diff"] <= 1e-9
    return W


def test_offline_smoke_all_modes_on_a_synthetic_world(monkeypatch, tmp_path, capsys):
    """The mode FUNCTIONS (not the CLI) run end to end with _FROZEN on the synthetic world, so the printing / writing
    paths and the by-construction asserts (zero NOISE overlap, QUIET explained, eligible-break parity) are exercised.
    Its numbers mean nothing."""
    W = _smoke_world(monkeypatch, tmp_path)
    monkeypatch.setattr(BAL, "MODE", "counts")
    BAL.mode_counts(W)
    out_counts = capsys.readouterr().out
    assert "THREE-WAY SPLIT" in out_counts and "total trades" not in out_counts.split("(no BALANCE exit was run")[0]
    monkeypatch.setattr(BAL, "MODE", "power")
    BAL.mode_power(W)
    out_power = capsys.readouterr().out
    assert "(no real direction was computed for display)" in out_power and "POWER LINES" in out_power
    # --power prints no per-year trade counts and no session counts (they print in the real run, bar 6)
    assert "per July-June year" not in out_power and "B1 SCHEDULE" not in out_power
    ov_rows = [r for r in out_power.splitlines() if "crown-flat" in r]
    assert ov_rows and not any("sessions" in r for r in ov_rows)
    with open(tmp_path / "cache" / "power.json", encoding="utf-8") as f:
        assert "B1_n_per_year" not in json.load(f)
    assert "sessions" not in pd.read_csv(tmp_path / "cache" / "overlap.csv").columns
    monkeypatch.setattr(BAL, "MODE", "run")
    BAL.mode_run(W)
    out_run = capsys.readouterr().out
    assert "STAGE A:" in out_run and "ES TRANSFER REPORT" in out_run and "BAND TWINS" in out_run
    assert out_run.index("POWER LINES") < out_run.index("CELLS (WF") < out_run.index("STAGE A:")
    assert out_run.index("STAGE A:") < out_run.index("SECTION 9 DIAGNOSTICS") < out_run.index("ES TRANSFER REPORT")
    assert "cost curve (NQ points" in out_run and "house 0.533" in out_run and "MNQ 1.200" in out_run
    assert "cost curve (ES points" in out_run and "house 0.363" in out_run and "MES 0.630" in out_run
    es_rows = [r for r in out_run.splitlines() if "cost curve (ES points" in r]
    assert es_rows and not any("0.533" in r or "1.200" in r for r in es_rows)
    cache = tmp_path / "cache"
    for f in ("counts_by_year.csv", "split3_days.csv", "power.json", "null_maxima.csv", "overlap.csv", "manifest.json",
              "trades_NQ_B1.csv", "trades_NQ_B2.csv", "trades_ES_B1.csv", "daily_NQ_B1.csv", "daily_ES_B2.csv",
              "trades_NQ_B1_twin20.csv", "daily_NQ_B1_twin60.csv"):
        assert (cache / f).exists(), f
    tr = pd.read_csv(cache / "trades_NQ_B1.csv")
    assert list(tr.columns[:15]) == BAL.TRADE_COLS
    assert len(pd.read_csv(cache / "null_maxima.csv")) == BAL.DRAWS
    with open(cache / "manifest.json", encoding="utf-8") as f:
        man = json.load(f)
    assert man["prereg"]["sections_3_6_8_sha256"] == BAL.PREREG_SECTIONS_SHA and "verdict" in man
    passed = man["verdict"]["passed"]
    assert man["auto_validate_space"]["stretch_12ths"]["default"] == (dict(BAL.CELLS)[passed[0]] if passed else None)


def test_run_aborts_before_direction_and_writes_the_verdict_before_reports(monkeypatch, tmp_path, capsys):
    """(a) An ES load / parity abort (or any other load) stops the real run BEFORE a cell row prints, so a re-run is
    clean. (b) A section 9 report failure after the verdict cannot hide it: the verdict line, the NQ trade / daily /
    twin files and manifest.json are on disk first (the ES files follow the NQ reports)."""
    W = _smoke_world(monkeypatch, tmp_path)
    monkeypatch.setattr(BAL, "MODE", "power")
    BAL.mode_power(W)
    capsys.readouterr()
    monkeypatch.setattr(BAL, "MODE", "run")
    orig = BAL.prepare

    def es_aborts(inst, P):
        if inst == "ES":
            raise SystemExit("ES: 35 roll switches in WF, not 36 - abort")
        return orig(inst, P)

    monkeypatch.setattr(BAL, "prepare", es_aborts)
    with pytest.raises(SystemExit, match="ES: 35 roll switches"):
        BAL.mode_run(W)
    out = capsys.readouterr().out
    assert "CELLS (WF" not in out and "STAGE A:" not in out and "BARS B1" not in out
    cache = tmp_path / "cache"
    assert not (cache / "manifest.json").exists() and not (cache / "trades_NQ_B1.csv").exists()
    monkeypatch.setattr(BAL, "prepare", orig)

    def diag_aborts(*a, **k):
        raise SystemExit("a section 9 report failed")

    monkeypatch.setattr(BAL, "diagnostics", diag_aborts)
    with pytest.raises(SystemExit, match="section 9 report failed"):
        BAL.mode_run(W)
    out = capsys.readouterr().out
    assert "STAGE A:" in out
    for f in ("manifest.json", "trades_NQ_B1.csv", "trades_NQ_B2.csv", "daily_NQ_B1.csv", "trades_NQ_B1_twin40.csv"):
        assert (cache / f).exists(), f
    assert not (cache / "trades_ES_B1.csv").exists()
