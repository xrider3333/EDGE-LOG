"""Tests for the 2026-09-23 per-trade SIZE contract in api/cloud_signal.py.

THE PROBLEM. A strategy plugin that sizes trades (NOISE_1_8_CT304.py, run #382; later
the KEEL overlay) used to fold its per-trade multiplier `s` straight into pnl_pts
(`pts = s*raw - (s-1)*cost`) and report nothing else, so run_leg_trades's
`exit_px = entry_px + pnl_pts * side` reconstructed a SYNTHETIC, cost/size-scaled
number instead of a real fill price, and nothing downstream could know how many
shares the trade actually wanted.

THE FIX (additive, optional, backwards compatible). A sizing plugin's result dict may
now carry `trade_sizes` (list of floats, same length/order as `trades`) and
`size_cost_pts` (the cost constant it folded in). When present and valid,
run_leg_trades inverts the fold (`raw = (pnl_pts + (size-1)*size_cost_pts) / size`) to
recover the real price and records the real per-trade `size` on the trade dict it
returns. A plugin that never sets these keys is completely unaffected -- see
tests/test_cloud_signal_exit_lag.py's own (a)/(b)/(c) suite, which exercises exactly
that path and is untouched by this file.

FAIL CLOSED. A DECLARED contract that is broken in any way (size_cost_pts missing, a
length mismatch, or any non-finite/non-positive size) must never guess: the whole call
returns no signals for that leg and logs why, rather than risk mis-pricing every order
it would otherwise send.
"""
import types

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs


# ── Fixtures shared by every test below ─────────────────────────────────────────────────

def _arrays(closes, base=None, freq="5min"):
    """Same minimal `arrays` shape tests/test_cloud_signal_exit_lag.py's own helper
    builds: only 'close' (n_bars, newest bar's price) and 'index' matter to a stub
    strategy that ignores the OHLC it is handed."""
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


def _stub(trades, sizes=None, cost=None):
    """A strategy stub that returns a FIXED, hand-crafted trade-tuple list -- same
    contract as tests/test_cloud_signal_exit_lag.py's _tuple_stub -- optionally
    carrying the additive `trade_sizes`/`size_cost_pts` keys a sizing plugin declares.
    Omitting `sizes` (the default) makes this an ordinary, non-sizing plugin."""
    mod = types.ModuleType("trade_size_stub")
    mod.STRATEGY_NAME = "TRADE_SIZE_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        n = len(trades)
        wins = sum(1 for t in trades if t[2] > 0)
        out = {"trades": list(trades) if return_trades else None, "num_trades": n,
              "total_pnl": sum(t[2] for t in trades), "win_rate": (wins / n) if n else 0,
              "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": wins,
              "losses": n - wins}
        if sizes is not None:
            out["trade_sizes"] = sizes
        if cost is not None:
            out["size_cost_pts"] = cost
        return out

    mod.run_backtest = run_backtest
    return mod


_CLOSES = [700.0, 701.0, 702.0, 703.0, 704.5]   # 5 bars; boundary is bar index 4


# ── Hand-computed inversion (the arithmetic is worked out here, not with the code's
#    own inversion formula) ──────────────────────────────────────────────────────────────

