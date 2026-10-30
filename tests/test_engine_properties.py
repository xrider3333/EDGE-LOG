"""C10 (AUTOMATIONS.md): property tests on engine rules, over many seeded random cases.

1. Folds: the walk-forward test slices tile the out-of-sample stretch exactly - no gap, no
   overlap, sum = n - init - and no fold trains on its own test bars.
2. Flat at close: with flat_eod on, every trade enters and exits on the same session.
3. No fill before signal: replace every bar from k on (k random, mid-session too) - every
   entry before k (bar, side, fill price) and every trade closed before k must be unchanged
   (the strategy cannot see the future), and each fill price sits inside its bar's range.
No hypothesis package on this machine, so cases come from numpy seeds (reproducible).
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from augur_engine.auto import wf_fold_specs  # noqa: E402
from augur_engine.engine import load_strategy  # noqa: E402

BARS_PER_DAY = 78          # 5m RTH
SEEDS = range(6)
CUTS_PER_TAPE = 8

# (file, params) - params keep each file on its live-legal path (ORB_3_0 refuses
# vol_filter without close_confirm: its look-ahead guard)
STRATS = [
    ("ORB_3_0.py", {"vol_filter": 0.0}),
    ("ORB_3_0.py", {"vol_filter": 1.2, "close_confirm": True, "target_R": 2.0}),
    ("ORB_3_6.py", {}),
    ("ORB_3_9.py", {}),
    ("NOISE_1_0.py", {}),
    ("NOISE_1_1_BASE.py", {}),
]


def _bars(seed, days=80):          # > the 44-session NOISE lookback
    rng = np.random.default_rng(seed)
    n = days * BARS_PER_DAY
    c = 15000 + np.cumsum(rng.normal(0, 6, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 1.5, n)
    h = np.maximum(o, c) + rng.exponential(3, n)
    l = np.minimum(o, c) - rng.exponential(3, n)
    v = rng.integers(500, 5000, n).astype(float)
    did = np.repeat(np.arange(days), BARS_PER_DAY)
    return o, h, l, c, v, did


def _trades(mod, bars, params):
    o, h, l, c, v, did = bars
    out = mod.run_backtest(o, h, l, c, volumes=v, day_id=did, return_trades=True, **params)
    if out is None:
        pytest.skip("strategy declined these params")
    return [tuple(t) for t in out.get("trades") or []]


# ── 1. folds ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("rolling", [False, True])
def test_folds_tile_the_oos_stretch(rolling):
    rng = np.random.default_rng(7)
    cases = [(int(n), int(k)) for n, k in zip(rng.integers(4000, 400_000, 300), rng.integers(0, 12, 300))]
    cases += [(4000, 0), (4001, 2), (4007, 8), (24000, 1), (99_999, 9)]
    for n, k in cases:
        specs = wf_fold_specs(n, k, rolling)
        init = int(n * 0.40)
        assert 2 <= len(specs) <= 8, (n, k)
        assert [s[0] for s in specs] == list(range(len(specs)))
        assert specs[0][3] == init and specs[-1][4] == n, (n, k)
        assert sum(te - ts for _, _, _, ts, te in specs) == n - init, (n, k)
        for (_, _, _, _, te), (_, _, _, ts2, _) in zip(specs, specs[1:]):
            assert te == ts2, (n, k)                      # contiguous, no gap/overlap
        for _, tr_s, tr_e, ts, te in specs:
            assert 0 <= tr_s < tr_e <= ts < te <= n, (n, k)   # train never reaches the test
            assert tr_s == (tr_e - init if rolling else 0), (n, k)


# ── 2. flat at close + 3. no fill before signal ─────────────────────────────────
@pytest.mark.parametrize("fname,params", STRATS, ids=lambda x: x if isinstance(x, str) else "")
def test_flat_at_close_and_fill_inside_bar(fname, params):
    mod = load_strategy(fname)
    seen = 0
    for seed in SEEDS:
        bars = _bars(seed)
        o, h, l, c, v, did = bars
        for t in _trades(mod, bars, params):
            ei, xi, _pnl, side, px = t[:5]
            assert 0 <= ei <= xi < len(c), (fname, seed, t)
            assert did[ei] == did[xi], ("held overnight", fname, seed, t)
            assert side in (1, -1), (fname, seed, t)
            assert l[ei] - 1e-9 <= px <= h[ei] + 1e-9, ("fill outside its bar", fname, seed, t)
            seen += 1
    assert seen > 0, f"{fname}: no trades on {len(SEEDS)} random tapes - property never exercised"


@pytest.mark.parametrize("fname,params", STRATS, ids=lambda x: x if isinstance(x, str) else "")
def test_future_bars_cannot_change_past_trades(fname, params):
    mod = load_strategy(fname)
    checked = 0
    for seed in SEEDS:
        bars = _bars(seed)
        o, h, l, c, v, did = bars
        full = _trades(mod, bars, params)
        rng = np.random.default_rng(1000 + seed)
        # cuts mid-session too: most leaks peek one or two bars ahead inside the day
        for k in rng.integers(50 * BARS_PER_DAY, len(c) - 2, CUTS_PER_TAPE):
            k = int(k)
            alt = _bars(500 + seed + k)
            shift = c[k - 1] - alt[3][k - 1]                # keep the price level continuous
            mixed = tuple(np.r_[a[:k], b[k:] + (shift if i < 4 else 0)]
                          for i, (a, b) in enumerate(zip(bars[:5], alt[:5]))) + (did,)
            base = [t for t in full if t[1] < k]
            got = _trades(mod, mixed, params)
            other = [t for t in got if t[1] < k]
            assert base == other, ("closed trade changed", fname, seed, k)
            # an entry at bar < k (its side and fill price) is decided before bar k exists
            ent = lambda ts: [(t[0], t[3], t[4]) for t in ts if t[0] < k]
            assert ent(full) == ent(got), ("entry changed", fname, seed, k)
            checked += len(base)
    assert checked > 0, f"{fname}: no trades closed before the cut - property never exercised"
