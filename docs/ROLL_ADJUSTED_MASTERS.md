# Roll-corrected NQ and ES masters (built 2026-09-26)

Owner GO on `ROLL_AUDIT.md` decision 13. This is the reference page for the new masters:
what they are, which one to use, and what you must say when you quote a result from them.

## Nothing existing changed

The 15 `db_noadj_*` masters are byte-for-byte as they were. No live or paper leg's data moved.
The no-adjust series are still the right data for anything that wants the real tradeable price
of the front contract. The 19 masters below are **new files with new registry rows**, sitting
beside them.

## The 19 new masters

Resolve them the usual way: `find_master(instrument, timeframe, session, source)`.

**`ADJ_*` — back-adjusted (`source=db_adj_rth` / `db_adj_eth`).** The newest segment keeps its
real prices; history is shifted to match. A price difference between any two bars is a real
difference. **Use these for anything that holds a position across a roll** — ENGU-Q, TTM, ORB,
and the books built from them.

| Master | Instrument | TF | Session | Rows | Span |
|---|---|---|---|---|---|
| `ADJ_NQ_1m_ETH.csv` | NQ | 1m | eth | 5,488,516 | 2010-06-06 .. 2026-09-25 |
| `ADJ_ES_1m_ETH.csv` | ES | 1m | eth | 5,660,208 | 2010-06-06 .. 2026-09-25 |
| `ADJ_NQ_1m_RTH.csv` | NQ | 1m | rth | 1,603,331 | 2010-06-07 .. 2026-09-25 |
| `ADJ_ES_1m_RTH.csv` | ES | 1m | rth | 1,598,881 | 2010-06-07 .. 2026-09-25 |
| `ADJ_NQ_2m_RTH.csv` | NQ | 2m | rth | 799,746 | 2010-06-07 .. 2026-09-14 |
| `ADJ_NQ_5m_ETH.csv` | NQ | 5m | eth | 1,144,059 | 2010-06-06 .. 2026-09-25 |
| `ADJ_ES_5m_ETH.csv` | ES | 5m | eth | 1,145,886 | 2010-06-06 .. 2026-09-25 |
| `ADJ_NQ_5m_RTH.csv` | NQ | 5m | rth | 321,802 | 2010-06-07 .. 2026-09-25 |
| `ADJ_ES_5m_RTH.csv` | ES | 5m | rth | 321,805 | 2010-06-07 .. 2026-09-25 |
| `ADJ_NQ_15m_RTH.csv` | NQ | 15m | rth | 105,665 | 2010-06-07 .. 2026-06-30 |
| `ADJ_ES_15m_RTH.csv` | ES | 15m | rth | 106,352 | 2010-06-07 .. 2026-09-14 |
| `ADJ_NQ_30m_RTH.csv` | NQ | 30m | rth | 53,527 | 2010-06-07 .. 2026-09-14 |
| `ADJ_ES_30m_RTH.csv` | ES | 30m | rth | 53,528 | 2010-06-07 .. 2026-09-14 |
| `ADJ_NQ_60m_RTH.csv` | NQ | 60m | rth | 28,827 | 2010-06-07 .. 2026-09-14 |
| `ADJ_ES_60m_RTH.csv` | ES | 60m | rth | 28,827 | 2010-06-07 .. 2026-09-14 |

**`FADJ_*` — forward-adjusted (`source=db_fadj_rth` / `db_fadj_eth`).** The *oldest* segment
keeps its real prices instead. Identical bar-to-bar differences, different absolute levels.
**Use these when a rule or a model feature is keyed to a price level learned from history**,
because back-adjusting moves sixteen years of history under it (`ROLL_AUDIT.md` 6.5). Built
only for the four masters the level-based consumers read:

| Master | Read by |
|---|---|
| `FADJ_NQ_5m_RTH.csv` | KEEL, the NinjaTrader NOISE gate |
| `FADJ_NQ_5m_ETH.csv` | the same, 24-hour variant |
| `FADJ_NQ_1m_ETH.csv` | the ENGU-Q ER gate |
| `FADJ_ES_1m_ETH.csv` | the ES 1-minute equivalent |

Ask for another one if you need it — one line in `FADJ_ONLY` in the builder.

## How they were built

`tools/build_adjusted_masters.py` reads each no-adjust master and applies
`augur_engine/rolls.py`, which reads one committed table per root,
`tools/data/rolls_NQ.csv` and `rolls_ES.csv` (built by `tools/build_roll_table.py`).

**An `ADJ_` master is exactly its no-adjust twin plus the table offsets, and nothing else.**
No hole filling, no re-sourcing, no smoothing. That property is what makes a before-and-after
comparison of a run meaningful, and it is why the summer-hole fill is deliberately not part of
this build (see `docs/DATA_TAIL_2026.md`).

