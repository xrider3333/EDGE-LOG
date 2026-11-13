# PREREG — ENGU-Q SWING STRUCTURE BREAK · NQ 1h / 4h / daily · multi-day holds

**Owner order 11-13 (MANAGER, board w121) PRICE-ACTION HUNT.** My lens: **swing structure —
higher-high / higher-low (and the short mirror), break of the last swing, on 1h/4h/daily NQ,
multi-day holds allowed, exit on structure break.** Price action only. Judged on **standalone EV R +
ROC/yr AND book lift**; ROC@$30k and drawdown are explicitly **not** the yardstick this round.
Power-first gate on gross vs cost with an **after-signal-only** random control; a gate pass queues the
900-trial validate immediately under the w120 standing GO.

Design date 2026-11-13. Lane ENGUQ. Instrument **NQ**, master `ADJ_NQ_60m_RTH.csv` (29,156 bars,
2010-06-07 .. 2026-11-12, volume on every bar). Stretch **pre-lockbox 2010-06-07 .. 2025-06-30**.
**The lockbox is not opened by anything in this document.**

---

## 1. THE DEAD CATALOGUE HITS THIS LENS TWICE, AND ONE OF THE HITS IS MY OWN FAMILY

Read first, as ordered (`hub-research-lists.md`, then the 289-entry tested catalogue). This is not a
near miss:

| catalogue entry | instruments / horizon | verdict |
|---|---|---|
| **"SWING 2.0 N-day Donchian long-only (multi-day trend)"** | **NQ, ES · days-weeks** | **FAILED lockbox — combined −$13,373 with blow-up losses** |
| **ENGU-Q higher-timeframe gates: session VWAP, 15m/60m momentum, ATR expansion, HIGHER LOWS, efficiency 0.35** | **NQ · multi-day** | **Six died** (only `ER ≥ 0.25` survived, and the crown later runs `er_th 0`) |
| WEEKLY opening range (Monday range breakout Tue–Fri) | NQ · 1–4 days | DEAD — best MAR 3.82 regime-concentrated; PF 1.21 but top-10 = 125% of net, ex-top-10 −$37k |
| Floor-pivot FADE and BREAKOUT | NQ · intraday | DEAD — breakout PF 1.16, "a worse ORB" |
| ORB structure forks (re-entry, failed-break reversal, pyramiding, entry cutoff, time stop, stale-out) | NQ · intraday | **DEAD 0/66** |
| ORB black-swan regime filters (**daily trend structure** + VIX) | NQ · intraday | DEAD — no filter improves MAR either window |
| Crown risk engine transplanted onto dips / turtle | NQ · days | **DEAD — "deletes the multi-day edge"** |
| ENGU-Q round 57 anatomy, on the crown's own trades | NQ · multi-day | **"breakout size, trendline quality, levels … carry nothing"** at signal time |
| Hourly intraday mean reversion (RSI + Bollinger) 30m/60m | NQ, ES · hours | DEAD — pooled OOS PF 1.00, MAR 0.03 |

**A Donchian N-day break IS a swing break, it was run long-only on NQ over exactly this horizon, and
it failed the lockbox with blow-up losses.** And "higher lows" was tested as a gate on my own crown
and died. **Two of my seven standing hold-finding confirmations also bear on the exit half:** the
crown risk engine "deletes the multi-day edge" when a tighter exit is transplanted onto a multi-day
leg, which is what "exit on structure break" is.

**The one fact in the catalogue that points the other way, and it is why this round runs at all:**
one NQ fade row records that **"NQ pays breakout-followers at every timescale."** Breakout-following
on NQ is not a dead mechanism — it is the house's adopted mechanism. ORB owns it intraday and
ENGU-Q owns it multi-day. **So the real question this round can answer is not "does a swing break
work" but "is there anything in a 1h/4h/daily swing break that the two crowns do not already own".**

## 2. What is genuinely untested, stated narrowly

