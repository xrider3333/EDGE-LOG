# ENGU-Q round 62 - PRE-REGISTRATION (written before any engine run)

Committed before a single cell was measured. Owner ask 2026-09-28 (MANAGER inbox #17): brainstorm
variations of ENGU-Q for more alpha, favouring new entry mechanisms and regime or session
conditions fixed BEFORE looking at results, and favouring ideas that make the edge less dependent
on one rare long hold.

## The structural fact this round is built on

Measured first, on the paper / NinjaTrader default cell, roll-corrected, whole window
(2,053 trades, $493,295):

| hold length | trades | share of trades | net | win rate |
|---|---|---|---|---|
| intraday, under 6 hours | 1,078 | 52.5% | **-$493,422** | 8.3% |
| 6 hours to 1 day | 485 | 23.6% | -$45,095 | 34.2% |
| 1-3 days | 220 | 10.7% | +$111,846 | 54.5% |
| 3-7 days | 160 | 7.8% | +$285,695 | 70.6% |
| 1-3 weeks | 84 | 4.1% | +$343,461 | 84.5% |
| over 3 weeks | 26 | 1.3% | +$290,809 | 100.0% |

**Every dollar ENGU-Q has ever made comes from trades that survive their first day, and the
same-day deaths cost almost exactly the whole net.** That is why the hold cap failed its bar on
2026-09-27: capping the hold removes the edge. The lever is therefore not "hold less", it is
**"stop paying for the trades that were never going to survive"**.

## Idea 1 (pre-registered here): the US cash session entry window

**Mechanism.** ENGU-Q was built to read context, location and the imbalance of buyers and
sellers. That imbalance only exists when real size is trading. Outside the US cash session the
NQ tape is thin, so a breakout there is noise - and the data says exactly that: day-one survival
by entry hour is 37-40% for 09:00-16:59 ET entries and 9-13% outside it, **in each of the four
eras 2010-14, 2015-18, 2019-22 and 2023-26, with no drift**. Non-cash-session entries are 53% of
all trades and 15.7% of all net, and inside the sealed year they LOSE $21,188 while cash-session
entries make $96,058.

**What changes.** One new gate, tested on the SIGNAL bar (never the fill bar): a signal is only
taken when the bar's own timestamp falls inside the US cash session, 09:30-16:00 ET. Exits,
stops, trailing, the limit scan and the hold are untouched, so a trade entered at 15:55 still
runs for weeks if it earns that. **The window is pinned to the cash session on mechanism, not to
the best-looking hours in the table above.** Neighbouring windows will be reported as a plateau,
never selected from.

**Data.** ADJ_NQ_1m_ETH (roll-corrected), 2010-06-07..2026-06-30, sealed split 2025-06-30,
cost 0.783 x $20 - the paper cell's own cost, since the paper cell is the owner's yardstick.

**Runner cost.** Zero for the triage: two continuous local runs. A validate, only if the triage
passes, is one 900-trial job of about 70 minutes.

## The bar - ALL SIX clauses must pass, or the idea is written up DEAD

Judged against the RAW TWIN, which is this same file with the window open to 24 hours, so every
row is a one-knob comparison. Owner yardstick, 2026-09-28.

1. **ROC % per year at a $30,000 worst drawdown, drawdown valued DAILY, beats the raw twin in
   BOTH stretches** - walk-forward and sealed year, shown separately, never pooled.
2. **Sortino beats the raw twin in BOTH stretches.**
3. At least **100 walk-forward trades** and **50 sealed-year trades**.
4. **The sealed year stays profitable without its single biggest trade.** The raw twin FAILS this
   clause today (-$16,283 without one 35-day hold), so this is the clause that decides whether
   the idea does what the owner actually asked for.
5. **Era stability inside the engine:** day-one survival for gated entries must beat non-gated
   entries in all four eras. One era failing kills it.
6. **Harness gate:** with the window open to 24 hours the new file must return a trade list
   identical to ENGUQ_1M_ETH_R2_1_0.py at the same parameters. If it does not, nothing below is
   a one-knob comparison and the round is void.

No clause may be moved after the numbers are read. The 2026-09-14 daily-stretch cap missed its
bar by 0.34 of a point and was left dead on purpose; the same rule applies here.

## How this could be fooling us - declared in advance

- **The screening numbers above come from a trade list, not the engine, and they use FILL time,
  not signal time.** About 45% of this file's fills land 2-10 bars after the signal, so the
  engine's gate is not the same cut as the table. The 15.7% figure is not a prediction.
- **A declined signal frees the slot, and the walk refills it with a later signal of the same
  move** (round 57, the reason four entry filters over-predicted). Here that effect should work
  in the idea's favour - an Asia-hours signal declined can be refilled at 09:30, which survives
  at three to four times the rate - but "should" is not "does", and a refill that arrives worse
  is the single likeliest way this idea dies in the engine.
- **The hours were read off the whole window, including the sealed year.** The cash-session
  window is a mechanism choice, but the fact that I looked at the table first cannot be undone;
  clause 5 (era stability) and the plateau report are the guards against it.
- **Measured re-entry economics cut against a blanket stand-down rule:** trades opening within 4
  hours of the previous exit on the same side are 56.5% of trades and 60.3% of net. So no
  "no-refill window" is proposed here - the refills carry the money.