def test_inversion_recovers_a_hand_computed_true_exit_price_long():
    """Ground truth fixed FIRST: entry 100.0, TRUE exit 106.0 (long, price rose 6.0
    points). Folded BY HAND using the plugin's own FORWARD convention (the opposite
    direction from run_leg_trades's inversion), NOISE_1_8_CT304.py's
    `pts = s*raw - (s-1)*cost`, with s=2.0, cost=0.5:

        pts = 2.0 * 6.0 - 1.0 * 0.5 = 12.0 - 0.5 = 11.5

    11.5 (not 6.0, not 106.0) is the only number handed to run_leg_trades as pnl_pts.
    The assertion is only meaningful because 106.0 was picked before 11.5 was derived
    from it -- the code has to invert 11.5 back to arrive there on its own."""
    entry_px = 100.0
    true_exit_px = 106.0
    s, cost = 2.0, 0.5
    folded_pnl = 11.5                     # = 2.0*6.0 - 1.0*0.5, worked out above by hand

    arrays = _arrays(_CLOSES)
    trades = [(1, 2, folded_pnl, 1, entry_px)]     # exit_bar(2) < n_bars-1(4): unambiguous
    cfg = {"strategy": _stub(trades, sizes=[s], cost=cost), "params": {}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is False
    assert out[0]["exit_px"] == pytest.approx(true_exit_px)
    assert out[0]["size"] == pytest.approx(2.0)


def test_inversion_recovers_a_hand_computed_true_exit_price_short():
    """Same idea, short side: entry 100.0, TRUE exit 94.0 (a short profits when price
    FALLS, so the true raw move is entry - exit = 6.0 points). Folded by hand with
    s=1.5, cost=0.4:

        pts = 1.5 * 6.0 - 0.5 * 0.4 = 9.0 - 0.2 = 8.8
    """
    entry_px = 100.0
    true_exit_px = 94.0
    s, cost = 1.5, 0.4
    folded_pnl = 8.8                      # = 1.5*6.0 - 0.5*0.4, worked out above by hand

    arrays = _arrays(_CLOSES)
    trades = [(1, 2, folded_pnl, -1, entry_px)]
    cfg = {"strategy": _stub(trades, sizes=[s], cost=cost), "params": {}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is False
    assert out[0]["exit_px"] == pytest.approx(true_exit_px)
    assert out[0]["size"] == pytest.approx(1.5)




def test_inversion_recovers_a_hand_computed_true_exit_price_fractional_keel_style():
    """A fractional size below 1.0 -- the KEEL overlay the owner wants next sizes every
    trade between half and double, so 0.5 must invert cleanly too. Ground truth fixed
    first: entry 100.0, TRUE exit 103.0 (long, +3.0 raw points). Folded by hand with
    s=0.5, cost=0.5:

        pts = 0.5*3.0 - (0.5-1.0)*0.5 = 1.5 - (-0.25) = 1.75
    """
    entry_px = 100.0
    true_exit_px = 103.0
    s, cost = 0.5, 0.5
    folded_pnl = 1.75                     # = 0.5*3.0 - (-0.5)*0.5, worked out above by hand

    arrays = _arrays(_CLOSES)
    trades = [(1, 2, folded_pnl, 1, entry_px)]
    cfg = {"strategy": _stub(trades, sizes=[s], cost=cost), "params": {}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is False
    assert out[0]["exit_px"] == pytest.approx(true_exit_px)
    assert out[0]["size"] == pytest.approx(0.5)


# ── A non-sizing leg is completely unaffected ───────────────────────────────────────────

def test_non_sizing_leg_is_completely_unaffected():
    """No trade_sizes at all (the ordinary case, every plugin today except
    NOISE_1_8_CT304.py): the exact pre-2026-09-23 exit_px arithmetic
    (entry_px + pnl_pts*side) and a "size" field that is always exactly 1.0."""
    entry_px = 701.0
    true_exit_px = 703.25
    trades = [(1, 4, true_exit_px - entry_px, 1, entry_px)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades), "params": {}}      # no sizes, no cost declared

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    t = out[0]
    assert t["exit_px"] == pytest.approx(true_exit_px)
    assert t["still_open"] is False
    assert t["size"] == 1.0


# ── FAIL CLOSED: a declared-but-broken contract emits nothing and logs why ──────────────

def test_fail_closed_when_size_cost_pts_is_missing():
    trades = [(1, 2, 5.0, 1, 700.0)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades, sizes=[1.5]), "params": {}}   # cost omitted
    logged = []

    out = cs.run_leg_trades(cfg, arrays, log=logged.append)

    assert out == []
    assert len(logged) == 1
    assert "size_cost_pts" in logged[0] and "missing" in logged[0]
    assert "refusing to emit signals" in logged[0]


def test_fail_closed_when_lengths_disagree():
    trades = [(1, 2, 5.0, 1, 700.0), (0, 1, 2.0, 1, 699.0)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades, sizes=[1.5], cost=0.5), "params": {}}   # 1 size, 2 trades
    logged = []

    out = cs.run_leg_trades(cfg, arrays, log=logged.append)

    assert out == []
    assert len(logged) == 1
    assert "trade_sizes has 1 entries for 2 trade" in logged[0]


@pytest.mark.parametrize("bad_size", [0.0, -1.0, -0.0001, float("nan"), float("inf"), float("-inf")])
def test_fail_closed_on_a_non_finite_or_non_positive_size(bad_size):
    trades = [(1, 2, 5.0, 1, 700.0)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades, sizes=[bad_size], cost=0.5), "params": {}}
    logged = []

    out = cs.run_leg_trades(cfg, arrays, log=logged.append)

    assert out == []
    assert len(logged) == 1
    assert "finite positive size" in logged[0]


def test_fail_closed_on_a_non_numeric_size():
    trades = [(1, 2, 5.0, 1, 700.0)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades, sizes=["not-a-number"], cost=0.5), "params": {}}
    logged = []

    out = cs.run_leg_trades(cfg, arrays, log=logged.append)

    assert out == []
    assert len(logged) == 1