**(a) A confirmed-pivot STATE MACHINE, not a price extreme.** SWING 2.0 was Donchian: break the
N-day high, no matter the path. A swing-structure rule is different — it requires a **confirmed pivot
low, then a confirmed pivot high, then a rising sequence of both**, and only then a break. Most
Donchian breaks are not HH+HL breaks. The two rules disagree often enough to be separate questions.

**(b) The trailing STRUCTURE exit.** Exit when price closes under the most recent confirmed pivot
low, which ratchets up as new pivots confirm. The catalogue has R-exits (dead 0 of 5), time stops,
hold caps and an X4-style trailing exit, but **no exit that trails on structure.** My own lane's
seven confirmations say shortening this family's hold taxes the edge — a structure trail is the one
trailing rule that lengthens the hold in a trend and only shortens it when the trend actually breaks,
so it is the fairest remaining test of that finding rather than another retread of it.

**(c) 1h and 4h NQ with multi-day holds.** The catalogue's hourly NQ row is mean reversion, not
structure, and ENGU-Q's 15m/60m gates were momentum filters on an existing entry, not a standalone
hourly entry.

**MY PRIOR: under 12% that any cell clears the bar.** Lower than the 15% I gave w119 and the 20% I
gave BBRF, because here a close relative of the design already **failed a lockbox**, which is worse
evidence than a draft-stage death. Two of the last three rounds in this lane closed at draft and I
expect this to be the third.

## 3. COST IS NOT THE BINDING CONSTRAINT HERE, AND THAT CHANGES WHAT A FAILURE MEANS

House NQ round trip **0.533 pt** at $20/pt ($10.66); BOOK #463's registered 24-hour ENGU-Q convention
is **0.783 pt**. On a 1h/4h/daily swing structure, R is tens to hundreds of NQ points, so cost is
**well under 2% of 1R** — against 11–36% in this lane's 5m work and 2–4% after the BBRF floor.

**So this round cannot fail on arithmetic.** If it dies it dies on the market, and I will not be able
to offer "the cost fraction was too high" as an explanation. Both rungs are carried: **0.533** (house)
and **0.783** (book convention). A stress rung of **1.566** (double the book convention) is also
reported, since a multi-day NQ swing position is exactly where slippage on a gap would land.

## 4. The design

**Direction: LONG ONLY for r1.** The short mirror is **pre-declared as its own arm** and not bolted
on later — ENGU-Q's own short mirror is DEAD ("every gate loses, 1–4/16 years"), so a short arm needs
its own prior and its own gate, not a free ride on this one.

**Pivots.** A **pivot high** at bar `i` is a bar whose high is the strict maximum of `high[i−k .. i+k]`;
a **pivot low** is the mirror. **A pivot is CONFIRMED only at bar `i+k` and may not be used until bar
`i+k+1`.** This is the whole look-ahead surface of the design and it is pinned in §5.

**Trend state (the HH/HL machine).** Keep the last two confirmed pivot highs `H1 > H2` (most recent
first) and the last two confirmed pivot lows `L1`, `L2`.
- `HH_AND_HL`: uptrend iff `H1 > H2` **and** `L1 > L2`.
- `HH_ONLY`: uptrend iff `H1 > H2`.

**Entry (long).** In an uptrend state, the first bar that **closes above `H1`**. **Fill at the NEXT
bar's open**, at market. One position at a time; no pyramiding (dead 0/66).

**Initial stop.** `L1`, the most recent confirmed pivot low, optionally floored:
- `STRUCT`: stop = `L1`.
- `STRUCT_ATR`: stop = `min(L1, entry − 1.0 × ATR20)` — i.e. the wider of the two, so the floor can
  only loosen a too-tight structure stop, never tighten it.

`R = entry − stop`, and **every gross figure in this round is reported in R, never in points**,
because R varies by cell and timeframe and a points comparison would compare position sizes.

**Exit — the trailing structure break.** Out at the first bar that **closes below the then-current
`L1`** (which ratchets upward as new pivot lows confirm), or at the stop, whichever comes first.
**Multi-day holds are allowed and there is no time cap and no target** — that is the point of the
round.

