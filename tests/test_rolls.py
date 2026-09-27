"""Roll table + roll adjustment correctness (ROLL_AUDIT.md section 6.8).

WHY. `augur_engine/rolls.py` is the ONE place every NQ/ES strategy now goes to remove the
price step at a contract switch (back_adjust for anything that holds across a roll,
forward_adjust for anything keyed to an absolute level). `tools/build_roll_table.py` is the
ONE place that writes the tables it reads. Both files carry a lot of hard-won detail in their
own docstrings - which rows are real rolls vs weekend gaps, which offsets are estimates, how
an in-bar splice is nudged onto the right side of a bar boundary, which anchor each adjustment
keeps fixed. This file exists so none of that detail can quietly regress: a bad edit to either
file should turn a test red here before it turns a backtest's P&L wrong.

Everything below uses SMALL SYNTHETIC series (a couple of switches on a made-up root, or a
handful of bars around one real switch) - never a real master, never sqlite, never the
network. The two real-table facts this file leans on hardest (the row/status counts and the
two ground-truth rows that are wrongly labelled as rolls in `contract_switches_*.csv`) were
independently verified before writing these tests; the tests assert them so a future change
that breaks them is caught, not re-derived from scratch each time.
"""
import csv
import os

import numpy as np
import pytest

from augur_engine import rolls
from tools import build_roll_table

REAL_DATA_DIR = build_roll_table.DATA


# ---------------------------------------------------------------------------------------
# Small helpers - a synthetic bar grid, and a synthetic roll-table CSV written to tmp_path
# so tests never touch the committed tables under tools/data/.
# ---------------------------------------------------------------------------------------

def _grid(start_sec, tf_seconds, n, price=10000.0, step=1.0):
    """n bars of length tf_seconds starting at start_sec, each bar a plain linear ramp with
    no wick (high == low == the open/close span). Any wick or step seen after an adjustment
    can then only have come from the adjustment itself, never from the synthetic input."""
    times = (start_sec + np.arange(n) * tf_seconds).astype("int64")
    opens = price + step * np.arange(n, dtype="float64")
    closes = opens + step
    highs = np.maximum(opens, closes)
    lows = np.minimum(opens, closes)
    return times, opens, highs, lows, closes


def _row(root, switch_sec, offset_pts, kind="mid_session", status="exact",
         old="OLDX", new="NEWX", source="databento_raw", offset_ci_pts=""):
    """One roll-table row in the exact column shape `rolls.load_table` expects."""
    return dict(root=root, old=old, new=new, switch_sec=switch_sec,
                switch_et=str(switch_sec), offset_pts="%.2f" % offset_pts,
                offset_ci_pts=offset_ci_pts, offset_sec="", kind=kind, source=source,
                status=status, note="")


def _write_roll_table(dirpath, root, rows):
    """Write a synthetic `rolls_<root>.csv` into tmp_path, in build_roll_table's own column
    order, so `rolls.load_table(root, table_dir=dirpath)` reads it exactly like a real one."""
    path = os.path.join(str(dirpath), "rolls_%s.csv" % root)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=build_roll_table.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


# ── 1. the committed tables match a fresh rebuild ───────────────────────────────────────
def test_committed_tables_match_a_fresh_rebuild():
    """If build_roll_table.rows_for() and the committed rolls_NQ/ES.csv ever drift apart,
    every consumer of rolls.py is silently reading a stale table instead of the one the
    build script would produce today - exactly the bug `--check` exists to catch. Calling
    rows_for() directly (rather than shelling out to `--check`) keeps this test fast and
    lets pytest report exactly which field differs."""
    for root in ("NQ", "ES"):
        built = build_roll_table.rows_for(root)
        path = os.path.join(REAL_DATA_DIR, "rolls_%s.csv" % root)
        with open(path, encoding="utf-8") as fh:
            have = list(csv.DictReader(fh))
        assert len(have) == len(built), "%s: committed has %d rows, rebuild has %d" % (
            root, len(have), len(built))
        for i, (h, r) in enumerate(zip(have, built)):
            for k in build_roll_table.COLUMNS:
                assert str(h.get(k, "")) == str(r.get(k, "")), (
                    "%s row %d field %r: committed=%r rebuild=%r"
                    % (root, i, k, h.get(k), r.get(k)))


