# ORB — the best configurations to use, with walk-forward performance (2026-09-14)

Supersedes the pick order in `ORB_FORWARD_RANKING.md`, which ranked on a return-over-drawdown ratio and was
corrected the same day. This version is judged the way the house now judges book changes: by MONEY, in the
walk-forward stage and by calendar year against the control, with drawdown reported beside it rather than
folded into a ratio.

Sources: every run document for the current ORB family (walk-forward in both windowing schemes, per-fold
results, the Stage-A in-sample figures and the sealed year), and a calendar-year replay of each configuration
through the engine on one contract to the sealed end 2026-08-13. Driver for the ranking columns:
`tools/orb_rank.py`.

## RUNBOARD

| # | Run | Type | Net | PF | MaxDD | MAR | IS | WF | LB | Verdict |
|---|-----|------|----:|---:|------:|----:|----|----|----|---------|
| 1 | #257 | wider stop, looser vol filter | $415,212 | 1.32 | $32,505 | 0.79 | PF 1.132 · 1,922 tr | **$339,110** · 7/8 folds · WFE 4.95 | $91,405 · PF 1.50 · 171 tr | ⭐ champion — most money, wins big years |
| 2 | #239 | control with breakeven 0.8 | $394,864 | 1.32 | $29,377 | 0.83 | PF 1.114 · 1,795 tr | $309,883 · 7/8 · WFE 4.42 | $94,268 · PF 1.50 · 178 tr | 🟡 candidate — cleanest mild upgrade |
| 3 | #234 | the control (in book #396) | $389,874 | 1.31 | $29,142 | 0.83 | PF 1.103 · 1,795 tr | $310,678 · 7/8 · WFE 4.65 | $88,943 · PF 1.45 · 178 tr | ⭐ champion — the reference, keep |
| 4 | #314 | stop 2.5, target 5, breakeven 0.5, both filters | $397,150 | 1.37 | $28,857 | 0.85 | PF 1.178 · 1,559 tr | $252,549 · 7/8 · WFE 3.15 (re-fitted) | $92,102 · PF 1.56 · 168 tr | 🟡 candidate — smoothest, gives up big years |
| 5 | #266 | no vol filter, wider stop | $408,743 | 1.31 | $32,505 | 0.78 | PF 1.118 · 1,933 tr | $334,080 · 7/8 · WFE 5.10 | $91,405 · PF 1.50 · 171 tr | 🟡 candidate — #257 without the filter |
| 6 | #250 | target 5.0 | $389,039 | 1.31 | $29,142 | 0.83 | PF 1.108 · 1,795 tr | $311,673 · 7/8 · WFE 4.57 | $86,988 · PF 1.44 · 178 tr | ⏸️ parked — same as the control |
| 7 | #294 | vol filter 0.75 | $386,710 | 1.31 | $28,477 | 0.84 | PF 1.117 · 1,720 tr | $290,411 · 7/8 · WFE 4.27 | $92,383 · PF 1.48 · 177 tr | ⏸️ parked — filter costs money |
| 8 | #297 | both filters tightened | $378,648 | 1.33 | $30,275 | 0.77 | PF 1.131 · 1,559 tr | $276,201 · 7/8 · WFE 4.00 | $98,179 · PF 1.54 · 168 tr | ❌ dead — drawdown dial, less money |
| 9 | #298 | both filters tightened further | $367,833 | 1.33 | $32,940 | 0.69 | PF 1.151 · 1,468 tr | $261,668 · 7/8 · WFE 3.72 | $105,977 · PF 1.60 · 164 tr | ❌ dead — loses $54k in big years |
| 10 | #260 | tight volume-pace gate | $309,704 | 1.31 | $26,030 | 0.74 | PF 1.129 · 1,366 tr | $224,227 · 7/8 · WFE 4.39 | $95,543 · PF 1.71 · 140 tr | ❌ dead — 51% of money in ten trades |

Net, PF, MaxDD and MAR are the whole window to 2026-08-13 on one contract. MAR = (net per year) / max drawdown.
IS = the validate's Stage-A first 75%. WF = the walk-forward out-of-sample money, anchored scheme (the scheme each
run chose), with folds held and walk-forward efficiency. LB = the sealed final 12 months.

## Money by calendar year against the control

| Run | Years better than #234 | Total vs #234 | In the four biggest years (2021, 2022, 2023, 2025) | Worst single year | Negative years |
|-----|:---:|---:|---:|---:|:---:|
| #257 | 9 of 17 | **+$25,338** | **+$17,138** | −$7,528 (2016) | 6 of 17 |
| #266 | 8 of 17 | +$18,868 | +$12,736 | −$7,528 (2016) | 7 of 17 |
| #314 | 9 of 17 | +$7,276 | **−$33,358** | **−$5,701 (2016)** | 5 of 17 |
| #239 | **10 of 17** | +$4,990 | +$580 | −$9,824 (2020) | 5 of 17 |
| #234 | — | — | — | −$14,299 (2020) | 5 of 17 |
| #250 | 3 of 17 | −$835 | +$340 | −$14,299 (2020) | 6 of 17 |
| #294 | 8 of 17 | −$3,164 | −$8,660 | −$8,597 (2020) | 6 of 17 |
| #297 | 11 of 17 | −$11,227 | −$36,595 | −$8,063 (2020) | 4 of 17 |
| #298 | 10 of 17 | −$22,041 | −$54,504 | −$10,056 (2020) | 5 of 17 |

## What the two measures agree on

1. **Loosening the filters adds money; tightening them removes it.** The walk-forward money falls in the same
   order the filters tighten — #257/#266 at $334-339k, the control cluster at $310k, #294 $290k, #297 $276k,
   #298 $262k — and the calendar years say the same thing, including in the four biggest years. The tighter
   filters are a drawdown dial. Round 55 said this about #297; the whole family says it.
2. **#257 is the configuration that actually earns more, not one that merely risks less.** Most walk-forward
   money of any real configuration, most money by calendar year, ahead in the big years, the least
   concentrated money in the family (35% in its top ten trades against the control's 43%), the most trades,
   and a milder worst year than the control. Its one cost is a deeper maximum drawdown: $32,505 against
   $29,142, about 12% more.
3. **#239 is the upgrade that costs nothing.** Moving only the breakeven from 1.0 to 0.8 wins more calendar
   years than anything else in the table (10 of 17), softens the worst year, and leaves the drawdown where it
   was. The money gain is small, $4,990.
4. **#314, the crown, is the smoothest ride and not the richest.** Best worst year, lowest drawdown, least
   tail-dependent money — and $33,358 behind the control in the four biggest years. Whether that is better
   depends on whether smoothness or money matters more. Its walk-forward figure is not comparable to the
   others: its run re-fits the parameters inside every fold, while the pinned runs replay one fixed
   configuration, so its $252,549 comes from a harder test.

## Two caveats that apply to every row

- **Walk-forward on a pinned run is weaker evidence than the label suggests.** With one configuration there is
  nothing to re-fit, so both windowing schemes return the same number and it is simply that configuration's
  money over the last seven eighths of history - history it was chosen on. The sealed year is the only stretch
  none of them saw, and on one year the spread between them is noise.
- **Differences inside the top cluster are small against what selection can manufacture.** This session's
  meta walk-forward showed that re-picking ORB parameters has no forward skill. So read this table as: the
  control cluster is sound, #257 is the one direction with consistent evidence of more money, and tightening
  filters costs money. Do not read a few thousand dollars between neighbours as a ranking.
