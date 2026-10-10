# SCOPE - CALMDAY: building on what works to cover #463's calm-tape gap (2026-10-10)

The owner asked (project thread, 2026-10-10): "look at our best models or configs and assess what made those particular configs
stand out. Then start looking at how to potentially combine them into one super model". Then: "Either 5th leg for calm days and/or
just another config family ... look at what works on those and build upon it something better and or new."

This is a scope and a DRAFT pre-registration. Nothing below has been run. No price or GEX data was read to write it. The drafting
session had no access to the masters or the GEX photograph.

## 1. What makes the four crowns work (from BOOK.md, ORB.md, ENGUQ.md, TTM.md, NOISE.md)

1. **The edge lives in the exits, not the entries.**
   - ORB #234: breakeven at 1R, then a ride to 5.5R.
   - ENGU-Q: every dollar is in holds longer than 3 days (+$634k). The 1,078 intraday deaths cost -$493k (ENGUQ.md round 62).
   - NOISE #422: 29% of trades carry 97% of the dollars. Those are single trend-day breaks held to the close.
   - TTM: a structural stop, with the exit on the second fading bar.
2. **The filters remove a known loser class; they do not find new winners.** Examples: skip shorts after a weak close, skip the
   top-5% volatility days, ORB's ATR regime filter, TTM's hourly confirmation.
3. **Compression into expansion is a theme in two legs.** TTM's squeeze fire, and NOISE's x1.75 size on hourly-squeeze trades.
4. **All four are volatility harvesters** (§10al). The book earns +$262 a day at low VIX against +$848 at high VIX, and 81% of its
   drawdown days fall in uptrends.

## 2. The calm-day graveyard (do not redo)

These ideas are already tested and dead or closed:
- Plain or VIX-timed long beta: CALMTAPE Q29, vol-managed exposure.
- Every unconditioned fade: REVERT r1/r2, VWAP_FADE, BALANCE r1, DDWEEK, intraday mean reversion.
- Short-vol carry: VOLCARRY, VRPES, VVIXTAIL.
- Overnight drift: the overnight seat is closed.
- Calendar and month-end flow.
- DIP as a seat: it loses in 2020 alongside the book.
- TTIBS as a seat: its drawdown rose 88%.
- NOISE low-volatility skip: no plateau.
- ENGU-Q quiet-ATR stand-down: dead.
- NR7 breakouts.
- The fundamentals-basket line.

**Read:** "a fifth leg that earns on calm days" has been hunted hard, at roughly 15 dead tries. The base rate for a new one is poor.
The cheaper lever is to make the existing legs **lose less on calm days**, and to condition on something the house has never
conditioned on.

## 3. Ranked candidates

| # | Idea | Builds on | Kind | Prior |
|---|---|---|---|---|
| 1 | **GAMMA r1 Arm C, GEXGATE:** ORB and NOISE stand down (or halve size) on long-gamma days | NOISE/ORB filter logic (remove a known loser class), plus the GAMMA r1 data and null already built | filter on existing legs | weak to moderate |
| 2 | **GAMMA r1 Arms A and B, as drafted:** momentum on short-gamma days, reversion on long-gamma days | the NOISE band / VWAP machinery, already at parity | new leg (B is the calm-day earner) | B weak (median ROC 1) |
| 3 | **ENGU-Q day-one survival as a SIZE TILT:** full size on 09:30-16:00 signals, reduced size outside | R62's era-stable survival split (38% vs 11% in all four eras) | config of an existing leg | moderate. A new look on a lockbox-read idea, so WF-only and disclosed |
| 4 | **QUIETNIGHT:** a narrow overnight range into an RTH trend day | compression into expansion (TTM, NOISE squeeze, ORB post-NR7 x1.25 tilt) | new config family | moderate, but adds to ORB's correlation, not the calm gap |

Ranks 1 and 2 share one owner gate (the parked GEX idea) and one data pull. The family null and the parity are already built in
tools/gamma_r1_stageA.py, so Arm C adds one cell family to a run that already exists.

## 4. DRAFT - GAMMA r1 ARM C, GEXGATE (for DISC / TTM review and MANAGER's GO; owner gate shared with arms A and B)

**Question.** Do #463's two intraday NQ breakout legs (ORB #234, NOISE #422) lose money on days the prior session's dealer gamma is
in its top tercile? If they do, a stand-down on those days adds DOLLARS to the book, not only a smaller drawdown.

**Mechanism.** Dealers who are long gamma sell rallies and buy dips, which damps intraday moves and pins price (Ni, Pearson,
Poteshman & White 2021; Barbon & Buraschi 2020). A breakout leg's losers are failed breaks. On damped days, a larger share of breaks
should fail. NOISE's July 2026 trip was a run of failed short breaks (§10at). This is the house's standard winning move (remove a
known loser class) on a state no house filter has used: the house held no options data before the GAMMA r1 photograph.

**What it is not.**
- It is not the NOISE low-volatility skip (dead). That conditioned on realised volatility, which is backward-looking. GEX is
  positioning.
- It is not a VIX gate. VIX-state seats are dead, and in this draft the VIX tercile is printed beside each cell as a confound check.

**Data.**
- The GAMMA r1 GEX photograph (sha-checked, rows after 2025-06-29 dropped).
- The state is exactly Arm A/B's: p = the rank of g(d-1) among the prior 252 GEX days. Long gamma = p >= 2/3.
- Legs: rebuilt through augur_engine.book on #463's pinned masters. Parity first: #463 WF 93.81 / 3.816, and the legs summing to
  the book's daily column to the cent.