# ── 2. row counts and status counts ─────────────────────────────────────────────────────
def test_row_and_status_counts_per_root():
    """A strategy deciding whether to trust a switch checks its `status`; a caller counting
    "how many rolls are in this history" uses `real_switches`. If either the not-a-roll count
    or the exact/estimated split ever moves without anyone noticing, that decision is made on
    stale assumptions - this pins the exact numbers ROLL_AUDIT.md counted by hand."""
    neg_counts = {"NQ": 33, "ES": 39}
    for root, neg_expected in neg_counts.items():
        table = rolls.load_table(root)
        assert len(table) == 71, "%s: expected 66 real + 5 not-a-roll = 71 rows" % root

        not_a_roll = [r for r in table if r["kind"] == "not_a_roll"]
        assert len(not_a_roll) == 5
        for r in not_a_roll:
            assert r["offset_pts"] == 0.0, "a not-a-roll row must never carry a real offset"

        real = rolls.real_switches(root)
        assert len(real) == 66
        assert all(r["kind"] != "not_a_roll" for r in real), (
            "real_switches() must exclude every not-a-roll row")

        exact = [r for r in real if r["status"] == "exact"]
        estimated = [r for r in real if r["status"] == "estimated"]
        assert len(exact) == 64
        assert len(estimated) == 2

        neg = [r for r in exact if r["offset_pts"] < 0]
        assert len(neg) == neg_expected, (
            "%s: expected %d negative (backwardation) offsets among the 64 exact rows, got %d"
            % (root, neg_expected, len(neg)))


# ── 3. the two wrongly-labelled ground-truth rows ───────────────────────────────────────
def test_mislabeled_ground_truth_rows_are_excluded_and_recorded_as_weekend_gaps():
    """This is the single most important correctness property in the whole table. The
    ground-truth file (`contract_switches_<root>.csv`) mislabels two ordinary weekend gaps
    as `inferred_after_raw_end`, which looks exactly like a switch to anything that isn't
    reading the note. If a future rebuild ever let these two rows back in as real switches,
    back_adjust would silently remove 412 and -384.5 points (NQ) of real weekend price move
    from the series - a fake "flat" stretch where a genuine gap traded."""
    truth = {
        ("NQ", 1781475000): 412.0,     # 2026-06-14 18:10 ET
        ("NQ", 1789337400): -384.5,    # 2026-09-13 18:10 ET
        ("ES", 1781475000): 65.25,
        ("ES", 1789337400): -50.0,
    }
    for (root, sec), real_weekend_move in truth.items():
        # the ground-truth file really does mislabel this row as a switch
        gt_path = os.path.join(REAL_DATA_DIR, "contract_switches_%s.csv" % root)
        with open(gt_path, encoding="utf-8") as fh:
            gt_rows = list(csv.DictReader(fh))
        gt_row = next(r for r in gt_rows if int(r["switch_sec"]) == sec)
        assert gt_row["source"] == "inferred_after_raw_end"
        # these two rows have no old/new contract, so contract_offset is blank - the real
        # weekend move is the raw price jump the ground-truth file recorded, master_jump
        assert float(gt_row["master_jump"]) == pytest.approx(real_weekend_move)

        # the built table does NOT treat it as a real switch...
        real_secs = {r["switch_sec"] for r in rolls.real_switches(root)}
        assert sec not in real_secs

        # ...it appears instead as an explicit not_a_roll row, sourced as a weekend gap,
        # with zero offset so nothing ever adjusts the real move out of the series
        row = next(r for r in rolls.load_table(root) if r["switch_sec"] == sec)
        assert row["kind"] == "not_a_roll"
        assert row["source"] == "weekend_gap"
        assert row["offset_pts"] == 0.0


