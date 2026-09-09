# POOL vs CROWN -- does carrying the shortlist beat crowning one cell?

Runs scored: **85**. Every number below is the SEALED LOCKBOX YEAR only -- the stretch the search never saw. Dollars, at each run's own contract size.

## What the stored curves are (checked before use)

Each finalist stores its sealed-year equity as a list of cumulative profit readings taken AFTER EACH TRADE, in index points, together with the bar number each reading sits on. Three things had to be handled:

- **They are thinned.** The engine keeps at most 80 readings per sealed year, so a finalist with 229 trades is drawn with 80 dots and the dips between them are invisible. Drawdown read off a thinned curve is therefore too shallow. It is thinned the same way for the crown and for the basket, so the comparison is fair, and the size of the understatement is reported below.
- **They are offset.** The sealed-year line starts at whatever the finalist had made before the sealed year opened. That starting level is subtracted so every finalist begins the sealed year at zero.
- **The last dot is not the end.** The thinning drops trailing trades, so the final dot can sit short of the finalist's true sealed-year result. The true end value is appended, which makes every finalist's contribution net out to the figure the run report shows.

Different finalists trade on different bars, so the lines are put on the shared bar numbering, held flat between trades (cumulative profit only moves when a trade closes) and then averaged. A finalist that took NO trades in the sealed year still gets its slice of the money and earns zero on it -- that is counted, not skipped. A finalist whose curve is missing from the run record entirely (older records stored only the top few) cannot be scored and is dropped.

Thinning cost, measured on the crown against the run report's own drawdown: median -2.5%, worst -27.9% (n=46). Typically small; it applies to both sides, so it moves the gap between crown and basket far less than it moves either one alone.

**Equal weight means 1/N.** Each finalist is scaled to 1/N of one contract before the lines are added, so the basket ties up the same money as the crown. Adding them at full size would be leverage, not diversification.

## 1-2. Crown, basket, top-three basket, random single finalist

*Profit factor* = money made divided by money lost. *Return over drawdown* = the year's profit divided by the deepest peak-to-trough fall. *Random single* = the average finalist, which is what you actually get if you pick one without a rule.

| Basket | Net | Profit factor | Max drawdown | Return over drawdown |
|---|---:|---:|---:|---:|
| CROWN alone | $35,589 | 1.42 | -$29,060 | 1.22 |
| ALL finalists, 1/N | $35,502 | 1.43 | -$23,802 | 1.32 |
| TOP 3 by walk-forward, 1/N | $37,774 | 1.43 | -$25,360 | 1.50 |
| RANDOM single finalist | $35,502 | 1.42 | -$27,073 | 1.19 |

Net and drawdown are the average across runs; profit factor and return over drawdown are the median, because both are ratios and a single run with a tiny drawdown would otherwise dominate.

**One thing the arithmetic settles before any test runs.** A 1/N basket's net is EXACTLY the average of the finalists' nets -- adding N lines and dividing by N is the same operation as averaging their end points. So the basket can never beat "pick one at random" on money; it IS pick-one-at-random on money. The only thing pooling can change is the SHAPE of the year, which means drawdown.

## 3. Drawdown -- where a basket is supposed to earn its keep

The basket's drawdown is guaranteed to be no worse than the average finalist's: the deepest fall of an average line can never exceed the average of the deepest falls. So *whether* it is shallower is not a finding and no test of it is reported here. The finding is HOW MUCH shallower, against what pooling would give if the finalists were genuinely different bets.

- Basket drawdown vs the AVERAGE single finalist: **14.3% shallower** on average (median 9.0%), across 85 runs.
- Basket drawdown vs the CROWN (a real comparison -- the crown is one specific finalist, not the average): +11.8% on average (median +4.5%), shallower in 60 of 85 runs.
- Basket shallower than the crown: sign test 60/85, p=0.0002; signed-rank p=0.0000, effect size r=+0.53.
- For scale: at the similarity these finalists actually show, the textbook blend formula predicts about **15%**, and if they were unrelated bets it would be about **61%**. Observed 14% sits at the near-identical end of that scale, not the diversified end.

## 4. Paired tests, run by run

Each run contributes exactly one crown number and one basket number, so the pair shares tape, costs and sealed window. The sign test asks only who won more often; the signed-rank test also weighs the size of each run's gap.

| Comparison | Median gap | Wins | Sign p | Signed-rank p | Effect size r |
|---|---:|---:|---:|---:|---:|
| Basket net - crown net | $653 | 46/84 | 0.4452 | 0.9183 | -0.01 |
| Top-3 basket net - crown net | $653 | 46/83 | 0.3800 | 0.1863 | +0.17 |
| Crown drawdown - basket drawdown (positive = basket shallower) | $1,642 | 60/85 | 0.0002 | 0.0000 | +0.53 |
| Basket return-over-drawdown - crown | +0.081 | 50/85 | 0.1284 | 0.1764 | +0.17 |
| Basket return-over-drawdown - random single | -0.000 | 41/85 | 0.8284 | 0.8317 | -0.03 |

