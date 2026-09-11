# ORB — which configurations deserve forward testing (2026-09-11)

Every configuration below already passed a full Auto-Validate at 7 of 8 walk-forward folds, so the
verdict does not separate them. What separates them is the sealed year, whether the money is spread
across many trades or sits in ten, how the configuration behaves inside the adopted book, and how
much evidence per month it will generate once it is live.

Built from: every ORB run in Past Runs (65 of them), the sealed-year figures on the run documents,
and `tools/orb_rank.py` / `_orb_rank.csv` for the parts the compare scatter plots do not carry —
concentration and the recent-regime read. Book figures come from round 53 (`ORB_ROUND53_BOOK_LEG.txt`).

## Three findings from this session that drive the ranking

1. **Ranking ORB configurations on the stretch they were chosen on has no forward skill.** Eleven
   non-overlapping forward years: re-picking the best configuration earned $166k, leaving the parent
   defaults alone earned $377k, a configuration drawn at random earned $312k. Inside the book it is
   worse than useless — selection-stretch and sealed-year scores are negatively correlated at −0.31.
   So full-window net and the five-year figure are the LEAST trustworthy columns here.
2. **The edge is improving, and not because we picked it.** Profit factor rises from 1.09 to 1.41
   across the crown's history, survives stripping the five biggest winners from every block, and
   reproduces on five configurations nobody ever selected. Every configuration in the table below
   shows the same first-half-to-second-half rise. Recent evidence is the representative evidence.
3. **Concentration has retracted three claims in this stack in one week.** A configuration whose
   money sits in ten trades is not forward-testable in any useful time frame, whatever its headline.

## The ranking

| # | Run | What it changes vs the control | Sealed yr $ | Sealed PF | Top-10 share | Ex-top-10 PF | 5y MAR | Trades | In the book, sealed yr | Call |
|---|-----|-------------------------------|------------:|----------:|-------------:|-------------:|-------:|-------:|------------------------|------|
| 1 | **#297** | vol-regime filter 0.70→0.75 and volume-pace 0.70→0.80 | 93,209 | 1.508 | 44% | 1.182 | 2.12 | 2,299 | **1st of 214 (11.54)** | **Add** |
| 2 | **#294** | vol-regime filter 0.70→0.75 only | 92,383 | 1.479 | 43% | 1.179 | 2.32 | 2,500 | not run | **Add** |
| 3 | #314 | stop 2.5, target 5.0, breakeven 0.5, both filters | 87,132 | 1.531 | **38%** | **1.231** | **2.79** | 2,299 | 10.04, below control | Keep |
| 4 | #257 / #266 | wider stop with a looser or absent vol filter | 90,235 | 1.495 | **35%** | 1.205 | 2.11 | **2,750** | not run | Optional |
| 5 | #239 | breakeven 1.0→0.8 | 94,268 | 1.495 | 42% | 1.184 | 2.30 | 2,607 | not run | Optional |
| 6 | #234 | the control itself | 88,943 | 1.453 | 43% | 1.175 | 2.37 | 2,607 | 10.33 | Keep |
| 7 | #298 | both filters tightened further (0.80/0.80) | **101,017** | 1.576 | 46% | 1.181 | **1.85** | 2,169 | not run | No |
| 8 | #260 | tight volume-pace gate | 89,908 | **1.668** | **51%** | **1.153** | 1.95 | 2,032 | not run | No |
| 9 | #244, #250 | stop 1.75 / target 5.0 alone | 90,036 / 86,988 | 1.49 / 1.44 | 45% / 42% | 1.16 / 1.18 | 2.07 / 2.35 | 2,607 | not run | No |
| 10 | #228, #230 | earlier families (3.5, 3.4) | 10,390 / 64,575 | 1.06 / 1.31 | — | — | — | — | not run | Superseded |

Already live in paper: the control (#234) since 2026-08-24, and #314 since 2026-09-08, plus a gate
leg on the control and three compression-tilt legs on #314.

## Why the top two

**#297 is the only configuration with independent evidence from two directions.** Standalone it is
third on the sealed year. Inside the adopted four-leg book it ranks first of 214 on the sealed year,
against the control's fourteenth, and the five rows beneath it are its own neighbours — it is a
plateau, not a spike. All nine configurations that beat the control on both stretches carry these two
filter settings, out of three filter settings tested. And the change is tiny: it keeps the control's
exact geometry and moves only the two filter thresholds.

**#294 earns its place by bracketing #297.** It moves one of the two filters. Running both forward
tells us which filter is doing the work, at the cost of one more paper leg. If only one slot is
available, take #297.

## Why not the ones with the best headlines

**#298 has the best sealed year in the table at $101,017 and should not be trusted for it.** It also
has the worst five-year and worst full-window risk-adjusted return of the group, and the fewest
trades but one. That shape — one excellent recent year on a configuration that is otherwise the
weakest — is the exact pattern that has been retracted three times in this stack this week.

**#260 has the best sealed-year profit factor at 1.668 and the worst concentration at 51%.** Over
half its money is ten trades, and stripping those ten leaves the weakest profit factor in the table.
It also trades least, so it would take longest to learn anything from.

**#314, the current crown, is not the standout its five-year figure suggests.** That figure is the
statistic it was crowned on, so it cannot also be evidence for it. On the sealed year it is second
from last in this group, and in the book it scores below the control it was meant to replace. What it
genuinely owns is robustness: the least tail-dependent money in the table and the strongest
improvement into the current regime. Keep it running, but it has not earned the crown twice.

## What I would actually do

Add #297 as a third opening-range paper leg beside the control and the crown, and #294 alongside it
if a fourth leg is cheap. Leave everything else alone. The four-leg book with the #297 leg is already
queued so the house scorer rules on the book half of this independently.
