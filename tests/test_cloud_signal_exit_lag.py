"""Tests for the 2026-09-22 exit-lag fix in api/cloud_signal.py's run_leg_trades().

THE BUG. Every strategy plugin the live QQQ/Webull paper book runs (NOISE_1_1_NBHD.py
-> NOISE_1_0.py "STEP E"; ORB_3_6_R6.py -> ORB_3_6.py "EOD flat"; ENGUQ_1M_ETH_R2_1_0.py's
end-of-walk block, and its compiled twin in augur_engine/fastloop.py's _walk_jit) force-
closes a position that is still open when the data it was handed runs out, and logs that
synthetic exit at the NEWEST bar's own close. run_leg_trades used to read
`exit_bar >= n_bars - 1` alone as "still open", which made a GENUINE exit that happens to
land on the newest bar (a stop fill, a band cross, a queued open fill, ...) indistinguishable
from one of these data-end guesses -- so every real exit on the newest bar was held back a
full bar and then collided with whatever entered next.

THE FIX. exit_bar == n_bars - 1 is now resolved by price: it reads as CLOSED when the
reported exit price differs from the newest bar's close by more than a tiny relative
tolerance, and as still OPEN only when it matches that close (the data-end guess's only
possible value). exit_bar < n_bars - 1 is untouched.

Two ways of exercising this, per the module's own existing test conventions (see
tests/test_cloud_signal.py): (1) run_leg_trades() called directly against a stub
strategy module that returns fixed, hand-crafted (entry_bar, exit_bar, pnl_pts, side,
entry_px) tuples -- the exact contract every plugin's return_trades=True path uses --
which pins down the price-vs-boundary logic in isolation; (2) the full step() diff/
idempotency pipeline with a stub keyed off len(closes), which proves the fix does not
disturb the EXIT-before-ENTRY ordering a downstream executor depends on when the two
share a tick.
"""
import os
import types

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs


# ── Direct run_leg_trades() unit tests: (a)/(b)/(c) ─────────────────────────────────────

def _arrays(closes, base=None, freq="5min"):
    """A minimal `arrays` dict shaped like tools/qqq_paper.py's build_arrays() output --
    the only things run_leg_trades reads off it for a stub strategy that ignores the
    OHLC it is handed: 'close' (n_bars and the newest bar's own price) and 'index'
    (entry_time / exit_time)."""
    n = len(closes)
    base = base or pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ)
    idx = pd.date_range(base, periods=n, freq=freq)
    c = np.asarray(closes, dtype=float)
    return {
        "open": c.copy(), "high": c.copy(), "low": c.copy(), "close": c,
        "volume": np.full(n, 1000.0),
        "day_id": np.zeros(n, dtype="int64"),
        "index": idx,
    }


def _tuple_stub(trades):
    """A strategy stub that ignores the OHLC arrays it is handed and always returns a
    FIXED, hand-crafted trade-tuple list -- lets a test dial in the exact
    exit_bar/price combination it wants to probe, decoupled from any real strategy's
    bar-by-bar mechanics. Same (entry_bar, exit_bar, pnl_pts, side, entry_px) contract
    tests/test_cloud_signal.py's own stub uses."""
    mod = types.ModuleType("exit_lag_tuple_stub")
    mod.STRATEGY_NAME = "EXIT_LAG_TUPLE_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        n = len(trades)
        wins = sum(1 for t in trades if t[2] > 0)
        return {"trades": list(trades) if return_trades else None, "num_trades": n,
               "total_pnl": sum(t[2] for t in trades), "win_rate": (wins / n) if n else 0,
               "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": wins,
               "losses": n - wins}

    mod.run_backtest = run_backtest
    return mod


def _cfg(trades):
    return {"strategy": _tuple_stub(trades), "params": {}}