def test_fail_closed_on_a_non_numeric_size_cost_pts():
    trades = [(1, 2, 5.0, 1, 700.0)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades, sizes=[1.5], cost="not-a-number"), "params": {}}
    logged = []

    out = cs.run_leg_trades(cfg, arrays, log=logged.append)

    assert out == []
    assert len(logged) == 1


def test_fail_closed_leg_uses_the_leg_key_in_its_log_line():
    """step() always passes leg_key -- confirms it reaches the log line so an owner
    reading the console knows WHICH leg refused to emit."""
    trades = [(1, 2, 5.0, 1, 700.0)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades, sizes=[1.5]), "params": {}}
    logged = []

    out = cs.run_leg_trades(cfg, arrays, leg_key="NOISE_382", log=logged.append)

    assert out == []
    assert logged and "NOISE_382" in logged[0]


# ── The still-open price test: valid for a declared-size leg, still conservative for
#    an undeclared one ──────────────────────────────────────────────────────────────────

def test_explicit_escape_hatch_is_honoured_even_when_sizes_are_declared():
    """An explicit eod_marks_at_close=False always wins. Declaring sizes makes the
    boundary price test VALID, but a caution written on the leg config must not be
    silently overridden by it: the conservative rule can only delay an exit by one
    bar, never invent one, so this boundary trade stays open until the next bar."""
    entry_px = 701.0
    true_exit_px = 703.25                 # genuinely NOT the newest bar's close (704.5)
    s, cost = 1.5, 0.4
    raw = true_exit_px - entry_px         # 2.25
    folded_pnl = s * raw - (s - 1.0) * cost
    arrays = _arrays(_CLOSES)
    trades = [(1, 4, folded_pnl, 1, entry_px)]      # exit_bar == n_bars-1: the boundary
    cfg = {"strategy": _stub(trades, sizes=[s], cost=cost), "params": {},
          "eod_marks_at_close": False}             # explicit caution -- must be honoured

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is True
    assert out[0]["exit_px"] is None
    assert out[0]["size"] == pytest.approx(s)

    # ...and WITHOUT the flag the same declared-size trade is recognised as closed on the
    # spot, at its true (un-folded) price - the reason the size contract exists.
    cfg.pop("eod_marks_at_close")
    out = cs.run_leg_trades(cfg, arrays)
    assert out[0]["still_open"] is False
    assert out[0]["exit_px"] == pytest.approx(true_exit_px)


def test_declared_size_leg_still_reads_the_ambiguous_boundary_as_open():
    """The inversion is algebraically exact, so a genuine data-end guess (folded from
    exactly the newest bar's close) must still resolve to exit_px == last_close and
    read as open -- sizing support must not make every declared-size trade at the
    boundary look artificially closed."""
    entry_px = 701.0
    s, cost = 2.0, 0.3
    true_exit_px = _CLOSES[-1]            # exactly the newest bar's close -> ambiguous/open
    raw = true_exit_px - entry_px
    folded_pnl = s * raw - (s - 1.0) * cost
    arrays = _arrays(_CLOSES)
    trades = [(1, 4, folded_pnl, 1, entry_px)]
    cfg = {"strategy": _stub(trades, sizes=[s], cost=cost), "params": {}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is True
    assert out[0]["exit_px"] is None
    assert out[0]["exit_time"] is None
    assert out[0]["size"] == pytest.approx(s)


def test_undeclared_size_leg_still_needs_the_manual_escape_hatch():
    """A plugin that folds size into pnl_pts WITHOUT declaring trade_sizes gets no
    automatic protection: the pre-existing manual eod_marks_at_close=False promise is
    exactly as required as it was before this contract existed."""
    entry_px = 701.0
    true_exit_px = 703.25                 # looks unambiguous by price alone
    trades = [(1, 4, true_exit_px - entry_px, 1, entry_px)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades), "params": {}, "eod_marks_at_close": False}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is True    # conservative, exactly as before this feature
    assert out[0]["size"] == 1.0


def test_undeclared_size_leg_without_the_hatch_gets_the_ordinary_price_test():
    """The flip side of the previous test: with no size declaration AND no manual
    hatch, behaviour is the plain pre-2026-09-23 price test -- unaffected either way
    by the new sizing machinery."""
    entry_px = 701.0
    true_exit_px = 703.25
    trades = [(1, 4, true_exit_px - entry_px, 1, entry_px)]
    arrays = _arrays(_CLOSES)
    cfg = {"strategy": _stub(trades), "params": {}}

    out = cs.run_leg_trades(cfg, arrays)

    assert len(out) == 1
    assert out[0]["still_open"] is False
    assert out[0]["exit_px"] == pytest.approx(true_exit_px)


