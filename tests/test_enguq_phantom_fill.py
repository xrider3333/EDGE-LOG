"""ENGU-Q phantom limit entries (WEBULL_GO_LIVE.md 3.7, MANAGER dispatch 2026-09-26).

THE BUG. ENGUQ_1M_ETH_R2_1_0.py's shallow-limit entry rests a resting limit and scans up to
_N_SCAN (10) bars for a fill (line ~297: `jmax = min(i + _N_SCAN, n - 1)`). A FULL backtest
always has all 10 bars available, so "no fill within the window" only ever means "this setup
is genuinely dead." A LIVE/incremental caller does not have that luxury: api/cloud_signal.py
re-runs the whole walk from scratch every tick on a window that keeps growing bar by bar, so
early on, `n - 1` can fall INSIDE a pending setup's fill window -- `jmax` gets clamped short
not because the setup failed, but because the data hasn't caught up yet. The old code cannot
tell those two apart and treats both as "dropped," so the walk moves on and can take a LATER
signal instead. One tick later, once enough bars exist to finish the ORIGINAL setup's scan,
that setup may turn out to fill after all -- and taking it makes the walk skip straight past
the later signal, which promptly disappears from the newly-recomputed trade list. The live
book already sent an order for it: a phantom trade, the real bug behind the two ghost ENGU-Q
records this file's evidence names (box signals.csv, 2026-09-17 and 2026-09-23).

THE FIX. `phantom_safe` (opt-in, default False = today's byte-for-byte behaviour): when the
fill-window scan comes up empty ONLY because the data ends before the window is over (jmax
was clamped below i + _N_SCAN), the walk stops right there instead of dropping the setup and
looking further -- no trade for that setup yet, and no later signal considered, until a fresh
call sees more bars and can finish the scan for real. Fixed identically in the interpreted
loop (ENGUQ_1M_ETH_R2_1_0.py) and its compiled twin (augur_engine/fastloop.py's _walk_jit).

THE FIXTURE. Hand-built, not the box's real QQQ tape: the repo keeps no tests/fixtures
directory of committed real-market data (see test_fastloop_parity.py / test_enguq_sel_parity.py
for the established pattern -- small synthetic tapes sized to exercise one mechanism), and the
real box cache is 1m OHLC with no public-facing meaning worth freezing into the suite. This
tape reproduces the SAME mechanism the 09-17 15:07 / 09-23 14:00 box incidents did: an earlier
setup (bar 20) whose true fill sits late in its 10-bar window (bar 29, i.e. delay 9), with a
second, independent, quick-filling setup (bar 26 -> 27) sitting entirely inside that window.
Every filter this file does not care about is neutralised (buf_atr=0, min_brk=0, vol_mult=0,
er_th=0, regime_len=0) so the only thing being exercised is the fill-window truncation branch.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import fastloop                                # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402

STRAT = "ENGUQ_1M_ETH_R2_1_0.py"
_N_SCAN = 10  # must match the strategy's own fixed constant

# Signal/fill bars this fixture is built around -- see module docstring.
BAR_A_SIGNAL = 20     # the EARLIER setup; a full backtest fills it late, at BAR_A_FILL
BAR_A_FILL = 29       # delay 9 -- inside the 10-bar window, but only just
BAR_B_SIGNAL = 26     # a genuinely independent LATER setup, sitting inside A's window
BAR_B_FILL = 27       # fills fast -- this is the trade the live bug books as a phantom

PARAMS = dict(
    tl_len=5, ema_len=3, atr_len=5, limit_atr=0.5, stop_mult=1.0,
    buf_atr=0.0, min_brk=0.0, vol_mult=0.0, er_th=0.0, regime_len=0,
    act_R=5.0, trail_frac=5.0, breakeven_R=0.0,
)


def _make_bars(n=60):
    """See the module docstring for the shape. Deterministic, no RNG."""
    c = np.full(n, 100.0); o = np.full(n, 100.0)
    h = np.full(n, 100.2); l = np.full(n, 99.8)

    iA = BAR_A_SIGNAL
    # descending highs feeding setup A's trendline (bars iA-5..iA-1)
    for k, v in enumerate([103.0, 102.5, 102.0, 101.5, 101.0]):
        idx = iA - 5 + k
        h[idx] = v; c[idx] = v - 0.3; o[idx] = v - 0.5; l[idx] = v - 0.6
    # A's breakout bar
    o[iA] = 101.0; c[iA] = 110.0; h[iA] = 110.5; l[iA] = 100.8

    # B's own descending-highs window, at a price level well above A's resting limit
    # (~108.7) so none of these lows can accidentally fill A early -- bars iA+1..iA+5
    for k, v in enumerate([116.0, 115.5, 115.0, 114.5, 114.0]):
        idx = iA + 1 + k
        h[idx] = v; c[idx] = v - 0.3; o[idx] = v - 0.5; l[idx] = v - 0.6

    iB = BAR_B_SIGNAL
    assert iB == iA + 6
    o[iB] = 114.0; c[iB] = 122.0; h[iB] = 122.5; l[iB] = 113.8
    # B's own fill, one bar later -- still well above A's limit
    o[iB + 1] = 121.0; c[iB + 1] = 121.2; h[iB + 1] = 121.4; l[iB + 1] = 111.0
    assert iB + 1 == BAR_B_FILL

    iAf = BAR_A_FILL
    for idx in range(iB + 2, iAf):
        o[idx] = 111.0; c[idx] = 111.2; h[idx] = 111.4; l[idx] = 110.9
    # A's true fill: a deep dip through its resting limit, delay 9 from the signal bar
    o[iAf] = 110.8; c[iAf] = 110.9; h[iAf] = 111.0; l[iAf] = 100.0

    for idx in range(iAf + 1, n):
        o[idx] = 100.0; c[idx] = 100.0; h[idx] = 100.2; l[idx] = 99.8

    return {"open": o, "high": h, "low": l, "close": c}


FULL_ARRAYS = _make_bars(60)


def _trades_on(arrays, n, phantom_safe, fastloop_off):
    """Full (entry_bar, exit_bar) tuples from ARRAYS truncated to the first n bars.

    NOTE on exit bars: a position still open when the truncated array ends is force-
    closed at the last bar's close (the strategy's own end-of-walk fallback -- see
    ENGUQ_1M_ETH_R2_1_0.py's tail and _walk_jit's `if in_pos:` block), which can make
    entry_bar == exit_bar at an early truncation purely because no later bar exists yet
    to manage it. That is a normal "still open" artifact of an incremental read (the
    same one api/cloud_signal.py's eod_marks_at_close logic accounts for), not a second
    bug -- so callers that care only about ENTRY decisions should compare entry bars
    (see `_entry_bars`), not full tuples, across different truncations.
    """
    truncated = {k: v[:n] for k, v in arrays.items()}
    # Save/restore rather than an unconditional pop (review finding, minor): a developer
    # running with EDGELOG_NO_FASTLOOP already set in their shell must get it BACK, not
    # cleared, once this helper returns.
    _had_env = "EDGELOG_NO_FASTLOOP" in os.environ
    _old_env = os.environ.get("EDGELOG_NO_FASTLOOP")
    if fastloop_off:
        os.environ["EDGELOG_NO_FASTLOOP"] = "1"
    try:
        res = run_backtest(STRAT, arrays=truncated, params=dict(PARAMS, phantom_safe=phantom_safe),
                           cost_pts=0.0, return_trades=True)
    finally:
        if fastloop_off:
            if _had_env:
                os.environ["EDGELOG_NO_FASTLOOP"] = _old_env
            else:
                os.environ.pop("EDGELOG_NO_FASTLOOP", None)
    if not res:
        return []
    return [(int(e), int(x)) for (e, x, *_rest) in res["trades"]]


def _trades(n, phantom_safe, fastloop_off):
    return _trades_on(FULL_ARRAYS, n, phantom_safe, fastloop_off)


def _entry_bars_on(arrays, n, phantom_safe, fastloop_off):
    return [e for e, _x in _trades_on(arrays, n, phantom_safe, fastloop_off)]


def _entry_bars(n, phantom_safe, fastloop_off):
    return [e for e, _x in _trades(n, phantom_safe, fastloop_off)]


@pytest.mark.parametrize("fastloop_off", [True, False], ids=["interpreted", "compiled"])
class TestPhantomFill:

    def test_flag_off_reproduces_the_box_bug(self, fastloop_off):
        """Truncated exactly like a live tick caught mid-scan: the bug books setup B
        (fills at bar 27) -- a trade the full-history run below never takes."""
        n = BAR_B_FILL + 2   # data ends just after B's own fill, well inside A's window
        assert n - 1 < BAR_A_SIGNAL + _N_SCAN, "fixture assumption: A's window is truncated"
        entries = _entry_bars(n, phantom_safe=False, fastloop_off=fastloop_off)
        assert entries == [BAR_B_FILL], (
            "expected the old bug to book the phantom B trade (open at end of data): %r"
            % entries)

    def test_flag_on_waits_instead_of_booking_the_phantom(self, fastloop_off):
        """Same truncated data, phantom_safe=True: no trade for A yet, and B is never
        even considered -- exactly 'no trade for that setup yet and no later signal
        considered' from the spec."""
        n = BAR_B_FILL + 2
        entries = _entry_bars(n, phantom_safe=True, fastloop_off=fastloop_off)
        assert entries == [], "phantom_safe must emit nothing while A's window is unresolved: %r" % entries

    def test_full_history_never_takes_the_phantom(self, fastloop_off):
        """Once all the data exists, A resolves (it fills late, at bar 29, which the
        strategy records as its OWN entry bar -- see fill_j) and B is skipped entirely:
        the phantom trade genuinely disappears from the true walk."""
        trades = _trades(60, phantom_safe=False, fastloop_off=fastloop_off)
        assert trades == [(BAR_A_FILL, BAR_A_FILL + 1)], trades
        assert all(e != BAR_B_FILL for e, _x in trades), (
            "the phantom B entry must not survive into the full-history read: %r" % trades)

    def test_flag_is_a_pure_parity_anchor_on_full_history(self, fastloop_off):
        """Requirement 2's full-history check: with every bar available, phantom_safe
        changes nothing -- same entries, same exits, same P&L, no extras, no omissions."""
        off = _trades(60, phantom_safe=False, fastloop_off=fastloop_off)
        on = _trades(60, phantom_safe=True, fastloop_off=fastloop_off)
        assert off == on, "phantom_safe must be a no-op once the data is complete: %r vs %r" % (off, on)

    def test_bar_by_bar_replay(self, fastloop_off):
        """The spec's own framing: 'running bar by bar must emit only the real (backtest)
        entries; without it the phantom appears.' Replays every truncation from the first
        bar a trade could exist through the full tape, exactly like cloud_signal.py
        re-running the whole walk on a rolling window that grows by one bar per tick.
        Compares ENTRY bars only -- an exit can legitimately lag behind on a truncated
        read (the position is genuinely still open); see `_trades`'s docstring."""
        seen_without_flag = set()
        seen_with_flag = set()
        for n in range(BAR_A_SIGNAL + 2, 61):
            seen_without_flag.update(_entry_bars(n, phantom_safe=False, fastloop_off=fastloop_off))
            seen_with_flag.update(_entry_bars(n, phantom_safe=True, fastloop_off=fastloop_off))

        final = set(_entry_bars(60, phantom_safe=False, fastloop_off=fastloop_off))
        # Without the flag, the phantom B entry is seen at some point along the replay --
        # documenting the old, buggy behaviour -- even though it is not in the final read.
        assert BAR_B_FILL in seen_without_flag
        assert BAR_B_FILL not in final
        # With the flag, no ENTRY is EVER seen mid-replay that the final full-history read
        # does not also contain -- no trade the strategy would need to take back.
        assert seen_with_flag <= final, (
            "phantom_safe must never emit an entry the full-history run disowns: %r not subset of %r"
            % (seen_with_flag, final))

    def test_bar_by_bar_delay_is_zero_on_a_non_lookahead_tape(self, fastloop_off):
        """Review finding 2: 'assert that every final entry is first seen with delay 0 or 1
        in the non-look-ahead fixture.' NOLA_ARRAYS (below) has no setup whose fill window
        overlaps a later signal, so phantom_safe never has anything to wait on -- every real
        entry must appear in the replay the INSTANT its own fill bar enters the data (delay
        0), exactly like the un-flagged walk. This is the control case for the delayed-entry
        behaviour test_delayed_real_entry (DEAD_A_ARRAYS) documents below."""
        final = _entry_bars_on(NOLA_ARRAYS, NOLA_N, phantom_safe=True, fastloop_off=fastloop_off)
        assert final == NOLA_FILLS, final
        for fill_bar in NOLA_FILLS:
            delay = None
            for n in range(fill_bar + 1, NOLA_N + 1):
                if fill_bar in _entry_bars_on(NOLA_ARRAYS, n, phantom_safe=True, fastloop_off=fastloop_off):
                    delay = n - (fill_bar + 1)
                    break
            assert delay is not None, "entry at bar %d never appeared by n=%d" % (fill_bar, NOLA_N)
            assert delay in (0, 1), (
                "entry at bar %d first seen with delay %r bars (n=%d) on a tape with no "
                "overlapping fill window -- phantom_safe should never add latency here"
                % (fill_bar, delay, fill_bar + 1 + delay))


# ─────────────────────────────────────────────────────────────────────────────
# NON-LOOK-AHEAD FIXTURE: two independent setups whose fill windows never overlap a later
# signal. Used as the control case above -- phantom_safe has nothing to wait on here, so it
# must reproduce the un-flagged entries with zero added delay.
# ─────────────────────────────────────────────────────────────────────────────
_NOLA_SIG = (20, 45)


def _nola_setup_block(o, c, h, l, sig, base=100.0):
    for k, v in enumerate([base + 3.0, base + 2.5, base + 2.0, base + 1.5, base + 1.0]):
        idx = sig - 5 + k
        h[idx] = v; c[idx] = v - 0.3; o[idx] = v - 0.5; l[idx] = v - 0.6
    o[sig] = base + 1.0; c[sig] = base + 10.0; h[sig] = base + 10.5; l[sig] = base + 0.8
    fillb = sig + 1
    o[fillb] = base + 9.0; c[fillb] = base + 9.2; h[fillb] = base + 9.4; l[fillb] = base + 3.0
    return fillb


def _make_nola_bars(n=70):
    c = np.full(n, 100.0); o = np.full(n, 100.0)
    h = np.full(n, 100.2); l = np.full(n, 99.8)
    fills = []
    prev_end = 0
    for sig in _NOLA_SIG:
        for idx in range(prev_end, sig - 5):
            o[idx] = 100.0; c[idx] = 99.9; h[idx] = 100.2; l[idx] = 99.8
        fillb = _nola_setup_block(o, c, h, l, sig, base=100.0)
        fills.append(fillb)
        prev_end = fillb + 1
    for idx in range(prev_end, n):
        o[idx] = 100.0; c[idx] = 99.9; h[idx] = 100.2; l[idx] = 99.8
    return {"open": o, "high": h, "low": l, "close": c}, fills


NOLA_N = 70
NOLA_ARRAYS, NOLA_FILLS = _make_nola_bars(NOLA_N)


def test_compiled_and_interpreted_agree_with_phantom_safe():
    """The compiled twin (augur_engine/fastloop.py) must match the interpreted loop on
    phantom_safe exactly like every other knob -- see test_fastloop_parity.py."""
    if not fastloop.HAVE_NUMBA:
        pytest.skip("numba not installed")
    for n in (BAR_B_FILL + 2, 60):
        for flag in (False, True):
            slow = _trades(n, phantom_safe=flag, fastloop_off=True)
            fast = _trades(n, phantom_safe=flag, fastloop_off=False)
            assert slow == fast, "n=%d phantom_safe=%s: interpreted %r vs compiled %r" % (
                n, flag, slow, fast)


# ─────────────────────────────────────────────────────────────────────────────
# DELAYED-REAL-ENTRY FIXTURE (review finding 2, "the full-history check ... fails there").
# Setup A here is a genuine, PERMANENT "no fill" -- true in the full backtest with the flag
# either on or off, unlike BAR_A_SIGNAL above (which fills late, at BAR_A_FILL). Setup B is
# the real trade, independent, sitting inside A's fill window, and fills fast. This is the
# shape of the box's real 2026-09-24 12:17 incident: phantom_safe does not drop the real
# trade -- it makes the walk wait for A's whole window to close (confirming A is dead) before
# it will even look at B, so B is emitted LATE relative to the un-flagged (buggy) walk. That
# lateness is the honest cost of the fix: a live caller with a per-leg late-entry cutoff (for
# example cloud_signal's 3-bar/180s rule on a 1m leg) can end up dropping an entry the fixed
# engine would otherwise have taken, rather than booking a phantom it never should have.
# ─────────────────────────────────────────────────────────────────────────────
DEAD_A_SIGNAL = 20
DEAD_B_SIGNAL = 26
DEAD_B_FILL = 27


def _make_dead_a_bars(n=60):
    c = np.full(n, 100.0); o = np.full(n, 100.0)
    h = np.full(n, 100.2); l = np.full(n, 99.8)

    iA = DEAD_A_SIGNAL
    for k, v in enumerate([103.0, 102.5, 102.0, 101.5, 101.0]):
        idx = iA - 5 + k
        h[idx] = v; c[idx] = v - 0.3; o[idx] = v - 0.5; l[idx] = v - 0.6
    o[iA] = 101.0; c[iA] = 110.0; h[iA] = 110.5; l[iA] = 100.8   # A's breakout, limit ~108.7

    for k, v in enumerate([116.0, 115.5, 115.0, 114.5, 114.0]):
        idx = iA + 1 + k
        h[idx] = v; c[idx] = v - 0.3; o[idx] = v - 0.5; l[idx] = v - 0.6

    iB = DEAD_B_SIGNAL
    o[iB] = 114.0; c[iB] = 122.0; h[iB] = 122.5; l[iB] = 113.8
    o[iB + 1] = 121.0; c[iB + 1] = 121.2; h[iB + 1] = 121.4; l[iB + 1] = 111.0
    assert iB + 1 == DEAD_B_FILL

    # A's ENTIRE 10-bar fill window (iA+1..iA+_N_SCAN, i.e. bars 21..30) stays well above its
    # ~108.7 resting limit -- A never fills, in a full backtest or a truncated one, flag on or
    # off. c<=o throughout so none of this accidentally reads as a fresh signal either.
    for idx in range(iB + 2, iA + _N_SCAN + 1):
        o[idx] = 111.0; c[idx] = 110.9; h[idx] = 111.4; l[idx] = 110.9
    for idx in range(iA + _N_SCAN + 1, n):
        o[idx] = 110.9; c[idx] = 110.8; h[idx] = 111.0; l[idx] = 110.7

    return {"open": o, "high": h, "low": l, "close": c}


DEAD_A_ARRAYS = _make_dead_a_bars(60)


@pytest.mark.parametrize("fastloop_off", [True, False], ids=["interpreted", "compiled"])
class TestDelayedRealEntry:

    def test_full_history_is_a_parity_anchor(self, fastloop_off):
        """A never fills either way (a genuine dead setup) -- phantom_safe changes nothing
        once the full tape is available."""
        off = _trades_on(DEAD_A_ARRAYS, 60, phantom_safe=False, fastloop_off=fastloop_off)
        on = _trades_on(DEAD_A_ARRAYS, 60, phantom_safe=True, fastloop_off=fastloop_off)
        assert off == on == [(DEAD_B_FILL, DEAD_B_FILL + 1)], (off, on)

    def test_flag_off_books_the_real_trade_as_soon_as_its_own_fill_bar_arrives(self, fastloop_off):
        n = DEAD_B_FILL + 2   # data ends right after B's own fill
        entries = _entry_bars_on(DEAD_A_ARRAYS, n, phantom_safe=False, fastloop_off=fastloop_off)
        assert entries == [DEAD_B_FILL], entries

    def test_flag_on_withholds_the_same_trade_until_a_is_confirmed_dead(self, fastloop_off):
        """Same truncation as above: phantom_safe correctly refuses to look past A until A's
        whole window is known -- so it has NOT yet booked the real B trade either, even
        though B's own fill bar is already in the data."""
        n = DEAD_B_FILL + 2
        entries = _entry_bars_on(DEAD_A_ARRAYS, n, phantom_safe=True, fastloop_off=fastloop_off)
        assert entries == [], (
            "phantom_safe must not book B before A's window is resolved, even though this "
            "is not a phantom this time: %r" % entries)

    def test_flag_on_eventually_catches_up_once_as_window_closes(self, fastloop_off):
        """Once n reaches the bar where A's window is provably exhausted (jmax == i+_N_SCAN,
        i.e. n-1 == DEAD_A_SIGNAL+_N_SCAN), the walk confirms A dead and takes B -- documenting
        the real number the report must quote: how many bars later than the un-flagged walk."""
        catch_up_n = DEAD_A_SIGNAL + _N_SCAN + 1
        entries = _entry_bars_on(DEAD_A_ARRAYS, catch_up_n, phantom_safe=True, fastloop_off=fastloop_off)
        assert entries == [DEAD_B_FILL], entries
        # one bar earlier, it must still be empty -- this IS the delay, not a fluke of range.
        still_waiting = _entry_bars_on(DEAD_A_ARRAYS, catch_up_n - 1, phantom_safe=True,
                                       fastloop_off=fastloop_off)
        assert still_waiting == [], still_waiting
        delay_bars = catch_up_n - (DEAD_B_FILL + 2)
        assert delay_bars > 0, "this fixture is supposed to demonstrate added latency, not none"