@pytest.mark.parametrize("side", [1, -1])
def test_exit_on_newest_bar_at_a_different_price_is_reported_closed(side):
    """(a) THE FIX: a trade whose exit lands on the newest bar at a price that is NOT
    that bar's own close -- e.g. a stop fill, a band cross, a queued open fill -- must
    be reported closed, not held back as a data-end guess."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    entry_px = 701.0
    true_exit_px = 703.25                      # NOT closes[-1] (704.5)
    pnl = (true_exit_px - entry_px) if side > 0 else (entry_px - true_exit_px)
    trades = [(1, 4, pnl, side, entry_px)]

    out = cs.run_leg_trades(_cfg(trades), arrays)

    assert len(out) == 1
    t = out[0]
    assert t["still_open"] is False
    assert t["exit_time"] == arrays["index"][4].isoformat()
    assert t["exit_px"] == pytest.approx(true_exit_px)


@pytest.mark.parametrize("side", [1, -1])
def test_eod_backstop_at_the_last_close_is_still_reported_open(side):
    """(b) A plugin-forced open position -- marked at EXACTLY the newest bar's close,
    the data-end fallback every plugin uses -- must still be reported open. This is
    the ambiguous case the fix has to preserve, not just the unambiguous one in (a)."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    entry_px = 701.0
    true_exit_px = closes[-1]                  # exactly the newest bar's close
    pnl = (true_exit_px - entry_px) if side > 0 else (entry_px - true_exit_px)
    trades = [(1, 4, pnl, side, entry_px)]

    out = cs.run_leg_trades(_cfg(trades), arrays)

    assert len(out) == 1
    t = out[0]
    assert t["still_open"] is True
    assert t["exit_time"] is None
    assert t["exit_px"] is None


def test_trade_closed_before_the_newest_bar_is_unaffected():
    """(c) exit_bar < n_bars - 1 must behave exactly as before the fix -- including the
    coincidental case where the exit price happens to equal THAT bar's own close, which
    is unambiguous either way because a newer bar exists after it."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    entry_px = 701.0
    exit_px = closes[2]                        # happens to equal bar 2's own close
    trades = [(1, 2, exit_px - entry_px, 1, entry_px)]

    out = cs.run_leg_trades(_cfg(trades), arrays)

    assert len(out) == 1
    t = out[0]
    assert t["still_open"] is False
    assert t["exit_time"] == arrays["index"][2].isoformat()
    assert t["exit_px"] == pytest.approx(exit_px)


def test_mixed_batch_each_trade_judged_on_its_own_terms():
    """Sanity check that the newest bar's close is captured once per call and applied
    correctly to EVERY trade in a batch: an early, unambiguous close; a genuine close
    on the newest bar at a different price; and a data-end guess on the newest bar, all
    in the same run_leg_trades() call."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    trades = [
        (0, 1, 1.0, 1, 700.0),                        # closed well before the boundary
        (2, 4, 704.0 - 702.5, 1, 702.5),              # genuine close on the newest bar, NOT its close (704.5)
        (3, 4, closes[-1] - 703.5, 1, 703.5),         # data-end guess on the newest bar
    ]

    out = cs.run_leg_trades(_cfg(trades), arrays)

    assert [t["still_open"] for t in out] == [False, False, True]
    assert out[1]["exit_px"] == pytest.approx(704.0)
    assert out[2]["exit_px"] is None


# ── eod_marks_at_close safety flag: the ORB partial-exit-blend hazard ───────────────────
# ORB_3_6.py:346-350's EOD-flat block reports a 50/50 blend of the partial-exit price and
# the final close instead of a clean close whenever a partial exit already fired (p_done,
# gated on `partial_exit_R > 0` at ORB_3_6.py:320/338). Under the price test that blend
# would usually read as a genuine close, flattening a position that is actually still
# open. It is inert only because the live ORB_314 params pin partial_exit_R=0.0
# (api/paper.py:177-180) -- a params change must not silently arm it, so run_leg_trades
# checks cfg["params"]["partial_exit_R"] itself rather than trusting that it stays zero.

