# SUPERSCALPER r2e - RE long vs an always-long twin on the PRE-WF rows: FAILS on all four tests (OUR PORT) - TV, 2026-10-16

Prereg `docs/PREREG_tv_superscalper_r2e_prewf_2026-10-16.md` (LF sha256 35407345..., witness prereg/tv-ssexplore5 @ c19e0ec7, pushed and
posted to MANAGER before the run; GO MANAGER #151; two adversarial reviews before the freeze). Harness `tools/superscalper_explore_r2e.py`
(LF 9f27ffee...). Port LF b8ef032f... at file defaults, close_rule 'any', intrabar 'worst', NQ 1m ETH no-adjust master id 34, QQQ helper
withheld (not held before 2016), ES helper id 30 checked per period. Output `C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2e.json`
(log `explore_r2e_run.log`). Pre-WF rows only: 2010-06-06 .. 2016-06-30, seven standalone periods. The validate window and lockbox unread.

## Step 0 - the QQQ control (dev years)
Parity gates passed (2023 2,311 / 2,005.9 / 0.5690; 2024 2,633 / 1,997.4 / 0.5853). With QQQ withheld the port makes 2,314 / 2,634 trades
(all 2,311 / 2,633 originals kept, +3 / +1); RE long 364 trades PF 1.207 / 412 PF 1.118 - same object (QQQ barely acts).

## Verdict: RE LONG FAILS PRE-WF - all four tests
| Test | Bar | Pre-WF (pooled 2010-06 .. 2016-06) | |
|---|---|---|---|
| A - beats the always-long twin | paired t >= 2.0 | mean d -0.08 pt a trade, sd 11.4, t -0.12 (n 310) | not separable from always-long drift |
| B - PF at +1 tick | >= 1.10 | 0.785 (0.838 at 0.706) | below the PF bar |
| C - trades a year | >= 100 | 51 | too thin |
| D - without the best exit date | PF >= 1.10 at +1 tick | 0.720 | one episode |

Per period RE long (trades / PF at 0.706): 2010H2 14 / 0.00; 2011 43 / 0.71; 2012 37 / 0.79; 2013 16 / 5.21; 2014 47 / 0.78;
2015 91 / 0.66; 2016H1 62 / 0.84 - one period of seven above 1.

Four numbers, pooled pre-WF daily P&L (ROC@30k / DD5@30k / DD% from peak / Sortino), at 0.706:
- RE long: -4.1 / $22.8k / 28.5% / -0.52 (1 EPISODE); at +1 tick ROC -4.7.
- The whole port: 1,902 trades (313 a year), PF 0.955: -3.2 / $8.7k / 28.3% / -0.34. All longs 1,345 trades PF 1.005 (ROC 0.3, twin
  t 1.12); all shorts 557 PF 0.859 (ROC -4.1).

## Reading
- r2d's carrier was the two dev years, not an entry edge: on six untouched years RE long loses after cost and is indistinguishable from
  holding long over the same clock windows. The path line closes. Selection had warned (best of 12 cells).
- The port trades far less at 2010-16 prices (313 a year vs 2,311-2,633 in 2023-24): its point-based gates (the 5-point minimum target, the
  15-point stop floor) bite at NQ 2,000-4,500. That is part of the object being tested, not a reason to rescue it - but it also means the
  validate's training stretches that start in 2016 (NQ ~4,500) see a thinner port than its later folds do.
- For the queued 900-trial validate: the whole port is PF 0.955 (ROC -3.2) on the pre-WF rows at file defaults. That is one more
  reason the priors (NOISE, STRATEGY-BEATING) put WF ROC >= 15 at 5-10%. The validate stays queued (owner order); nothing changes.