# ── 4. back_adjust / forward_adjust anchors and identical diffs ────────────────────────
def test_back_and_forward_adjust_anchor_opposite_ends_with_identical_diffs(tmp_path):
    """back_adjust and forward_adjust exist to serve two different callers (ROLL_AUDIT 6.5):
    a strategy that holds across a roll needs back-adjusted (today's-contract) levels, a
    level-keyed rule needs forward-adjusted (original-contract) levels. If either anchor
    were wrong - if back_adjust nudged the newest bar, or forward_adjust nudged the oldest -
    the "current" contract's own recent history would no longer read as the real recent
    prices, defeating the entire point of picking one adjustment over the other. And if the
    two methods ever produced different bar-to-bar differences, they would disagree about
    every trade's P&L despite both claiming to reflect the same underlying price moves."""
    off_a, off_b = -5.0, 3.0
    tf = 3600
    base = 6_000_000 * tf
    switch_a = base + 5 * tf
    switch_b = base + 15 * tf
    _write_roll_table(tmp_path, "ZT", [
        _row("ZT", switch_a, off_a, kind="mid_session"),
        _row("ZT", switch_b, off_b, kind="mid_session"),
    ])
    times, opens, highs, lows, closes = _grid(base, tf, 20, price=15000.0, step=1.5)

    ob, hb, lb, cb, info_b = rolls.back_adjust(
        times, opens, highs, lows, closes, "ZT", tf, table_dir=str(tmp_path))
    of, hf, lf, cf, info_f = rolls.forward_adjust(
        times, opens, highs, lows, closes, "ZT", tf, table_dir=str(tmp_path))

    assert not info_b["synthetic"].any() and not info_f["synthetic"].any(), (
        "both switches sit exactly on a bar boundary in this grid - neither should be mixed")

    total = off_a + off_b
    assert cb[-1] == pytest.approx(closes[-1]), "back_adjust must leave the newest bar untouched"
    assert cb[0] - closes[0] == pytest.approx(total), (
        "back_adjust must shift the oldest bar by the sum of every later offset")
    assert cf[0] == pytest.approx(closes[0]), "forward_adjust must leave the oldest bar untouched"
    assert cf[-1] - closes[-1] == pytest.approx(-total), (
        "forward_adjust must shift the newest bar by minus that same sum")
    np.testing.assert_allclose(np.diff(cb), np.diff(cf), atol=1e-9,
                                err_msg="back and forward adjustment must agree on every "
                                        "bar-to-bar move - they may only disagree on the anchor")


# ── 5. a boundary switch is not mixed, and the step loses exactly the offset ───────────
def test_boundary_switch_is_not_mixed_and_the_step_loses_only_the_offset(tmp_path):
    """A switch that lands exactly between two bars is the easy, common case - 64 of the 66
    real switches are like this. If it were ever treated as mixed, back_adjust would throw
    away a perfectly good bar's high/low for no reason. And if the offset weren't removed
    cleanly from the step across it, every ordinary (non-in-bar) roll would leave a phantom
    price move in the adjusted series - the exact defect ROLL_AUDIT built this table to fix."""
    offset = -7.5
    tf = 3600
    switch_sec = 5_000_000 * tf
    _write_roll_table(tmp_path, "ZB", [_row("ZB", switch_sec, offset, kind="mid_session")])
    times, opens, highs, lows, closes = _grid(switch_sec - 3 * tf, tf, 6, price=4000.0, step=2.0)
    assert times[3] == switch_sec, "bar 3 must be the first bar starting at the switch"

    o, h, l, c, info = rolls.back_adjust(
        times, opens, highs, lows, closes, "ZB", tf, table_dir=str(tmp_path))
    assert not info["synthetic"].any()

    raw_step = closes[3] - closes[2]
    adjusted_step = c[3] - c[2]
    assert adjusted_step == pytest.approx(raw_step - offset)


# ── 6. an in-bar switch IS mixed - real NQ 2026-09-14 11:30 row, 5-minute grid ─────────
def _the_tail_row():
    row = next(r for r in rolls.real_switches("NQ") if r["switch_et"] == "2026-09-14 11:30")
    assert row["kind"] == "in_bar" and row["status"] == "estimated"
    return row