**Sample honesty.** 85 runs, but only **7 strategy families** (ORB 28, ENGU-Q 18, NOISE 17, TTMSQZ 13, TTIBS 6, GAPGO 2, NQDIP 1). Runs of one family re-search the same instrument over the same tape, so they are nowhere near independent -- the effective sample is closer to the family count than the run count. Collapsing each family to its own average first:

- basket minus crown, one number per family: median $3,892, 4/7 families favour the basket, sign p=1.0000, signed-rank p=0.8125.
- crown drawdown minus basket drawdown, one number per family: median $5,480, 6/7 families favour the basket, sign p=0.1250.

## 5. How different are the ten finalists really?

Each knob is measured against the span the search actually swept it over, so 1.0 means the two finalists sit at opposite ends of that knob. A knob every finalist agrees on is called FROZEN and left out.

- Knobs FROZEN across all finalists: median **25%** of them -- the shortlist agrees outright on a quarter of the knobs and spreads out on the rest.
- Distance between two finalists, as a share of the span the search swept: median **0.33**, closest pair in the median run 0.12.
- Pairs close enough to call the same settings (within 5% of the searched span): median **0%** of all pairs; 0 pairs identical outright; on settings alone, median **100%** of the finalists count as distinct.
- The test that cannot be argued with -- do they TRADE differently? Comparing the sealed-year lines themselves: median **100%** of finalists produced a distinct line, and 10 of 85 runs contain at least one pair that traded identically despite different settings.
- And what actually decides it -- how alike their MONEY is. Splitting the sealed year into 26 equal stretches and correlating the finalists' profit stretch by stretch: median **+0.79** (1.0 means they win and lose in the same weeks, 0 unrelated), 62 of 85 runs above +0.50. High enough that the basket is largely one bet repeated.

So the finalists look different on paper -- they sit far apart on the knobs they argue about -- but they make their money in the same weeks. Different settings, same bet.

## 6. Verdict

- **Money: no.** Against the crown the median gap is $653 per run, basket ahead in 46 of 84, sign p=0.445, signed-rank p=0.918; across families 4/7. Against picking a finalist at random the basket cannot win at all -- it is the same number by arithmetic. Pooling is not a way to make more money.
- **Drawdown: yes, but small and mostly mechanical.** 14% shallower than the average finalist (a guaranteed direction, so only the size is news) and +12% shallower than the crown, median gap $1,642, 60/85 runs, p=0.000, r=+0.53. Real, but a fraction of what pooling ten genuinely different bets would give.
- **Return over drawdown: no.** Median gap +0.08 (sign p=0.128, signed-rank p=0.176, r=+0.17). The one variant that does look better is the TOP-3-by-walk-forward basket, whose median return over drawdown is the highest in the table above -- but it is not significant either (0.101) and the candidate board already showed walk-forward rank does not carry over.

**So: pooling buys a slightly smoother year and nothing else, and even that is mostly arithmetic.** The basket earns the same as picking a finalist blindly (it is that number), does not beat the crown on money, and its drawdown advantage is a fraction of what pooling genuinely different bets would deliver.

**Practicality check -- the one that decides it.** The finalists look different on the knobs but their sealed-year profit correlates at +0.79 and 10 of 85 runs contain finalists that traded IDENTICALLY. A basket of near-identical bets is not diversification; it is the same bet at a different size. The observed 14% drawdown cut against the 61% that unrelated bets would give is the measurement of exactly how cosmetic this is.

**Recommendation.** The standing advice to "carry the finalists as a SET" is NOT supported. It should be restated as: the search's shortlist contains no extra money, and averaging it is not a risk tool because the shortlist is one bet wearing ten hats. If a smoother equity line is the goal, pool across FAMILIES, where the profit really does arrive at different times -- not across one search's finalists.

## Per-family summary (per-run rows are in `pool_vs_crown.csv`)

| Family | Runs | Crown net | Basket net | Crown DD | Basket DD | DD cut vs avg finalist | Distinct lines | Profit corr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ORB | 28 | $55,228 | $53,550 | -$17,172 | -$11,691 | 19% | 88% | +0.81 |
| ENGU-Q | 18 | $50,973 | $57,035 | -$47,525 | -$46,105 | 6% | 94% | +0.62 |
| NOISE | 17 | $42,295 | $31,601 | -$20,432 | -$17,123 | 19% | 100% | +0.64 |
| TTMSQZ | 13 | -$12,279 | $1,456 | -$27,128 | -$13,558 | 15% | 100% | +0.57 |
| TTIBS | 6 | $8,375 | -$8,403 | -$53,894 | -$54,311 | 3% | 100% | +0.89 |
| GAPGO | 2 | -$27,206 | -$11,936 | -$49,224 | -$33,495 | 9% | 100% | +0.64 |
| NQDIP | 1 | $5,920 | $9,812 | -$11,999 | -$5,727 | 26% | 100% | +0.19 |

Generated by `tools/pool_vs_crown.py` from the cached run reports. No Firestore read, no job queued.