# ── signals.csv ledger: the "size" column migrates cleanly ──────────────────────────────

def test_signals_csv_size_column_migrates_cleanly(tmp_path):
    """An existing signals.csv written before the "size" column existed must gain it
    through the same generic header-migration path as bar_source/trade_id before it
    (_read_signals_header / _migrate_signals_header): old rows keep every value they
    had, pick up a blank "size" (meaning 1.0/unsized, per SIGNAL_COLS's own comment),
    and an "older reader" -- one that only ever looks up the pre-size column names --
    keeps working against the migrated file."""
    import csv

    path = tmp_path / "signals.csv"
    old_cols = cs.SIGNAL_COLS[:-1]
    assert old_cols[-1] == "trade_id" and "size" not in old_cols
    old_row = {"emitted_at": "2026-09-01T00:00:00-04:00", "leg": "NOISE_304",
              "event": "ENTRY", "side": "long", "ref_time": "2026-09-01T09:30:00-04:00",
              "ref_price": "700.0", "shares": "1", "reason": "", "bar_source": "yfinance",
              "trade_id": "abc123"}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old_cols)
        w.writeheader()
        w.writerow(old_row)

    assert cs._read_signals_header(str(path)) == old_cols

    cs._migrate_signals_header(str(path), cs.SIGNAL_COLS)

    new_header = cs._read_signals_header(str(path))
    assert new_header == cs.SIGNAL_COLS
    assert new_header[-1] == "size"

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["size"] == ""              # blank pad -- same convention as every
                                              # prior column addition (bar_source, trade_id)
    assert rows[0]["trade_id"] == "abc123"    # untouched by the upgrade
    assert rows[0]["ref_price"] == "700.0"

    # an "older reader" that only knows the pre-size columns still reads every one of
    # them correctly (DictReader keys by name, so the new trailing column is simply
    # never looked up).
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        old_view = [{k: r[k] for k in old_cols} for r in reader]
    assert old_view == [old_row]

    # a NEW row appended after the migration carries a real size value straight
    # through _append_signals's normal path.
    cs._append_signals([dict(old_row, emitted_at="2026-09-02T00:00:00-04:00",
                            trade_id="def456", size=1.5)],
                       {"state_dir": str(tmp_path), "signals_path": str(path)})
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[1]["size"] == "1.5"
    assert rows[1]["trade_id"] == "def456"


def test_seed_and_entry_and_exit_events_all_carry_a_size_field(tmp_path):
    """End to end through step()/_diff_leg: SEED gets a blank size (not applicable --
    it names a batch of absorbed trades, not one trade), while a real ENTRY and its
    EXIT both carry a numeric "size" -- 1.0 for a leg that never declares one."""
    base = pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ)
    closes = [700.0, 701.0, 702.0, 703.0]
    opens = [699.5, 700.5, 701.5, 702.5]
    epoch_df = pd.DataFrame({
        "time": [int((base + pd.Timedelta(minutes=i)).tz_convert("UTC").timestamp())
                for i in range(4)],
        "open": opens,
        "high": [max(o, c) + 0.3 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.3 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1000.0] * 4,
    })

    def run_backtest(opens_, highs, lows, closes_, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        n = len(closes_)
        trades = []
        if n >= 3:
            trades.append((1, n - 1, float(closes_[n - 1]) - float(opens_[1]), 1, float(opens_[1])))
        n_t = len(trades)
        return {"trades": trades if return_trades else None, "num_trades": n_t,
               "total_pnl": sum(t[2] for t in trades), "win_rate": 1.0 if n_t else 0,
               "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": n_t, "losses": 0}

    mod = types.ModuleType("size_field_stub")
    mod.STRATEGY_NAME = "SIZE_FIELD_STUB"
    mod.DEFAULT_PARAMS = {}
    mod.run_backtest = run_backtest

    paths = cs._paths(home=str(tmp_path / "size_field_home"))
    import os
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)
    legs = {"SZ": {"strategy": mod, "timeframe": "1m", "params": {}, "warmup_sessions": 5,
                  "max_entry_age_sec": 3600}}

    seed = cs.step(now=(base + pd.Timedelta(minutes=2, seconds=10)).to_pydatetime(),
                   legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    assert seed[0]["size"] == ""

    call1 = cs.step(now=(base + pd.Timedelta(minutes=3, seconds=10)).to_pydatetime(),
                    legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in call1] == ["ENTRY"]
    assert call1[0]["size"] == 1.0

    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        header = f.readline().strip().split(",")
    assert header == cs.SIGNAL_COLS