### The roll table

66 switches per root: **64 measured exactly** from `databento_raw` by the max-volume-per-day
rule, and **2 estimated** (below). Plus 5 rows marked `not_a_roll`, which exist so that a feed
seam, a weekend gap, a holiday or the end of the summer hole is never adjusted out again.

Two of those not-a-roll rows matter especially: `contract_switches_*.csv` labelled
2026-06-14 18:10 and 2026-09-13 18:10 as `inferred_after_raw_end`, and they are **not rolls** —
`ROLL_AUDIT.md` 2.7 shows they are ordinary weekend gaps on the still-current contract.
Adjusting them out would have erased 412 and −384.5 points of real price movement.

`offset_pts` is **new contract minus old**, so it is negative in backwardation — which is the
majority of our history: **33 of 64 NQ and 39 of 64 ES switches are negative**, nearly all in
the near-zero-rate years. Nothing here assumes a roll steps price up.

### Anchoring, stated deliberately

Every adjusted master is anchored on the **current front contract**, not on its own last bar.
So any two of them are on the same price scale and a book can combine legs across timeframes.
A master that ends before the September 2026 switch (the 15m/30m/60m/2m ones) therefore carries
a non-zero shift on its final bar. That is correct, not a bug.

### Mixed bars are marked in the file

Twice in 2026 a switch happened *inside* a bar: its open is one contract, its close is another,
and its high and low are a blend that cannot be recovered. Those bars are rebuilt as a **body
with no wick** — high and low equal the max and min of the adjusted open and close — and carry
`synthetic=1` and `source=roll_synthetic` in the CSV itself, so you can find them without
reading this page. `rolls.guard_masks()` returns the same thing as a `no_fill` mask.

Worked example, NQ 5m RTH at 2026-09-14 11:30 ET:

```
NOADJ  11:25  O 29071.25  H 29090.00  L 29062.50  C 29078.00
NOADJ  11:30  O 29077.00  H 29460.50  L 29076.00  C 29454.50   <- 384 points of "range"
ADJ    11:25  O 29366.25  H 29385.00  L 29357.50  C 29373.00
ADJ    11:30  O 29372.00  H 29454.50  L 29372.00  C 29454.50   synthetic
```

**Mixedness depends on the bar size, so it is recomputed per series, never stored.** NQ 5m has
*four* mixed bars, not two: the 2013-09-12 20:02 and 2015-06-11 20:01 switches are bar-aligned
at 1 minute but fall strictly inside a 5-minute bar.

## Read this before quoting a result

**Four offsets are ESTIMATES, not measurements.** The raw feed stops 2026-06-07, so the 2026
tail switches were estimated against the other root and against the NinjaTrader capture:

**Updated 2026-09-28: the September pair are now MEASURED, not estimated.**

| Root | Switch (ET) | Offset | Range | Status | Method |
|---|---|---|---|---|---|
| NQ | 2026-06-15 03:30 | +293.00 | 288..300 | estimated | contract spread + NQ/QQQ ratio + minute ratio |
| ES | 2026-06-15 05:30 | +64.00 | 61..66 | estimated | contract spread + ES/SPY ratio + minute ratio |
| NQ | 2026-09-14 11:30 | **+296.50** | 292.50..300.50 | **measured** | master minus NinjaTrader capture: flat 0.00 over the 600 minutes before, +296.50 over the 535 after |
| ES | 2026-09-14 11:30 | +67.75 | 67.50..68.00 | **measured** | same; the original estimate was right to the tick |

The NQ figure moved from an estimated +295.00 to a measured **+296.50**. The original estimate
took a median over a window that also spanned the NinjaTrader capture's OWN roll a day later,
which pulled it down. `tools/roll_watch.py --selftest` re-derives both numbers from the live
feeds on demand.

**June 2026 will always be an estimate.** The NinjaTrader capture begins 2026-06-23, after
that switch, so there is no second feed to measure it against. Only a Databento re-pull could
settle it.

This was raised as a blocker before the work started and the owner said go, so the uncertainty
is carried in the data rather than in prose: `status=estimated` with the range in the table, a
count in every master's provenance JSON, and `rolls.guard_masks(..., block_estimated=True)` to
keep a caller flat across them.

### The estimates reach further back than 2026, and this is the part to read twice

Back-adjusting shifts a bar by the sum of **every later switch**. So a 2020 bar's price *level*
in an `ADJ_` master carries the two estimated 2026 offsets, even though no estimated switch
falls anywhere near 2020. A 200-bar 2020 series comes back shifted **+3,628.00**, and roughly
12 of those points are estimate rather than measurement.

**Forward adjustment does not have this property.** It subtracts a constant containing the same
terms, so they cancel, and a `FADJ_` master's pre-2026 levels are fully measured.