**GAP REALISM, and it matters more here than anywhere else in this lane's work.** The master is
RTH-only, so a multi-day position is not watched overnight. **A stop is therefore filled at
`min(stop, that bar's open)`** — if the session gaps through the stop, the fill is the gap open and
not the stop price. Naive stop fills on an RTH tape would hand this design free money on exactly the
days it should lose most, and SWING 2.0's recorded failure mode was **blow-up losses**.

## 5. Look-ahead guards, pinned by name

1. **A pivot is not known when it forms.** It is confirmed `k` bars later and is usable only from
   `i+k+1`. Every `H1`/`L1`/`H2`/`L2` read at bar `t` comes from pivots confirmed strictly before `t`.
2. **Signal bar complete, fill at the next bar's open.**
3. **ATR20 shifted one bar.**
4. **4h and daily bars are resampled from the SAME 60m master** — one tape, no splice. There is no
   registered NQ 4h or 1d master and I will not manufacture one from a second source.
5. **Empty resample bins are DROPPED, never forward-filled** — a bar that did not trade must not
   become a signal bar or a pivot.
6. **Stops are checked before any favourable price on every bar**, and gap-filled per §4.

## 6. The grid — 36 cells, hard bounds

| knob | values |
|---|---|
| `TF` timeframe | **1h** (the 60m master), **4h** (two blocks a session: 09:30–13:29, 13:30–close), **1d** (one bar a session) |
| `k` pivot half-width | 2, 3, 5 |
| trend definition | `HH_AND_HL`, `HH_ONLY` |
| stop | `STRUCT`, `STRUCT_ATR` |

**3 × 3 × 2 × 2 = 36 cells.** No knob is added after a result is seen; a method change is an addendum
with its own sha.

## 7. The power-first gate, with an AFTER-SIGNAL-ONLY random control

Per MANAGER #153 and the owner's w121 wording. For each cell:

- **n, sd, and the one-sample MDE** `sd·sqrt(7.85/n)` on per-trade R.
- **The random control:** for every signal, draw an entry bar **on or after the signal bar, inside the
  same position's own forward window**, same side, and run the **identical** stop, gap rule and
  structure exit. **20 draws per signal, seed fixed at 20261113.** The control may never draw a bar
  earlier than the signal bar, so it cannot see information the real arm did not have — the defect
  that inflated STRONGBAR's control to ROC ~10.
- **The paired difference** `delta = mean(signal R) − mean(control R)` against the two-sample MDE
  `sd·sqrt(15.7/n)`.

**Verdicts, pre-declared:**

- **TIMING IS NOTHING** — `delta` at or below the two-sample MDE. The structure break adds nothing
  over entering at a random later bar in the same move. **If all 36 land here the round closes at
  draft and that is the reported result.**
- **THIN** — under 20 trades a year. (Lower than the 50/yr floor used on 5m work: a daily-frame swing
  rule cannot produce 50 trades a year and holding it to that number would be a rigged bar. **20/yr
  is declared here, before any count is seen.**)
- **UNDER COST** — mean R at or below the 0.783 cost-in-R row.
- **OPEN** — clears all three. Only these go to the 900-trial validate.

**No clause can be satisfied by construction** (the w119 rule, kept): a paired difference against a
matched control scores zero for a strategy with no edge, and the control's own mean must be shown to
vary across cells rather than return a constant — **a constant repeated across heterogeneous cells is
never a result.**

## 8. The bar — what counts as a pass, on THIS round's yardstick

The owner changed the yardstick for w121: **standalone EV R + ROC/yr AND book lift; ROC@$30k and
drawdown are not judged.** So:

1. **`delta` beats its own two-sample MDE** (§7).
2. **EV R > 0 after the 0.783 cost row**, and still positive at the 1.566 stress row.
3. **ROC/yr > 0**, defined here, before any measurement, as **annualised net $ on a $100,000 nominal
   account at 1 NQ contract** — stated explicitly because "ROC/yr" is otherwise ambiguous once the
   $30k-drawdown base is set aside.
