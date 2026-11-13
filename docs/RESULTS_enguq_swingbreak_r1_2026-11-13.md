# RESULTS — ENGU-Q SWING STRUCTURE BREAK · NQ 1h / 4h / daily · r1

**VERDICT: CLOSES AT DRAFT. 0 of 72 cells OPEN; all 72 read TIMING IS NOTHING.** No trial budget
spent, no strategy file, no lockbox opened, nothing touched live, paper, the box or any account.

Prereg `docs/PREREG_enguq_swingbreak_2026-11-13.md`, frozen body sha
`fd0820c6bde7c9b4a00fea9d3235b5ecf5298d146e42585ac25910ebd5979b1b` at commit `68a886c4`
(**verified MATCHES by the harness at start**, read back from that commit rather than from the
working file); with ADDENDUM 1 the file's sha is `1161e687…`. Gate
`tools/enguq_swingbreak_gate.py` (selftest 27 PASS), output
`C:\EdgeLog\_anatomy_cache\enguq_swingbreak_gate\gate.json`.

Master `ADJ_NQ_60m_RTH.csv`, 29,156 bars; **pre-lockbox 26,707 60m bars, 2010-06-07 .. 2025-06-30,
15.06 yr.** 4h and daily resampled from that one tape, empty bins dropped.

---

## 1. TWO DEFECTS IN MY OWN HARNESS, BOTH FOUND BEFORE REPORTING, AND THE FIRST ONE WOULD HAVE SENT A VALIDATE

**This is the most important section of this document.** The first two versions of this gate printed
**13 OPEN cells.** Under the w120 standing GO an OPEN cell queues a 900-trial validate **with no
further approval**. Both OPENs were artefacts of my own control.

**Defect 1 — the control had a different R from the signal arm.** The control entered mid-move and
was given *its own* structure stop, i.e. the trail as of its entry bar. By then the trail has
ratcheted up to just under price, so the control's R was far smaller than the signal arm's, it
stopped out at −1R almost every time, and the control mean was **−0.27 to −0.50 R in all 72 cells**.
`delta` was therefore measuring **stop width**, not **entry timing**. Fixed by giving the control the
signal trade's own risk in points — which is also the literal reading of §7's *"run the IDENTICAL
stop"*.

**Defect 2 — the control's draw window was the realised hold.** I drew the control's entry from
`[signal bar, the trade's own exit bar]`. **That upper bound is the future.** Winners ran long, so
their controls were drawn deep into an already-extended move and bought the top; losers stopped out
fast, so their controls had one or two bars to choose from. **The control was conditioned on the very
outcome it was meant to be compared against.** Fixed by drawing from a **fixed horizon of H bars
after the signal**, declared in advance and blind to any outcome.

**The tell that caught both, and it is worth keeping as a rule:** in both broken versions, **0 of 72
heterogeneous cells had the signal worse than the control.** A perfectly one-sided sign across 72
cells spanning three timeframes, three pivot widths and two exit rules is not an edge, it is a
structural artefact — the same family of error as "a constant repeated across heterogeneous cells is
never a result". **After the repair the sign is two-sided: the signal is worse than its control in
19 of 72 cells**, which is what a real comparison looks like.

**The horizon is not doing the work, and this is checked rather than assumed:**

| control horizon `H` | control mean R | mean `delta` | cells beating their MDE2 |
|---|---|---|---|
| 5 bars | +0.1023 | **+0.0313** | **0 of 72** |
| **10 bars (judged)** | +0.1036 | **+0.0301** | **0 of 72** |
| 20 bars | +0.1354 | **−0.0018** | **0 of 72** |

The verdict is identical at every horizon, so the one free choice in the repaired control changes
nothing.

## 2. The result

| | |
|---|---|
| cells screened | **72** (36 × two exit arms, ADDENDUM 1) |
| **OPEN** | **0** |
| **TIMING IS NOTHING** (`delta` ≤ its two-sample MDE) | **72** |
| signal worse than a later random entry | 19 of 72 |
| best `delta` | **0.1616 R** (`1d k=3 HH S+ATR close`) against **MDE2 0.7947** — **5× underpowered** |
| mean `delta` across all cells | **+0.0301 R** |

**The structure break adds essentially nothing over entering at a random bar within the next 5–20
bars with the same risk and the same exit.**

## 3. The part that is NOT a failure, and it is why this round is worth its ledger row

**68 of 72 cells have positive EV R after the 0.783 book round trip, and all 68 survive the 1.566
stress row.** Best cell `1d k=3 HH S+ATR close`: **EV R 0.4378, ROC/yr 7.37%**. That is a real,
positive, cost-proof expectancy — and **it does not belong to the entry.**

**Cost was never the constraint, exactly as §3 of the prereg predicted:** the round trip is **0.13%
to 0.62% of 1R** here, against 11–36% in this lane's 5m work. **So this round could not fail on
arithmetic, and it did not — it failed on the market, and the failure is specifically a failure of
the TRIGGER, not of the trade.** The control earns **+0.10 R** doing nothing but entering long at an
arbitrary bar in the same uptrend with the same stop and the same exit.

**Where the positive EV actually comes from, measured not asserted:**