What this does and does not mean:

- **Bar-to-bar differences are unaffected** outside 2026. Anything trading on relative moves,
  percentages, or differences is not touched by the estimate at all.
- **Absolute levels are affected everywhere** in an `ADJ_` master. A rule with a fixed price
  threshold, or a model feature keyed to a level, sees a series whose whole history sits about
  12 points (NQ) off a hypothetical measured version. That is small against a 3,628-point shift,
  but it is not zero, and it is another reason a level-based consumer should use `FADJ_`.
- `rolls.back_adjust` / `forward_adjust` report this as `info["levels_rest_on_estimate"]`, which
  is method-dependent for exactly this reason. `info["has_estimated"]` is the narrower question:
  does an estimated switch fall inside the series you hold.

**A lockbox that ends after 2026-06-05 contains an estimated switch outright. Say so when you
quote it.** A Databento re-pull for 2026-06..09 replaces the estimates with measured values —
see `docs/DATA_TAIL_2026.md`, where that purchase is recommended for three other reasons too.

## How it was checked

- **`ROLL_AUDIT.md` 6.8 test 2 reproduces.** Mean |master's own 1-minute jump − table offset|
  across the mid-session switches is **NQ 0.400 and ES 0.118**, against the figures the audit
  states independently (0.40 / 0.12). The 18:00 reopen switches are excluded, as that test
  specifies, because a Sunday-evening gap is mostly real price movement.
- **Back and forward adjustment give identical bar-to-bar differences**, and the total shift is
  the sum of all offsets: +3,732.25 on NQ, +653.00 on ES over sixteen years.
- **`tests/test_rolls.py`** (21 tests) covers the table, the per-grid mapping, the mixed-bar
  rebuild, the guards, `stitch_usd` and the degenerate cases. Writing it found two real bugs in
  `rolls.py`, both since fixed and now pinned by tests: a switch outside the series was being
  attached to an end bar (so a 2020 series was guarded because of a 2026 roll, and reported
  `has_estimated=True`), and the reach of the estimates described above was not reported at all.
- Re-verify the table at any time with `python tools/build_roll_table.py --check`.

## Which rows a guard may trust

Three statuses, weakest last. **Ask `rolls.is_trustworthy(row)`, do not compare the string** -
the vocabulary already grew once, on 2026-09-28, and a guard testing `status == "exact"`
silently starts refusing rows that are perfectly good.

| Status | Means | Trust it? |
|---|---|---|
| `exact` | measured from contract-level raw data (`databento_raw`). The 64 switches to 2026-06-05, and nothing else unless that feed returns | yes |
| `measured` | measured from two independent feeds that rolled at different times, with a stated sample size and spread | yes |
| `estimated` | inferred, with no second feed to check it against. Today only the June 2026 pair | no - `guard_masks(block_estimated=True)` keeps a caller flat across these |

## Keeping the masters and the table in step

The table is not frozen. `python tools/build_adjusted_masters.py --verify` reports any master
built from an older version of it; each master records a fingerprint of the switch times and
offsets it was built from. A stale master is not wrong, it is just built on different numbers
than the table now holds - which is exactly the thing that is invisible without the check.

## December 2026, and every roll after it

`databento_raw` stopped, so a new switch is measured from the Yahoo master minus the
NinjaTrader capture: the two roll at different times, so their spread steps by one carry.
`tools/roll_watch.py` does the measurement and `tools/roll_watch_nightly.py` runs it unattended
each evening a roll window is open, appends the row when the measurement is clean, and posts
to TTM and MANAGER either way - a silent night shows up as a silent night rather than as
nothing having run. It never appends twice and never writes a row it is unsure of.

The December 2026 expiry is Friday **2026-12-18**, so the window is **12-08 to 12-17**. Rows it
writes carry `status=measured` and `source=capture_spread`. If both feeds ever roll in the same
minute the spread never steps and nothing is written; the calendar guard in
`augur_engine/roll_guard.py` arms for the whole window regardless, so a caller is protected
either way.

## What is still open

1. **Re-validate on these masters.** `ROLL_AUDIT.md` 6.7 lists the runs — roughly 20 runs and
   books at 900 trials, so 20 to 30 runner-hours, outside market hours. Not started here.
2. **The Databento re-pull** for 2026-06..09, which would turn the four estimates into
   measurements and fill the summer holes at the same time.
3. **The summer-hole fill** in the 1-minute masters, still an open owner call with its own
   tradeoff (`docs/DATA_TAIL_2026.md`).
4. **Per-file shift-invariance.** `ROLL_AUDIT.md` 6.5 test 10 says each strategy file must be
   checked at its own real parameters before it is declared safe to run on back-adjusted data.
   That check has been done for some files, not all; do it before trusting a re-validation of a
   file that is not on that list.