**Cells (WF 2016-07-01 .. 2025-06-29 only; lockbox unread).**
- C1 PRIMARY: ORB #234 AND NOISE #422 take no entry on long-gamma days. ENGU-Q and TTM are unchanged.
- C2: the same days at 0.5x (5 MNQ per NQ). It is tradeable.
- C3 NEIGHBOUR: top quartile (p >= 3/4), stand down.
- Per-leg rows (ORB only, NOISE only) are reported, not judged.
- ENGU-Q is excluded because its dollars are multi-day holds, and a one-day state does not describe them. TTM is excluded because
  it is ES 30m with near-zero overlap.

**The first number read (and the binding one).** Each leg's WF net on long-gamma days, with trade count, PF and $/trade, against its
net on the other days.

**Stage A bar (all must pass, C1 judged).**
- **C-A1 dollars, not drawdown:** ORB + NOISE WF net on long-gamma days < 0. If that money is positive, the cell FAILS whatever its
  ROC says, because a drawdown-only gain cannot be confirmed (§10y).
- **C-A2:** #463 with C1 beats #463 on WF ROC@$30k AND on $ a year. DD5 is printed beside both, and the cell is flagged if it is
  driven by one episode.
- **C-A3 luck:** C1's ROC gain over #463 > the family null's p95. The null is the GAMMA r1 shuffled-label null with Arm C's cells
  added to the family max: 1,000 draws, seed 20261007.
- **C-A4 stability:**
  - C-A1 holds in both halves (2016-21 and 2022-25, the 0DTE question);
  - it holds without 2020;
  - it holds without the single best removed-day loss.
- **C-A5 counts:** at least 100 WF trades removed, and at least 25 in every July-June year (thin years flagged).
- **C-A6:** C3 also has net < 0 on its removed days.
- **Look count:** this is a book look. It is added to the LOOKS ledger, and the 71-look chance band (§10z) is printed beside the
  gain.

**Prior, written down now.**
- ORB #234 still earns about +$100 a trade in the LOW-VIX tercile (r24_triage), and GEX and VIX are related. So the prior that
  ORB loses on long-gamma days is weak.
- NOISE's prior is better: its losses cluster in failed breaks, and L nets -$301,860 on the 689 quiet no-break days (BALANCE counts).
  But "no break" is known only after the day, and GEX is known before it.
- Median expectation: C-A1 fails for ORB and is close for NOISE. It runs because the data, harness and null already exist.

**What follows.**
- **PASS:** a per-leg plugin gate reading the daily photograph, a window-pinned ranged Auto-Validate per leg, then the adoption page
  (owner's call on WF plus mechanism, per §10aa).
- **FAIL:** a ledger row. GEX is not tried as a filter again, on any cut.

## 5. DRAFT - ENGU-Q R67 SURVIVAL TILT (sketch only; the ENGU-Q lane owns it)

- R62 found that cash-session signals survive day one 36-39% of the time in all four eras, against 11-15% for the rest. The gate
  failed only Sortino by 2% and the lockbox-without-biggest-trade clause.
- A tilt keeps the long-hold winners that a gate throws away. Cells: out-of-window signals at 0.5x / 0.75x, in-window at 1.0x. The
  0.5x cell is the primary.
- **Honest flag:** R62's numbers, including its lockbox, are already seen. This is a follow-on look on a known split. It is judged on
  WF only, the R62 read is disclosed as prior, and it is counted in the look ledger.

## 6. "Have the best configs keep searching" (owner, 2026-10-10): where search can still pay

**Parameter search inside the four crowns' own files is saturated.** Five saved search populations were checked
(tools/r16_results/ryr_search_{orb,noise,ttm,enguq_eth,enguq_er}.csv) for leaders sitting at the edge of their ranges.
- The only edges point to wider trails on ENGU-Q (trail_frac at 4.0) and a wider Keltner on TTM (kc_mult at 2.0).
- ENGUQ.md §1.0 already shows that the wider-trail corner is a tail artifact: ERW at 5.0 loses money without its top 10 trades.
- ORB's leaders sit where the crown already is (2-bar range, no partial exit).
- The meta walk-forward found no forward skill in re-picking ORB parameters, and every recent book challenger sits inside the
  71-look chance band.

More searching on the same NQ/ES history adds trials, not information.

**Where the crowns can still search: new markets.** TRANSFER r1 (ledger 2.29, tools/rocfrontier/PREREG_TRANSFER_R1.txt, plus
r1b) runs ORB #314, the NOISE #422 core and the TTM #458 core UNCHANGED on ZN / 6E / CL / GC 1m, plus RTY / YM 5m.
- It is fully pre-registered and parity-ready. It is blocked only by data: the owner declined Databento on 2026-09-30 (Standard
  CME plan, $199 for one month).
- It is the one search that tests the crowns' mechanisms out of sample. A pass would add legs from different asset classes,
  which is what the book's correlation map needs.
- **Honest caveat:** TRANSFER r2 found the crowns' edges do not carry to bond or gold FUNDS at 5 minutes and are flat on DIA /
  IWM. So the prior for ZN / GC is weak. CL and 6E have no fund read.

## 7. Owner decision (2026-10-10 18:21 UTC, project thread)

The owner said: "not buying anyting so you choose". The choice made on that delegation is **GAMMA r1 only, with Arm C added**.
TRANSFER r1 stays shelved because it needs paid data.
- This is the owner's go for GAMMA r1 Stage A. It lifts the 2026-08-15 park on the GEX idea for this test only.
- Arm C (§4) joins the shared family null, and the bars do not move.
- Order: Arm C parity first (#463 WF 93.81 / 3.816, legs to the cent), then Stage A for all three arms. WF only, lockbox unread.