def test_in_bar_switch_produces_a_synthetic_no_fill_body_only_bar():
    """The two 2026 in-bar switches are the one case rolls.py admits it cannot be honest
    about: the bar's high/low are a blend of two contracts and cannot be recovered. If this
    bar were treated as clean, its fabricated wick would look like real intrabar range to
    any strategy or indicator reading it, and an order could fill inside a price that never
    traded. `synthetic` + `no_fill` are the only defense against exactly that."""
    row = _the_tail_row()
    switch_sec, offset = row["switch_sec"], row["offset_pts"]
    tf = 300
    times = np.array([switch_sec - tf, switch_sec, switch_sec + tf], dtype="int64")
    opens = np.array([29000.0, 29077.0, 29454.5])
    closes = np.array([29077.0, 29454.5, 29460.0])
    highs = np.array([29080.0, 29500.0, 29470.0])   # bar 1 carries a real wick beyond o/c
    lows = np.array([28990.0, 29050.0, 29440.0])    # ... on both sides

    o, h, l, c, info = rolls.back_adjust(times, opens, highs, lows, closes, "NQ", tf)

    assert info["synthetic"].tolist() == [False, True, False]
    assert info["synthetic"][1] and info["no_fill"][1]
    assert not info["synthetic"][0] and not info["synthetic"][2]

    open_shift = o[1] - opens[1]
    close_shift = c[1] - closes[1]
    assert open_shift != close_shift, (
        "a mixed bar's open (old contract) and close (new contract) must take different "
        "shifts - that is what makes it mixed at all")
    assert abs(open_shift - close_shift) == pytest.approx(offset)

    # the wick is gone - high/low are exactly the max/min of the two adjusted prices,
    # a body with no wick, never the original (unrecoverable) blended range
    assert h[1] == max(o[1], c[1])
    assert l[1] == min(o[1], c[1])


@pytest.mark.parametrize("tf", [60, 1800])
def test_in_bar_switch_stays_mixed_on_a_coarser_or_finer_grid(tf):
    """The nudge that keeps an in-bar switch off a false bar boundary has to work on every
    timeframe a master might be resampled to - 1-minute, 5-minute, 30-minute, hourly. If the
    nudge only worked on the grid it was written against, coarser or finer masters would
    silently treat this switch as a clean boundary and fabricate a wick-bearing bar instead
    of flagging it, exactly the failure mode item 6 above guards against."""
    row = _the_tail_row()
    switch_sec = row["switch_sec"]
    times = np.array([switch_sec - tf, switch_sec, switch_sec + tf], dtype="int64")
    m = rolls.roll_map(times, "NQ", tf)
    assert m["mixed"].tolist() == [False, True, False]


# ── 8. the mixed mask counts switches strictly inside a bar, with no double counting ───
def test_mixed_mask_counts_only_switches_strictly_inside_a_bar(tmp_path):
    """A strategy sizing its no-fill/no-entry windows off `mixed` needs the count to be
    exactly right: too few and a straddled bar gets treated as tradeable, too many (double
    counting, or flagging a boundary switch as mixed) and perfectly good bars get needlessly
    blacked out, silently shrinking every backtest's opportunity set."""
    tf = 3600
    base = 7_000_000 * tf
    rows = [
        _row("ZM", base + 1 * tf, 1.0, kind="mid_session"),       # bar boundary - not mixed
        _row("ZM", base + 2 * tf + 1800, 2.0, kind="mid_session"),  # mid-bar - mixed
        _row("ZM", base + 3 * tf, 3.0, kind="mid_session"),       # bar boundary - not mixed
        _row("ZM", base + 4 * tf + 900, 4.0, kind="in_bar"),      # mid-bar - mixed
    ]
    _write_roll_table(tmp_path, "ZM", rows)
    times = (base + np.arange(6) * tf).astype("int64")  # bars 0..5, i.e. [base, base+6*tf)
    m = rolls.roll_map(times, "ZM", tf, table_dir=str(tmp_path))

    n_strictly_inside = sum(
        1 for r in rows
        if times[0] < (r["switch_sec"] + (1 if r["kind"] == "in_bar" else 0)) < times[-1] + tf
        and (r["switch_sec"] + (1 if r["kind"] == "in_bar" else 0)) % tf != 0
    )
    assert n_strictly_inside == 2
    assert int(m["mixed"].sum()) == 2, "exactly the two mid-bar switches should be mixed"


