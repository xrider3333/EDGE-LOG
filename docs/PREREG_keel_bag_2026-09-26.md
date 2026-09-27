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
