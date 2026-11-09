# RESULTS — ENGU-Q BODY BREAK, R-FLOORED (BBRF) · ES 5m · intraday only

**THE ROUND CLOSES AT DRAFT. No trial budget was spent, and I recommend none be.** The owner's
fixed-R intraday exit does not pay on this family's one supported entry — **0 of 72 exit cells clear
the bar, the best fold count anywhere is 3 of 8 against a bar of 7, and 0 of 72 are profitable once
slippage is counted.**

**And the design's own claim was confirmed, which is what makes the close worth something.** The R
floor did exactly what it was built to do: cost fell from r2's 0.11–0.36 of 1R to **0.0275–0.0553 of
1R**. The arithmetic problem is fixed and the edge still is not there. That separates two questions
that were tangled together before today, and answers the second one.

Prereg `docs/PREREG_enguq_bodybreak_rfloor_2026-11-09.md`, body sha
`6fe6f7525bfb84d66b9a7f7167ed8db68f79b5ab2182490c89d5b5e5d5ceeeea` (verified by the harness at
start), addenda 1 and 2 appended before their own measurements. Harnesses
`tools/enguq_bbrf_gate.py` (selftest PASS 16) and `tools/enguq_bbrf_stage2.py` (selftest PASS 9).
Pre-lockbox ES 5m, 1,058,658 bars, 2010-06-06 .. 2025-06-30, 15.07 years. **The lockbox was not
opened.** Owner order 11-09, MANAGER #149, board w118.

---

## 1. The gate: no entry cell has an edge distinguishable from zero

48 cells, entry and R floor only, gross compared **in R and never in points**.

| | result |
|---|---|
| cells whose held-to-close expectancy is distinguishable from zero | **0 of 48** |
| cells whose expectancy beats the real 0.45 pt round trip | **0 of 48** |
| best baseline anywhere | **+0.0266 R**, against that cell's own MDE of **0.0768 R** and its own cost of **0.0541 R** |
| largest baseline magnitude anywhere | −0.0425 R, against an MDE of 0.1124 R |
| cost in R, across the grid | **0.0275 – 0.0553** |

- **Every cell's baseline is smaller than its own minimum detectable edge.** With 605 to 2,208 trades
  per cell and a per-trade spread near 1.0 R, the MDE runs 0.049 to 0.145 R; no cell's measured
  expectancy reaches its own threshold in either direction. The honest statement is **not** "the entry
  loses" — it is **"the entry's intraday expectancy is indistinguishable from zero at this sample
  size."**
- **The R floor worked, and that is the one claim of the design that survives.** r2's risk of 1.5–5.3
  points made the real round trip 8–30% of 1R; flooring the stop at 8/12/16 points put it at
  2.75–5.53%. A fixed-R target is now arithmetically reachable. It still does not pay.
- **More body is WORSE here.** The `b = 3.0` cells are mostly negative while `b = 2.0` is mostly
  positive-but-indistinguishable. The body test's value in r2 and in the overlap round **does not
  extend to a third-multiple body**, and I am not reading it as if it did.

### 1a. MY GATE'S CEILING CLAUSE WAS NEAR-VACUOUS — a defect in my design, on the record

Addendum 1 made the hard close depend on the mean maximum favourable excursion falling at or below
cost in R. **Measured, the ceiling is 0.56 to 1.07 R in every one of the 48 cells**, including cells
whose held-to-close expectancy is plainly negative — because **a floored, therefore wide, stop almost
guarantees a large favourable excursion somewhere in a session**. The clause can never fire.

**So the 36 "OPEN" verdicts the gate printed are not evidence of anything, and I am saying so before
anyone reads them as encouraging.** Addendum 2 replaced the clause with the baseline-against-MDE
reading above, and sent the one question the baseline genuinely cannot answer to stage 2.

## 2. Stage 2: the owner's own exits, measured in full

**The question the gate could not settle.** A fixed target truncates the outcome distribution, so
where the favourable excursion mean-reverts, taking a target can pay more than holding to the close.
That is a real mechanism and it deserved a measurement rather than an argument.