# ── 9. guard_masks: flat_by, no_entry, no_fill, and block_estimated ────────────────────
def test_guard_masks_flat_by_no_entry_and_block_estimated(tmp_path):
    """These three masks are what a live strategy actually consults before it holds,
    enters, or fills across a switch. Get `flat_by` wrong and a position is still open when
    the roll happens; get `no_entry` wrong and a new position opens straddling it; get
    `no_fill` wrong (or forget `block_estimated`) and an order fills inside a bar whose price
    is, at best, a measured estimate rather than a traded fact."""
    tf = 3600
    base = 8_000_000 * tf
    rows = [
        _row("ZG", base + 3 * tf, 1.0, kind="mid_session", status="exact"),
        _row("ZG", base + 6 * tf, 2.0, kind="mid_session", status="estimated"),
    ]
    _write_roll_table(tmp_path, "ZG", rows)
    times = (base + np.arange(8) * tf).astype("int64")

    g_off = rolls.guard_masks(times, "ZG", tf, table_dir=str(tmp_path), block_estimated=False)
    assert g_off["flat_by"].tolist() == [False, False, True, False, False, True, False, False]
    assert g_off["no_entry"][3] and g_off["no_entry"][4]
    assert g_off["no_entry"][6] and g_off["no_entry"][7]
    assert not g_off["no_fill"].any(), (
        "neither switch is mixed, and block_estimated is off - an exact switch's own bar "
        "must not be no_fill unless it is actually mixed")

    g_on = rolls.guard_masks(times, "ZG", tf, table_dir=str(tmp_path), block_estimated=True)
    assert g_on["no_fill"][5] and g_on["no_fill"][6] and g_on["no_fill"][7], (
        "block_estimated must widen no_fill around the ESTIMATED switch's bar")
    assert not g_on["no_fill"][0:5].any(), (
        "block_estimated must not touch the EXACT switch, which was never mixed")


# ── 10. estimated_switches() and roll_map's has_estimated ──────────────────────────────
def test_estimated_switches_returns_exactly_two_rows_per_root():
    """estimated_switches() is how a caller finds the four (two per root) 2026 tail rows
    whose offset came from cross-referencing another root or a NinjaTrader capture rather
    than from the raw feed. If this ever returned more or fewer, either a genuinely measured
    switch would get treated as uncertain, or an uncertain one would slip through as if it
    were measured."""
    for root in ("NQ", "ES"):
        est = rolls.estimated_switches(root)
        assert len(est) == 2
        assert all(r["status"] == "estimated" for r in est)
        assert all(r["kind"] == "in_bar" for r in est), (
            "both of this root's estimated switches are the in-bar tail rows")


def test_has_estimated_true_for_a_series_that_covers_the_2026_tail():
    """A caller that gates on has_estimated needs it to actually fire when a series really
    does cross one of the four estimated switches - the positive case block_estimated exists
    to serve."""
    row = _the_tail_row()
    tf = 300
    times = np.array([row["switch_sec"] - tf, row["switch_sec"], row["switch_sec"] + tf],
                      dtype="int64")
    m = rolls.roll_map(times, "NQ", tf)
    assert m["has_estimated"] is True


def test_has_estimated_is_false_for_a_series_that_ends_well_before_2026():
    """If has_estimated reports True for a plain 2020 backtest that never goes anywhere near
    the 2026 tail, every caller that reasonably refuses to trust a has_estimated=True result
    would refuse perfectly good, fully-measured history - the opposite of what the flag is
    for."""
    tf = 3600
    t = np.array([1577880000 + i * tf for i in range(200)], dtype="int64")  # 2020, hourly
    m = rolls.roll_map(t, "NQ", tf)
    assert m["has_estimated"] is False


