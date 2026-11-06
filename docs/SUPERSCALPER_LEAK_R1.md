# SUPERSCALPER 240-minute look-ahead - found, fixed (1_1), and sized on the pre-WF rows (TV, 2026-10-20)

Found by the memory-light port's chunking audit (MANAGER #165); reported to MANAGER #1557; MANAGER #168: fix it as
MISC_SUPERSCALPER_1_1 and size the leak on 2010-16. MANAGER #169, after the sizing below (0 trades changed at 16 knob points =
immaterial to the read): T32 (the 900-trial validate on MISC_SUPERSCALPER_1_0, job Lrp43nRV2uevSPAuWUU5) CONTINUES on 1_0;
MISC_SUPERSCALPER_LITE_1_1 (the memory-light copy of 1_1) is the port for a confirmation run if T32 passes, and for any later run.

## The leak (MISC_SUPERSCALPER_1_0, build line ~1998)
The HTF trend gate maps 5 / 15 / 60 / 240-minute buckets onto the 1-minute chart with "lookahead off": a bucket is shown from
the chart bar whose close reaches the bucket's end time E. For the 240-minute buckets (17:00-21:00 ... 13:00-17:00 CT) 1_0 set
E = min(natural 4-hour end, 16:00 CT). But bars after 16:00 CT stayed in the 13:00-17:00 CT bucket (2010-16 data holds bars to
16:14 CT), so from the 15:59 CT bar on, the chart read that bucket's FINAL close (and the EMA 9 / 21 of the bucket closes that
includes it) - up to ~15 bars in the future. The 5 / 15 / 60-minute buckets end at their natural boundaries and were causal.

## The fix (MISC_SUPERSCALPER_1_1)
One line: every 240-minute bucket ends at its natural 4-hour boundary, so a bucket is visible only once it has closed (the
13:00-17:00 CT bucket from the next session's first bar). The 16:00 CT cap is gone. Knobs, defaults, the six paths, exits,
fills and the walk are byte-for-byte 1_0. 1_0 keeps its rules; its LEAKS header note waits until T32 finishes, because the
trial cache keys every trial on the strategy file's sha - editing 1_0 mid-run would make T32 re-pay its trials at the next
re-claim (the PC signs out nightly).

## Proof of causality (cut-data probe, 2015 Q1, 79,574 NQ 1-minute bars, the golden fixture)
For sampled bars i, the build was rerun on the data CUT at i and every value at bar i compared with the full-data run (the 13
signal outputs and all 16 HTF values). 102 samples: every bar 15:50-16:20 CT on 3 days with post-16:00 bars (72) + 30 spread.
- 1_0: 40 of 102 bars differ - every one at 15:59-16:13 CT, always the 240-minute close / EMA 9 / EMA 21 (never the 5/15/60,
  never the 240-minute mid-range, never a signal output on these samples).
- 1_1: 0 of 102 differ.

## Size of the leak (tools/superscalper_leak_r1.py; out C:\EdgeLog\_research_cache\tv_scalp\superscalper\leak_r1.json)
Pre-WF rows only: NQ 1m ETH no-adjust master id 34, seven standalone periods 2010-06-06 .. 2016-06-30 (the r2e periods), file
defaults, fill 'worst', FIFO pairing, cost 0.706 pt, $20 a point. Trades matched on (signal bar, side, path).

| File | Trades | Net PF | ROC@30k | DD5@30k | DD% from peak | Sortino |
|---|---|---|---|---|---|---|
| 1_0 (leaks) | 1,900 | 0.959 | -2.95 | $8.7k | 28.3% | -0.31 (1 EPISODE) |
| 1_1 (fixed) | 1,900 | 0.959 | -2.95 | $8.7k | 28.3% | -0.31 (1 EPISODE) |

Trades changed at the defaults: 0 of 1,900 (0 only in 1_0, 0 only in 1_1, 0 same entry with a different exit).
Trades changed across the knob space (--configs 12: the parity harness's 3 targeted points - window lengths at both ends,
every toggle off, vix none, session filters, stop cap, max hold - and 12 seeded lattice draws over all searchable knobs,
seed 20261020; 15 configs x 7 periods = 105 run pairs): 7,017 trades in each file, 0 changed (0 / 0 / 0).

## Reading
- The look-ahead is real in the values but did not move a single trade on six untouched years at 16 knob points: the leaked bars are the
  last ~15 minutes of the CME session, and the 240-minute gate there did not decide an entry. That does not make 1_0 usable:
  a file that can read ahead is not a clean object, so 1_1 replaces it for every later run; but since no trade moved at 16 knob
  points, T32's read on 1_0 stands (MANAGER #169).
- Nothing live or paper used this file. A confirmation run (only if T32 passes) and any later run use MISC_SUPERSCALPER_LITE_1_1
  (the fixed rules, built in memory-light chunks, trade-for-trade identical to 1_1).
- 2026-11-06: T32 finished as run #496 and FAILED (docs/SUPERSCALPER_VALIDATE_R496.md, DEAD). The conditional confirmation run is not run, 1_0 now carries its LEAKS header, and MISC_SUPERSCALPER_LITE_1_1 was never built or shipped.