def test_partial_exit_r_active_keeps_the_old_conservative_rule_even_with_a_differing_price():
    """A leg whose declared params turn on ORB's partial-exit blend cannot trust the
    boundary price at all: even a price that looks unambiguously like a genuine close
    (the exact fixture from test (a)) must still read as open, because that same
    "unambiguous-looking" price is exactly what a 50/50 partial-exit blend produces."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    entry_px = 701.0
    true_exit_px = 703.25                        # looks unambiguous, same fixture as (a)
    trades = [(1, 4, true_exit_px - entry_px, 1, entry_px)]
    cfg = {"strategy": _tuple_stub(trades), "params": {"partial_exit_R": 2.5}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    t = out[0]
    assert t["still_open"] is True
    assert t["exit_px"] is None
    assert t["exit_time"] is None


def test_partial_exit_r_off_gets_the_price_based_fast_path():
    """The identical trade and leg shape, but with partial_exit_R explicitly 0 -- ORB_314's
    actual live value -- is exactly the safe case the fix targets: the differing price is
    trusted and the trade reads closed."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    entry_px = 701.0
    true_exit_px = 703.25
    trades = [(1, 4, true_exit_px - entry_px, 1, entry_px)]
    cfg = {"strategy": _tuple_stub(trades), "params": {"partial_exit_R": 0.0}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    t = out[0]
    assert t["still_open"] is False
    assert t["exit_px"] == pytest.approx(true_exit_px)
    assert t["exit_time"] is not None


def test_eod_marks_at_close_escape_hatch_is_explicit_and_one_directional():
    """The manual escape hatch (for a future plugin that folds size into pnl_pts, e.g.
    NOISE_1_8_CT304.py -- see the SYNTHETIC EXIT PRICE comment in run_leg_trades) forces
    the same old rule as partial_exit_R does, independently of it. And the flag is not a
    two-way override: an explicit True must NOT be able to waive the partial_exit_R
    check -- only the strategy's own declared params can prove the boundary price safe."""
    closes = [700.0, 701.0, 702.0, 703.0, 704.5]
    arrays = _arrays(closes)
    entry_px = 701.0
    true_exit_px = 703.25
    trades = [(1, 4, true_exit_px - entry_px, 1, entry_px)]

    explicit_false = {"strategy": _tuple_stub(trades), "params": {},
                      "eod_marks_at_close": False}
    assert cs.run_leg_trades(explicit_false, arrays)[0]["still_open"] is True

    explicit_true_but_partial_exit_on = {"strategy": _tuple_stub(trades),
                                         "params": {"partial_exit_R": 1.0},
                                         "eod_marks_at_close": True}
    assert cs.run_leg_trades(explicit_true_but_partial_exit_on, arrays)[0]["still_open"] is True


# ── End-to-end step() test: (d) same-tick EXIT-before-ENTRY ordering ────────────────────

def _paired_stub():
    """Models the 2026-09-22 scenario end to end, through the real step()/_diff_leg
    pipeline rather than run_leg_trades() in isolation: an older trade (A) sits at the
    data boundary looking ambiguously open (force-closed at the newest bar's own close)
    until one more bar arrives and resolves it as a genuine mid-session close -- on
    that SAME bar a brand new position (B) enters, and is now itself the fresh
    ambiguous trade sitting at the new boundary. A synthetic model of the mechanism
    (branches on len(closes), the same technique tests/test_cloud_signal.py's own
    _stub_module uses), not any one plugin's bar-by-bar rules."""
    mod = types.ModuleType("cloud_signal_paired_stub")
    mod.STRATEGY_NAME = "PAIRED_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        n = len(closes)
        trades = []
        if n == 3:
            # A is discovered, ambiguously open at the (then) boundary bar 2 -- a plain
            # data-end guess, marked at that bar's own close.
            entry_a = float(opens[1])
            exit_a = float(closes[2])                   # == newest close -> ambiguous/open
            trades.append((1, 2, exit_a - entry_a, 1, entry_a))
        elif n >= 4:
            # Bar 3 arrives. It reveals A actually closed INTRABAR on bar 3 (a stop/band
            # touch at that bar's OPEN, not its close) -- STILL exactly at the boundary,
            # so only the price test, not the bar index, can tell this apart from a fresh
            # data-end guess: the old `exit_bar >= n_bars - 1` rule alone would have kept
            # calling this "open" forever. B fills on that SAME bar at the SAME price (the
            # same-bar stop-out-then-re-entry mechanism NOISE_1_0.py documents) and is
            # itself the new ambiguous trade sitting at the (new) boundary.
            entry_a = float(opens[1])
            exit_a = float(opens[3])                     # off bar 3's close -> unambiguous
            trades.append((1, 3, exit_a - entry_a, 1, entry_a))
            entry_b = float(opens[3])
            exit_b = float(closes[n - 1])                # == newest close -> ambiguous/open
            trades.append((3, n - 1, exit_b - entry_b, 1, entry_b))
        n_t = len(trades)
        wins = sum(1 for t in trades if t[2] > 0)
        return {"trades": trades if return_trades else None, "num_trades": n_t,
               "total_pnl": sum(t[2] for t in trades), "win_rate": (wins / n_t) if n_t else 0,
               "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": wins,
               "losses": n_t - wins}

    mod.run_backtest = run_backtest
    return mod


def _paired_epoch_df(base):
    times = [base + pd.Timedelta(minutes=i) for i in range(4)]
    epoch = [int(t.tz_convert("UTC").timestamp()) for t in times]
    closes = [700.0, 701.0, 702.0, 703.0]
    opens = [699.5, 700.5, 701.5, 702.5]
    return pd.DataFrame({
        "time": epoch,
        "open": opens,
        "high": [max(o, c) + 0.3 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.3 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1000.0] * 4,
    })


def test_same_tick_exit_then_entry_is_emitted_in_order(tmp_path):
    """(d) The 2026-09-22 collision, end to end. Trade A sits at the data boundary
    looking ambiguously open; one more bar arrives and reveals it actually closed
    INTRABAR right at that same (still current) boundary -- resolvable only by the
    price fix, since the bar index alone never stops looking like the boundary -- in
    the very same tick that a fresh trade B, filling on that identical bar, first
    becomes visible. The older trade's EXIT must still be ordered before the new
    trade's ENTRY: an executor that saw them the other way around would open the new
    position before flattening the old one. Without the fix this EXIT is never emitted
    at all (the old `exit_bar >= n_bars - 1` rule calls A "still open" forever, since
    its exit_bar never stops being the newest bar in the call where it is finally
    resolvable), which is a strictly worse failure than a mere ordering slip."""
    base = pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ)
    epoch_df = _paired_epoch_df(base)
    paths = cs._paths(home=str(tmp_path / "paired_home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)

    legs = {"PAIR": {"strategy": _paired_stub(), "timeframe": "1m", "params": {},
                     "warmup_sessions": 5, "max_entry_age_sec": 3600}}

    # SEED on a too-small history (n < 3 -> the stub has taken no trades yet).
    seed = cs.step(now=(base + pd.Timedelta(minutes=2, seconds=10)).to_pydatetime(),
                   legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    assert "absorbed 0 historical trade" in seed[0]["reason"]

    # 3 bars closed: trade A is discovered sitting at the boundary -> ENTRY only.
    call1 = cs.step(now=(base + pd.Timedelta(minutes=3, seconds=10)).to_pydatetime(),
                    legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in call1] == ["ENTRY"]
    assert call1[0]["side"] == "long"

    # 4th (newest) bar closes: A resolves to a confirmed close -- STILL exactly at the
    # boundary -- in the SAME tick that B's entry, on that very bar, first becomes
    # visible.
    call2 = cs.step(now=(base + pd.Timedelta(minutes=4, seconds=10)).to_pydatetime(),
                    legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in call2] == ["EXIT", "ENTRY"], \
        "the older trade's EXIT must be emitted before the new trade's ENTRY in the same tick"
    assert call2[0]["ref_price"] == pytest.approx(702.5)   # opens[3]: A's real, intrabar exit
    assert call2[1]["side"] == "long"
    assert call2[1]["ref_price"] == pytest.approx(702.5)   # opens[3]: B's entry, same bar+price

    # B itself is correctly still open -- not a third, phantom EXIT in this same tick.
    state = cs._load_state(paths)
    open_recs = [r for r in state["legs"]["PAIR"]["trades"].values() if not r["exit_emitted"]]
    assert len(open_recs) == 1
    assert open_recs[0]["entry_px"] == pytest.approx(702.5)