# ── 11. stitch_usd: sign, multiplier, and multi-switch trades ─────────────────────────
def test_stitch_usd_sign_multiplier_and_multi_switch_sum(tmp_path):
    """stitch_usd exists purely to audit an UNADJUSTED backtest: how many of a trade's
    dollars were never a price move. Get the sign backwards and a short trade that was
    actually charged for a roll would look like it profited from it instead - the exact
    kind of silent mis-statement ROLL_AUDIT exists to catch, and the multiplier has to be
    applied so the number is real dollars, not points."""
    tf = 3600
    base = 9_000_000 * tf
    _write_roll_table(tmp_path, "ZS", [
        _row("ZS", base + 10 * tf, 5.0, kind="mid_session"),
        _row("ZS", base + 20 * tf, -3.0, kind="mid_session"),
    ])
    times = (base + np.arange(30) * tf).astype("int64")
    mult = 20.0
    kw = dict(table_dir=str(tmp_path))

    # entirely inside one segment - no switch between entry and exit - books nothing
    assert rolls.stitch_usd(times, "ZS", tf, 0, 5, side=1, mult=mult, **kw) == 0.0

    # long held across the first switch only
    v = rolls.stitch_usd(times, "ZS", tf, 5, 15, side=1, mult=mult, **kw)
    assert v == pytest.approx(5.0 * mult)

    # a short books the negative of what the long books, same window
    v = rolls.stitch_usd(times, "ZS", tf, 5, 15, side=-1, mult=mult, **kw)
    assert v == pytest.approx(-5.0 * mult)

    # held across BOTH switches - the sum of both offsets
    v = rolls.stitch_usd(times, "ZS", tf, 5, 25, side=1, mult=mult, **kw)
    assert v == pytest.approx((5.0 + -3.0) * mult)


# ── 12. load_table: unknown root, and no cache leak across table_dir ───────────────────
def test_load_table_raises_a_helpful_error_for_an_unknown_root():
    """A typo'd root (or a strategy file for an instrument this table was never built for)
    must fail loudly with a pointer to the fix, not silently return an empty/wrong table."""
    with pytest.raises(FileNotFoundError, match="no roll table for"):
        rolls.load_table("ZZZ_NOT_A_REAL_ROOT")


def test_table_cache_does_not_leak_between_table_dirs(tmp_path):
    """load_table caches by (root, directory) so a backtest doesn't re-read the CSV every
    slice. If that cache key ever collapsed to just the root, a synthetic or scratch table
    passed with a different table_dir would either leak into, or be shadowed by, the
    committed production table - and because both answer to the same root name, nothing
    downstream would notice until the numbers were already wrong."""
    real = rolls.load_table("NQ")               # primes the cache for the real table first
    assert len(real) == 71

    _write_roll_table(tmp_path, "NQ", [_row("NQ", 999_999 * 3600, 42.0, kind="mid_session")])
    custom = rolls.load_table("NQ", table_dir=str(tmp_path))
    assert len(custom) == 1
    assert custom[0]["offset_pts"] == 42.0

    # reading the differently-keyed table must not have disturbed the real one
    assert rolls.load_table("NQ") is real
    assert len(rolls.load_table("NQ")) == 71


# ── 13. degenerate input does not raise ────────────────────────────────────────────────
def test_degenerate_inputs_do_not_raise():
    """A lockbox slice, a single-bar smoke test, or brand-new data can legitimately hand
    this module zero bars, one bar, or a series that sits entirely before the first switch
    or entirely after the last one. None of those are errors, and a crash here would take
    down an otherwise-fine backtest for a reason that has nothing to do with its strategy."""
    tf = 3600

    empty_t = np.zeros(0, dtype="int64")
    empty_p = np.zeros(0, dtype="float64")
    o, h, l, c, info = rolls.back_adjust(empty_t, empty_p, empty_p, empty_p, empty_p, "NQ", tf)
    assert len(c) == 0
    assert len(info["synthetic"]) == 0

    one_t = np.array([1_600_000_000], dtype="int64")
    one_p = np.array([100.0])
    o, h, l, c, info = rolls.back_adjust(one_t, one_p, one_p + 1, one_p - 1, one_p + 0.5,
                                          "NQ", tf)
    assert len(c) == 1

    # entirely before NQ's first real switch (2010-06-10)
    before_t, bo, bh, bl, bc = _grid(1_000_000_000, tf, 5, price=1000.0, step=1.0)
    o, h, l, c, info = rolls.back_adjust(before_t, bo, bh, bl, bc, "NQ", tf)
    assert len(c) == 5

    # entirely after NQ's last real switch (2026-09-14)
    after_t, ao, ah, al, ac = _grid(1_900_000_000, tf, 5, price=1000.0, step=1.0)
    o, h, l, c, info = rolls.back_adjust(after_t, ao, ah, al, ac, "NQ", tf)
    assert len(c) == 5