- **67 of 72 cells have one fold holding more than 40% of the net** — against a 40% cap. Only **23 of
  72** reach 7 of 8 folds. **The best EV cell holds 55.9% of its net in one fold and wins 5 of 8.**
- So even taken at face value, the expectancy is **concentrated**, and the house's fold clauses — kept
  in §8 of the prereg precisely because an EV-R-and-ROC/yr yardstick with no fold count is how a
  one-episode result gets adopted — reject it independently of the control.

| timeframe | cells | mean EV R | mean `delta` | mean MDE2 | mean ROC/yr | trades/yr |
|---|---|---|---|---|---|---|
| 1h | 24 | +0.1465 | **−0.0024** | 0.3009 | 6.92% | 20.6 |
| 4h | 24 | +0.0698 | +0.0103 | 0.5139 | 3.82% | 6.5 |
| 1d | 24 | +0.1753 | +0.0823 | 0.7148 | 3.94% | 3.6 |

**The 1h frame is the only one with enough trades to say anything sharp, and there `delta` is
negative.** The daily frame has the largest `delta` and the largest MDE — 3.6 trades a year over 15
years cannot resolve an edge of this size, and saying so is the honest reading rather than pointing
at 0.0823.

## 4. ADDENDUM 1's prediction, scored — the eighth confirmation, with its caveat

I predicted **before measuring** that `CLOSE_ONLY` (the looser arm, which honours the structure trail
only on a close) would beat `TRAIL_STOP` (which takes it intrabar), on this lane's seven standing
confirmations that shortening this family's hold taxes the edge.

| | `TRAIL_STOP` | `CLOSE_ONLY` |
|---|---|---|
| mean hold | 24.1 bars | **30.9 bars** |
| mean EV R after cost | 0.1119 | **0.1492** |
| mean ROC/yr | 4.27% | **5.52%** |
| paired cells won (EV R) | 12 of 36 | **24 of 36** |
| paired cells won (ROC/yr) | 12 of 36 | **24 of 36** |

**Confirmed, and it is the EIGHTH independent read, the first on a STRUCTURAL exit.** The caveat
belongs next to it: **36 paired cells are not 36 independent experiments** — they share a tape, and
neighbouring pivot widths and timeframes overlap heavily. 24 of 36 is suggestive, not a p-value.
**And it is a comparison between two losing arms:** both fail the gate, so this says the longer hold
loses less, not that it wins.

## 5. The dead catalogue was right, and the specific thing it got right

§1 of the prereg named **"SWING 2.0 N-day Donchian long-only, NQ+ES, days-weeks — FAILED lockbox,
combined −$13,373 with blow-up losses"** and **ENGU-Q's own HIGHER LOWS gate, one of six that died.**
My prior was **under 12%**, the lowest I have written in this lane, and the round closed.

**What this round adds beyond "it died again":** SWING 2.0 died with negative money, so it was always
open to the reply "the rule was fine, the parameters were wrong". **This round says something
stricter: the rule makes money (68 of 72 cells, cost-proof) and the money is not the rule's.** A
confirmed-pivot HH/HL state machine, a trailing structure exit, three timeframes and two stop styles
all earn roughly what entering long at an arbitrary bar in the same uptrend earns. **The catalogue's
other line — "NQ pays breakout-followers at every timescale" — is confirmed and is exactly the
problem: NQ pays the follower, not the break.**

Combined with w119 (ES 15m candle+volume, 48 of 48 beta), STRONGBAR (NQ 5m) and TRENDOC (daily trend
held intraday loses to always-long), **this lane has now measured four different trigger families
against matched controls and found the trigger worth nothing in all four, while the long-side
exposure was worth something in all four.**

## 6. What this round did NOT do

- **No run records.** The 72 cells carry per-trade R and a pooled net, but **no daily dollar series**,
  so there are no four numbers to write and nothing is re-derived from a net — the same call as
  BBRF's and w119's gate cells (`2.220`, `2.221`).
- **No book-lift run.** §8 made book lift reported-not-gated; a standalone gate failure makes it
  unnecessary, and a book-lift run on an entry that does not beat its own control would be reading a
  number with no question behind it.
- **No short arm** (ENGU-Q's short mirror is separately DEAD), **no ETH arm**, **no pyramiding,
  re-entry or limit fills**, **no second data source**.
- **ROC@$30k, DD5, DD% and Sortino were not judged**, per the owner's w121 yardstick change; they are
  not in this gate's JSON because no daily series was built, and that is stated here rather than left
  to be noticed.

## 7. Look-ahead guards, as pinned in §5

Pivots confirmed `k` bars late and usable only from `i+k+1`; signal bar complete, **fill at the next
bar's open**; ATR20 shifted one bar; 4h and 1d resampled from the one 60m tape with **empty bins
dropped, never forward-filled**; stops checked intrabar with the ratchet applied **before** the bar's
stop check (deferring it would hand the trade a free bar below its own structure) and **never raised
above the last known price**; **a stop fills at `min(stop, that bar's open)`**, so a session that gaps
through the stop fills at the gap open — the single most important realism guard here, because
SWING 2.0's recorded failure mode was blow-up losses and this is an RTH tape holding positions
overnight.