4. **≥ 20 trades a year** (§7).
5. **≥ 7 of 8 folds positive**, and **no single fold holding more than 40% of the net** — kept from
   the house bar, because an EV-R-and-ROC/yr yardstick with no fold count is exactly how a one-episode
   result gets adopted.
6. **Book lift** measured against BOOK #463 — reported, not gated, since a standalone gate failure
   makes a book-lift run unnecessary.

**ROC@$30k, DD5, DD% and Sortino are still COMPUTED and carried in the JSON** wherever a daily dollar
series exists, and are simply **not used to judge**. Measuring them costs nothing and discarding them
would make this round unreadable against every other row in the ledger.

## 9. What this round will NOT do

- **No lockbox opened**; pre-lockbox only, ending 2025-06-30.
- **No short arm, no pyramiding, no re-entry, no limit fills** ("through the level by one tick"
  remains unimplemented in this lane and stays its own pre-declared arm).
- **No second data source** and no ETH arm — the ETH tape is a separate pre-declared arm, and it
  matters (NQ carries much of its move overnight), but mixing an RTH entry with an ETH exit inside
  one round would confound the two.
- **Nothing touches live, paper, the box or any account.**
- **No bound re-cut after seeing a result.**

---

## ADDENDUM 1 — my own exit rule was two readings of one rule, and one of them could never fire

**Appended 2026-11-13, BEFORE any cell was measured.** The frozen body above is unchanged and keeps
its own sha `fd0820c6bde7c9b4a00fea9d3235b5ecf5298d146e42585ac25910ebd5979b1b` (commit `68a886c4`);
this addendum has its own sha and is verified separately.

**The defect.** Section 4 specified the exit as *"the first bar that closes below the then-current
`L1` … or at the stop, whichever comes first"*, with the stop itself ratcheting up to `L1`. **Those
are not two conditions. A bar that closes below a level has necessarily traded below it, so the
intrabar stop at that same level always fires first and the "close below" clause can never fire.**
It is satisfied-by-construction in the dead direction — the identical near-vacuity that made BBRF's
MFE ceiling clause worthless and its 36 "OPEN" verdicts meaningless (ledger `2.220`). I wrote §7's
"no clause can be satisfied by construction" into this very prereg and then broke it in §4.

**The fix, declared before any measurement: the two readings become two arms and BOTH are run.**

| arm | the rule | character |
|---|---|---|
| **`TRAIL_STOP`** | the literal reading — the stop **ratchets up** to each newly confirmed pivot low and is taken **intrabar** | **tight**: out the moment structure is touched |
| **`CLOSE_ONLY`** | the swing-trading reading — the **original** pivot low stays as the disaster stop, taken intrabar, but the **trail is honoured only on a CLOSE** below it | **loose**: gives a multi-day hold room to breathe |

**The grid therefore doubles from 36 cells to 72.** No other bound moves; no knob was added after a
result, because no result exists yet.

**Two ordering rules fixed with it, both look-ahead-relevant and both now covered by the selftest:**

1. **`L1[i]` is the last pivot low confirmed STRICTLY BEFORE bar `i`, so it is already known at bar
   `i`'s open and the ratchet must happen BEFORE that bar's stop check.** Deferring it one bar would
   quietly hand the trade a free bar below its own structure.
2. **The trail is only ever raised to a level below the last price actually known** (the previous
   bar's close). Without that guard, a pivot low the market has already run past could arm a stop
   *above* the market and book an instant loss at entry.

**I predict `CLOSE_ONLY` beats `TRAIL_STOP`** — this lane has seven independent confirmations that
shortening this family's hold taxes the edge, and `TRAIL_STOP` is the shorter-hold arm. Writing that
down now so the prediction is testable rather than retrofitted. **If both arms fail, that prediction
is untested rather than confirmed**, and I will report it that way.