# ── 14. nothing mutates its inputs ──────────────────────────────────────────────────────
def test_back_and_forward_adjust_do_not_mutate_caller_arrays():
    """A strategy typically re-slices its own opens/highs/lows/closes arrays and hands them
    to more than one adjustment or one timeframe. If either function mutated in place, the
    second call would silently be adjusting an already-adjusted series instead of the raw
    one - a bug that would only show up as numbers being subtly, cumulatively wrong."""
    tf = 3600
    times, opens, highs, lows, closes = _grid(1_600_000_000, tf, 10, price=15000.0, step=2.0)
    o0, h0, l0, c0 = opens.copy(), highs.copy(), lows.copy(), closes.copy()

    rolls.back_adjust(times, opens, highs, lows, closes, "NQ", tf)
    np.testing.assert_array_equal(opens, o0)
    np.testing.assert_array_equal(highs, h0)
    np.testing.assert_array_equal(lows, l0)
    np.testing.assert_array_equal(closes, c0)

    rolls.forward_adjust(times, opens, highs, lows, closes, "NQ", tf)
    np.testing.assert_array_equal(opens, o0)
    np.testing.assert_array_equal(highs, h0)
    np.testing.assert_array_equal(lows, l0)
    np.testing.assert_array_equal(closes, c0)


# ---------------------------------------------------------------------------------------
# A switch outside the series must not attach itself to an end bar, and back-adjusting an
# old series still leans on the 2026 estimates. Both found by the test suite above, fixed
# 2026-09-26.
# ---------------------------------------------------------------------------------------

def _old_series(n=200, tf=3600):
    """200 hourly bars in 2020 - nowhere near any 2026 switch."""
    return np.array([1577880000 + i * tf for i in range(n)], dtype="int64"), tf


def test_a_switch_after_the_series_ends_is_not_attached_to_the_last_bar():
    """searchsorted clamps an out-of-range index, so a 2026 roll silently became "the last
    bar" of a 2020 series. A caller then keeps that bar flat for no reason and cannot tell
    the false positive from a real one."""
    t, tf = _old_series()
    m = rolls.roll_map(t, "NQ", tf)
    n = len(t)
    # every switch is outside this series, so none of them claims a bar in [0, n)
    assert m["n_switches"] == 0
    assert not m["in_series"].any()
    assert not ((m["switch_bars"] >= 0) & (m["switch_bars"] < n)).any()
    g = rolls.guard_masks(t, "NQ", tf)
    assert not g["flat_by"].any() and not g["no_entry"].any() and not g["no_fill"].any()


def test_n_switches_counts_this_series_while_the_total_stays_available():
    """A caller asking "does my data contain a roll" needs an answer about its own bars; the
    whole-table count is still useful for reporting, so both are reported."""
    t, tf = _old_series()
    m = rolls.roll_map(t, "NQ", tf)
    assert m["n_switches"] == 0
    assert m["n_switches_total"] == len(rolls.real_switches("NQ"))
    # a series that really does span the September 2026 splice reports one
    t2 = np.array([1789399800 - tf * 5 + i * tf for i in range(20)], dtype="int64")
    m2 = rolls.roll_map(t2, "NQ", tf)
    assert m2["n_switches"] == 1 and m2["has_estimated"] is True


def test_back_adjusting_an_old_series_still_rests_on_the_2026_estimates():
    """The one that matters for quoting results. Back-adjusting shifts a bar by the sum of
    every LATER switch, so a 2020 bar's level carries the two estimated 2026 offsets even
    though no estimated switch falls inside 2020. Forward adjustment subtracts a constant
    holding the same terms, so they cancel and its old levels are fully measured. Anyone
    reporting a back-adjusted figure has to know its levels are not purely measured."""
    t, tf = _old_series()
    z = np.full(len(t), 9000.0)
    _, _, _, _, back = rolls.back_adjust(t, z, z, z, z, "NQ", tf)
    _, _, _, _, fwd = rolls.forward_adjust(t, z, z, z, z, "NQ", tf)
    assert back["has_estimated"] is False          # none INSIDE the series
    assert back["levels_rest_on_estimate"] is True   # but the shift includes them
    assert fwd["levels_rest_on_estimate"] is False   # they cancel here
    assert back["shift_close"][0] != 0.0
    assert fwd["shift_close"][0] == 0.0