72 cells: 6 result-blind entry cells (**every gate cell with n ≥ 2,000 at s = 1.5**, across all three
floors — trade count was fixed by the grid before anything was measured and cannot peek at an
outcome) × `T` ∈ {1.0, 1.5, 2.0, 3.0} × `M` ∈ {12, 24, 48} bars. Stop wins ties. Flat at the earlier
of `M` bars or the 15:55 close, so **every trade closes the same session**.

| | result |
|---|---|
| cells clearing the full bar | **0 of 72** |
| cells with positive net at 0.45 pt | **1 of 72** |
| cells with positive net at 0.95 pt (with slippage) | **0 of 72** |
| best fold count anywhere | **3 of 8** (the bar is 7 of 8) |

**The single positive cell, and why it is not a candidate.** `w=20 f=8 T=3.0 M=48`: net **$4,596**
across 15.07 years — **$305 a year** — ROC@$30k **0.22**, DD5 **$14,925**, DD% from peak **40.65**,
Sortino **0.07**, **2 of 8 folds**, `one_episode` **TRUE**, and **one fold holds 552% of the net**
against a pre-registered 40% cap, which means the other folds collectively lost money. It fails five
of the six clauses. At the slippage row the same cell loses **$50,129**.

## 3. THE FINDING THAT DOES SURVIVE — and it points the opposite way to the order

**Net improves monotonically as the trade is allowed to run longer and farther**, measured inside a
design that never holds overnight at all:

| target `T` | mean net $ | mean folds won | | time stop `M` | mean net $ | mean folds won |
|---|---|---|---|---|---|---|
| 1.0 R | −53,953 | 1.28 | | 12 bars (1 h) | −49,611 | 1.33 |
| 1.5 R | −41,502 | 1.78 | | 24 bars (2 h) | −40,209 | 1.67 |
| 2.0 R | −34,911 | 1.78 | | 48 bars (4 h) | **−32,110** | **1.96** |
| 3.0 R | **−32,208** | 1.78 | | | | |

- **Both gradients run the same way: the tighter the target and the shorter the hold, the more it
  loses.** The owner's 1R target is the single worst of his four, and the one-hour time stop is the
  worst of his three.
- **This is the seventh independent confirmation in this lane that cutting this family's hold short
  taxes the edge** — after shelf No. 39 (0 of 15), hold cap r2 (116 dead values), executor r1's T08
  (112% of net from holds through the close), Webull arm C (26.09 → 6.17), pullback-break r2, and the
  R-exit retrofit (0 of 5 on every crown). **The novel part is that it now holds strictly inside a
  session**, with no overnight hold anywhere in the design, so it is not an artefact of comparing
  intraday against multi-day.
- **What I would tell the owner plainly:** his eye for the entry is not the problem and the body
  observation was right twice. What the tape will not give him on this shape is a quick, fixed-size
  win — every step he takes toward letting it run costs him less, and the gradient does not turn
  around before it runs out of session.

## 4. My prior, and whether I kept to it

My prereg said **under 20%** that this clears the bar, and named six prior reads against it. It did
not clear. **I am not claiming credit for that** — the useful part is not the direction, which was
easy, but the two things the round pinned down: that r2's failure was arithmetic rather than a
market finding (the floor fixed it and nothing changed), and that the hold gradient survives inside a
single session.

## 5. What this round did NOT do

- **No trial budget spent, and no 900-trial validate queued.** MANAGER #149 required a GO before the
  budget; the gate closed the round before a GO was needed, which is what a power-first gate is for.
- **No strategy file written**, so nothing went near the plugin gate.
- **No lockbox opened.** Nothing touched live, paper, the box or any account.
- **No limit fills.** Every entry and exit is a market order at a bar's open or a touched level; the
  "through the level by one tick" rule remains unimplemented in this lane and stays a separate
  pre-declared arm.
- **No cells merged** to reach the trades-a-year floor, and no bound re-cut after seeing a result —
  both changes to the method are addenda with their own shas.

## 6. Run records

**72 run records written**, one per stage-2 cell, each from that cell's own daily dollar series with
zero days included, stage `preLB`, family `ENGU-Q`, ES 5m, at the 0.45 pt real round trip. **The 48
gate cells get none**: they are per-trade R statistics with no daily dollar series, and numbers not
measured with a daily series are not written.
