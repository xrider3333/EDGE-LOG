# PRE-REGISTRATION (DRAFT for MANAGER) - which part of the 09-27 NOISE "fixed" package carries it? (2026-10-05)

Custom ML queue item 2 under MANAGER #50 (MANAGER asked: the 09-27 package read ~109-112 WF ROC at $30k against #422's
85, and NOISE round 69 has now shown its compression WEIGHT alone does not carry that). Walk-forward ONLY. The package's
lockbox was read on 09-27 (round 61 / run #457), so no lockbox is read here and a pass can only ever become a forward
no-order shadow. The only numbers computed before this draft are the feature-only counts below (no P&L read).

## Map placement first (docs/MDL_MAP_R1.md)
A re-sizing of #463's NOISE leg: it must beat PLAIN EXTRA NOISE (the same leg scaled to the same mean size) inside
BOOK #463 (WF 93.8 / Sortino 3.82 at $30k). Standalone ROC at $30k is leverage-free, so a standalone #422 read cannot
tell a tilt from extra size; the book read can. Plausible: the package's standalone WF gain (~109 vs 85) is far above
the extra-NOISE line, and book round 58 found the NOISE leg the one place re-sizing has shown anything real.

## The package (frozen 09-27, ml_keel.compression_sizes with v12's fixed settings; no model)
On top of #422's own sizes (1x, or 1.75x in its compressed hours): KEEL's 60-minute squeeze (sq60_on) x1.5; Friday
entries x1.5; FOMC pre-statement entries (statement day, entry before 14:00 ET) x0.5; product capped at 3.

**Feature-only counts (BOOK #463's NOISE leg, NQ 5m RTH no-adjust, WF 2016-07-01..2025-06-29, 2,797 trades):**
| part | WF trades tilted | 2011-01..2016-06 block |
|---|---|---|
| squeeze x1.5 | 308 | 245 |
| Friday x1.5 | 510 | 264 |
| FOMC x0.5 | 66 | 20 |
| full package | 820 (60 at 2.25x) | 479 |
The cap of 3 NEVER binds (largest package multiplier 2.25x; capped and uncapped are identical), so it is not a part.

## Arms (each is the #463 NOISE leg re-sized; every other leg and the book convention unchanged)
- **P** = the full package.
- Leave-one-out: **P-squeeze**, **P-Friday**, **P-FOMC**.
- Singles: **squeeze**, **Friday**, **FOMC** (each alone on #422).

## Yardstick and twin
BOOK #463 rebuilt from the identical leg runs (parity 93.8 / 3.82 asserted first, as in tools/noise_hedge_tilt.py).
For every arm its own twin = #463 with the NOISE leg scaled by c = mean(m x s) / mean(s) over WF trades (s = #422's own
size), i.e. plain extra NOISE at the same average size. Unified convention: daily-valued, years = (last - first) / 365.25.

## Bars for a part to "carry" the package (Stage A, walk-forward only), judged on its SINGLE arm
1. Beats its twin AND #463 on WF ROC at $30k AND Sortino.
2. Without Feb-Apr 2020: still beats its twin.
3. Beats its twin in >= 6 of the 9 WF years (July-June).
4. The untuned 2011-01..2016-06 block: beats its twin.
5. Aim, not shape: its WF ROC lead over its twin is above the 98.3rd percentile (95% over the three singles) of
   1,000 shuffles of its own multipliers across the WF NOISE trades, each shuffle scored against its own twin at its
   own c (seed 20261005).
6. >= 100 tilted WF trades. **FOMC has 66, so FOMC can never pass; it is reported only** (power stated now).

Attribution (reported regardless, never a bar): each leave-one-out drop = lead(P) - lead(P-part); P and every arm's
lead over its twin, ROC and Sortino; per-year leads.

## What a result means
- A part that passes 1-6 -> a forward no-order shadow judged by the paired sequential stop (running-mean form,
  docs/PREREG_paired_sequential_stop_2026-09-29.md) at 50 closed relevant trades. NOISE's sub-arm reader
  (tools/noise_fixed_subarm_read.py, c0787605) already tracks full / Friday / FOMC forward; a squeeze pass would add a
  squeeze sub-arm there via the NOISE lane. RUNBOARD entry either way.
- If P itself fails bar 1 inside the book, the 09-27 standalone gain was extra size, not aim, and the package is
  recorded dead as a book re-sizing (ledger + memory); NOISE's forward reader keeps running as NOISE decides.
- No variants (no other multipliers, days or thresholds). Nothing live or in the book changes without the owner.

## Priors to disclose
- Friday 1.5x FAILED the tilt guard in NOISE round 47.
- Book round 62 parts check (09-27, old convention, standalone): package 3.63 return/DD vs 3.33 without squeeze vs
  #422 2.82 - both the squeeze and Friday+FOMC looked positive standalone; never read against plain extra NOISE.
- The ML shuffle audit (09-30): no ML-sized leg beat its own shuffled sizes at the 95th pct in both stretches.
- NOISE round 69 (10-04): more weight on #422's own compressed hours LOWERS WF ROC at $30k (84.6 -> 80.9 at 2.25x).
