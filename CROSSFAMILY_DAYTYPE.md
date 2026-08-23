# CROSS-FAMILY DAY-TYPE FILTER — does NOISE's "shorts fail after weak closes" transfer to ORB and ENGU-Q?

> Round log opened **2026-08-18**. Harness: `tools/crossfamily_daytype.py`.
> Strategy forks: `augur_strategies/ORB_3_8.py` (ORB 3.6 + the filter) and
> `augur_strategies/ENGUQ_1M_DT_1_0.py` (ENGU-Q 1m RTH engine + the filter).
> Both knobs default OFF and both forks are proven bit-identical to their parents
> with the knob off (smoke tests in each file's `__main__`).

---

## 1. The idea being tested

The 2026-08-17 NOISE campaign (see `NOISE.md`) found that **not taking SHORT entries on the
day after a session closed in the bottom 20% of its own range** was NOISE's single best
standalone filter: +$52,200 over the full window, 98.6% of the gain on the short side,
positive in 14 of 17 years, still +$19.3k after stripping its 10 luckiest avoidances, and it
nearly tripled the ES cross-instrument result. The same "shorts fail after weak closes" shape
had been noticed on four-plus strategy families in this program, but it had **never been built
and tested as an explicit filter on ORB (the standing crown, live in NinjaTrader) or on
ENGU-Q**. That is the gap this round closes.

**The measurement, identical in all three families** — for session *i*, take the PRIOR
session's close position inside its own range, `(close - low) / (high - low)`. It is
unavailable (and the filter inert) on the first session and on any zero-range session.
Everything it reads is a finished prior-session bar, so it is causal by construction.

**The four modes tested on each family:**

| mode | what it does |
|---|---|
| `skip_bot_short` | no SHORT entries the day after a bottom-20% close (NOISE's winner) |
| `skip_bot_all` | no entries at all the day after a bottom-20% close |
| `skip_top_long` | no LONG entries the day after a top-20% close |
| `skip_top_all` | no entries at all the day after a top-20% close |

---

## 2. GROUND TRUTH established before touching anything

### ORB
- **Standing crown: run #234 = `ORB_3_6_C2.py`** ("ride + breakeven", certified 2026-08-17;
  it replaced run #230 / `ORB_3_4_C221.py`). Config: opening range 2 bars, first-candle
  direction, stop 2.0x range, buffer 0.25, close-confirmed entry, target 5.5R, breakeven at
  1.0R, partial and trail both OFF, ATR-regime 0.7, volume-pace 0.7, flat at the close, skip
  holidays.
- **Crown numbers, full history 2010-06-07 → 2026-08-13:** 2,607 trades, $389,874 net,
  PF 1.307, max drawdown $29,142, net/DD 13.38.
- **Lockbox: 2025-08-13 → 2026-08-13, and it is SPENT.** `ORB_3_6_C2.py`'s own docstring says
  the window "has been read MANY times across this research program — treat LB rows as
  encouraging, not confirmatory", and the seven-run plateau study of 2026-08-17 read it seven
  more times. Nothing in this round can spend it further, so the lockbox column below is
  reported as a confirmatory check and was never used to select anything.
- **Selection window used here: 2010-06-07 → 2025-08-12** (the crown's own optimize window).

### ENGU-Q
- **Two live reference points, both used.** The RTH champion is run #149's config, visible as
  run #227 / `ENGUQ_1M_149F_1_0.py`, and it is the ENGU-Q leg inside the current legal book
  baseline ("book A" = ORB #234 + ENGU-Q RTH, $843,388 net / MAR 14.50). The 24-hour branch
  (runs #226 and #235) is the certified deployment candidate but is a different tape. This
  round tests the **RTH champion engine**, because that is the leg the book actually carries.
- **Crown numbers, 2010-06-07 → 2026-06-30:** 2,048 trades, $477,520 net (the file's own
  documented repro figure, reproduced to the cent by this round's harness).
- **Lockbox: SPENT.** The trailing year has been read on runs #198, #223, #226, #227, #232 and
  #235 and throughout challenger rounds 13-15. Treated as confirmatory only.
- **Selection window used here: 2010-06-07 → 2025-06-30.** Confirmatory year:
  2025-07-01 → 2026-06-30. The window stops at 2026-06-30 on purpose — the 1-minute RTH master
  has a real data hole from 2026-07-17 to 2026-08-05.
- **Structural fact that shapes the whole test: ENGU-Q IS LONG-ONLY.** NOISE's winning mode,
  `skip_bot_short`, is a no-op here by construction (asserted in the fork's smoke test). The
  modes that can bite are `skip_bot_all` (blocks longs after a weak close) and the two
  `skip_top` modes (block longs after a strong close).

Both families' baselines were reproduced locally through the real engine before any variant
was scored. ORB: 2,607 trades / $348,129 on the #230 control and 2,607 / $389,874 on the #234
crown, both exact. ENGU-Q: 2,048 trades / $477,520, exact.

---

## 3. PRE-REGISTERED ADOPTION BAR (written before the sweep was run)

A variant is adopted on a family only if it clears **all five** of these on that family's own
selection window:

1. **Net dollars at least the crown's** on the same window and the same data.
2. **net/DD (MAR) at least the crown's** on the same window.
3. **No year made materially worse** — no calendar year may lose more than $5,000 relative to
   the crown, and the count of improved years must exceed the count of worsened ones.
4. **A plateau, not a magic number** — the effect must survive at all three pre-declared
   thresholds, 0.15 / 0.20 / 0.25 for the bottom modes (0.85 / 0.80 / 0.75 for the top modes).
   A variant that only works at one threshold is noise and is rejected.
5. **The mechanism must show up on the side the theory predicts** — for `skip_bot_short` the
   gain has to be predominantly on the short side; for the `skip_top` modes, on the long side.

Anything clearing all five also gets the NOISE campaign's concentration check (share of the
gain from the single best year and from the ten best removed trades) before it is persisted as
a run. Nothing is crowned on the lockbox column, and the lockbox is not consulted during
selection.

---

## 4. RESULTS — the filter does NOT transfer to either family

**Verdict in one line: nothing clears the bar on either family, and on ORB the underlying
mechanism is not merely absent but REVERSED.** Twenty-two variants were scored (ORB: four
modes at three thresholds each; ENGU-Q: three live modes at three thresholds each). Not one
of them cleared gate 1 (net dollars at least the crown's). Every number below was computed by
`tools/crossfamily_daytype.py`, whose control run reproduces both crowns exactly.

### 4.1 ORB (run #234 crown) — selection window 2010-06-07 to 2025-08-12

| # | Run | Type | Net | PF | MaxDD | net/DD | IS (selection) | WF | LB | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 234 | ORB ride+BE, filter OFF (the crown) | $389,874 | 1.31 | $29,142 | 13.38 | $300,932 | not re-run | $88,943 / PF 1.45 | crown |
| 2 | local | + skip shorts after a weak close, cutoff 0.15 | $372,970 | 1.31 | $33,564 | 11.11 | $284,545 | not run | $88,425 / 1.51 | fails net |
| 3 | local | + skip shorts after a weak close, cutoff 0.20 | $368,864 | 1.31 | $33,564 | 10.99 | $286,237 | not run | $82,627 / 1.48 | fails net |
| 4 | local | + skip shorts after a weak close, cutoff 0.25 | $381,385 | 1.33 | $26,796 | 14.23 | $284,840 | not run | $96,546 / 1.61 | fails net |
| 5 | local | + skip everything after a weak close, 0.15 | $347,368 | 1.30 | $29,946 | 11.60 | $262,024 | not run | $85,344 / 1.51 | fails net and MAR |
| 6 | local | + skip everything after a weak close, 0.20 | $303,353 | 1.28 | $29,946 | 10.13 | $228,002 | not run | $75,351 / 1.45 | fails net and MAR |
| 7 | local | + skip everything after a weak close, 0.25 | $291,451 | 1.29 | $27,619 | 10.55 | $214,903 | not run | $76,547 / 1.50 | fails net and MAR |
| 8 | local | + skip longs after a strong close, 0.85 | $337,042 | 1.28 | $30,750 | 10.96 | $257,381 | not run | $79,662 / 1.46 | fails net and MAR |
| 9 | local | + skip longs after a strong close, 0.80 | $330,573 | 1.28 | $31,269 | 10.57 | $254,860 | not run | $75,713 / 1.45 | fails net and MAR |
| 10 | local | + skip longs after a strong close, 0.75 | $338,512 | 1.29 | $29,078 | 11.64 | $259,661 | not run | $78,851 / 1.49 | fails net and MAR |
| 11 | local | + skip everything after a strong close, 0.85 | $291,014 | 1.26 | $30,954 | 9.40 | $207,014 | not run | $84,000 / 1.56 | fails net and MAR |
| 12 | local | + skip everything after a strong close, 0.80 | $271,315 | 1.26 | $35,743 | 7.59 | $194,311 | not run | $77,003 / 1.52 | fails net and MAR |
| 13 | local | + skip everything after a strong close, 0.75 | $277,540 | 1.28 | $28,109 | 9.87 | $189,399 | not run | $88,141 / 1.71 | fails net and MAR |

Selection-window deltas against the crown, in dollars: skipping shorts after a weak close
costs between $14,695 and $16,387 depending on the cutoff. Skipping both sides costs $38,908
to $86,028. Skipping longs after a strong close costs $41,271 to $46,072. Skipping both sides
after a strong close costs $93,917 to $111,533.

**The one thing that did travel is a small risk improvement, and it is not enough.** Skipping
shorts after a weak close raised ORB's profit factor at all three cutoffs (from 1.28 to
1.30-1.31), lowered the selection-window drawdown from $29,142 to $26,796, and lifted the
selection-window net/DD from 10.33 to between 10.62 and 10.68. That is a genuine,
plateau-stable, small risk-adjusted gain. It is bought with roughly $15,000 of net profit, and
the pre-registered bar asks for net dollars first. Gate 3 fails badly as well: 2022 alone gives
back $27,215.

### 4.2 ENGU-Q (run #149 / #227 RTH champion) — selection window 2010-06-07 to 2025-06-30

The `skip_bot_short` mode is omitted because ENGU-Q is long-only, which makes it a structural
no-op (the fork's smoke test asserts it is bit-identical to the parent). For the same reason
the two "skip after a strong close" modes are identical here.

| # | Run | Type | Net | PF | MaxDD | net/DD | IS (selection) | WF | LB | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 14 | 227 | ENGU-Q 1m RTH, #149 config, filter OFF | $477,521 | 1.41 | $65,635 | 7.28 | $364,699 | not re-run | $88,852 / PF 1.42 | crown |
| 15 | local | + skip everything after a weak close, 0.15 | $421,519 | 1.35 | $50,373 | 8.37 | $300,242 | not run | $96,238 / 1.54 | fails net |
| 16 | local | + skip everything after a weak close, 0.20 | $407,835 | 1.34 | $48,486 | 8.41 | $279,516 | not run | $104,826 / 1.62 | fails net |
| 17 | local | + skip everything after a weak close, 0.25 | $313,924 | 1.25 | $65,533 | 4.79 | $241,629 | not run | $74,945 / 1.40 | fails net and MAR |
| 18 | local | + skip longs after a strong close, 0.85 | $470,937 | 1.44 | $60,559 | 7.78 | $348,303 | not run | $102,496 / 1.56 | fails net |
| 19 | local | + skip longs after a strong close, 0.80 | $465,097 | 1.45 | $58,296 | 7.98 | $340,560 | not run | $106,926 / 1.61 | fails net |
| 20 | local | + skip longs after a strong close, 0.75 | $445,955 | 1.46 | $52,853 | 8.44 | $313,675 | not run | $104,831 / 1.62 | fails net |

Selection-window deltas: skipping everything after a weak close costs between $64,457 and
$123,069. Skipping longs after a strong close costs between $16,396 and $51,024.

**The near-miss, and it is a real one.** Skipping long entries the day after a strong close
lifts ENGU-Q's selection-window net/DD from 5.94 to 7.98, cuts the selection-window drawdown
from $61,426 to $42,659 (down 31%), and raises the profit factor from 1.36 to 1.41 — and it
does all of that at all three cutoffs, so it is a plateau and not a magic number. It costs
$24,139 of net profit, about 6.6%, which fails gate 1. On the full window it also turns
ENGU-Q's only losing year (2022, minus $44,796) into roughly minus $11,000, while making 2024
worse by $30,508. This is a drawdown-shaping candidate, not a profit lever, and under the
pre-registered bar it is not adopted.

### 4.3 The mechanism, read directly — this is the important part

Every crown trade was bucketed by where the PRIOR day closed inside its own range, with no
filter applied at all. This shows what the filter is betting on, before any filter exists.

**ORB, full window, average net dollars per trade:**

| prior-day close position | all trades | long | short |
|---|---|---|---|
| 0.0-0.2 (weak close) | +$183 | +$287 | **+$86, PF 1.14 (n=248)** |
| 0.2-0.4 | +$153 | +$130 | +$181 |
| 0.4-0.6 | +$201 | +$151 | +$255 |
| 0.6-0.8 | +$80 | **-$103, PF 0.79 (n=252)** | +$277 |
| 0.8-1.0 (strong close) | +$145 | +$131 | +$161 |

**ORB's shorts after a weak close are PROFITABLE, at +$86 each across 248 trades.** On NOISE
the same population loses $118 each. That is a sign flip, not a weaker version of the same
effect, and it is exactly why the filter subtracts money here. The attribution confirms it: the
235 short trades the filter removes on the selection window were worth +$14,695 in total, an
average of +$63 each, and the decomposition ties back to the dollar with zero added and zero
altered trades (ORB takes one trade per session, so a veto is purely subtractive).

ORB's genuinely bad population sits somewhere else entirely: **long entries after a day that
closed in the 0.6-0.8 band lose $103 each across 252 trades, profit factor 0.79.** That is a
new, unexploited lead. This round did not chase it, because it was not what was pre-registered.

**ENGU-Q, full window, average net dollars per trade (long-only):**

| prior-day close position | n | net | average | PF |
|---|---|---|---|---|
| 0.0-0.2 (weak close) | 453 | $209,281 | **+$462** | 1.64 |
| 0.2-0.4 | 403 | $63,822 | +$158 | 1.28 |
| 0.4-0.6 | 322 | $81,215 | +$252 | 1.51 |
| 0.6-0.8 | 352 | $107,048 | +$304 | 1.62 |
| 0.8-1.0 (strong close) | 518 | $16,156 | **+$31** | 1.06 |

ENGU-Q's best trades by a wide margin are the ones taken the day after a weak close, and its
worst are the ones after a strong close. That is the "buy weakness" meta-finding this program
has banked before, confirmed cleanly on a third family — and it explains both ENGU-Q results
above. Blocking entries after a weak close destroys the best population; blocking them after a
strong close removes the thinnest one and takes a lot of drawdown out with it.

### 4.4 Attribution and concentration

All eight decompositions tie back to the dollar (removed, minus added, plus altered, equals the
net delta), which is the harness's own gate. On ENGU-Q, blocking entries after a weak close
removes 457 trades and ADDS 723 new ones, because a blocked entry leaves the strategy flat and
later signals it would otherwise have slept through now fire. That is exactly the effect the
NOISE campaign flagged, and it is why this filter had to be built into the engine rather than
applied to a saved trade list.

For the record, the ten best individual avoidances are larger than the whole delta in several
modes (for ORB's skip-shorts-after-a-weak-close they are worth +$39,547 against a delta of
minus $14,695). Since every mode fails on direction anyway, the concentration check is moot —
there is no gain to test for fragility.

---

## 5. VERDICT AND WHAT TO DO WITH IT

1. **The NOISE day-type filter does not transfer to ORB or to ENGU-Q.** Both crowns stand
   unchanged: run #234 for ORB, the #149 config for ENGU-Q. Nothing was queued to the runner
   and no crown moved.
2. **The "shorts fail after weak closes" pattern is NOT program-wide.** It is real on NOISE and
   it is sign-flipped on ORB. Anyone citing it as a cross-family regularity should stop. The
   honest statement is that it is a NOISE result which has now been tested on the two families
   that matter most and failed on both.
3. **The "buy weakness" half of the meta-finding DID hold on both new families.** Trades taken
   after a weak close are the better population for ORB longs, and dramatically so for ENGU-Q.
   That is the part worth carrying forward.
4. **Two leads this round uncovered and deliberately did not chase**, because they were not
   pre-registered and chasing them here would be moving the goalposts:
   a. ORB long entries after a 0.6-0.8 prior-day close lose money, profit factor 0.79 over 252
      trades. A pre-registered test of that specific band is the obvious next round.
   b. Skipping ENGU-Q long entries after a strong close is a plateau-stable 31% drawdown
      reduction for 6.6% of net profit, and it repairs ENGU-Q's only losing year. If the owner
      ever wants ENGU-Q sized up into a freed drawdown budget, that is the lever to test on a
      capital-matched basis. It is NOT an adoption under the bar as written.
5. **Both forks stay in the library with their knobs default OFF**, so the next session can
   re-run any of this in one command. Both pass `tools/exec_feasibility_audit.py` with zero
   failures and zero warnings, and both are proven bit-identical to their parents with the
   filter off.
6. **Neither lockbox was spent by this round.** Both were already spent before it started, the
   lockbox columns above are confirmatory only, and no selection decision consulted them.

---

# ROUND 2 — the two ENGU-Q day-type levers round 1 banked and did not chase (2026-08-22)

> Harness: `tools/enguq_daytype_levers.py`. Same engine fork (`ENGUQ_1M_DT_1_0.py`), same
> pinned windows, same cost model. Round opened and this section written 2026-08-22 BEFORE
> any lever result was computed. Owner away; assignment = test the two leads §5.4 banked.

## R2.0 Scope and honesty notes, written first

- **Baseline: the RTH champion** (run #149 config, visible as run #227). Selection window
  2010-06-07 → 2025-06-30 ONLY; the trailing year 2025-07-01 → 2026-06-30 is a SPENT lockbox
  (read on #198/#223/#226/#227/#232/#235) — it gets ONE confirmatory look at the end,
  labelled, and selects nothing.
- **Sizing is a POST-PROCESSING OVERLAY on `return_trades` output, and here is why that is
  honest.** The engine models exactly 1 NQ contract and cannot express per-trade size. Every
  trade's netted dollars are `(points − 0.533) × $20`, where 0.533 pts = $5.66 round-trip
  commission / $20 + 0.25 pt slippage — BOTH components are per contract, so a trade taken at
  size `s` nets exactly `s ×` the 1-lot netted dollars. Sizing therefore commutes with the
  cost model and an overlay is exact for fractional NQ multiples. What the overlay CANNOT
  see: fills themselves (a 2-lot market order may slip more than 2 × a 1-lot; at ENGU-Q's
  size on NQ this is negligible but it is an assumption), and micro-contract commission drag
  (MNQ ≈ $1.98/RT per micro incl. 0.25 pt slippage at $2/pt, vs $10.66 per NQ — so 10 MNQ
  cost ≈ $19.80 vs $10.66, an extra ≈ $9.14 per 1×-equivalent trade). The micro view below
  charges that drag explicitly.
- **ML-score size tilts are a DEAD family in this program (0/12 cleared, 2026-08-10).**
  LEAD 2 is still a size tilt. The difference claimed: the trigger is a single
  pre-registered structural day-type feature (prior session's close position, causal by
  construction), not a fitted model score. The bar below is strict anyway, and if it fails
  it goes in the same graveyard.
- **ENGU-Q drawdown realities:** 27% win rate by design, 47% of 6-trade windows hold 5+
  losers, and the maxDD statistic's 95% CI is wider than the statistic itself. Sizing up
  multiplies EVERY future loss; equal-DD on the selection window does NOT mean equal-DD on
  futures paths. This is stated here so the verdict language cannot soften it later.

## R2.1 LEAD 1 pre-registration — equal-drawdown resize of the strong-close skip

Variant = `skip_top_long` (no LONG entries the day after the prior session closed in the top
band of its range), thresholds 0.85 / 0.80 / 0.75 — the exact round-1 grid, nothing refit.

**Sizing rule (declared before any result):** `s = baseline selection-window maxDD ÷ variant
selection-window maxDD`, capped at 1.50. Applied uniformly to every variant trade.
Views reported: (a) fractional `s` (primary, exact under the cost model above);
(b) nearest-integer NQ (baseline is 1 NQ, so s < 1.5 rounds to 1 = the unsized round-1
fail — reported honestly as such); (c) micro view: `round(10·s)` MNQ, charged the extra
micro commission drag stated in R2.0.

**Adoption bar — ALL must hold on the selection window, fractional view:**
1. Equal-DD net: `s × variant net > baseline net` ($364,699).
2. Plateau: gate 1 holds at ALL THREE thresholds.
3. Worst year: the sized variant's worst calendar year is not worse than the baseline's
   worst calendar year by more than $5,000.
4. Concentration (DISQUALIFYING): add the 10 most-lucrative avoided trades back into the
   sized variant's trade sequence (entry order), recompute its selection-window maxDD,
   re-derive `s'` under the same rule and cap — `s' × adjusted net` must STILL beat the
   baseline net. If the edge lives in 10 lucky avoidances, it dies here.
5. Tradeability: the micro view (c) must also beat baseline net after micro commission
   drag — otherwise the result is "fractional-only" and NOT adopted.

## R2.2 LEAD 2 pre-registration — the buy-weakness size tilt

Variant = the UNFILTERED champion trade list, with trades entered the day after a WEAK close
(prior session close position ≤ threshold) taken at `m ×` size, all other trades at 1×.
No entry is added, moved or removed — overlay on the champion's own `return_trades` output.

**Grid (declared before any result):** `m ∈ {1.5, 2.0}` × threshold `∈ {0.15, 0.20, 0.25}`.
Six cells, nothing else will be tried, no refinement pass.

**Adoption bar — ALL must hold on the selection window:**
1. Net: tilt net > baseline net ($364,699).
2. MAR: tilt net/maxDD > baseline net/maxDD.
3. Plateau: gates 1+2 hold at ALL SIX grid cells (both tilt sizes, all three thresholds).
4. Worst year: the tilt's worst calendar year not worse than the baseline's worst calendar
   year by more than $5,000.
5. Concentration (DISQUALIFYING): the net gain must survive zeroing the 10 largest
   single-trade EXTRA contributions (the `(m−1) ×` slice of the 10 best tilted winners).
6. Integer note reported: 2.0× = 2 NQ (clean); 1.5× = 1 NQ + 5 MNQ (micro drag charged
   as in R2.0).

## R2.3 Discipline

- Champion reproduction ($477,520 / 2,048 full window) through the real engine BEFORE any
  lever is scored; mismatch = stop.
- Lockbox: one confirmatory paragraph at the end, clearly labelled, selects nothing.
- If a lever clears its full bar it earns a pinned single-config path + exec audit + ONE
  queued auto-validate pinned to run #227's window; note that a per-trade-size variant
  cannot currently be expressed as a validate run without engine work — that limitation is
  stated rather than worked around.
- Every tested cell lands on COMPARE ▸ STUDIES regardless of verdict.

## R2.4 RESULTS — both levers die on the pre-registered concentration gate

**Verdict in one line: both levers beat the champion on headline money at every cell of
their pre-declared grids — and BOTH are disqualified by the concentration check, which was
pre-registered as disqualifying. Nothing is adopted, nothing was queued.** The champion was
reproduced through the real engine first: full window n=2,048 / $477,521, selection window
n=1,964 / $364,699 / maxDD $61,426 / MAR 5.94 — parity PASS to the dollar. Every figure
below is from `tools/enguq_daytype_levers.py` (committed) on the pinned windows.

### LEAD 1 — equal-drawdown resize of the strong-close skip

| # | Run | Type | sized net (SEL) | vs base | PF | SEL DD | MAR | worst yr | conc gate | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 21 | 227 | baseline, 1 NQ | $364,699 | — | 1.36 | $61,426 | 5.94 | 2022 −$44,796 | — | baseline |
| 22 | local | skip strong close ≥0.85, sized 1.375x | $478,842 | +$114,143 | 1.40 | $61,426 | 7.80 | 2022 −$18,561 | **FAIL** | dead |
| 23 | local | skip strong close ≥0.80, sized 1.440x | $490,380 | +$125,681 | 1.41 | $61,426 | 7.98 | 2022 −$16,059 | **FAIL** | dead |
| 24 | local | skip strong close ≥0.75, sized 1.500x (cap) | $470,512 | +$105,813 | 1.41 | $59,576 | 7.90 | 2022 −$12,816 | **FAIL** | dead |

- **Gates 1/2/3/5 all PASS at all three thresholds** — a genuine plateau: at equal
  selection-window drawdown the filtered strategy makes $106k-$126k MORE than the baseline,
  its worst year improves by ~$30k, and even the honest micro implementation (14-15 MNQ,
  charged $1.98/RT per micro) still beats the baseline net at every threshold
  ($450,564-$466,409 vs $364,699).
- **Gate 4 (concentration) FAILS at all three thresholds, and it is not close.** Put the 10
  luckiest avoided trades back (worth −$45,097 / −$45,667 / −$48,652 at 1x), recompute the
  drawdown, re-derive the sizing under the same rule: the equal-DD net collapses to
  $278,866 / $295,160 / $278,619 — WORSE than the unfiltered baseline. The whole equal-risk
  gain rests on ten avoided losers out of ~500 skipped trades. Ten trades in fifteen years
  is luck, not a mechanism, and the gate was pre-registered as disqualifying.
- **The integer reality is also brutal at 1 NQ base size:** the derived sizes are 1.37x-1.50x,
  and the nearest whole NQ is 1 — which is the unsized round-1 fail. Only micros (or 2 lots
  at the capped 0.75 cell) can express the size, with the stated commission drag.
- **Confirmatory lockbox look (SPENT window, selected nothing):** sized variants earned
  $140,910-$157,246 vs baseline $88,852 — but their within-lockbox drawdown was
  $79,260-$83,870 vs the baseline's $65,635. **The equal-drawdown promise broke in the very
  first out-of-selection year** — exactly the fragility the "maxDD CI is wider than the
  statistic" memo predicts, and independent support for non-adoption.

### LEAD 2 — buy-weakness size tilt

| # | Run | Type | net (SEL) | vs base | PF | SEL DD | MAR | worst yr | conc gate | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 25 | local | 1.5x on entries after weak close ≤0.15 (322 trades) | $446,718 | +$82,019 | 1.40 | $68,860 | 6.49 | −$42,803 | **FAIL** | dead |
| 26 | local | 1.5x after weak close ≤0.20 (432) | $464,290 | +$99,591 | 1.40 | $76,070 | 6.10 | −$46,172 | **FAIL** | dead |
| 27 | local | 1.5x after weak close ≤0.25 (537) | $473,579 | +$108,880 | 1.40 | $73,526 | 6.44 | −$46,995 | **FAIL** | dead |
| 28 | local | 2.0x after weak close ≤0.15 (322) | $528,736 | +$164,037 | 1.43 | $78,333 | 6.75 | −$40,811 | **FAIL** | dead |
| 29 | local | 2.0x after weak close ≤0.20 (432) | $563,881 | +$199,182 | 1.43 | $90,713 | 6.22 | −$47,547 | **FAIL** | dead |
| 30 | local | 2.0x after weak close ≤0.25 (537) | $582,459 | +$217,761 | 1.43 | $85,626 | 6.80 | −$49,194 | **FAIL** | dead |

- **Gates 1-4 PASS at ALL SIX cells** — net up, MAR up, a full plateau across both tilt
  sizes and all three thresholds, worst year within the $5k band everywhere. The
  buy-weakness population is real (round 1 measured it at +$462/trade vs +$31 after strong
  closes) and tilting it is mechanically profitable in-sample.
- **Gate 5 (concentration) FAILS at ALL SIX cells.** The gain minus the 10 largest
  single-trade extra contributions is negative in every cell (−$3,319 to −$20,166). This is
  structural: ENGU-Q's top-10 winners carry ~83% of its net BY DESIGN, so any proportional
  size-up of a population containing monster winners is a bet on catching the next monster,
  not on the broad population. The pre-registered gate treats that as disqualifying, and it
  was written down before the sweep ran — no goalposts moved.
- **Honest family note:** ML-score size tilts are 0/12 dead in this program. This was a
  single causal structural feature, not a fitted score — and it still failed, on the same
  concentration axis. The tilt graveyard now holds both kinds.
- Confirmatory lockbox look: tilt nets $91,373-$102,481 vs baseline $88,852, with lockbox
  drawdowns $73,085-$94,296 vs $65,635 — modest extra money, every dollar of it bought with
  extra drawdown.

### R2.5 What is banked

1. **Both round-1 leads are now CLOSED with a clean negative.** The drawdown lever's
   equal-risk upgrade and the buy-weakness tilt both clear every profit gate and both fail
   concentration — the improvements ride on ~10 trades out of 15 years. Champion #149/#227
   stands untouched at 1 NQ.
2. **The sizing machinery is an overlay, stated plainly:** the engine models 1 NQ; sizing
   was applied to `return_trades` output, exact for fractional NQ multiples because both
   cost components are per contract; micro views charged MNQ commission drag explicitly.
   No engine fork gained a sizing knob, so nothing needed a byte-identity proof; the
   existing `ENGUQ_1M_DT_1_0.py` filter fork is unchanged and the exec-feasibility audit
   still passes (0 failures).
3. **Nothing was queued to the runner, no lockbox was spent** (one labelled confirmatory
   look on the already-spent trailing year, which selected nothing).
4. All 9 tested cells + baseline are on COMPARE ▸ STUDIES (rows 351-360).
