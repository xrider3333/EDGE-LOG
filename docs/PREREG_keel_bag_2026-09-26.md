# PRE-REGISTRATION — seed-averaged KEEL v12 on NOISE #304 and NOISE #382 (2026-09-26)

Written and committed BEFORE any seed-averaged size was computed. Nothing below may change after the
first result is read; anything learned afterwards goes in a clearly marked POST-HOC section.

## Why
`tools/keel_fix_roll_check.py --seeds 6` (commit 1d93582) showed KEEL's lockbox is mostly seed: six
other seeds put NOISE #382 + KEEL's lockbox at 61-104 %/yr with drawdown $39.7k-$64.3k, and the shipped
seed (42) gave the best lockbox of seven on both legs. Walk-forward moved only 4-7%. The owner said GO
(via MANAGER, 2026-09-26) on averaging the size over several seeds.

## The build under test ("KEEL v12, 7-seed average")
- Engine as on main at 85be1b8 or later (gap_atr look-ahead fixed), `keel_walk(..., version="v12")`.
- Per trade, size = the MEAN of the seven per-seed v12 sizes, same features, same trades.
- **Primary bag = seeds 90001-90007**, none of which has ever been read. Seed 42 and 1042-6042 are
  deliberately excluded because their results have been seen.
- Two further independent bags, seeds 90011-90017 and 90021-90027, exist only to measure how much a
  bag still depends on its seeds.

## Tape and stretches (the round-60 ones, fixed)
NQ 5m RTH no-adj master, 2010-06-07 .. 2026-09-16, cost 0.533, NOISE #304 = `NOISE_1_0.py` crown
params, NOISE #382 = `NOISE_1_8_CT304.py` (30-min, 16, 1.15, 2.0x). Walk-forward 2016-06-30 .. 2025-07-16,
lockbox from 2025-07-16. Per stretch: net, max drawdown, return per drawdown (annual net / drawdown),
ROC %/yr on $100k, and the engine's Sortino (`sortino_from_pnls`).

## Comparators
- RAW: the leg with no KEEL.
- SINGLE-SEED MEDIAN: the median, per statistic, of the seven single-seed v12 runs already seen
  (seeds 42, 1042, 2042, 3042, 4042, 5042, 6042), recomputed in the same run. This is what a randomly
  chosen single seed is expected to deliver; seed 42 alone is reported for information only, because
  it is the luckiest of the seven.

## The bar — PASS needs all four, on BOTH legs, for the primary bag
- **P1 (KEEL still earns its keep):** walk-forward return per drawdown AND walk-forward Sortino are at
  least raw's.
- **P2 (averaging costs little):** walk-forward return per drawdown AND walk-forward Sortino are at
  least 97% of the single-seed median's.
- **P3 (lockbox veto only):** lockbox return per drawdown is at least raw's.
- **P4 (it is actually steadier):** across the three bags, the lockbox net spread (max/min - 1) is at
  most HALF the spread of the seven single seeds, and the walk-forward net spread is also at most half.

## What happens next
- PASS: Paper: WB gets the exact build (seeds 90001-90007, mean of sizes) for the live Webull NOISE
  sizing, deployed only while flat. The engine gets the version so validates and the live box match.
- FAIL on P4 alone: averaging does not tame the seed; report it, change nothing.
- Any other FAIL: nothing live changes; the shipped single-seed v12 stays.
- Not changed by this round whatever the result: every NOISE crown, the event and compression tilts,
  and ENGU-Q.

---

## RESULT (read 2026-09-26, after the bar above was committed as 696c00f) - FAIL

`python tools/keel_bag_check.py --report` (per-seed sizes cached at C:\EdgeLog\_anatomy_cache\keel_bag).

| leg | row | WF ROC %/yr | WF ret/DD | WF Sortino | LB ROC %/yr | LB ret/DD | LB Sortino |
|---|---|---|---|---|---|---|---|
| NOISE #304 | raw | 36.6 | 2.16 | 3.79 | 55.2 | 2.25 | 3.16 |
| NOISE #304 | single seed 42 (shipped) | 58.1 | 2.17 | 4.57 | 96.4 | 3.57 | 4.43 |
| NOISE #304 | single-seed median | 56.7 | 2.10 | 4.42 | 82.6 | 3.12 | 3.63 |
| NOISE #304 | **bag 1 (primary)** | 55.7 | 2.11 | 4.42 | 86.1 | 3.03 | 3.87 |
| NOISE #382 | raw | 55.9 | 2.67 | 3.87 | 77.6 | 2.33 | 2.95 |
| NOISE #382 | single seed 42 (shipped) | 84.1 | 2.60 | 4.22 | 111.8 | 2.85 | 3.22 |
| NOISE #382 | single-seed median | 85.9 | 2.59 | 4.38 | 101.0 | 2.36 | 2.82 |
| NOISE #382 | **bag 1 (primary)** | 84.7 | 2.59 | 4.24 | 95.2 | 2.33 | 2.74 |

- **#304: P1 FAIL, P2 PASS, P3 PASS, P4 PASS.** Walk-forward return per drawdown 2.11 against raw 2.16.
- **#382: P1 FAIL, P2 FAIL, P3 FAIL, P4 PASS.** P2 misses by a hair (Sortino 4.24 against a 4.25 line);
  P3 misses because the lockbox return per drawdown only ties raw (2.33).
- **P4 passes by a wide margin on both.** Across three independent bags the lockbox net spread falls
  from 48% to 21% (#304) and from 83% to 6% (#382); walk-forward from 6.7% to 1.8% and 4.4% to 0.7%.

**What it means.** Averaging does exactly what it was meant to do - it removes the seed. What is left
underneath is the finding: **on this tape KEEL's walk-forward return per drawdown is raw's, not better**
(bags 2.04-2.11 vs 2.16 on #304; 2.53-2.59 vs 2.67 on #382). P1 fails for the single-seed median too,
so this is a property of KEEL, not of averaging. What KEEL does add robustly is about 50% more money
at a proportionally larger drawdown, with a better Sortino (4.42 vs 3.79; 4.24 vs 3.87). That is closer
to well-placed leverage than to an edge. The shipped seed's lockbox advantage was luck: every bag is
below it.

**Per the pre-registration: nothing live changes.** The single-seed v12 stays on the Webull NOISE leg.
Whether a sizing layer that matches raw's return per drawdown should stay live at all is an owner call,
not something this round can decide.
