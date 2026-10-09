# BOOK — the deployed pile of strategies, scored as ONE account

> Living handoff doc. **Started 2026-08-18** (book-optimization session). A "book" is what
> the owner actually trades: several strategies running side by side in one account, one
> contract each. The BOOK job type (shipped v71.42) pools every leg's trades by exit date
> and scores the pile as a single strategy, so drawdown and profit factor are the account's
> real numbers rather than a sum of separate backtests.
>
> Everything in this file was computed by `tools/t8_noise_book.py`, which refuses to print a
> single result until it has reproduced (a) every leg's published standalone number and
> (b) run #238's saved book document to the dollar through `augur_engine.run_book`.
>
> **ADOPTED BOOK: #449 on the fixed legs = run #463 (FRONTIER), owner via MANAGER on 2026-09-28 - replaces #366.**
> ORB #234 + ENGU-Q #335 + TTM #369 (fixed = #459) at three ES + NOISE #422. On the owner's yardstick
> (ROC %/yr at a $30k worst drawdown valued daily): 60.3 before / 164.8 in the lockbox,
> against #366's re-run 57.1 / 151.7. Section 10n. The staged #397 flip was dropped.
>
> **OWNER DECISIONS 2026-10-05 (via MANAGER #81, section 10aa):** #463 stays adopted. No backtest book candidate is ever passed on
> #463's lockbox year; the walk-forward selects, forward shadow lines are HARM MONITORS (paired stops), and adoption is the owner's
> call on walk-forward plus mechanism, from an adoption page. ORB314 / Q4 / VT / ORB239 are NOT ADOPTED (harm monitors only); KEEL
> stays a monitored shadow; NOISE #422 stays at 1.0x and the x1.25 line is read on dollars at 36 months.

---

## 1. How the BOOK machinery actually works (read this before designing a book run)

**Legs.** A book job carries a `legs` list. Each leg names a strategy file, a frozen
parameter set, an instrument, a timeframe, a session, a data source, a cost in points, a
dollar-per-point multiplier, and an optional weight. Nothing is tuned inside a book run —
it is a replay of already-frozen configurations.

**Weighting is supported and it is a plain multiplier.** Each leg's trade profit and loss is
multiplied by its `weight` before pooling. A weight of 2 is two contracts of that leg; a
weight of 0.5 is half a contract, which is not directly tradeable in a single futures
product. The default is 1, and every book run to date has used 1 for every leg.

**Trades are stamped by EXIT date.** A trade that spans midnight lands in the day it was
closed. Pooling by day is what makes the book's drawdown honest: a day where one leg loses
and another wins nets out before the account curve moves.

**Profit factor is trade-level over the pooled pile. Drawdown is measured on the daily
account curve** and reported as a positive number.

**The lockbox window is simply the last N months of the book's own window**, where N comes
from the job's `lockbox_months` field, counted at 30.44 days per month back from the last
day that has a trade. It is not inherited from any leg. Run #238 asked for 18 months, which
is why its lockbox starts on 2025-02-10 rather than on either leg's own lockbox date. That
choice matched NOISE's own 18-month lockbox boundary, but it does **not** match the ORB
leg's, whose parameters were still being selected until 2025-08-12. So roughly the first six
months of run #238's "lockbox" were data the ORB leg had already seen. That is a real
caveat, not a bug — and it is why every table below reports two lockbox slices.

**A book never produces walk-forward folds.** This is deliberate and confirmed in the code:
the results list that would carry fold numbers is left empty on purpose so the app can never
show a walk-forward figure for a run that did not do one. What a book reports instead is an
eight-equal-stretch consistency count, and that count must never be presented as
walk-forward. Verdicts are: pass when the lockbox slice is profitable with a profit factor
of at least 1.0 and at least six of the eight stretches are profitable.

---

## 2. What was pinned for this round

| Thing | Choice | Why |
|---|---|---|
| ORB leg (current crown) | `ORB_3_6_C2.py`, run #234 | the standing crown, certified 2026-08-17, passes 6 of 6 and sits on a mapped plateau |
| ORB leg (comparison) | `ORB_3_4_C221.py`, run #230 | the leg run #238 actually used, kept so the comparison is like-for-like |
| ENGU-Q leg | `ENGUQ_1M_1_0.py` at the certified 149 deployment parameters | the day-session ENGU-Q that the owner's stated baseline blend is built from |
| NOISE legs | `NOISE_1_1_BASE / SBS / SBS_V90 / SBA / V98`, plus run #238's own leg rebuilt from its saved parameters | the pinned campaign candidates plus the incumbent |
| Window, books of 5-minute legs only | 2010-06-07 to 2026-08-12 | run #238's exact window, so the comparison is pinned |
| Window, any book containing a 1-minute leg | 2010-06-07 to 2026-06-30 | the NQ 1-minute day-session master has a genuine three-week hole from 2026-07-17 to 2026-08-05; a backtest spanning it is invalid |
| Costs | 0.533 points per round trip, multiplier 20 | the program-wide convention on NQ |

**Lockbox discipline, stated plainly.** NOISE's lockbox is spent and confirmatory only, so
no NOISE decision in this round was made on it. ORB's lockbox year, 2025-08-13 to
2026-08-13, has been read many times across the hunt and is treated as encouraging rather
than confirmatory. ENGU-Q's day-session baseline has been re-read repeatedly too. Nothing
below was **selected** on any lockbox; the lockbox columns are reported after the fact.

---

## 3. RUNBOARD — every book combination tested

All figures local, computed by `tools/t8_noise_book.py`. Maximum drawdown is positive.
"IS" for a book means the pre-lockbox stretch; a book emits no walk-forward folds, so the
walk-forward column is not applicable everywhere and the eight-stretch consistency count is
shown in its place under "slices".

### 3.1 Standalone legs, for reference (2010-06-07 to 2026-08-12)

| # | Leg | Net | PF | MaxDD | net/DD | slices | LB from 2025-02-10 | Trades |
|---|---|---|---|---|---|---|---|---|
| 1 | ORB #230 crown (`ORB_3_4_C221`) | $348,129 | 1.263 | $35,474 | 9.81 | 7/8 | $134,346 | 2,607 |
| 2 | ORB #234 crown (`ORB_3_6_C2`) | $389,874 | 1.307 | $29,142 | 13.38 | 7/8 | $167,198 | 2,607 |
| 3 | NOISE plain champion | $335,981 | 1.221 | $32,076 | 10.47 | 7/8 | $58,191 | 5,633 |
| 4 | NOISE as used in run #238 | $367,959 | 1.322 | $34,418 | 10.69 | 8/8 | $34,499 | 4,418 |
| 5 | NOISE skip-shorts-after-weak-close | $388,181 | 1.287 | $30,473 | 12.74 | 8/8 | $66,984 | 5,214 |
| 6 | NOISE that plus skip-wildest-10% | $380,745 | 1.387 | $21,865 | 17.41 | 7/8 | $59,948 | 4,429 |
| 7 | NOISE skip-all-after-weak-close | $366,855 | 1.337 | $29,041 | 12.63 | 7/8 | $58,072 | 4,404 |
| 8 | NOISE skip-wildest-2% | $384,690 | 1.291 | $22,334 | 17.22 | 7/8 | $74,968 | 5,347 |

### 3.2 Two-leg books on the OLD ORB crown — the direct run #238 comparison

Window 2010-06-07 to 2026-08-12, 18-month lockbox, exactly run #238's setup. Row 10 IS
run #238, reproduced to the dollar.

| # | Book | Net | PF | MaxDD | net/DD | slices | LB (2025-02-10) | LB (2025-08-13) | Trades | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 9 | ORB #230 + NOISE plain champion | $684,110 | 1.240 | $42,670 | 16.03 | 7/8 | $192,537 | $103,648 | 8,240 | control |
| 10 | ORB #230 + NOISE run #238 leg | $716,089 | 1.290 | $39,809 | 17.99 | 7/8 | $168,845 | $101,299 | 7,025 | the incumbent |
| 11 | ORB #230 + skip-shorts-after-weak-close | $736,310 | 1.275 | $40,369 | 18.24 | 7/8 | $201,330 | $106,793 | 7,821 | beats the incumbent |
| 12 | ORB #230 + that plus skip-wildest-10% | $728,874 | 1.316 | $37,718 | 19.32 | 8/8 | $194,294 | $107,321 | 7,036 | beats the incumbent |
| 13 | ORB #230 + skip-all-after-weak-close | $714,984 | 1.297 | $35,696 | 20.03 | 7/8 | $192,418 | $121,943 | 7,011 | best net/DD here |
| 14 | ORB #230 + skip-wildest-2% | $732,820 | 1.277 | $42,670 | 17.17 | 7/8 | $209,314 | $129,868 | 7,954 | best lockbox, worst drawdown |
| 15 | ORB #230 alone, no NOISE leg | $348,129 | 1.263 | $35,474 | 9.81 | 7/8 | $134,346 | $64,575 | 2,607 | reference |

### 3.3 Two-leg books on the CURRENT ORB crown

Same window and lockbox, ORB leg upgraded from run #230 to run #234.

| # | Book | Net | PF | MaxDD | net/DD | slices | LB (2025-02-10) | LB (2025-08-13) | Trades | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 16 | ORB #234 + NOISE plain champion | $725,855 | 1.260 | $40,470 | 17.94 | 7/8 | $225,390 | $128,016 | 8,240 | control |
| 17 | ORB #234 + NOISE run #238 leg | $757,834 | 1.314 | $37,609 | 20.15 | 7/8 | $201,697 | $125,666 | 7,025 | incumbent, upgraded ORB |
| 18 | ORB #234 + skip-shorts-after-weak-close | $778,055 | 1.297 | $38,169 | 20.38 | 7/8 | $234,183 | $131,160 | 7,821 | best net |
| 19 | ORB #234 + that plus skip-wildest-10% | $770,619 | 1.342 | $35,518 | 21.70 | 8/8 | $227,147 | $131,688 | 7,036 | best PF, only 8-of-8 |
| 20 | ORB #234 + skip-all-after-weak-close | $756,729 | 1.321 | $33,691 | 22.46 | 7/8 | $225,270 | $146,310 | 7,011 | best net/DD and drawdown |
| 21 | ORB #234 + skip-wildest-2% | $774,565 | 1.299 | $40,470 | 19.14 | 7/8 | $242,167 | $154,236 | 7,954 | best lockbox, worst drawdown |
| 22 | ORB #234 alone, no NOISE leg | $389,874 | 1.307 | $29,142 | 13.38 | 7/8 | $167,198 | $88,943 | 2,607 | reference |

### 3.4 The owner's baseline and the three-leg question

Window 2010-06-07 to 2026-06-30 (the 1-minute data hole forces the earlier end date),
lockbox slice from 2025-08-13.

| # | Book | Net | PF | MaxDD | net/DD | slices | LB net | LB net/DD | Trades | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 23 | ORB #234 alone | $373,305 | 1.299 | $29,142 | 12.81 | 7/8 | $72,373 | 2.81 | 2,584 | leg |
| 24 | ENGU-Q day-session alone | $477,521 | 1.409 | $65,635 | 7.28 | 8/8 | $129,266 | 1.97 | 2,048 | leg |
| 25 | **BASELINE: ORB #234 + ENGU-Q, 1:1** | $850,825 | 1.352 | $58,171 | 14.63 | 8/8 | $201,639 | 3.85 | 4,632 | the thing to beat |
| 26 | 3-leg, + NOISE plain champion | $1,177,115 | 1.301 | $63,111 | 18.65 | 8/8 | $231,021 | 4.23 | 10,237 | better net/DD, worse PF and drawdown |
| 27 | 3-leg, + NOISE run #238 leg | $1,212,970 | 1.343 | $62,395 | 19.44 | 8/8 | $232,548 | 4.31 | 9,027 | better net/DD, worse drawdown |
| 28 | 3-leg, + skip-shorts-after-weak-close | $1,232,683 | 1.329 | $60,405 | 20.41 | 8/8 | $237,534 | 4.35 | 9,820 | better net/DD, worse drawdown |
| 29 | **3-leg, + that plus skip-wildest-10%** | **$1,245,994** | **1.369** | **$56,090** | **22.21** | 8/8 | **$258,808** | **5.21** | 9,048 | **better on every axis** |
| 30 | 3-leg, + skip-all-after-weak-close | $1,215,603 | 1.349 | $61,239 | 19.85 | 8/8 | $256,929 | 5.20 | 9,017 | better net/DD, worse drawdown |
| 31 | 3-leg, + skip-wildest-2% | $1,225,798 | 1.330 | $57,250 | 21.41 | 8/8 | $257,214 | 4.71 | 9,953 | better net/DD, slightly worse drawdown |

Row 29 is the only combination that improves the baseline on net, profit factor, maximum
drawdown, net-over-drawdown and lockbox all at once.

### 3.5 Year by year, baseline versus the best three-leg book

The baseline has one losing year (2016, minus $2,279). The three-leg book has none — 2016
turns into plus $6,143 — and it beats the baseline in 15 of the 17 years. The two years it
trails are 2010 (a partial year, minus $1,934) and 2013 (minus $1,072). The gains are
concentrated in the post-2018 high-volatility regime, which is the same regime caveat that
already attaches to the ORB leg.

---

## 4. Correlations between legs, measured directly

Daily dollar profit and loss, union of trading days with non-trading days filled as zero,
2010-06-07 to 2026-06-30.

| Pair | Correlation |
|---|---|
| ORB #234 versus ENGU-Q day-session | 0.010 |
| ORB #234 versus NOISE plain champion | 0.547 |
| ORB #234 versus NOISE run #238 leg | 0.516 |
| ORB #234 versus skip-shorts-after-weak-close | 0.534 |
| ORB #234 versus that plus skip-wildest-10% | 0.389 |
| ORB #234 versus skip-all-after-weak-close | 0.412 |
| ORB #234 versus skip-wildest-2% | 0.440 |
| ENGU-Q versus any NOISE leg | 0.030 to 0.057 |
| NOISE leg versus NOISE leg | 0.703 to 0.967 |

**The previously banked 0.21 to 0.25 ORB-to-NOISE figure does not reproduce.** On daily
account dollars the correlation is roughly 0.39 to 0.55 depending on the NOISE variant, and
it is stable across eras: 0.41 to 0.47 over 2010-2017, 0.39 to 0.55 over 2018-2026, and 0.42
to 0.47 over the most recent lockbox stretch. Anyone quoting 0.21 to 0.25 for this pair
should stop. The diversification is real but weaker than assumed, because both strategies
are day-session NQ intraday systems.

**Two useful consequences.** The filtered NOISE variants are meaningfully *less* correlated
with ORB than the plain champion is (0.39 versus 0.55), so the filters buy diversification as
well as standalone performance. And ENGU-Q remains the genuinely independent leg at 0.01,
which is why it contributes the most drawdown reduction per dollar of profit.

---

## 5. Per-leg weighting — tested, pre-registered, and not adopted

**Rule declared before any weighted result was looked at.** Candidate weights of 0.5, 1.0,
1.5 and 2.0 on the ENGU-Q and NOISE legs, with the ORB leg fixed at 1.0 as the unit.
Selection metric: net-over-drawdown on the pre-lockbox stretch only, 2010-06-07 to
2025-08-12. The 2025-08-13 onward stretch was then read once, after the pick, and is
reported whatever it says.

The rule picks ENGU-Q at 0.5 and NOISE at 2.0. On the pre-lockbox stretch that scores 23.31
against equal weighting's 16.47. After the fact, on the held-out stretch, it scores 4.87
against equal weighting's 4.63 — a gain of about 5 percent on a single read of one short
window.

**Not adopted, for three reasons.** The held-out improvement is far smaller than the
in-sample improvement, which is the classic signature of a fitted weight. The held-out
ranking of the sixteen weight combinations barely resembles the pre-lockbox ranking, so the
selection metric is not predicting what it claims to predict. And the winning weights shrink
the one leg that is genuinely uncorrelated with the others, which is the opposite of what
diversification argues for. Equal weighting stands. A 0.5 weight is also not directly
tradeable in a single NQ contract.

---

## 6. Conclusions

1. **A better NOISE leg does make a better book.** Every one of the four pinned filter
   variants produces a book that beats the plain-champion control on both net profit and
   net-over-drawdown, on both ORB crowns.
2. **Run #238 did not use the best available NOISE leg.** Holding its ORB leg fixed, four of
   the five alternatives beat it on net-over-drawdown and three beat it on net profit. The
   variant it used has the weakest recent-period performance of all of them standalone.
3. **The book's ranking of NOISE legs is not the same as the standalone ranking.** Standalone,
   skip-wildest-10% and skip-wildest-2% have the best net-over-drawdown by a wide margin. In
   the book, skip-all-after-weak-close wins net-over-drawdown and skip-shorts-after-weak-close
   wins net profit. Legs must be judged inside the book, not beside it.
4. **NOISE earns a slot next to the ORB and ENGU-Q baseline.** Adding the skip-shorts plus
   skip-wildest-10% variant as a third leg improves net profit by 46 percent, raises profit
   factor from 1.352 to 1.369, *lowers* maximum drawdown by $2,081, raises net-over-drawdown
   from 14.63 to 22.21, keeps all eight stretches profitable, raises the held-out stretch from
   $201,639 to $258,808, and removes the baseline's only losing year.
5. **The honest caveats.** The improvement is largest in the post-2018 regime. Three legs is
   three contracts of margin, so the fair comparison is net-over-drawdown rather than net
   profit — and net-over-drawdown improves, which is the answer that matters. The
   ORB-to-NOISE correlation is around 0.4, not the 0.21 to 0.25 previously recorded, so the
   diversification benefit is real but smaller than the old figure implied. And the ORB leg's
   own lockbox year has been re-read many times across this program, so the held-out columns
   here are encouraging rather than confirmatory.

---

## 7. Reproduce and queue

```
python tools/t8_noise_book.py --verify     # parity gates only
python tools/t8_noise_book.py              # the full round above
python tools/queue_t8_books.py             # queue the four owner-visible book jobs
```

`tools/queue_t8_books.py` checks the runner queue first and refuses to add if it is already
deep. It queues four book runs so the results land in Past Runs where the owner evaluates
things: the upgraded two-leg book on skip-wildest-10%, its skip-all-after-weak-close sibling,
the two-leg baseline control, and the three-leg candidate.

---

## 8. Open items

- The four queued book runs still need to land and be read in the app.
- A book run reports no walk-forward folds by design. If books become the unit the owner
  crowns on, the eight-stretch consistency count is a weak substitute and a real
  fold engine for books is worth building.
- The book lockbox is a single number chosen by month count. Letting a job name an explicit
  lockbox start date would remove the awkwardness of run #238's boundary sitting inside the
  ORB leg's own optimize window.
- The NOISE leg used by run #238 is not one of the pinned `NOISE_1_1_*` files. If it is to
  stay in circulation it should be pinned like the others; if not, it should be retired in
  favour of the variants that beat it here.

---

## 10. 2026-09-09 — the risk clause every book bar used was inert, and what replaces it

**The clause.** Every book bar written in this repo up to today read some version of *"annualised
MAR at least X above the adopted book, at a WHOLE-RUN drawdown within Y percent of it, with a
lockbox at least as large."* The middle clause is the one that broke.

**Why it cannot bind.** A book's whole-run maximum drawdown is ONE stretch of tape. A candidate leg
that took no trades inside that stretch cannot move the number at any weight. The TTM leg is the
worked example: BOOK runs #336, #337 and #341 all record a whole-run drawdown of **$34,329.21 — the
same to the cent** — even though #336 and #341 carry three ES contracts of a leg #337 does not have
at all. The stretch belongs to the two NQ legs; the ES leg was absent for all of it.

**The audit.** `tools/book_clause_audit.py` asked the question of every book adoption on the board.
Verdicts, all on the pinned windows the stored runs used:

| adoption | worst stretch | who paid | added leg present? | old clause | lockbox clause |
|---|---|---|---|---|---|
| **#336 vs #337** — TTM adopted as a leg | 2022-04-27..05-24, $34,329 | ENGU-Q 92%, ORB 8% | **no, 0 days** | PASS | **PASS** (LB DD $26,235 vs $33,112 — it *improved* it) |
| **#341 vs #336** — validated tilt | same, unchanged | same | **no, 0 days** | MISS (MAR x1.049) | MISS (same reason) |
| **#342 vs #336** — tilt + ES 15m | 2022-04-27..05-24, $34,564 | same | **no, 0 days both legs** | PASS | **PASS** (LB DD $26,098 vs $26,235) |
| **weak-edge ETF book** #332 / #338 | its own: 2011-05-30..08-16 $73,194 / 2011-06-15..08-16 $43,818 | NQDIP 43%, then the QQQ/IWM legs | depends on the incumbent: **all 7** trade the r25 champion's 2020 stretch (dip-buyers, and that is a crash), but only **1 of 7** (GLD, 1 day) touches today's #337 baseline stretch | its bar had no drawdown clause; the stack bar it MISSED is unaffected | MISS harder — the stack raises lockbox drawdown 74–89% |
| **NASDAQ WF book** (B11) | champion's: 2020-02-25..03-25, $71,773 | ENGU-Q ETH 63%, ORB 37% | **yes — 6 of 8 legs, −$52k of the stacked −$123,925** | PASS (+28% MAR here vs the +15% bar) | **MISS** — the stack raises last-12-months drawdown 104% |
| **ORB x ENGU-Q 1:1 blend** | 2020-02-25..03-25 ($58,171 RTH leg / $71,773 ETH leg) | both legs, roughly half each | both present | n/a (a net/DD ranking) | not inert, but a one-month denominator |

**So: nothing is retracted.** Two families split cleanly.

*Decided on an inert clause, but the verdict survives the stronger one:* the three TTM book runs.
The ES leg traded the incumbent's worst stretch **zero** days in all three, so the drawdown clause
could not have failed — but #336 and #342 pass a lockbox-drawdown clause too, and #342 passes it
because it **lowered** the lockbox drawdown ($26,098 vs $26,235), which is exactly the evidence the
whole-run clause could never have supplied. #341 misses under both, for the same MAR reason
already recorded.

*Not inert at all:* the ETF and NASDAQ books. Both are dip-buying families and the incumbent's
worst stretch is a crash, so their legs are heavily present in it — the NASDAQ book's eight legs
add **−$52,391** of the stacked **−$123,925**, and all seven ETF legs trade the r25 champion's
stretch. Their MAR bars were doing real work.

**The one headline to re-read is B11's.** It cleared its +15% MAR bar honestly, but the same stack
raises the champion's whole-run drawdown **+73%** and its last-12-months drawdown **+104%**
($38,838 → $79,330) and **fails a lockbox-drawdown clause outright**. A bar written on MAR alone
cannot see that; a bar written on lockbox drawdown would have. The evidence is put in front of the
owner, not acted on here. (Two arithmetic notes on B11, recorded rather than repeated: the champion
half of "8.31 → 11.20" reproduces at 8.30, but the stacked half does not — the eight book legs give
10.60 (+28%) and only pooling all ten saved OOS series, which adds two per-fold JOINT series that
are **not** part of the 8-leg book, reaches 11.30 (+36%). Every reading clears +15%.)

**THE REPLACEMENT CLAUSE — use this wording for every future book bar.**
`tools/book_dd_attribution.bar_text()` prints it so a queue driver states it rather than
re-inventing it:

> BAR (pre-registered) against *the incumbent book*: (1) annualised MAR at least 1.05x it;
> (2) **LOCKBOX drawdown** within 5 percent of it; (3) lockbox net at least as large. The
> WHOLE-RUN drawdown is reported as a **check, not a gate**: it is set by one stretch of tape, so
> a leg that took no trades in that stretch cannot move it at any weight and the comparison says
> nothing about the risk being added.

The lockbox drawdown is the right number because it is measured on tape the legs' parameters never
saw AND it actually responds to weight — the TTM leg's lockbox drawdown climbs $26,235 → $29,128
going from three contracts to six while the whole-run number never moves at all.

**The engine now supplies the evidence itself.** `augur_engine/book.py` writes
`book.worst_stretch`, `book.worst_stretch_lockbox` and `book.inert_legs` onto every book result:
the stretch's dates and depth, each leg's dollars and trading days inside it, and the names of any
leg that was absent. The rows sum to the drawdown to the cent (the span is the days strictly AFTER
the peak — including the peak day double-counts its P&L). COMPARE ▸ RUNBOARD's BOOKS table shows
the stretch under each book's legs and flags the absent ones in yellow. Guarded by
`tests/test_book_worst_stretch.py`.

**Reproduce**

```
python tools/book_dd_attribution.py --run 341 --vs 336 --new-legs 1   # one pair, both clauses
python tools/book_clause_audit.py                                     # the whole audit
```

### 10a. B11 RE-JUDGED — three BOOK cards queued 2026-09-09 (owner ask)

Owner: *"re-judge B11 — queue the lockbox-clause version of that stack."* Driver
`tools/queue_b11_lockbox_rejudge.py`, prediction `tools/data/b11_lockbox_rejudge_prediction.txt`.

**The bar is B11's own with exactly one clause swapped:** MAR >= incumbent x1.15 (unchanged),
**LOCKBOX drawdown within 5%** (was whole-run), lockbox net >= incumbent (unchanged).

**What is being run, and what is not.** B11's book re-picks its parameters every fold, so it
cannot be replayed as a BOOK job — a book run replays FIXED parameters. The cards run the
*tradeable* representation of the same family, `NQDIP_1_0.py` at the configs its own validates
crowned: the NQ 5m leg from run #307 (PASSED) and the QQQ 1d leg from run #308 (**FAILED**, zero
lockbox trades — carried anyway, because dropping the QQQ half would quietly re-scope B11's
QQQ+NQ claim). A pass would not restore B11; a miss does not by itself retract it.

| card | what | job |
|---|---|---|
| **CONTROL-A** | ORB #234 + ENGU-Q ETH #226 — the champion B11 was *actually* judged against, which had never been stored as a run. Without it none of B11's clauses were checkable. | `YBB48OUdD099jropRhDR` |
| **CAND-A2** | CONTROL-A + NQDIP NQ 5m + NQDIP QQQ 1d — the full QQQ+NQ shape | `Y0CBQV2oNuCxMlWTglrK` |
| **CAND-B1** | the adopted book #336 + NQDIP NQ 5m — the only version that bears on what is traded today | `NrhrTugDQtfMrMDDk7po` |

**CAND-A1 was not queued**: it already exists as stored BOOK #311, same window and lockbox. It
becomes judgeable the moment CONTROL-A lands.

**THE CARDS LANDED — runs #346, #347, #348 — AND EVERY FIGURE MATCHES THE PREDICTION TO THE
DOLLAR.** All three MISS, under BOTH clauses, and the clause that fails is **MAR, not risk**.

| card | run | net | whole DD | ann.MAR | lockbox | LB DD | PF | slices |
|---|---|---|---|---|---|---|---|---|
| CONTROL-A (champion of the day) | **#347** | $793,811 | $71,903 | 0.687 | $201,204 | $35,723 | 1.31 | 8/8 |
| CAND-A1 (= stored #311) | #311 | $1,269,839 | $114,107 | 0.693 | $232,508 | $40,097 | 1.40 | 8/8 |
| CAND-A2 (full QQQ+NQ shape) | **#346** | $1,857,814 | $154,999 | 0.746 | $294,996 | $38,160 | 1.51 | 8/8 |
| CONTROL-B (adopted book) | #336 | $1,119,697 | $34,329 | 2.031 | $193,170 | $26,235 | 1.49 | 8/8 |
| CAND-B1 (#336 + dip leg) | **#348** | $1,595,725 | $74,275 | 1.337 | $224,475 | $32,457 | 1.55 | 8/8 |

| judged | vs | MAR (bar x1.15) | whole-run DD | **lockbox DD** | lockbox net | old | new |
|---|---|---|---|---|---|---|---|
| #311 | #347 | **x1.008** ✗ | x1.587 | x1.122 | x1.156 ✓ | MISS | MISS |
| #346 | #347 | **x1.086** ✗ | x2.156 | x1.068 | x1.466 ✓ | MISS | MISS |
| #348 | #336 | **x0.659** ✗ | x2.164 | x1.237 | x1.162 ✓ | MISS | MISS |

**What this says about B11.** Its headline was MAR x1.35 on a x1.15 bar. Frozen into the tradeable
file the same family reaches **x1.008 and x1.086** — and on the book the owner actually trades it
is harmful: **x0.659, drawdown $34,329 → $74,275**. Every card still makes more money and holds a
bigger lockbox net; what it does not do is earn that money at a comparable risk. **The +35% looks
like a property of the walk-forward construction — re-picking parameters every fold — rather than
of anything that can be traded with fixed settings.** That is a stronger and narrower statement
than "B11 fails the new clause", and it is the honest reading of these five cards. B11 is NOT
retracted here: the walk-forward result stands as what it is, an out-of-sample walk-forward
result, and what is now on record beside it is that its tradeable form does not clear its own bar.

**The clause swap was not what decided it, and that is worth saying plainly.** On the A cards the
lockbox drawdown is the *kinder* number: whole-run ratios x1.587 and x2.156 against lockbox ratios
x1.122 and **x1.068** — the last of those is nearly inside the 5% tolerance. Had MAR passed, the
new clause would have been the easier gate, not the harder one. The two clauses disagree about the
direction of the risk on this candidate, which is exactly why both print on every card.

**A finding the new engine block produced on its own:** #348 reports
`inert_legs = ['TTMSQZ_3_0_ES30N.py']`. Adding the dip leg **moves the book's worst stretch** from
2022-04-27..05-24 ($34,329) back to the 2020 crash ($74,275) — and in that different stretch the
TTM leg is the absent one. So which legs are inert is not a fixed property of a leg; it moves with
the composition of the book. Any bar quoting a whole-run drawdown has to be re-read whenever a leg
is added, not just the first time.

Results log `tools/data/b11_lockbox_rejudge_results.txt`. STUDIES block `b11rejudge`.

**The prediction, written before the runs** (offline, `tools/book_dd_attribution.py`, same legs) —
kept here because every line of it was confirmed:

| card | vs | MAR | whole-run DD | **lockbox DD** | lockbox net | verdict |
|---|---|---|---|---|---|---|
| #311 (CAND-A1) | CONTROL-A | **x1.008** | x1.587 | x1.122 | x1.156 | MISS |
| CAND-A2 | CONTROL-A | **x1.086** | x2.156 | x1.068 | x1.466 | MISS |
| CAND-B1 | BOOK #336 | **x0.659** | x2.164 | x1.237 | x1.162 | MISS |

**All three miss — and the clause that kills them is not the risk clause, it is MAR.** B11's
headline was MAR x1.35; frozen into a tradeable file the same family reaches x1.01 and x1.09
against a x1.15 bar, and on today's book it is actively harmful (x0.659, drawdown $34,329 ->
$74,275). **The +35% appears to belong to the walk-forward construction — re-picking parameters
every fold — rather than to anything that can be traded with fixed settings.**

**And a point that cuts against the finding that motivated this:** on the A cards swapping to the
lockbox drawdown makes the bar *easier*, not harder. Whole-run DD ratios are x1.587 and x2.156
while lockbox DD ratios are x1.122 and x1.068 — the latter nearly inside the 5% tolerance. The two
clauses disagree about the direction of the risk here, which is why both are printed on every card
rather than one replacing the other silently.

### 10c. THE ETF BOOK STACK RE-JUDGED — the first verdict the clause swap actually changes

Owner: *"now do the same for the ETF book stack."* Driver `tools/queue_etf_lockbox_rejudge.py`;
prediction and results in `tools/data/etf_lockbox_rejudge_{prediction,results}.txt`. Runs **#349,
#350, #351**, every figure matching a prediction written before they ran, **to the dollar**.

**A stronger test than the B11 re-judge.** B11's book re-tunes every fold, so only a weaker
"tradeable representation" of it could be run. The ETF legs *are* fixed-parameter files — exactly
the seven BOOK run #338 carries — replayed unchanged. Nothing is approximated here.

**The bar is B1's own stack bar with one clause swapped:** MAR ≥ incumbent ×1.15 (unchanged),
**LOCKBOX drawdown within 5%** (was the whole-run denominator), net ≥ 90% of the incumbent's
(unchanged — B1's "give up ≤ 10% of its net"). Window 2010-06-07..2026-06-30, 12-month lockbox, so
run #347 is the incumbent for this re-judge and the B11 one alike.

| card | run | net | whole DD | ann.MAR | lockbox | LB DD | PF | slices |
|---|---|---|---|---|---|---|---|---|
| CONTROL-A (champion of the day) | #347 | $793,811 | $71,903 | 0.687 | $201,204 | $35,723 | 1.31 | 8/8 |
| **ETF-A1** champion + 7 ETF legs | **#349** | $1,318,092 | $93,429 | 0.878 | $253,632 | $36,950 | 1.40 | 8/8 |
| **ETF-S** the 7 ETF legs alone | **#350** | $524,281 | $43,818 | 0.787 | $52,428 | $25,007 | 1.75 | 8/8 |
| CONTROL-B (adopted book) | #336 | $1,119,697 | $34,329 | 2.031 | $193,170 | $26,235 | 1.49 | 8/8 |
| **ETF-B1** adopted book + 7 ETF legs | **#351** | $1,643,978 | $53,597 | 1.910 | $245,598 | $48,867 | 1.55 | 8/8 |

| judged | vs | MAR (×1.15) | net (≥0.90) | whole-run DD | **lockbox DD** | old | new |
|---|---|---|---|---|---|---|---|
| **#349** | #347 | **×1.278** ✓ | ×1.660 ✓ | ×1.299 ✗ | **×1.034** ✓ | MISS | **PASS** |
| #351 | #336 | **×0.940** ✗ | ×1.468 ✓ | ×1.561 ✗ | ×1.863 ✗ | MISS | MISS |

**#349 IS THE FIRST CARD ON THIS BOARD WHERE THE CLAUSE SWAP CHANGES THE VERDICT — and it changes
it towards adopting something the old clause blocked.** The two clauses disagree by a factor of
nine on the same candidate: the whole-run drawdown says the stack costs **+30%** more drawdown, the
lockbox drawdown says it costs **+3.4%**.

**And the disagreement is NOT an inert clause.** `inert_legs = []` on #349: all seven ETF legs
trade inside the champion's worst stretch, because that stretch is the 2020 crash and these are
dip buyers. Both numbers are real measurements of different stretches. The whole-run figure is
2020; the lockbox figure is 2026-06-17..06-26, where the ETF legs contribute almost nothing and
94% of the loss is the ENGU-Q leg the incumbent already carried. **That is the honest reading: the
ETF legs cost drawdown in a crash and cost nothing in the sealed year.** Which of those a bar
should price is a judgement about what kind of risk the account is actually exposed to, and it is
the owner's call — not something the clause swap settles by itself.

**This is a CANDIDATE, not an adoption, and four things stand between it and one:**
1. **No leg-level validate.** None of the seven has ever been through Auto-Validate — they are
   round-25 sweep cells. A BOOK card is not a substitute for a validate; that is exactly the
   NQDIP_1_1 lesson (run #315 passed a sweep at MAR 10.2 and failed its validate 3-of-8 folds).
2. **Two of the seven are near-duplicates** (QQQ RSI2 long-only and QQQ RSI2 both-sides). They
   post identical dollars in both worst stretches. The bar does not price that concentration.
3. **The window is not B1's.** It adds a year past r25's 2025-06-29 cut — genuine holdout for
   these legs, but it means the ×1.278 here is not comparable to B1's recorded +12%, which was
   also a different object (the 20-leg equal-risk book, not these seven).
4. **ETF-S has two losing years of its own** (14 of 16). The stack cards hide that because the NQ
   legs paper over them.

**ETF-B1 settles the question that actually bears on the deployed book: no.** Adding these legs to
what is traded today cuts MAR 6% and **nearly doubles the lockbox drawdown** ($26,235 → $48,867).
Whatever #349 says about the old champion pairing, this family does not belong on book #336.

**#351 reproduced the same moving-target effect the B11 re-judge found:** its `inert_legs` is
`['TTMSQZ_3_0_ES30N.py']` — the leg not under test — because adding the ETF legs moved the book's
worst stretch from 2022-04-27..05-24 back to the 2020 crash, where TTM also took no trades. Two
independent candidates have now moved a book's worst stretch by being added to it.

### 10d. THE SEVEN ETF LEGS, VALIDATED INDIVIDUALLY — 6 of 6 FAIL, and run #349 is WITHDRAWN

Owner: *"validate the seven ETF legs individually."* This was blocker #1 on the run-349 candidate in
§10c. Drivers `tools/queue_etf_leg_validates.py`, readers `tools/etf_leg_validate_report.py` and
`tools/etf_leg_prewindow.py`; logs `tools/data/etf_leg_{validates,prewindow}.txt`.

**Seven legs, six validates.** The two "near-duplicate" QQQ RSI2 legs differ only in `allow_shorts`,
and `augur_engine/auto.py` treats a bool as categorical that is **always searched over both values**
— so one validate answers for both. That alone disposes of the near-duplicate caveat: they were
never two independent legs. Full discovery over each file's own ranges, nothing pinned. Window
2009-06-01..2026-06-30 (exactly what r25 loaded), 12-month lockbox, `min_trades` lowered from the
usual 300 to r25's own floor of 100 because these legs only produce 122-221 trades in 17 years.

| run | leg | verdict | gates | failed | wfe roll | wfe anch | trades/param | lockbox n | crown = book cell? |
|---|---|---|---|---|---|---|---|---|---|
| #354 | DBL7 GLD | **FAIL** | 4/6 | wfe, sample | 0.167 | 0.668 | 25.0 | 6 | no |
| #355 | DBL7 TLT | **FAIL** | 4/6 | wfe, consistency | 0.050 | 0.234 | 35.2 | 2 | no |
| #356 | DBL7 QQQ | **FAIL** | 3/6 | wfe, pbo, consistency | 0.061 | 0.000 | 32.5 | 0 | no |
| #357 | RSI2 IWM | **FAIL** | 2/6 | wfe, pbo, consistency, sample | 0.215 | 0.465 | 24.9 | 12 | no |
| #358 | RSI2 QQQ | **FAIL** | 4/6 | wfe, consistency | 0.332 | 0.096 | 30.8 | 0 | no |
| #359 | PB20 QQQ | **FAIL** | 3/6 | wfe, pbo, consistency | 0.205 | 0.000 | 63.0 | 0 | no |

**Every single one fails walk-forward efficiency** — 0.050 to 0.332 against a 0.5 threshold — and
five of six also fail consistency. **And not one crown is the cell the book carries**, so even
setting the verdicts aside, the book's r25 cells were never validated (the run #343 precedent,
pre-registered before these ran).

**These are not noise cells, and that is what makes the result interesting.** Every leg shows a
statistically significant in-sample edge: t = 2.41 to 5.57, all p < 0.02, `causal` returns "entry
timing carries real signal" on all six, and `plateau` returns HIGH GROUND on all six. What they do
not do is survive being re-fitted forward. High in-sample significance, a real plateau, and
walk-forward efficiency near 0.1 is the textbook signature of an edge that does not generalise.

**The second holdout says the same thing from the other side.** On 2006-01-03..2009-05-31 — which
r25 never downloaded and which was deliberately excluded from the validate window — two of the six
crowns lose money (DBL7 QQQ −$928, PB20 QQQ −$18,681). More telling: **the simple r25 cell beats the
300-trial crown there in 5 of 6 legs** (GLD $36,388 vs $23,690; TLT $6,292 vs $1,999; IWM $26,683 vs
$20,685; QQQ RSI2 $11,538 vs $4,563; QQQ PB20 +$11,970 vs −$18,681). A 300-trial search on a leg
with ~150 trades is fitting noise, which is exactly what `pbo` reported on three of them ("likely
overfit selection", 0.409 to 0.901).

**THE PRE-REGISTERED CONSEQUENCE, APPLIED.** §10c and the queue driver both committed in advance:
*"if any leg FAILS, #349 is re-scored on the survivors and the lockbox clause re-applied; run #349's
PASS is provisional on these six validates."* All six failed, so there are no survivors and there is
nothing to re-score. **The run-349 ETF stack candidate is WITHDRAWN.** It is not a close call and it
does not need another book run.

**RETIRED FROM THE SHADOW BOOK 2026-09-09** (owner: *"retire the ETF legs from the shadow book"*).
The `ETFBOOK_332` paper leg — added that same morning, live_from 2026-09-09 — never wrote a row: it
needed a runner restart to activate and the validates landed first. It is now archived rather than
deleted, the house convention: the leg comes out of `PAPER_LEGS`, its `LEG_SOURCE` provenance block
stays so any report naming the key still resolves, and the board keeps it behind SHOW ARCHIVED with
its colour and label intact. A forward test exists to find out whether an edge survives going
forward; six of six had already answered that, so shadow time on them buys nothing.

*One switch, not two.* The runner hook in `api/runner.py` is deliberately left wired.
`etf_book_shadow.maybe_nightly_update` now returns immediately when `ETFBOOK_332` is absent from
`PAPER_LEGS`, so registration is the only switch and re-adding the entry turns the whole path back
on with nothing else to remember. That matters more than it looks: this leg's evening job appends
Yahoo bars to the frozen daily masters, so a half-retirement — off the board, still appending —
would have been invisible, because no row is written anywhere a person looks.
`tests/test_etf_book_shadow.py` pins both halves (the hook is off while the leg is unregistered and
comes back when it is re-registered; the provenance block survives), and removing the check makes
that test fail.

**What this does and does not say about the clause work.** It does not retract anything in §10 or
§10c: the lockbox-drawdown clause behaved exactly as designed — it flagged #349 as a *candidate*,
listed the missing leg validates as blocker #1, and blocker #1 is what killed it. The clause swap
was never the weak link. **The legs were.** The lesson is the older one, sharpened: a book card
measures how a pile of legs behaves together and can look excellent while every leg in it is
individually unvalidated. Run #315 taught it for NQDIP_1_1; this is the same lesson at book scale.

### 10e. OPEN TRADES VALUED DAILY — a second drawdown reading on every book (2026-09-25, v73.899)

**Why.** Every book figure counts a trade on the day it CLOSES. That is exact for an intraday leg
and blind for one that holds for weeks: ENGU-Q (`ENGUQ_1M_ETH_R2_1_0.py`) has held a trade 143
days on NQ, and its 182 trades held over 5 days carry $901,692 of a leg that nets $603,381. While
those trades are open their swings never reach the book's daily curve. Found in book round 56
(`BOOK_ROUND56_ROC.txt` section 5).
> Roll audit (2026-09-25): on roll-corrected prices this leg nets $499,155, not $603,381
> (ROLL_AUDIT.md 3.2); see 10f.

**What changed.** `augur_engine/book.py` scores the same dollars twice. The headline - every
stored number, every bar - stays the at-close reading. `book.mtm` values each open position at
the last close of every day it is open (the book's own day stamp) and lets the exit day carry the
remainder, so each trade's increments sum EXACTLY to its closed dollars. Keys: `whole`,
`pre_lockbox`, `lockbox` (each `{total_pnl, max_drawdown}`), `worst_stretch`,
`worst_stretch_lockbox`, `marked_trades`, `multi_day_legs`, `drawdown_differs`, `net_differs`.
Same policy as `day_rule` (10b): a second reading, never a replacement. COMPARE's book rows (the
RUNBOARD tile and the BOOKS view) print it under the book's name for the stage on screen, only
when it differs - never for an intraday-only book.

| book | stage | at close | open trades valued daily |
|---|---|---|---|
| #397 FRONTIER | lockbox drawdown | $25,357 | **$49,855** (2026-06-18 to 06-26) |
| #397 FRONTIER | pre-lockbox drawdown | $33,567 | $34,449 |
| #396 (recommended) | lockbox drawdown | $27,506 | $49,855 |
| #372 FRONTIER PENTA | lockbox drawdown | $34,205 | $54,539 |

> Roll audit: corrected, #397's pre-lockbox drawdown is $40,971 at close / $41,853 valued daily and
> its lockbox drawdown $25,893 at close; the #396 and #372 rows do not move (10f). The $49,855
> stretch sits just after the unrepaired June 2026 switch.

Whole-run net is identical to the cent on all three, and the at-close figures reproduce the stored
runs exactly (756 ENGU-Q trades marked, none unmarkable).

**Bars.** Book bars (section 10's clause) are still written on the at-close figures; whether a bar
should use the valued-daily reading is an owner call. Sizing should read the valued-daily drawdown.

**Backfill.** `python tools/backfill_book_mtm.py --runs <ids> [--write]` re-runs a stored book,
refuses unless its at-close figures match the stored run to the cent, and writes only `book.mtm`.
Gates: `tests/test_book_mtm.py`, `tools/runboard_books_probe.py` (both book tables, every stage).

**Not in this change:** the quarterly-roll steps a multi-week leg books on the no-adjust masters
(about $39,580 = 6.6% of the ENGU-Q NQ leg's net, measured by the sibling session; see
`BOOK_ROUND56_ROC.txt` section 5b).
> Superseded by ROLL_AUDIT.md 4.6: 36 crossings book $38,985 ($34,240 pre-lockbox, $4,745 in the
> lockbox); with the changed trades the leg loses $104,226 and the books 8.0-8.5% - see 10f.

**Correction for the DIP legs (2026-09-25, after v73.899).** The first version valued every open
position as side x (close - entry) x the leg's multiplier. The DIP files (`NQDIP_1_0.py`,
`NQDIP_1_1.py`, `ETFDIP_DBL7/PB20/RSI2_1_0.py`) size themselves - whole MNQ micros, or shares for a
$100k notional - and return DOLLARS, so a book runs them at multiplier 1 and their open positions
were valued at $1 a point. NQDIP also leaves each quarterly roll gap out of its P&L. Each of those
files now declares `PNL_UNITS = "usd"` and values its own open trades in `mark_open_trades()`, which
the book uses in place of the price formula (`book._plugin_marks`); a dollar-P&L file without the
hook has its multi-day trades booked at close and counted as unmarked, never priced at $1 a point.
Same commit: `ETFDIP_RSI2_1_0.py` recorded a short's side as +1 (net was always right; open values
and the side column were inverted). Checked against an independent calculation on all nine DIP
runs to 1e-12 (e.g. DIP on NQ #423 pre-lockbox drawdown valued daily $57,455, was $36,497; DIP on ES
#425 lockbox $22,371, was $11,800). The stored book runs with DIP legs are re-scored with the backfill
right after this ship (its dry run: at-close figures reproduce to the cent; points-only books unchanged):

| book | whole-run drawdown valued daily | lockbox, valued daily |
|---|---|---|
| #311 | $128,341 (was $112,129) | $41,942 (was $43,749) |
| #332 | $114,320 (was $73,038) | $70,136 (was $61,426) |
| #338 | $68,855 (was $43,814) | $42,122 (was $35,556) |
| #346 | $194,056 (was $152,619) | $60,094 (was $42,060) |
| #348 | $90,758 (was $78,208) | $42,803 (was $40,823) |
| #349 | $110,605 (was $95,466) | $57,430 (was $40,269) |
| #350 | $68,855 (was $43,814) | $44,905 (was $24,994) |
| #351 | $68,000 (was $57,074) | $52,500 (was $36,424) |

Gates: `tests/test_dip_open_marks.py` (each file's open values plus its own costs rebuild its closed
P&L to the cent, across roll seams; every file with a `notional` knob must have the hook).

### 10f. Roll-audit restatement (2026-09-25/26) - #366, #396 and #397 on roll-corrected legs

**What was done.** `ROLL_AUDIT.md` (2026-09-25) re-ran the three current books locally with every
leg's quarterly contract rolls corrected (section 4.3): the ENGU-Q #335 leg on back-adjusted NQ
1-minute prices, the TTM leg on back-adjusted ES 30-minute prices, and NOISE #304 with the
prior-close fix. Every "stored" figure below was first reproduced from the stored run to the dollar.
**No stored run was changed**: Past Runs, the RUNBOARD and every table above this section still show
the raw figures. These are local re-runs, not new BOOK jobs.

**Window.** 2010-06-07 to 2026-06-30 with the lockbox from 2025-06-30 (ROLL_AUDIT.md 4.3), so the
pre-lockbox stretch is 2010-06-07..2025-06-29 (5,502 days = 15.06 years) and the lockbox is
2025-06-30..2026-06-30 (365 days = 0.9993 year at 365.25 days a year). ROC %/yr is EL's column: net
per year as a percentage of a $100k account (`BOOK_ROUND56_ROC.txt` section 1). This convention
reproduces round 56's stored-run figures exactly (#397 97.4 / 306.3, #396 98.5 / 307.3).

**What these numbers do NOT include: the June 2026 roll.** The June 2026 contract switch sits inside
one bar of the NQ 1-minute 24-hour master, and none of the columns below repairs it. Repaired on its
own, it takes a further **-$5,860** off the ENGU-Q #335 leg on both the whole run and the lockbox
(V, ROLL_AUDIT.md 3.2), so each book should fall by about that much more. The TTM and NOISE legs also
carry the uncorrected June gap on the day-session masters, and that part is not quantified. The audit
marks the combined book figures *to be recomputed* (4.3).

#### BOOK #396 (recommended)

| Figure | Stored | Roll-corrected | Change |
|---|---|---|---|
| Whole-run net | $1,790,319 | $1,640,039 | -$150,280 (-8.4%) |
| Pre-lockbox net | $1,483,223 | $1,340,004 | -$143,219 (-9.7%) |
| Lockbox net | $307,096 | $300,034 | -$7,062 (-2.3%) |
| Pre-lockbox drawdown, at close | $36,562 | $43,967 | +$7,405 (+20.3%) |
| Pre-lockbox drawdown, valued daily | $37,444 | $44,849 | +$7,405 (+19.8%) |
| Lockbox drawdown, at close | $27,506 | $27,506 | none |
| Lockbox drawdown, valued daily | $49,855 | $49,855 | none (see the June note above) |
| Pre-lockbox net/DD | 40.57 | 30.48 | |
| Lockbox net/DD | 11.16 | 10.91 | |
| Profit factor, pre-lockbox / lockbox | 1.5105 / 1.5984 | 1.4488 / 1.5855 | |
| ROC %/yr, pre-lockbox | 98.5 | 89.0 | -9.5 points |
| ROC %/yr, lockbox | 307.3 | 300.2 | -7.1 points |
| Consistency (8 stretches) | 8/8, PASS | 8/8, PASS | |

#### BOOK #397 (FRONTIER)

| Figure | Stored | Roll-corrected | Change |
|---|---|---|---|
| Whole-run net | $1,773,541 | $1,623,261 | -$150,280 (-8.5%) |
| Pre-lockbox net | $1,467,499 | $1,324,280 | -$143,219 (-9.8%) |
| Lockbox net | $306,042 | $298,981 | -$7,061 (-2.3%) |
| Pre-lockbox drawdown, at close | $33,567 | $40,971 | +$7,404 (+22.1%) |
| Pre-lockbox drawdown, valued daily | $34,449 | $41,853 | +$7,404 (+21.5%) |
| Lockbox drawdown, at close | $25,357 | $25,893 | +$536 (+2.1%) |
| Lockbox drawdown, valued daily | $49,855 | $49,855 | none (see the June note above) |
| Pre-lockbox net/DD | 43.72 | 32.32 | |
| Lockbox net/DD | 12.07 | 11.55 | |
| Profit factor, pre-lockbox / lockbox | 1.5226 / 1.6073 | 1.4586 / 1.5942 | |
| ROC %/yr, pre-lockbox | 97.4 | 87.9 | -9.5 points |
| ROC %/yr, lockbox | 306.3 | 299.2 | -7.1 points |
| Consistency (8 stretches) | 8/8, PASS | 8/8, PASS | |

#### BOOK #366 (adopted until 2026-09-28, starred)

| Figure | Stored | Roll-corrected | Change |
|---|---|---|---|
| Whole-run net | $1,685,715 | $1,550,996 | -$134,719 (-8.0%) |
| Pre-lockbox net | $1,395,904 | $1,268,246 | -$127,658 (-9.1%) |
| Lockbox net | $289,811 | $282,750 | -$7,061 (-2.4%) |
| Pre-lockbox drawdown, at close | $36,562 | $40,854 | +$4,292 (+11.7%) |
| Pre-lockbox drawdown, valued daily | $37,444 | $41,736 | +$4,292 (+11.5%) |
| Lockbox drawdown, at close | $28,066 | $28,066 | none |
| Lockbox drawdown, valued daily | $49,855 | $49,855 | none (see the June note above) |
| Pre-lockbox net/DD | 38.18 | 31.04 | |
| Lockbox net/DD | 10.33 | 10.07 | |
| Profit factor, pre-lockbox / lockbox | 1.4862 / 1.5634 | 1.4303 / 1.5504 | |
| ROC %/yr, pre-lockbox | 92.7 | 84.2 | -8.5 points |
| ROC %/yr, lockbox | 290.0 | 282.9 | -7.1 points |
| Consistency (8 stretches) | 8/8, PASS | 8/8, PASS | |

#### For comparison: #379 and #372

| Figure | #379 stored | #379 corrected | #372 stored | #372 corrected |
|---|---|---|---|---|
| Whole-run net | $1,773,184 | $1,622,903 | $1,667,190 | $1,550,566 |
| Pre-lockbox net | $1,479,042 | $1,335,823 | $1,383,367 | $1,273,814 |
| Lockbox net | $294,142 | $287,081 | $283,823 | $276,752 |
| Pre-lockbox drawdown, at close | $33,350 | $33,350 | $36,487 | $37,918 |
| Pre-lockbox drawdown, valued daily | $35,993 | $35,993 | $37,369 | $38,800 |
| Lockbox drawdown, at close | $26,683 | $26,683 | $34,205 | $34,205 |
| Lockbox drawdown, valued daily | $49,855 | $49,855 | $54,539 | $54,539 |
| Pre-lockbox net/DD | 44.35 | 40.05 | 37.91 | 33.59 |
| Lockbox net/DD | 11.02 | 10.76 | 8.30 | 8.09 |
| ROC %/yr, pre-lockbox / lockbox | 98.2 / 294.3 | 88.7 / 287.3 | 91.8 / 284.0 | 84.6 / 276.9 |
| Consistency (8 stretches) | 8/8, PASS | 8/8, PASS | 8/8, PASS | 8/8, PASS |

**Where each figure comes from.**
- Whole-run net, lockbox net, both net/DD ratios and the pre-lockbox drawdown at close: ROLL_AUDIT.md
  4.3, first table ("Before" and "All three fixes" columns).
- Pre-lockbox drawdown valued daily: ROLL_AUDIT.md 4.3, second table (V).
- Pre-lockbox net, lockbox drawdown at close and valued daily, and profit factor: the audit's output
  file `work\sweep-holders\impact\books_run1.log` (the "stored" and "V3_ttm_noise_enguq" lines, which
  are the "All three fixes" state of 4.3). #397's corrected lockbox drawdown ($25,893) is also printed
  in `work\harness-misc\book_impact.log`.
- ROC %/yr, stored: `work\harness-misc\book_years.log` and `BOOK_ROUND56_ROC.txt` section 4. ROC %/yr,
  roll-corrected: arithmetic on the corrected pre-lockbox and lockbox nets (net / 15.0637 years /
  $1,000, and net / 0.99932 year / $1,000). The audit file prints ROC only for a state with ENGU-Q and
  TTM corrected but not NOISE: #396 89.1 / 300.2, #397 88.1 / 299.2, #366 84.4 / 282.9.
- #372: ROLL_AUDIT.md 4.4 gives only its ENGU-Q leg delta (-$103,706) and "stays PASS" (M). Every other
  #372 figure is from `books_run1.log`.
- The "Change" column is arithmetic.
- Verification (ROLL_AUDIT.md 4.3): #396 and #397 are **V** (re-run by a second agent). #366 is V except
  its TTM+NOISE and all-three columns, which are M: one agent measured them, and they follow
  arithmetically from verified leg deltas. #379 is **M**; #372 is **M** (4.4).

**Where the money goes.** Whole-run net, from the columns of ROLL_AUDIT.md 4.3:

| Book | ENGU-Q fix alone | TTM + NOISE fixes | All three |
|---|---|---|---|
| #366 | -$104,226 | -$30,493 | -$134,719 |
| #396 | -$104,226 | -$46,054 | -$150,280 |
| #397 | -$104,226 | -$46,054 | -$150,280 |

- **ENGU-Q.** The -$104,226 is the #335 leg falling from $603,381 to $499,155 (-17%, V, 3.2). Only
  $38,985 of it is money booked across switches. The rest is a different sequence of trades,
  dominated by one March 2023 entry that a stale regime average let through just after a roll.
- **TTM and NOISE.** The TTM part is -$43,180 for TTM #369 x3 in #396/#397 (V) and -$27,620 for
  TTM #353 x3 in #366 (M) (3.3). The NOISE #304 leg moves -$2,874 ($405,980 to $403,106, V, 3.4).
- **Lockbox net.** Every book's lockbox net falls by about $7,061, and all of it is the ENGU-Q leg:
  the TTM and NOISE lockboxes do not move (3.3, 3.4).

**Why the pre-lockbox drawdowns rise.** All of the rise is one new TTM short on 2020-03-17, inside the
Feb-Mar 2020 worst stretch (4.3, V). It costs 3 x -$2,468 = -$7,404 with TTM #369 (#396, #397) and
3 x -$1,431 = -$4,292 with TTM #353 (#366). The valued-daily worst stretch is 2020-03-02..2020-03-27
in every variant. #379 does not move because its worst stretch is May 2022, which the correction does
not touch (4.3, M).

**Finding 1 - #396 over #366 now rests on the held-back year alone** (ROLL_AUDIT.md 4.3; owner call,
7 item 4).
- **Before the correction**, #396 led on both stretches: selection n/DD 40.57 against 38.18, and
  lockbox n/DD 11.16 against 10.33.
- **Corrected, #366 is slightly ahead on the selection stretch** (31.04 against 30.48). #396's TTM
  leg takes the new 2020 short three times at -$2,468, while #366's takes it at -$1,431.
- **#396 still wins the held-back year**: $300,034 / PF 1.585 against $282,750 / PF 1.550 (n/DD 10.91
  against 10.07).
- **#396 still makes more money.** It is $89,043 ahead on whole-run net, down from $104,604
  (`book_years.log`). Its corrected ROC is 89.0 against 84.2 before the lockbox and 300.2 against
  282.9 in it (arithmetic, tables above).
- **Calendar-year test (book55c, M).** Years 2011-2025 are counted. A year is a #396 win when it
  makes at least as much net with no deeper in-year drawdown, and a loss when it makes less net
  with a deeper drawdown.

  | Correction state | #396 vs #366, wins / losses of 15 |
  |---|---|
  | Stored | 6 / 1 |
  | ENGU-Q fixed | 7 / 1 |
  | TTM fixed alone | 4 / 3 |
  | ENGU-Q and TTM fixed (NOISE not fixed in this test) | 5 / 3 |

- **In the same test**, #397 against #396 goes from 6 / 4 to 7 / 4. The TTM-leg swap (#353 to #369)
  earns more net in 11 of 15 years, not 13 (M).
- **Still owed.** The audit asks for this test to be re-run with every leg corrected, NOISE
  included, before the recommendation is re-decided.

**Finding 2 - #397 now trails #379 by 19% on the selection stretch** (ROLL_AUDIT.md 4.3 and 3.8
items 8 and 13; owner call, 7 item 5).

| Correction state | #397 selection n/DD | #379 selection n/DD | #397 below #379 |
|---|---|---|---|
| Stored | 43.72 | 44.35 | 1.4% |
| TTM fixed alone | 34.76 | 43.05 | 19.3% |
| TTM + NOISE fixed | 34.69 | 42.97 | 19.3% |
| All three fixed | 32.32 | 40.05 | 19.3% |

- **"19%" means #397's ratio is 19% below #379's.** Put the other way, #379 is about 24% above (3.8
  item 8). The ENGU-Q-only state was not computed for #379.
- **The held-back-year ranking does not change.** #397 leads 11.55 against 10.76 corrected (12.07
  against 11.02 stored).
- **The gap comes from #397's drawdown.** #379's selection-stretch drawdown stays at $33,350,
  because its worst stretch (May 2022) is untouched. #397's drawdown rises to $40,971 through the new
  2020 TTM short.

**What this does not change.**
- **Verdicts.** Every variant of all five books is PASS 8/8 (4.3, and `books_run1.log` for #372).
- **ROC order, lockbox.** The order of the five books is unchanged.
- **ROC order, pre-lockbox.** The only swap is at the bottom: #372 (84.6) moves just ahead of #366
  (84.2). This is arithmetic from the tables above.
- **Book bars.** Section 10 bars are still read on the stored at-close figures. Re-running #366, #396
  and #397 (then #379, #371, #378 and #339) as BOOK jobs on corrected masters is proposed in
  ROLL_AUDIT.md 6.7 item 4. It waits for owner approval and for the adjusted masters to be built.
- **The valued-daily lockbox drawdown ($49,855, 2026-06-18..06-26).** It sits just after the June
  2026 switch and was not re-checked with that switch repaired (4.3).

Reproduce: the audit's scripts and logs are listed at the end of ROLL_AUDIT.md
(`C:\EdgeLog\_anatomy_cache\rollaudit\work\sweep-holders\impact\` and `work\harness-misc\`).

**Elsewhere in this file, figures the audit also restates** (history is left as written; ROLL_AUDIT.md
section in brackets, V = verified by a second agent, M = measured once):
- 3.4 row 24, the ENGU-Q day-session leg of #227: nets $374,531 corrected, not $477,521; run #227's
  drawdown $65,635 -> $87,683 (3.2, V). Rows 25/29 (#262, #261) carry that leg: #262 stays PASS (4.4, M).
- 10's "$34,329.21 - the same to the cent" (#336 / #337 / #341): #337 loses its ENGU-Q #309 leg delta
  (-$96,992) and stays PASS (4.4, M); the drawdown itself was not restated.
- 10's weak-edge ETF book #332: drawdown $75,755 with DIP's true switch days; the r25 gates still hold
  (4.4, M).
- 10a / 10c: #347 $793,811 -> $702,192 with 8/8 -> 7/8 stretches; #311 / #346 / #348 at-close drawdowns
  +$7,668 each (#311 $114,107 -> $121,775) on the corrected DIP leg (4.4, M); the MAR ratios there were
  not recomputed.
- 10e's DIP figures: at close, DIP on NQ #423's drawdown is $47,505 (true switch days) / $39,458
  (back-adjusted), and DIP on ES #425's is $66,592-$68,714, not $54,016 (3.6, V). The valued-daily DIP
  figures in 10e were not restated.

### 10g. Round 58 — beating #397's ROC / YR with ML: no (2026-09-25)

**The ask and the fair comparison.** Owner: *"beat roc/yr on our best frontier model … ML's count."* ROC / YR
doubles when contracts double, so every candidate was scaled by one book-wide factor, set on the pre-lockbox
stretch only so its pre-lockbox drawdown (the worse of at-close and valued-daily) matches #397's $34,449, then
carried unchanged into the lockbox. Pre-registered bar at that size: pre ROC ≥ 102.3 (1.05 × 97.4), lockbox
ROC ≥ 306.3, lockbox drawdown within 5% ($26,625 at close / $52,348 valued daily), more net in ≥ 10 of 15 years.

**Result: no genuine beat in ~71 books** (58a grid of 60, 58b volatility dial, 58c KEEL v12 / #422, 58d ENGU-Q's own gate).

| book, at #397's drawdown | pre ROC | lockbox ROC | lockbox DD at close | verdict |
|---|---|---|---|---|
| #397 FRONTIER as run | 97.4 | 306.3 | $25,357 | — |
| ENGU-Q et@0.55 cut + NOISE #422 (58d) | 103.3 | 321.0 | $26,492 | passed, then **refuted** |
| NOISE #422 in the NOISE slot (58c) | 105.7 | 322.7 | $27,955 | misses the drawdown clause only — **owner call** |
| + NOISE #398 x1 (58a, closest) | 108.5 | 328.2 | $28,821 | misses the drawdown clause |

**Why the 58d pass is refuted.** It holds only at gate seed 42 and start 2010-06-07 (0 of 10 other seeds, 0 of 4
other starts, +0.25 cost fails); its $133 of drawdown headroom is two ENGU-Q losers on 2025-11-25 that seed 42
skipped; and the cut loses money ($36,277 before the lockbox) and scores winners at chance (AUC 0.495).
**The #335 gate belongs to run #335's champion (cost 0.533), not to #397's ENGU-Q leg (R2 defaults, cost 0.783)**:
moved onto the leg it takes the lockbox from $107,941 to $14,705. No validated gate exists for that leg.

**Owner call (not a recommendation):** NOISE #422, the validated 1.75x compression tilt, in place of #304 earns
more in 15 of 15 years at an unchanged pre-lockbox drawdown, but misses the lockbox at-close cap by $1,330, and
its lockbox gain sits at the 78.9th percentile of random upsizing, it adds only 2.7% at matched
volatility, and it fails the bar at the tradable 1.7x and 1.8x sizes (1.75 NQ is not a whole
number of micros).

**Pre-audit.** All figures are on the unadjusted masters (10f restates the books); ROLL_AUDIT.md later found roll phantom P&L in the
ENGU-Q NQ leg. Both sides of every comparison carry the same legs, so the verdicts stand; the absolute ROC
figures are pre-audit. Full write-up: `BOOK_ROUND58_ML.txt` (data and scripts in
`C:\EdgeLog\_anatomy_cache\frontier_ml\`, outside git).

### 10h. BOOK #417 / #418 / #419 re-run with their frozen settings - read runs #430 / #429 / #431 (2026-09-26)

**Why.** The three jobs queued 2026-09-24 carried NO params on every leg they shared with their source
book (the legs look copied from a run doc's `book.legs`, which never stores params). A leg with empty
params runs the strategy file's own defaults, so ORB, ENGU-Q and (in #419) NOISE #304 were not the
frozen legs: ENGU-Q ran 2,843 trades / $420,506 instead of 1,949 / $603,381; ORB $337,940 instead of
$373,305; #419's NOISE $395,169 instead of $405,980. The TTM legs happened to be right (their defaults
equal the frozen settings). **The stored #417 / #418 / #419 do not describe the books their names
claim - read the re-runs.** ELwA: Features is adding a runner guard against empty-params legs.

**How.** Each re-run is the source book's job legs VERBATIM plus exactly the change the broken job's own
name and label state: #417 and #418 swap the NOISE slot from NOISE #304 to the live NOISE leg (NOISE
#382, run #382's champion); #419 adds TTIBS #300 as a fifth leg. Before queueing, #396 and #366
reproduced their stored figures to the cent from their own legs, and every shared leg matched its
source-run leg to the cent. The runner's results equal that local re-run to the cent. Queue script and
parity table: `C:\EdgeLog\_anatomy_cache\manager_0926\` (`queue_books_0926.py`, `parity_table.json`).

| run | what it is | pre-lockbox net / ROC %/yr | pre DD at close / valued daily | lockbox net / ROC %/yr | lockbox DD at close / valued daily | stretches |
|---|---|---|---|---|---|---|
| **#430** | re-run of #417: #396 with NOISE #382 in the NOISE slot | $1,675,397 / 111.2 | $37,738 / $40,306 | $328,445 / 328.7 | $32,467 / $55,474 | 8/8 PASS |
| **#429** | re-run of #418: #366 with NOISE #382 in the NOISE slot | $1,588,077 / 105.4 | $37,738 / $40,306 | $311,161 / 311.4 | $33,292 / $55,474 | 8/8 PASS |
| **#431** | re-run of #419: #396 + TTIBS #300 as a fifth leg | $1,858,429 / 123.4 | $68,852 / $72,102 | $343,905 / 344.1 | $48,074 / $77,370 | 8/8 PASS |
| #396 | reference | $1,483,223 / 98.5 | $36,562 / $37,444 | $307,096 / 307.3 | $27,506 / $49,855 | 8/8 PASS |
| #366 | reference | $1,395,904 / 92.7 | $36,562 / $37,444 | $289,811 / 290.0 | $28,066 / $49,855 | 8/8 PASS |

ROC %/yr = net per year on a $100k account (15.06 years before the lockbox, 1.0 in it). Book runs carry
no Sortino (the book engine does not compute one). Figures are on the stored, unadjusted masters, like
every stored run (10f).

**Reading (no decision taken here).**
- **NOISE #382 in the NOISE slot (#430 vs #396):** +$192,174 before the lockbox for +$1,176 of at-close
  drawdown; +$21,350 in the lockbox for +$4,961 at close and +$5,620 valued daily. Scaled to #396's
  pre-lockbox at-close drawdown it reads about 107.8 / 318.4 %/yr against 98.5 / 307.3, with a lockbox
  at-close drawdown about 14% deeper. Same swap on #366 (#429): the same dollars. Whether to trade NOISE
  #382 (or #422, 10g) in the book's NOISE slot is an **owner call**.
- **TTIBS #300 as a fifth leg (#431 vs #396):** +$375,205 before the lockbox, but the pre-lockbox
  drawdown nearly doubles ($36,562 -> $68,852) and the worst stretch moves from Feb-Mar 2020 to
  Jul-Aug 2024. Scaled to #396's drawdown it reads about 65.5 / 182.8 %/yr - well below #396. On these
  numbers the add does not pay for its drawdown; the TBIS chat re-reads TTIBS from #431.

### 10i. Real book runs on roll-corrected masters - #435 / #436 / #437 / #438 (2026-09-26)

**What.** Owner GO (decision 13, via MANAGER): re-run the current books as real BOOK jobs on the
roll-corrected masters EL-CBU-STOCKS registered on 2026-09-26 (sources `db_adj_eth` / `db_adj_rth`:
Panama back-adjusted on the 64 exact contract switches of `tools/data/contract_switches_*.csv`, with
the June and September 2026 in-bar splices repaired). Legs are each book's frozen job legs VERBATIM
except the data source.

**What is and is not corrected.** ENGU-Q and TTM run on back-adjusted prices, which is exactly how
ROLL_AUDIT.md corrected them (3.2, 3.3). ORB is immune (identical trades either way, 3.4). **NOISE stays
on the no-adjust master**: the audit corrected NOISE with a strategy-side prior-close fix (3.4), and a
back-adjusted master gives NOISE a different, wrong answer (its bands are percent-of-price; measured
$4.7k-$19k off the audit figure). NOISE's own correction is small (NOISE #304 -$2,874, 3.4). The masters
also repair the June 2026 splice, which no audit figure includes (ENGU-Q -$5,860, ROLL_AUDIT 3.2).

**Parity.** Before queueing, the frozen legs on the no-adjust masters reproduced stored #366 / #396 /
#397 / #430 to the cent, and on the corrected masters every trade closing before the June splice
equalled the audit's own code path trade for trade. The runner's results equal that local run to the
dollar, and every leg ran on the intended master (no fallback). Script, targets and logs:
`C:\EdgeLog\_anatomy_cache\rolladj_books\` (`rolladj_books.py`, `rolladj_targets.md`).

| run | = | whole net | pre-lockbox net / ROC %/yr | pre DD at close / valued daily | lockbox net / ROC %/yr | lockbox DD at close / valued daily | stretches |
|---|---|---|---|---|---|---|---|
| **#435** | #366 roll-corrected | $1,548,011 | $1,271,120 / 84.4 | $40,854 / $41,736 | $276,890 / 277.1 | $28,066 / $49,855 | 8/8 PASS |
| **#436** | #396 roll-corrected | $1,637,053 | $1,342,879 / 89.1 | $43,967 / $44,849 | $294,174 / 294.4 | $27,506 / $49,855 | 8/8 PASS |
| **#437** | #397 roll-corrected | $1,620,275 | $1,327,154 / 88.1 | $40,971 / $41,853 | $293,121 / 293.3 | $25,893 / $49,855 | 8/8 PASS |
| **#438** | #430 roll-corrected | $1,850,577 | $1,535,052 / 101.9 | $45,143 / $46,024 | $315,524 / 315.7 | $32,467 / $55,474 | 8/8 PASS |

Stored (unadjusted) figures for comparison: #366 92.7 / 290.0, #396 98.5 / 307.3, #397 97.4 / 306.3,
#430 111.2 / 328.7 %/yr. Books carry no Sortino (the book engine does not compute one).

**The ranking, restated (no decision taken here).** Return per drawdown = net per year / at-close
drawdown, per stretch.
- Before the lockbox: #438 2.26, **#437 2.15**, #435 2.07, #436 2.03.
- In the lockbox: **#437 11.3**, #436 10.7, #435 9.9, #438 9.7.
- At one common risk (each scaled to #366's pre-lockbox drawdown, $40,854): #438 92.2 / 285.7,
  **#437 87.9 / 292.5**, #435 84.4 / 277.1, #436 82.8 / 273.5 %/yr.
- Reading: FRONTIER #397 (#437) is the most balanced - first in the lockbox, second before it. The NOISE
  #382 slot (#438) makes the most money and the best pre-lockbox ratio, but the deepest drawdowns and the
  weakest lockbox ratio. #396 over #366 now rests on the lockbox alone (it trails #366 before the
  lockbox), as ROLL_AUDIT 4.3 found. #379 (which the audit ranks above #397 on the selection stretch)
  was not re-run here. Adoption (#366 / #396 / #397, and the NOISE slot) stays the owner's call.

### 10j. DIP on ES #432 as a book seat or its own book - #440 / #439 / #441 (2026-09-26)

**What.** The TV chat's pre-registered book test (docs/DIP_ES_CASE.md 3c, commit d491b177), owner GO via
MANAGER. **Information for the owner, not an eligibility pass:** DIP on ES's overfit question is still
unresolved (DIP_ES_CASE.md 4). Baseline = **#436** (#396 on the roll-corrected masters, 10i). DIP legs =
`NQDIP_1_2.py` with the frozen champions of #432 (ES) and #433 (NQ), 5m RTH on the no-adjust master (the
file handles roll seams itself), cost 0 and mult 1 because the file sizes itself and returns dollars. Two
sizes only, fixed in advance: $100k and $50k notional. The runner's results equal the local run to the
dollar; the local run first reproduced stored #436 to the cent.

**The seat rule (pre-set, vs #436 on the same window):** more net than #436 in at least as many full
calendar years (2011-2025) as it nets less, AND higher whole-run net; lockbox drawdown at close within +5 %
(cap $28,881); whole-run drawdown at close not worse than +10 % (cap $48,364). Sortino = daily at-close
book P&L on a $100k account, every weekday counted, times the square root of 252.

| run | book | whole net | ROC %/yr pre / lockbox | whole DD at close / valued daily | lockbox DD at close / valued daily | Sortino pre / lockbox | years more / less than #436 | stretches | seat rule |
|---|---|---|---|---|---|---|---|---|---|
| #436 | baseline | $1,637,053 | 89.1 / 294.4 | $43,967 / $49,855 | $27,506 / $49,855 | 3.96 / 6.25 | - | 8/8 | - |
| **#440** | #436 + DIP on ES $100k | $2,016,359 | 112.1 / 327.2 | **$109,956** / $97,783 | **$30,374** / $53,618 | 4.07 / 6.99 | 13 / 2 | 8/8 | **FAIL** - both drawdown clauses |
| **#439** | #436 + DIP on ES $50k | $1,827,126 | 100.7 / 310.3 | **$76,727** / $69,030 | $27,997 / $51,468 | 4.23 / 6.64 | 13 / 2 | 8/8 | **FAIL** - whole-run drawdown |
| **#441** | DIP on ES $100k + DIP on NQ $100k | $972,102 | 59.9 / 70.5 | $106,050 / $118,999 | $13,110 / $34,841 | 2.32 / 5.14 | - | 8/8 | not gated |

**Reading (no decision taken here).**
- As a seat, DIP on ES adds money in 13 of 15 years (it trails #436 in 2018 and 2022) and lifts Sortino,
  but it more than doubles the whole-run drawdown at full size and adds 75 % at half size. Both seats'
  worst stretch is the February-March 2020 crash (2020-02-26 to 2020-03-27), where DIP on ES loses at the same time as the
  other legs. Neither size passes; full size also breaks the lockbox clause.
- At one common risk (each scaled to #436's pre-lockbox drawdown, $43,967) the seats read 44.8 / 130.8
  (full) and 57.7 / 177.8 (half) %/yr against #436's 89.1 / 294.4: the extra money costs more than its
  share of drawdown.
- As its own book, DIP (ES + NQ) makes 59.9 / 70.5 %/yr, loses money in 2011, 2018 and 2022, and reads
  24.8 / 29.2 %/yr at #436's drawdown. Its daily P&L is uncorrelated with #436 before the lockbox (DIP on
  ES -0.009, DIP on NQ 0.005; DIP on ES vs DIP on NQ 0.327), so it would diversify a second account, but it
  is far weaker than the book per unit of drawdown.
- Same shape as the 2026-09-09 DIP on NQ fifth-seat rejection: DIP's own drawdown is bigger than the
  whole book's. Adoption stays the owner's call; nothing was adopted. Script and logs:
  `C:\EdgeLog\_anatomy_cache\dip432_book\` (`dip432_eval.py`, `verify_runs.py`).

### 10k. Round 60 - one-leg swaps on the roll-corrected #397: #445 / #444 / #446 (2026-09-27)

**What.** MANAGER tasker (2026-09-27): run the next pre-registered backtests in the book lane. Base =
**#437** (#397 on the roll-corrected masters, 10i), its job legs verbatim with ONE leg swapped and every
leg's source pinned. Pre-registration, written before B2/B3 were computed:
`C:\EdgeLog\_anatomy_cache\stage397\PREREG_R60.txt`. The runner equals the local run to the cent on all three.

**The bar for the two NOISE-slot books** (round 58's, re-based on #437): scale the book so its
pre-lockbox drawdown (the worse of at-close and valued daily) equals #437's $41,853. Then it needs (1)
pre ROC >= 1.05 x 88.1, (2) lockbox ROC >= 293.3, (3) lockbox drawdown within +5 % at close (cap $27,188)
and valued daily (cap $52,348), and (4) more net than #437 in >= 10 of the 15 years 2011-2025.

| run | #437 with | ROC %/yr pre / lockbox | pre DD at close / valued daily | lockbox DD at close / valued daily | Sortino pre / lockbox | years more than #437 | bar |
|---|---|---|---|---|---|---|---|
| #437 | (base) | 88.1 / 293.3 | $40,971 / $41,853 | $25,893 / $49,855 | 3.98 / 6.31 | - | - |
| **#445** | TTM = run #428's cell (roll guard, entry cutoff 5) | 87.6 / 295.6 | **$33,567** / $34,449 | $25,893 / $49,855 | 4.02 / 6.37 | 6 | no bar (the TTM chat's leg call) |
| **#444** | NOISE = run #422 (1.75x compression tilt) | 96.4 / 309.8 | $40,971 / $41,853 | **$27,955** / $49,855 | 4.21 / 6.48 | **15** | **MISSES clause 3 only**, by $767 |
| **#446** | NOISE = run #382 (2x tilt) | 100.9 / 314.7 (at scale 0.973: 98.1 / 306.1) | $42,147 / $43,029 | $30,706 / $55,474 | 4.04 / 5.97 | 14 | **MISSES clause 3**, both readings |

**Reading (no decision taken here).**
- **NOISE #422 in the NOISE slot is the same answer as round 58, a little closer.** It needs no scaling:
  it leaves the pre-lockbox drawdown unchanged. It makes more money in all 15 years and lifts Sortino.
  It misses only the lockbox drawdown at close, $27,955 against the $27,188 cap (+8.0 % against +5 %).
  On the unadjusted masters it missed by $1,330. Pre-registered answer: no; it stays an owner call.
- **NOISE #382 misses more clearly.** As traded, its lockbox drawdown is +18.6 % at close and +11.3 %
  valued daily, and it is still over both caps at the scale the bar uses.
- **#445 persists the staged TTM variant** (docs/BOOK_397_ADOPTION_STAGED.md section 5). It removes
  $7,404 of the Feb-Mar 2020 drawdown and adds 2.3 points in the lockbox at the same lockbox drawdown.
  The #428 cutoff was chosen in-sample and missed its own MAR clause, so the leg decision stays with the
  TTM chat.

**Round 60b (same day, TTM inbox #12 + MANAGER inbox #13), pre-registered in the same file before C1-C3 were
computed.** C1 re-bases the NOISE-slot bar on #436 (cap: lockbox drawdown $28,881 at close, $52,348 valued
daily; pre ROC >= 93.6; lockbox ROC >= 294.4; >= 10 of 15 years). C2 and C3 carry the TTM chat's exact leg:
`TTMSQZ_3_0_ES30SSOF2R347.py`, which is the #428 roll-guard cell sized 3 / 4 / 7 whole ES contracts by the
file itself, at weight 1 on the no-adjust master. Its leg net ($358,609.80) equals this chat's own 3 / 4 / 7
re-pricing to the cent.

| run | book | ROC %/yr pre / lockbox | pre DD at close / valued daily | lockbox DD at close / valued daily | Sortino pre / lockbox | years more than its base | bar |
|---|---|---|---|---|---|---|---|
| #436 | base: #396 roll-corrected | 89.1 / 294.4 | $43,967 / $44,849 | $27,506 / $49,855 | 3.96 / 6.25 | - | - |
| **#449** | #436 with NOISE #422 | **97.5 / 310.8** | $43,967 / $44,849 | $27,506 / $49,855 | 4.18 / 6.42 | **15** | **CLEARS all four clauses** |
| #435 | base: #366 roll-corrected | 84.4 / 277.1 | $40,854 / $41,736 | $28,066 / $49,855 | 3.80 / 5.85 | - | - |
| **#448** | #435 with TTM = R347 | 88.8 / 293.8 | $36,562 / $37,444 | $27,506 / $49,855 | 4.01 / 6.25 | 11 | no bar (TTM chat's leg call) |
| #437 | base: #397 roll-corrected | 88.1 / 293.3 | $40,971 / $41,853 | $25,893 / $49,855 | 3.98 / 6.31 | - | - |
| **#450** | #437 with TTM = R347 | 87.8 / 292.7 | $33,567 / $34,449 | $25,893 / $49,855 | 4.03 / 6.31 | 6 | no bar (TTM chat's leg call) |

- **NOISE #422 clears on #396's legs and misses on #397's.** The same swap adds the same $141,652 to the NOISE
  leg in both books. On #396's legs it touches neither worst stretch, so both drawdowns stay put. On #397's
  legs it deepens the lockbox's worst stretch from $25,893 to $27,955. The swap was tried on two bases, and
  only one clears, so read the pass as base-specific rather than a property of #422 alone. Round 58's other
  cautions still apply: it is a size tilt on the same trades, and in the lockbox it sits at the 79th
  percentile of random upsizing.
- **The TTM chat's leg lowers the pre-lockbox drawdown on every base.** The TTM chat traced this to a
  2020-03-17 losing short that the roll-guarded #369 cell takes and the #428 cell does not. On #366's legs it lifts 84.4 / 277.1 to 88.8 /
  293.8. Its entry cutoff was chosen in-sample, so the leg decision stays with the TTM chat.
- **Nothing is adopted.** The open owner questions are now: which book (#366, #396 or #397), which NOISE leg
  (#304 or #422), and which TTM leg (#369 or R347).

### 10l. Round 61 - combined frontier books with ML-sized legs, and DIP on ES #452 as a seat (2026-09-27)

**What.** The owner asked, via MANAGER (#15/#16): take each paper-traded family's frontier leg, raw or
ML-sized, combine the legs by daily P&L valued daily, and read walk-forward and lockbox separately. Every
size is frozen before the lockbox. Custom ML exported the ML legs with raw twins to `C:\EdgeLog\book_legs\`.
This chat built the rest from the engine. Pre-registration and addendum A were written before any combined
result: `C:\EdgeLog\_anatomy_cache\frontier_combo\PREREG_R61.txt`.

**Grid: 18 books.** NOISE #422 raw x ORB {#314 raw, #314 HYBRID DD tree, #257 raw} x ENGU-Q {the book leg
(R2 defaults at 0.783), #335 champion raw, #335 HYBRID DD rf} x TTM {#455 roll-safe 3 / 4 / 7, #368 KEEL x3}.
No NOISE ML legs were exported, so none was tested. The common windows are WF 2016-10-17..2025-06-13
(8.65 years) and LB 2025-08-14..2026-06-24 (0.86 years). The engine-built baselines reproduce #449, #437 and
#435 to the cent.

**The bar** (vs #449): (1) WF ROC at a $30k drawdown >= 1.05 x #449's; (2) WF Sortino >= #449's; (3) lockbox
ROC at the WF-set size >= #449's; (4) lockbox drawdown at that size <= 1.05 x #449's.

| book | WF ROC %/yr as run / at $30k / at $50k | WF DD (valued daily) | WF Sortino | LB ROC as run / at the WF $30k size | LB DD at that size | LB Sortino | bar vs #449 |
|---|---|---|---|---|---|---|---|
| #449 | 155.5 / 104.0 / 173.3 | $44,849 | 4.12 | 295.0 / 197.3 | $30,143 | 4.53 | - |
| #437 | 139.0 / 99.7 / 166.1 | $41,853 | 3.83 | 277.4 / 198.8 | $29,651 | 4.35 | - |
| #435 | 135.0 / 97.0 / 161.7 | $41,736 | 3.70 | 260.7 / 187.4 | $32,983 | 4.05 | - |
| best of 18: NOISE #422 + ORB #257 + ENGU-Q book leg + **TTM #368 KEEL** | 210.0 / **148.3** / 247.2 | $42,475 | 5.24 | 402.9 / 284.6 | **$33,098** | 6.19 | misses (4) |
| **#456** = same with **TTM #455** (best roll-safe, rank 2) | 160.9 / **147.2** / 245.3 | $32,794 | 4.32 | 282.5 / 258.4 | **$42,534** | 4.36 | misses (4) |

The median book of the 18 reads 94.0 at $30k. #456 is the rank-2 book queued as a real BOOK run on the
standard window: 99.1 / 293.1 %/yr, pre-lockbox drawdown $33,264 at close (#449: $43,967), lockbox drawdown
$27,310, 8 of 8 stretches. The runner equals the local run to the cent.

**Reading (no decision taken here).**
- **No combined book beats #449.** Both top books clear the first three clauses and fail the fourth. Sized
  up to #449's walk-forward risk, their lockbox drawdown runs deeper than #449's: +9.8 % for the best book and
  +41 % for #456. The walk-forward drawdown advantage does not carry into the lockbox.
- **The top book's TTM leg is not roll-safe.** #368 KEEL runs on unadjusted prices, and about 14 % of the raw
  #368 leg's walk-forward money is fake roll-day trades ($256,421 unadjusted against $224,924 roll-corrected).
  It carries 36 % of that book's net. Treat #456 as the honest best combination.
- **The ML legs add nothing in the book at matched drawdown.** Each ML leg was swapped for its own raw twin
  inside the best book, reading WF at $30k and then LB:
  - ORB HYBRID DD tree: 137.4 against 145.8, lockbox 283.4 against 284.2.
  - ENGU-Q HYBRID DD rf: 80.8 against 97.3, lockbox 129.4 against 164.9. Custom ML also reports that the
    stored hybrid lockbox overstates a truly frozen gate by 24 %.
  - TTM KEEL: 148.3 against 149.8 in WF. It is higher in the lockbox (284.6 against 256.6), but only on
    11 trades.
- **What #456 is made of.** Share of WF net: NOISE 32 %, ORB 25 %, ENGU-Q 26 %, TTM 17 %. Its worst WF
  drawdown (2022-04-26 to 05-03) is ORB 51 %, ENGU-Q 32 % and NOISE 17 %. Daily correlations: NOISE with ORB
  0.40, ENGU-Q with the others 0.20, TTM with the others 0.02-0.12. Worst day -$22,273 WF and -$21,061 LB;
  worst month -$17,924 WF and -$13,248 LB.
- **DIP, as a comparison only:** DIP on ES #452 alone reads 31.0 %/yr at a $71,941 WF drawdown (Sortino 0.92).
  Added to the best book, it lowers WF ROC at $30k from 148.3 to 87.9.
- **DIP on ES #452 as a seat** (TV's ask; the same test as 10j, vs #436): #453 at $100k reads 121.6 / 318.6 %/yr
  but has a whole-run drawdown of $111,845 against a $48,364 cap, and a lockbox drawdown of $29,536 against
  $28,881. #454 at $50k reads 105.5 / 306.3 with a whole-run drawdown of $77,511. Both FAIL, again in the
  2020 crash. The runner equals local to the cent on both.

Scripts, streams and the full report: `C:\EdgeLog\_anatomy_cache\frontier_combo\` (`combo_eval.py`,
`combo_report.txt`, `combo_results.json`) and `...\dip452_book\`.

**Addendum B - the NOISE sizing legs (MANAGER #17; pre-registered as addendum B before the streams existed).**
Custom ML exported the NOISE legs on the no-adjust 5m tape. NOISE is flat by the close, and its #422 raw twin
matches the engine to $0.63 over 2016-2026. Each leg was swapped into #456's legs (ORB #257, the ENGU-Q book
leg, TTM #455) and into the ORB #314 base. Common windows: WF 2016-07-13..2025-06-13 and LB
2025-08-14..2026-06-29.

| #456's legs with NOISE = | WF ROC as run / at $30k | WF DD | WF Sortino | LB ROC as run / at the WF $30k size | LB DD as run / at that size | vs #449 | vs #456 |
|---|---|---|---|---|---|---|---|
| (#449 itself) | 151.7 / 101.5 | $44,849 | 4.14 | 293.3 / 196.2 | $49,855 / $33,349 | - | - |
| #422 raw (= #456) | 157.0 / 143.6 | $32,794 | 4.34 | 280.9 / 256.9 | $49,475 / $45,259 | misses (4) | - |
| **#422 + fixed tilts** | **178.1 / 158.1** | $33,792 | **4.80** | **315.1** / 279.8 | **$49,475** / $43,923 | misses (4) | **BEATS** |
| #422 + KEEL 7-seed | 189.7 / 168.0 | $33,872 | 4.81 | 300.5 / 266.1 | $49,162 / $43,543 | misses (4) | BEATS |
| #382 + fixed tilts | 186.9 / 148.3 | $37,809 | 4.72 | 323.5 / 256.7 | $56,494 / $44,826 | misses (4) | misses (1)(3) |

- **The fixed tilts add, and so does KEEL on #456's legs.** Each was read against its own raw twin at matched
  drawdown, WF at $30k then LB:
  - #422 fixed tilts: 158.1 against 143.6, lockbox 279.8 against 256.9 on #456's legs, and they add on the
    ORB #314 base too.
  - #422 KEEL 7-seed: 168.0 against 143.6 on #456's legs. It adds NOTHING on the ORB #314 base (132.0 against
    140.5), so its gain is base-specific.
  - #382 fixed tilts against #382 raw: 148.3 against 125.8.
- **Against #449, every NOISE swap still misses clause 4 at the walk-forward-matched size.** #449's 2020
  walk-forward drawdown makes its matched size small; a book with a smaller walk-forward drawdown is sized up,
  and its lockbox drawdown then runs deeper.
- **At OWN size (k = 1), #456's legs with the #422 fixed tilts beat #449 on every read.**
  - Walk-forward: 178.1 against 151.7 %/yr, drawdown $33,792 against $44,849, Sortino 4.80 against 4.14.
  - Lockbox: 315.1 against 293.3 %/yr, drawdown $49,475 against $49,855, Sortino 4.74 against 4.54.
  - #456 alone at own size also passes clause 4 ($49,475 against $49,855), but its lockbox return is lower
    (280.9 against 293.3).
  - Caveat: the Friday and compression tilts were found on pre-lockbox data, so part of the WF gain is
    in-sample. The lockbox (+12 % on #456 at the same lockbox drawdown) is the out-of-sample read.

**Persisted as run #457 (MANAGER GO, a test, not an adoption).** #456's legs with the NOISE #422 leg
carrying the paper compression gate. The gate settings are compression 1.5x, Friday 1.5x, half size
before Fed statements, and a cap of 3; they are the exact settings of Custom ML's export tool. The engine
leg equals Custom ML's stream ($775,876.48 against $775,876.24; no day off by more than $0.05), and the
combination figures above reproduce exactly. The runner equals the local run to the cent, 8 of 8 stretches.

| Standard window | #457 | #449 |
|---|---|---|
| ROC %/yr, pre-lockbox / lockbox | 112.3 / 322.9 | 97.5 / 310.8 |
| Drawdown, pre-lockbox, at close / valued daily | $33,264 / $33,792 | $43,967 / $44,849 |
| Drawdown, lockbox, at close / valued daily | **$30,051** / $49,475 | $27,506 / $49,855 |

The lockbox drawdown at close is 9 % deeper than #449's; valued daily it is slightly smaller.

**Addendum C - lockbox concentration (MANAGER #20; clause 5 pre-registered before the numbers).**
The house top-10 rule is scaled to one lockbox year of sixteen, so k = 1: remove each book's single largest
lockbox trade, from the at-close series and from the valued-daily marks. In every book it is the same trade:
**ENGU-Q, held 2026-04-07 to 2026-05-12, +$91,152**, which is 28-33 % of each book's lockbox net. Every ENGU-Q
leg here is the roll-corrected paper leg, valued daily.

| book | lockbox ROC %/yr as run / without it | lockbox DD at close as run / without it | lockbox DD valued daily | lockbox Sortino as run / without it | without it, at the WF-set $30k size |
|---|---|---|---|---|---|
| #435 (= #366) | 277.1 / 185.9 | $28,066 / $36,875 | $49,855 | 5.85 / 3.91 | 133.6 |
| #437 (= #397) | 293.3 / 202.1 | $25,893 / $32,619 | $49,855 | 6.31 / 4.33 | 144.9 |
| #449 | 310.8 / 219.6 | $27,506 / $36,315 | $49,855 | 6.42 / 4.52 | 146.9 |
| #456 | 293.1 / 201.9 | $27,310 / $35,484 | $49,475 | 6.06 / 4.15 | 184.7 |
| #457 | 322.9 / 231.7 | $30,051 / $37,682 | $49,475 | 6.28 / 4.48 | 205.7 |

- **Clause 5** (the candidate's lockbox ROC without its top trade, at its WF-set size, is at least the
  reference's):
  - vs #449: #456 and #457 PASS; #437 FAILS (144.9 against 146.9).
  - vs #435: #437, #449, #456 and #457 all pass.
- **The valued-daily lockbox drawdown does not move** without the trade. It is set by the June 2026 stretch,
  after the trade closed. The at-close drawdown deepens by about $7-9k, because the win had been covering
  losses.
- **#457's lockbox gain from the NOISE tilts is not a clean read.** The tilts were chosen reading #243/#304's
  lockbox. It stays flagged until Custom ML's re-score on the clean weeks lands.

### 10as. Q34 ENGU-Q TIMING SPLIT: an RTH-only executor that holds overnight keeps the leg's edge within the noise; the dollars sit in the exits (2026-10-09, a report)

**What it is.**
- MANAGER #139 item 2, following 10an (Q31), where WHEN ENGU-Q holds was worth about +12 ROC points standalone. The owner GO'd ENGU-Q holding
  overnight on the Webull paper book, so the question is what part of WHEN survives an executor that only trades in regular hours.
- Walk-forward only (the S1 stretch), lockbox unread, no adoption. Valuation is Q31's: NQ 1m ETH master, book UTC days, 1.0 NQ while on.
- Run before main on branch prereg/frontier-enguqtiming-1009 (b4058c1e). Note docs/PREDATA_frontier_enguqtiming_2026-10-09.txt, LF f129c9ed;
  script tools/rocfrontier/q34_enguq_timing.py, LF 5c4fda01; both hashes matched at the start.
- **Part A** splits WHEN in two:
  - ENTRY timing: an entry-only twin (the leg's own entry bars, held for a duration shuffled among its walk-forward trades and cut at the
    next entry; 200 shuffles) against the always-on twin.
  - STOP-EXIT timing: the in-position twin (the real exits at bar closes) against the entry-only twin.
- **Part B** re-does the chain for the RTH executor. A signal inside regular hours fills at that bar's close. Any other signal fills at the
  next regular session's 09:30 open, gap included. Positions may be held overnight. An entry and exit that land on the same open cancel.

**Results (standalone ROC@30k, $ a year, DD5).**

| Line | ROC@30k | $ a year | DD5 |
|---|---|---|---|
| Always-on twin (0.605 NQ) | 12.29 | $25,376 | $40,915 (one episode) |
| Entry-only twin | 22.28 | $15,496 | $18,320 |
| In-position twin | 24.46 | $40,876 | $32,351 (one episode) |
| ENGU-Q (the leg) | 26.09 | $42,266 | $31,177 (one episode) |
| RTH executor: entry-only twin | 12.63 | $13,195 | $23,621 (one episode) |
| RTH executor: the leg | 24.57 | $38,587 | $35,511 (one episode) |

- **Power first.** Leg vs executor: the line is 12.69 ROC points. Entry-only vs in-position (the exit part): 20.06. Added for disclosure:
  the entry part 13.81, the delay alone 12.35.
- **The executor:**
  - Leg vs executor: +1.52 ROC points against a line of 12.69, **not distinguishable at this resolution**.
  - The executor keeps 91% of the leg's dollars a year.
  - As a seat on L: 116.81 vs 121.06, DD5 $34,473 vs $34,392.
- **The split:**
  - ENTRY timing is +9.99 ROC points (72% of the leg's +13.80 lead over always-on), and STOP-EXIT timing is +2.18 (16%). Both are under
    their lines, so the split is not resolved.
  - In dollars the picture flips. Entries alone earn $9,880 a year **less** than holding always-on; their ROC gain is a smaller drawdown
    (the entry-only twin is in the market less). The exits carry the dollars: +$25,380 a year, ahead in 8 of 9 years.
- **Under the executor:**
  - The entry part's edge disappears (12.63 vs always-on 12.29).
  - The exit part carries everything (+11.94 points, keeps 100% of its dollars): by the pre-set word, exit timing SURVIVES. Entry timing has
    no positive dollars to survive.
- **Counts on the walk-forward:** 1,194 trades.
  - 672 entries and 586 exits are signalled outside regular hours.
  - 370 trades (31%) never happen under the executor: their entry and exit both land before the same open.
- **Where the executor pays:** the July 2024 to June 2025 year is $50,952 worse. Its January to April 2025 drawdown is $43,804 against the
  leg's $20,266, the overnight gaps. Its February to May 2024 drawdown is also deeper ($47,108 vs $32,456). In 5 of 9 years the executor
  does better.

**Read.**
- What survives an RTH-only, overnight-hold executor is all of WHEN, within the noise: its leg leads always-on by 12.28 points against the
  leg's in-position 12.17.
- It survives because positions are held overnight. The overnight signals become next-morning fills, and the exits still carry the dollars.
- The split between entry and exit timing cannot be resolved on 9 years of data. Do not tune either half on it.
- The paper book's overnight-hold GO stands on this evidence. No change proposed.
- **Could fool us:** NQ bar opens stand in for QQQ prints; the duration shuffle keeps the length distribution but not its link to market
  state; 2016-25 favours holding.

### 10ar. The harm monitor is built (tools/harm_monitor.py) - its first read trips NOISE's A1 on July; ENGU-Q reads from 08-07 (2026-10-09)

**What it is.** MANAGER #140 OK'd 10aq and said build it. tools/harm_monitor.py is the weekly read.
- It re-runs #463's four legs on #463's pinned masters through augur_engine.book, the same path the bands came from. It reads no Firestore.
- It does not use the runner's paper shadow, which runs ORB and TTM on the no-adjust master rather than #463's.
- Output: one post to MANAGER's inbox each Monday (trips first, then each leg's distance to A1 / A2 in plain words) and a copy under
  C:\EdgeLog\harm_monitor. There is no phone push and no change to any leg.
- Tests (tests/test_harm_monitor.py): a planted shortfall and a planted drawdown trip; an on-pace path and a WF-like random path do not.
- The Monday 06:10 MST trigger is drafted (bookq/EdgeLog_FRONTIER_harm_monitor.xml), not registered: MANAGER first, then the owner.

**Three build choices that 10aq did not spell out.**
- **Rows** are the book's calendar, as on the walk-forward: every regular session plus any day a leg has $, zero where a leg is flat.
  The record ends at the last session before the run day that every RTH master holds.
- **A1 is checked every 6th row from the start**, exactly as calibrated. A trip stays a trip.
- **ENGU-Q and the #463 total read from 2026-08-07, not 07-01.**
  - The NQ 1m ETH master has no bars from 07-01 to 08-05 (the known hole; free sources keep 7 days of 1m).
  - The engine carries ENGU-Q's 06-29 trade across the hole and books its whole loss, -$20,406, on 08-06.
  - 08-07 is the first day ENGU-Q starts flat after that.
  - From now on, a gap of two or more sessions in any leg's master pauses that leg (and the total) instead of reading it.

**First read (2026-10-09, data through 10-08).**

| Leg | Days | Forward net | Against the backtest's pace | A2 drawdown (deepest / alarm) |
|---|---|---|---|---|
| ORB | 75 | $15,186 | $6,584 ahead | $13,886 / $48,721 |
| TTM (x3) | 75 | -$2,309 | $6,088 behind (27% of the way to A1) | $2,309 / $35,583 |
| NOISE | 75 | $10,509 | **A1 TRIPPED at the 07-17 check** (-2.71 vs -2.44); now $2,276 behind | $13,932 / $23,068 |
| ENGU-Q | 49 (from 08-07) | $19,775 | $12,682 ahead | $12,772 / $63,754 |
| #463 | 49 (from 08-07) | $18,394 | $5,141 behind (8%) | $22,046 / $62,640 |

- ORB's big-day watch line: 3 days above $5,898 against about 0.8 expected. TTM: 0 against 0.8.
- **NOISE.**
  - Ten losing days from 07-01 to 07-24 put it $13.7k behind pace by the 07-17 check, past its line.
  - It made the money back from 07-29 to 08-04 (+$23k) and is now near pace.
  - By the frozen rule that is a trip: worse than the backtested leg does 2.5% of the time. It is harm shown, not decay proven. Reported to
    MANAGER the same day (#805). Nothing changes unless the owner decides.
- **Checked.**
  - From 08-13, the engine's NOISE days equal the runner's paper shadow (NOISE #422, same master) to the dollar, apart from small
    differences in the last week where recent bars were restated. That took 1 Firestore read, by document id.
  - The paper shadow has no NOISE #422 rows before 08-13, so the July losses rest on the complete 5m master alone.

### 10aq. Q33 FORWARD HARM-MONITOR SPEC for #463's legs, weighted by decay exposure: ORB and TTM first (2026-10-09, a spec)

**What it is.** MANAGER #139 item 1. It is a spec only: nothing is built or read forward yet. It turns 10ao's decay ranking into the weekly
check on each leg's forward record.
- The lockbox stays spent, and no candidate is passed or failed by these reads.
- The book lines' registered paired stops (10y) are unchanged.
- Alarm lines and power come from each leg's walk-forward daily $ (marked to market, book days; bookq/q33_harm_spec.py, a stationary block
  bootstrap with mean block 20, 2,000 three-year paths). No forward data was read to set them.

**What is read each week (Monday, before the open), in this order: ORB, TTM, then NOISE, ENGU-Q, and #463 as a whole.**
- **The record:** each leg's forward daily $ at #463's size, from 2026-07-01 (the first day after the backtests' last bar).
- **Two cuts of that record:**
  - DECAY reads the engine shadow (the runner's daily re-run on new bars): the strategy exactly as backtested, on new data.
  - EXECUTION reads the paper fills of record (Webull paper; NinjaTrader demo where a leg trades there) minus the shadow.
  - Only DECAY is judged against the bands below. The execution gap goes to the paper lanes' reconcile as it does now.
- **A1, SHORTFALL:** the forward sum of (each day's $ minus the walk-forward daily mean), against minus c x sd x sqrt(days).
  - c is set so a leg exactly as backtested crosses within 36 months only 2.5% of the time.
- **A2, DRAWDOWN:** the forward running drawdown against the depth a three-year path of the backtested leg exceeds only 2.5% of the time.
- **ORB and TTM only, a WATCH line (never an alarm):** the forward count of "big days" (above the leg's own walk-forward 99th percentile; about
  3 a year).
  - 81% of ORB's walk-forward net and 166% of TTM's come from those days (10ao), so a year without them is the earliest hint of decay.
  - It has no power to decide anything, so it is only shown.

| Leg | WF Sharpe a year | A1 line c | A2 drawdown alarm (WF worst) | Big-day threshold |
|---|---|---|---|---|
| ORB | 1.14 | 2.53 | $48,721 ($29,142) | $5,898 |
| TTM (x3) | 0.73 | 2.20 | $35,583 ($17,730) | $3,032 |
| NOISE | 2.00 | 2.44 | $23,068 ($17,591) | - |
| ENGU-Q | 1.09 | 2.40 | $63,754 ($48,599) | - |
| #463 | 1.98 | 2.23 | $62,640 ($44,849) | - |

**When an alarm trips.**
- FRONTIER reports to MANAGER the same day: the leg, which alarm, the forward record against its band, and the execution gap beside it.
  MANAGER takes it to the owner.
- Never an automatic change. The leg keeps trading as it is until the owner decides.
- A trip means "the forward record is worse than the backtested leg produces 2.5% of the time". It is evidence of harm, not proof of
  decay.
- False alarms: a leg exactly as backtested trips A1 or A2 within 36 months about 4% of the time (the two alarms overlap). Across the five
  monitored lines, expect one false alarm somewhere in 36 months about one time in five.

**Power: how much forward data before it can say anything** (the chance of an alarm when the leg has changed; bootstrap of its own days):

| Leg | Edge cut to 55% (the decay paper's average): by 12 / 24 / 36 months | Edge gone: by 12 / 24 / 36 months (median) | Losing as fast as it used to win: median |
|---|---|---|---|
| ORB | 3% / 10% / 17% | 13% / 41% / 63% (29 months) | 10 months |
| TTM (x3) | 3% / 6% / 12% | 7% / 22% / 40% (beyond 36) | 17 months |
| NOISE | 14% / 33% / 47% | 61% / 90% / 98% (10 months) | 3 months |
| ENGU-Q | 5% / 9% / 14% | 14% / 33% / 51% (35 months) | 11 months |
| #463 | 13% / 30% / 47% | 63% / 91% / 98% (9 months) | 3 months |

**Read.**
- **What the monitor can promise:** a leg that starts LOSING is caught within a year (TTM within about 17 months).
- **What it cannot see:** a leg whose edge merely halves is invisible within 36 months for every leg.
- **Where silent decay can hide:** NOISE and the book show an edge that has gone to zero within about 10 months. ORB, ENGU-Q and above all
  TTM can lose their whole edge and still not trip in 36 months a third to a half of the time (ORB 37%, ENGU-Q 49%, TTM 60%). Their low Sharpe and their dependence on a few big
  days are why.
- **That is the decay weighting:** ORB and TTM are read first, carry the big-day watch line, and a quiet 36 months for them is stated in
  advance as "not shown", never as "fine".
- **Next, if MANAGER approves:** FRONTIER builds the weekly read on the runner's shadow (a small script and a RUNBOARD note line per leg).

### 10ap. Q30 EFFECTIVE TRIALS: the book looks are about 2 independent ideas, not 71; #485's 307 settings are about 30 (2026-10-09, a report)

**What it is.** MANAGER #128 item 1, from the owner's reading list: Lopez de Prado & Lewis (2019) for the count, and Bailey & Lopez de Prado
(2014) for the Deflated Sharpe.
- **The question:** how many INDEPENDENT trials are the book-look family and one 900-trial Auto-Validate? Then restate #463's WF Deflated
  Sharpe with that count beside the raw count.
- **How it ran:** a report, WF only, lockbox unread. MANAGER reviewed the note (#133; TV was named second reviewer and posted nothing by the
  deadline). It ran before main from branch prereg/frontier-efftrials-1009 (note LF 3c02ff35...; script tools/rocfrontier/q30_efftrials.py,
  LF eb0e7bb5... after one disclosed fix to #485's validity count, made before any number).
- **The method (one choice each):** daily series; distance sqrt((1 - rho) / 2); ONC as published (k-means at every k, silhouette t-stat
  quality, recursion); E = the number of clusters.
- **The looks:** 39 of LOOKS r1's 71 counted looks could be rebuilt as daily series on the S1 WF, marked to market.
  - 27 are saved book runs; 12 are arithmetic on #463's records (sizing rules, the agreement tilt, the MDL refs).
  - The other 32 (round 58's ML-gated looks and one-offs) enter as a band: E_low = E(39), E_high = E(39) + 32.
  - 15 of the 27 saved runs (09-26/27) rebuild $100-146k lower than stored. The cause is the TTM entry-bar-stop fix (b3242e77, 09-27
    14:50), which came after them; it is one leg's level and leaves the clusters unchanged.
- **#485:** all 307 saved settings re-run on its tuning window (2016-01-04..2025-06-29). The run's own count of 243 could not be rebuilt
  as a subset (every saved setting has 687+ in-sample trades), so the family is all 307, with N = 243 printed beside it.

| Family | Series | Median correlation | E (ONC) | Second seed |
|---|---|---|---|---|
| Book looks (rebuildable) | 39 of 71 | 0.951 | 2 (38 #463-type books + the DIP-only book #441) | 2 |
| #485 settings | 307 | 0.840 | 30 (independence ratio 0.098; the champion's cluster holds 9) | 33 |

| Deflated Sharpe | N | Expected max of N trials (a year) | DSR |
|---|---|---|---|
| #463 WF (Sharpe 1.84 a year, 2,626 days) | 2 (E_low) | 0.37 | 1.000 |
| | 34 (E_high) | 1.52 | 0.889 |
| | 71 (raw) | 1.72 | 0.677 |
| #485 champion (Sharpe 1.65, tuning window) | 30 (E) | 0.49 | 0.9999 |
| | 243 (the run's count) | 0.67 | 0.9995 |
| | 307 (all saved) | 0.69 | 0.9993 |

**Read.**
- **The raw look count overstates the trial burden.** The rebuildable looks are near copies of one book (correlation 0.95). Even at the
  harsh bound, where every un-rebuildable look counts as independent (N = 34), #463's WF Sharpe clears the luck bar (DSR 0.889). At the raw
  71 it reads 0.677.
- **Caveat:** the variance of trial Sharpes behind the expected maximum rests on only two clusters.
- **#485's tuning searched about 30 ideas, not 307 or 900:** the champion sits among 9 near-twins. Its Deflated Sharpe is unaffected
  (0.999+ at every N).
- **Per the note, this is EVIDENCE for a family-level luck bar (RESEARCH.md item 7), not a change.** No threshold moves: the 71-look chance
  bands (10z) and the 900-trial budget stand.

### 10ao. Q32 DECAY NOTE: what Falck, Rej & Thesmar's decay features predict for NOISE and ORB (2026-10-09, a short note)

**What it is.** MANAGER #128 item 3, from the owner's reading list. It is a note, not a test: no forward line, no haircut applied to any
number. The paper is "Why and how systematic strategies decay" (Quantitative Finance 22(11), 2022; arXiv 2105.01380).
- **The paper's sample:** 72 published US long-short equity factors.
- **Average decay:** out-of-sample Sharpe is about 0.57 x in-sample (median ratio 0.55).
- **What predicts more decay:**
  - a later publication date: the ratio falls 0.05 a year, and this alone explains 30% of the spread;
  - a signal that needs more than two operations to compute: -0.49 on the ratio;
  - an in-sample Sharpe that leans on a few observations: -0.21 per SD (and -0.16 per SD for subsample instability).
- **What barely matters:** arbitrage proxies (larger, more liquid names decay more) are marginal once the others are in.

**The features, applied** (outlier measures computed on the WF, each leg's marked-to-market daily $; bookq/q32_decay_features.py):

| Leg | WF Sharpe a year | Sharpe without its best 1% of days (27) | Best 1% of days, share of net | > 2 operations |
|---|---|---|---|---|
| NOISE | 1.86 | 1.15 (-0.70) | 49% | yes |
| ORB | 1.06 | 0.26 (-0.80) | 81% | yes |
| ENGU-Q | 1.01 | 0.32 (-0.69) | 73% | yes |
| TTM (x3) | 0.68 | -1.03 (-1.71) | 166% | yes |
| #463 | 1.84 | 1.24 (-0.60) | 46% | - |

- **Complexity:** both NOISE and ORB fall in the paper's riskier "more than two operations" group.
  - NOISE: a band built from time-of-day moves, a VWAP exit, and volatility and day-type filters.
  - ORB: the opening range, a buffer, a pace filter, a close confirm, a stop and a breakeven.
- **Recency:** both start from public templates (Zarattini et al., 2023-24) tuned in-house in 2025-26. The paper's yearly trend was fitted
  on factors published 1970s-2010 and cannot be extrapolated, but its direction says expect at least the average haircut.
- **Liquidity:** NQ futures are among the most liquid markets, so trading cost does not shelter the edge from arbitrage.
- **Dependence on a few days:** this is the feature that separates the legs.
  - NOISE earns half its net on its best 1% of days and keeps a 1.15 Sharpe without them.
  - ORB earns 81% there and keeps 0.26.
  - TTM is negative without its best 1%.
- **The paper's subsample-instability measure does not separate daily series** (0.08-0.10 for every leg), so it is not used.

**Read.**
- **On the paper's features, ORB is the more decay-exposed of the two, and NOISE the less** (highest Sharpe, least dependence on a few days).
  TTM is the most exposed leg of all on this one measure.
- **Where the haircut applies:** the paper's discount runs from IN-SAMPLE (where a factor was chosen) to out-of-sample. Our WF figures are
  already walk-forward (post-selection), so the 0.55 ratio belongs to the tuning figures, not to WF.
- **The decay the paper cannot price** is the next step, WF to live (arbitrage and regime). The book's one lockbox year showed none (LB 155.5
  vs WF 93.8), but that year is spent.
- No change. It feeds the forward harm monitors (10u): if a leg decays, ORB's and TTM's forward reads should show it first.

### 10an. Q31 DRIFT TWIN for ENGU-Q: its seat leads a constant-exposure NQ holding by 24.7 ROC points on L - not distinguishable at this resolution (2026-10-09, a report)

**What it is.** MANAGER #128 item 2, from the owner's reading list (Huang, Li, Wang & Zhou 2020, "Time-series momentum: is it there?").
- **The question:** does ENGU-Q #335's seat add anything over simply holding NQ at the SAME average exposure? If it does, is the gain WHEN it
  holds or HOW it trades?
- **How it ran:** a report, walk-forward on the S1 line's stretch, lockbox unread. The pre-data note was reviewed by MANAGER (#130) and by
  ENGUQ (#131 / #132, four edits folded) and ran before main from branch prereg/frontier-drifttwin-1009 (note LF 06c3f4fc...; script
  tools/rocfrontier/q31_drifttwin.py).
- **The facts behind the twins (positions only):** ENGU-Q is long-only, one NQ contract while on, and in the market on 60.5% of WF bars.
  - Its time-average position is 0.605 NQ.
  - On days it is fully held, its beta is 0.982 (ENGUQ, R2 0.962).
- **The rows:** each is valued like the leg's own daily curve (NQ 1m ETH back-adjusted master, book UTC days, rolls from
  tools/data/rolls_NQ.csv).
  - The always-on twin holds 0.605 NQ all the time.
  - The in-position twin holds 1.0 NQ on exactly the bars the leg holds.
  - Always-on to in-position isolates WHEN; in-position to the leg isolates HOW (fills and exits).
- **Power first:** the minimum detectable lead (50% line) is 33.4 points for L vs L', 19.9 for the leg vs the always-on twin, and 2.8 for the
  leg vs the in-position twin.

| Line (WF 2016-07..2025-06) | ROC@30k | DD5 | Worst DD | Sortino | $ a year | $ on R |
|---|---|---|---|---|---|---|
| ENGU-Q (the leg) | 26.09 | $31,177 (one episode) | $48,599 | 1.680 | $42,266 | -$360,558 |
| Always-on twin, 0.605 NQ | 12.29 | $40,915 (one episode) | $61,925 | 0.977 | $25,376 | -$197,969 |
| In-position twin, 1.0 NQ on the leg's bars | 24.46 | $32,351 (one episode) | $50,125 | 1.603 | $40,876 | -$362,270 |
| L (ENGU-Q in) | 121.06 | $34,392 | $36,526 | 3.926 | $147,395 | -$887,447 |
| L' = L with the always-on twin in ENGU-Q's place | 96.41 | $34,443 | $40,610 | 3.907 | $130,506 | -$724,859 |
| L'' = L with the in-position twin in its place | 117.67 | $34,723 | $37,225 | 3.874 | $146,005 | -$889,159 |
| L without ENGU-Q (10ak) | 82.04 | $29,208 (one episode) | $38,444 | 3.935 | $105,129 | -$526,890 |

**The read (pre-set wording).**
- **Not distinguishable at this resolution.** L - L' = +24.65 ROC points, against a minimum detectable lead of 33.41. The leg alone leads
  the always-on twin by +13.8, against an MDE of 19.9.
- **The decomposition:**
  - WHEN the leg holds is worth about +12 points standalone (+$15.5k a year, always-on to in-position). Part of that is the trailing stop
    getting out during declines, so it is timing, but not proof of skill at entry.
  - HOW it trades (fills against the bar closes) adds +1.6 points (+$1.4k a year), ahead of the in-position twin in 8 of 9 years.
  - Gross of costs, the leg reads 27.71 (its ~1,194 WF round trips cost ~$2.1k a year; the twin's rolls cost ~$35).
- **Where the timing pays:** the leg sat out the always-on twin's two worst episodes (2021-11..2022-12, $61.9k; 2025-02..04, $58.8k). Its
  own worst is spring 2022 ($48.6k, one episode).
- **On R the twin loses LESS** (-$198k vs the leg's -$361k), so the leg's seat value is a smaller worst drawdown and more dollars a year,
  not R money.
- No weight change, no adoption, no forward line. Book changes are the owner's, and the lockbox is spent (10y / 10z).

### 10am. Q29 CALMTAPE r1: long ES held only on a calm uptrend FAILS against buy-and-hold at the same exposure (2026-10-09, WF, Stage A)

**What it is.** The one shape Q28's map (10al) shortlisted: a long ES leg held only when the tape is calm and trending up, flat otherwise,
read as a seat on the S1 line. It is walk-forward only, with the lockbox unread, and it ran before main from branch
prereg/frontier-calmtape-1009 (prereg LF sha256 01da6b00...; harness tools/rocfrontier/r30_calmtape.py, LF d7feea47...; the power line was
committed first, at 11c9ad4b). Reviews: MANAGER #125 (the bar) and #126 (2 edits, folded before any number).
- **The legs:** CT1 holds 1 MES unit when VIX <= 16 and ES is above its 200-session mean. CT2 holds min(2, 16 / VIX) units on every uptrend
  day.
- **Timing (#126):** the state comes from day t's closes (ES's 16:00 print, the CBOE VIX close); the fill is day t+1's 09:30 open. VIX rows
  on CME-holiday sessions are dropped (23 rows).
- **Costs:** $2.50 a side, and two sides a unit on each roll.
- **The bar (#125):** each leg must beat buy-and-hold ES at the SAME average exposure:
  - (i) its ROC lead over the twin above the family null's p95 = 5.49 points. The null is random 20-session hold blocks with the leg's own
    count; the statistic is the max over both legs.
  - (ii) more dollars on R than the twin, also with the leg's best R episode taken out of both.
  - (iii) at least 6 of 9 years positive, and positive without its best 1% of days.

| Line (WF 2016-07..2025-06, per MES unit) | ROC@30k | DD5 | Worst DD | Sortino | $ a year |
|---|---|---|---|---|---|
| CT1 (VIX <= 16 and uptrend, 1 unit) | 4.29 | $1,963 (one episode) | $4,292 | 0.65 | $614 |
| Twin, buy-and-hold at 0.443 units | 9.85 | $2,068 | $2,686 | 0.81 | $882 |
| CT2 (uptrend, 16 / VIX units) | 10.75 | $2,663 (one episode) | $3,632 | 0.86 | $1,302 |
| Twin, buy-and-hold at 0.845 units | 9.85 | $3,941 | $5,118 | 0.81 | $1,680 |

- **CT1: FAIL.** Its lead is -5.56 against the 5.49 bar. It is negative without its best 1% of days, and positive in 8 of 9 years.
- **CT2: FAIL.** Its lead is +0.91 against the 5.49 bar. It passes (ii) and (iii): 7 of 9 years positive, +$2,843 without its best 1%.
- **On R, neither leg earns.** Both lose on the line's drawdown days (CT1 -$1,016, CT2 -$7,162), just less than their twins (-$6,703 /
  -$12,774). Bar (ii) passes only because long ES itself loses on R.
- **The halves:**
  - CT1: 15.1 vs its twin's 9.6 in 2016-07..2020-12, then 3.6 vs 10.6 in 2021-01..2025-06.
  - CT1's worst year is 2024-25 (-$3,224): the calm filter was on into the August and December 2024 drops.
  - CT2: 15.6 vs 9.6, then 11.6 vs 10.6.
- **Seat read (report only; no candidate):**
  - CT1 at share 0.25: L + cX = 123.72 / DD5 $34,860 / Sortino 3.912 (L: 121.06 / $34,392 / 3.926).
  - CT2 at share 0.25: 114.02 / $36,023.

**Read.**
- **The calm tape is cheap to hold for a reason.** Equity days in that state pay little, and the turn from calm to stress gives no warning.
  CT1's worst days (2024-12-18, 2024-07-24, 2024-09-03) all started in the calm state.
- **The trend filter alone is not an edge here.** It sits out the downtrends, but buy-and-hold at the same average exposure earns as much
  or more per unit of drawdown. CT2's +0.91 lies well inside what random 20-session holding gives.
- This agrees with VRPES (2.103, VIX-level timing loses to always-long) and with Cederburg et al. (2020: volatility-managed exposure fails
  in real time).
- **The calm-tape line is CLOSED:** no NQ cell, no third threshold. The book's weak state (10al) stays unfilled with the data we hold.

### 10al. Q28 R ANATOMY r1: the S1 line's drawdown days, by market state - the book harvests volatility and is weakest on a calm tape (2026-10-08, a map)

**What it is.** A map, not a strategy: it runs nothing, scores no candidate and adds no looks. It is walk-forward only, and it ran before main
from branch prereg/frontier-ranatomy-1008 (prereg LF sha256 8972ad42...; script tools/rocfrontier/r29_ranatomy.py).
- **The days:** each of #463's WF days is classed by a state known at that day's open, built from closes strictly before the day.
- **The four states:**
  - ES trend: the prior close against its 200-session mean (roll-corrected ES 5m RTH master).
  - VIX level, in WF terciles (14.3 / 19.8).
  - VIX / VIX3M: inverted when the ratio is at or above 1.
  - Scheduled macro day: FOMC, then CPI, then NFP.
- **What is summed:** L's dollars, and each leg's, on R (the line's 45 episodes / 762 days) and on all days.
- **Checks:** parity was checked first (121.06, 45 / 762), and the legs plus 0.264 x RES sum to L to the cent.

| State | Days (R) | L on R | L on all days | L per day, all days | Worst leg on R |
|---|---|---|---|---|---|
| ES up (above its 200-session mean) | 2,113 (621) | -$625,718 | +$812,372 | +$384 | ENGU-Q -$239,878 |
| ES down | 513 (141) | -$261,729 | +$513,279 | +$1,001 | ENGU-Q -$120,680 |
| VIX low (<= 14.3) | 907 (303) | -$157,658 | +$237,356 | +$262 | ENGU-Q -$45,821 |
| VIX mid | 869 (235) | -$292,367 | +$367,755 | +$423 | ENGU-Q -$124,163 |
| VIX high (> 19.8) | 850 (224) | -$437,423 | +$720,540 | +$848 | ENGU-Q -$190,574 |
| VIX / VIX3M inverted | 191 (43) | -$96,200 | +$212,324 | +$1,112 | ENGU-Q -$46,036 |
| FOMC days | 71 (21) | -$59,055 | +$24,104 | +$339 | NOISE -$22,164 |
| CPI days | 102 (28) | -$48,187 | +$61,041 | +$598 | ENGU-Q -$43,415 |
| NFP days | 108 (29) | -$47,496 | +$90,152 | +$835 | ORB -$17,207 |

Without the March 2020 episode the shapes hold. Of the inverted state's 43 R days, 19 are that episode. Per-leg tables, with and without it,
are in C:\EdgeLog\_anatomy_cache\rocfrontier\ranatomy_r1\ranatomy.json.

**Read.**
- **The book is a volatility harvester.** Per day it earns most when the tape is stressed: in downtrends (+$1,001), at high VIX (+$848) and
  with the term structure inverted (+$1,112). Its drawdown days in those states are large but are repaid within the same state.
  - That is why long-volatility and inversion hedges (10w, Q12 / Q13) failed: they pay where the book already earns.
  - The inverted state carries only 11% of R's losses.
- **Its weak state is the calm tape.** At low VIX the book makes only +$262 a day; a third of those days are drawdown days, and 81% of all
  R days fall in uptrends. The grind happens in quiet bull markets.
- **Macro days are not where R lives.** ORB and NOISE lose on FOMC days, but only about $1,200 a year together, so a stand-down is not
  worth a prereg.
- **The shortlist (judgement; each still needs its own prereg, power line and Stage A):** a leg that EARNS ON A CALM, LOW-VIX UPTREND - for
  example volatility-managed long index exposure (Moreira-Muir 2017), held when VIX is low and the trend is up and cut as VIX rises - is
  the one shape the map says the book lacks. Its risk is the turn from calm to stress, which is exactly where the book already earns. A
  crisis hedge is NOT on the list.

### 10ak. A3 LEAVE-ONE-OUT, restated on the S1 line: with RESMOM in, every one of #463's four legs pays its way (2026-10-08, a report)

**What it is.** Scoping item A3, asked for by MANAGER (#121). Each adopted leg is taken out of #463, and out of the S1 line L, then read on the
yardstick with DD5 beside it. It is walk-forward only, with no new strategy and no weight proposal: every weight change is another look
inside the 71-look band (10z), and a forward year cannot decide a gain that comes only from a smaller drawdown (10y).
- **Inputs:** the legs are #463's registered legs (augur_engine.book, the same machinery as Q23); they sum to the book's daily column to
  the cent.
- **Parity:** #463 and L reproduce their registered figures through the seat pipeline's check_parity.

| Line | ROC@30k | DD5 | Worst DD | Sortino | $ a year |
|---|---|---|---|---|---|
| #463 | 93.81 | $36,095 | $44,849 | 3.816 | $140,235 |
| L = #463 + 0.264 x RES (S1) | 121.06 | $34,392 | $36,526 | 3.926 | $147,395 |
| #463 without ORB | 94.69 | $32,827 | $33,820 | 3.572 | $106,747 |
| L without ORB | 98.93 | $33,189 | $34,543 | 3.637 | $113,907 |
| #463 without ENGU-Q | 75.04 | $28,087 (one episode) | $39,168 | 3.908 | $97,969 |
| L without ENGU-Q | 82.04 | $29,208 (one episode) | $38,444 | 3.935 | $105,129 |
| #463 without TTM | 99.56 | $34,798 | $37,825 | 3.532 | $125,527 |
| L without TTM | 118.09 | $32,816 | $33,707 | 3.637 | $132,687 |
| #463 without NOISE | 58.43 | $33,816 (one episode) | $46,445 | 2.824 | $90,463 |
| L without NOISE | 82.01 | $30,075 | $35,713 | 2.958 | $97,623 |

Each leg's share of #463's losses on its 460 drawdown days: ENGU-Q 53%, ORB 33%, NOISE 25%, TTM 7%. Every leg LOSES on those days and on R;
that is where drawdowns come from. Without its best episode, each leg still loses there.

**Read.**
- **On L, taking out any one leg lowers ROC:** ORB -22.1, ENGU-Q -39.0, TTM -3.0, NOISE -39.1. With RESMOM's line as the reference, all
  four legs earn their seat.
- **On #463 alone, dropping ORB (94.69) or TTM (99.56) reads higher.** But each loses money - $33.5k and $14.7k a year - and the whole gain
  is a smaller worst drawdown. That is the drawdown-only kind of gain 10y says a forward read cannot confirm. TTM's line is already a
  harm monitor (10ad); ORB's is not proposed.
- **This supports keeping the four legs at their adopted sizes.** It adds no candidate and no forward line.

**Files.** C:\EdgeLog\_anatomy_cache\a3\a3_loo.json; the script is C:\EdgeLog\_anatomy_cache\bookq\a3_loo.py. A ledger row follows, docs-only.

### 10aj. Q26 QUALITY r1 FAILS and the fundamentals-basket line is CLOSED; Q27 RREV r1 is closed at the cost map (2026-10-08)

**What ran.** Both ran on RESMOM's engine (r17 'close', pinned 3151ef0a), walk-forward only, as seats over the S1 line L (121.06). They ran
before main from branch prereg/frontier-quality-1008, under MANAGER's GO #121.
- **QUALITY prereg:** LF sha256 b31ced3b..., with its power addendum committed before any cell ran.
- **RREV prereg:** LF sha256 e666c655...
- **QUALITY's data:** SEC companyfacts as filed, held (income e142ef05..., assets 83c099bd...), point in time: the first-filed annual
  value, usable only strictly before the rank, and stale after 18 months.

**QUALITY r1 - FAIL, both cells.** The bar was ROC 15. The null's MAX p95 was 6.89. The edge needed for 50% power was about $19,000 a year.

| Cell | ROC@30k | DD5 | Worst DD | WF net | Beta to ES | L + seat at 0.25 / 0.10 | $ on R (without best) | DO on #463's days |
|---|---|---|---|---|---|---|---|---|
| GPA (gross profit / assets) | 7.06 | $32,757 (one episode) | $47,278 | +$100,108 | -0.02 | 121.48 / 121.74 | +$21,597 (+$4,657) | 0.045 (null p95 0.030) |
| OPA (operating income / assets) | -1.05 | $260,480 | $260,480 | -$81,755 | -0.12 | 83.69 / 118.39 | +$188,812 (+$146,704) | 0.252 (null p95 0.030) |

The random-name null's p95 on R: GPA $21,809, OPA $22,341.
- **Coverage:** 177-274 names a month had both scores. ETFs and foreign filers carry no US-GAAP facts.
- **GPA** clears the null (7.06 > 6.89) but not the bar. All of it was earned before 2022 (the halves read 15.8 / -0.4), and it fails the
  best-1% checks. Its seat moves L by under one ROC point (+0.4 / +0.7) with a slightly lower DD5. That is inside the looks band and not a
  candidate.
- **OPA is the clearest drawdown-day earner FRONTIER has measured:** +$189k on L's drawdown days, +$147k without its best episode, seven
  times the null's p95. But it pays for it in the 2020-21 junk rally (-$148k in 2020; -$199k over 2020-04 .. 2021-02), so its seat
  LOWERS L. It is insurance that bleeds in 2019-21 - the same shape as CUSTOM-ML's DISTRESS-ML r1 (#122) and FRONTIER's short-growth
  insurance (memory: short-growth insurance fails). Its beta is -0.12, inside the 0.20 limit, so its R money is credited - and it still
  does not pay.

**The fundamentals-basket line is CLOSED for this data (MANAGER #121).** B8 (asset growth) and B9 (value) are not drafted. With CUSTOM-ML's
FUND-ML r1 (#120: value + profitability - investment, -2.0) and DISTRESS-ML r1 (#122, -1.2), three house reads of US fundamentals
baskets on the top-500 names over 2016-25 lose or fall short. What earns on R (OPA, distress) bleeds in the junk rally.

**RREV r1 - CLOSED AT THE COST MAP, with no Stage A** (MANAGER #121's extra step; picks only, no hold return computed).
- **Turnover:** the reversal cells replace 88% (REV) and 92% (RREV) of their names every month.
- **The edge needed, as a gross monthly spread on $200,000 a side:**
  - 0.73% just to break even at 20 bps a side (counting only the names that change; 0.80% under the engine's convention). With 25% room
    that is 0.92%.
  - 0.93% to reach the Stage A bar half the time.
- **The anchor, stated in the prereg before the check:** the decayed large-cap residual-reversal spread, at the upper end of the
  literature, is 0.70%.
- It clears neither line, so no power run and no cell P&L were made. Looks: none.

**Files.** Results in C:\EdgeLog\_anatomy_cache\rocfrontier\quality_r1\ (stageA, power, data with manifests) and rrev_r1\rrev_costmap.json.
Harnesses tools/rocfrontier/r27_quality.py and r28_rrev.py. RUNBOARD rows Q26-QUALITY-R1 and Q27-RREV-R1; the ledger rows follow,
docs-only.

### 10ai. THE RESMOM LINE IS RESTATED UNDER HYGIENE RULE S1 - every FRONTIER seat read now uses 121.06 (2026-10-08)

**What changed.** STRATEGY-BEATING's restatement landed on main (ledger 2.99; r17_resmom.py's 'close' reading, MANAGER #127). The reference
line L = #463 + 0.264 x RES now reads, walk-forward:
- **ROC @ $30k 121.06**, DD5 $34,392, Sortino 3.926, worst drawdown $36,526, $147,395 a year. File resmom_cells_daily_wf_close.csv,
  sha256 e204dd53... (FRONTIER checked it independently, to the dollar).
- The registered 120.82 (file bed7bf8b) is history only. The 'keep' reading (120.95, 86721fda) was never adopted.
- L's drawdown days R do not move: still 45 episodes and 762 days. So 10ab's seat yardstick and every seat read on R keep their basis.

**What FRONTIER switched.**
- **The adoption page (v9):** the RESMOM row now reads 121.1 (+29%), $147,395 a year (+$7,160 over #463), DD5 $34,392.
- **The ENGU-Q size ladder on the S1 line** (Q23, the same prereg re-read; a report):

| ENGU-Q size | ROC @ $30k | Sortino | Worst DD | DD5 | $ a year |
|---|---|---|---|---|---|
| x1.00 | 121.06 | 3.926 | $36,526 | $34,392 | $147,395 |
| x0.75 | 126.10 | 4.074 | $32,553 | $30,779 | $136,829 |
| x0.50 | 111.84 | 4.166 | $33,868 | $28,972 | $126,262 |
| x0 (reference) | 82.04 | 3.935 | $38,444 | $29,208 (one episode) | $105,129 |

  This matches the registered ladder to within 0.3 ROC on every row. Three quarters of ENGU-Q still reads higher, with a smaller drawdown,
  while making $10,566 a year less. It stays a report, with no change recommended (10ad).
- **The seat pipeline's parity** (augur_engine/seat_pipeline.py, still a draft with ELWA): line_L = (121.06, 3.926, 36,526).
- **SEASON r1 and HIGH52 r1 (10ah)** ran on this line with r17 pinned to STRATEGY-BEATING's witness commit. Main's r17 hashes the same
  (LF sha256 3151ef0a...), so neither run needs repeating.

### 10ah. Q24 SEASON r1 and Q25 HIGH52 r1 (scoping items B2 / B3): both DEAD at Stage A, and neither is a seat (2026-10-08)

**What ran.** Two monthly stock-basket families on RESMOM r1's engine (r17, imported unchanged). Each was judged under MANAGER's hygiene
rule S1 (r17's 'close' reading), walk-forward only, and read as a seat over the S1-restated RESMOM line L (121.06, file e204dd53).
- **How it ran early.** Both ran before main, under MANAGER's run-before-main rule (#117 / #118). The preregs, harnesses and power lines
  were pushed as branch prereg/frontier-season-1008 before each run. SEASON's prereg LF sha256 is b86b6108..., HIGH52's is f1433cd4...;
  r17 was pinned to STRATEGY-BEATING's witness commit d873fd07 (LF sha256 3151ef0a...).
- **SEASON** (Heston-Sadka 2008, same-calendar-month returns). LAG12 = the name's return in the month being entered, one year earlier.
  AVG = that month's mean over every prior year on file - 1 year in 2017, rising to 9 in 2025.
- **HIGH52** (George-Hwang 2004). PTH = the price over its 52-week closing high. PTHX = PTH with both the 12-1 return and RESMOM's
  residual score taken out (MANAGER #116), so it measures what L does not already hold.

**Power line first (committed before any cell ran).** The bar is ROC@30k >= 15, which is $15,000 a year at a $30k worst drawdown; the
null's MAX p95 was only 4.5 / 4.9, so the 15 floor binds. To clear it, a cell needed a true edge of about $17,500 a year at 50% power,
or $23,000 at 80%, at its own size (50 a side at $4,000). A seat needed about $33,000-38,000 more on R than the null's median.

| Cell | ROC@30k | DD5 | Worst DD | WF net | Net at 0 bps | Beta to ES | L + seat at 0.25 | $ on R (without best episode) |
|---|---|---|---|---|---|---|---|---|
| LAG12 | -1.79 | $152,716 | $152,716 | -$82,112 | -$41,485 | +0.02 | 88.6 | -$96,611 (-$113,143) |
| AVG | -3.30 | $176,834 | $176,834 | -$174,773 | -$134,136 | +0.07 | 96.6 | -$160,534 (-$171,651) |
| PTH | 2.28 | $78,166 (one episode) | $150,170 | +$102,593 | +$143,118 | -0.37 | 107.3 | +$43,634 (-$3,029) |
| PTHX | -1.62 | $92,010 (one episode) | $213,428 | -$103,780 | -$63,232 | -0.31 | 94.1 | +$82,551 (+$50,066) |

L alone = 121.06. The random-name null's p95 on R: LAG12 $21,453, AVG $21,155, PTH $22,928, PTHX $25,173.

**Verdict.**
- **SEASON: DEAD, both cells.** They lose before costs, turn over 85-87% of their names a month, and their worst entry month is
  January (-$99k / -$100k). The measured edge is negative, far below the power line, so this is dead, not undecidable. Earnings season
  is not separated: the earnings calendar the house holds covers Nasdaq-100 members only.
- **HIGH52: FAIL, both cells.**
  - PTH earns $11,400 a year: under the bar and under the 50% power line. It also fails the years and best-1% checks, and its worst
    drawdown is one episode.
  - Both cells are partly short-market bets: beta to ES is -0.37 (PTH) and -0.31 (PTHX), past the 0.20 limit. So PTHX's +$83k on R,
    though above the null, is reported, never credited.
  - Both seats LOWER L. Their correlation with RES on R is +0.64 (PTH) and +0.44 (PTHX).
- **Neither family is a seat.** SEASON's history is short (the stock cache starts in 2016, so each rank sees 1-9 years); only a longer
  history could change that call.

**Files.** Results in C:\EdgeLog\_anatomy_cache\rocfrontier\season_r1\ and high52_r1\ (the Stage A and power JSONs). Harnesses
tools/rocfrontier/r25_season.py and r26_high52.py. Run logs in C:\EdgeLog\_anatomy_cache\bookq\ (season_* and high52_*). RUNBOARD rows
Q24-SEASON-R1 and Q25-HIGH52-R1; the ledger rows follow, docs-only.

### 10ag. THE CAPACITY LINE (MANAGER assessment 10-05 order 5c): what #463 and its candidate seats need in margin, in contracts the owner can trade (2026-10-07)

**Sources (provenance in `C:\EdgeLog\_research_cache\margins\margins_provenance_20261008.json`).**
- **Broker:** NinjaTrader's public margin page, https://ninjatrader.com/pricing/margins/. Fetched 2026-10-07 18:11 MST; saved as
  `ninjatrader_margins_20261008.html`, sha256 5d917bbb...; the page says "Margins as of 2026-08-31".
- **Exchange:** CME's margin page was NOT read. It timed out to a fetch tool, and CME's margin service answered 403 with a scraping block
  (its terms forbid automated access); this was not retried or worked around. The broker's overnight initial is exactly 110% of its
  maintenance on all four contracts, which is CME's speculator ratio, so the overnight figures below are exchange-level. **The owner
  should confirm them on cmegroup.com.**

| Contract | Day (intraday) margin | Overnight maintenance | Overnight initial |
|---|---|---|---|
| NQ | $1,000 | $42,248.33 | $46,473.17 |
| MNQ (1/10 NQ) | $100 | $4,224.83 | $4,647.32 |
| ES | $500 | $26,028.77 | $28,631.65 |
| MES (1/10 ES) | $50 | $2,602.88 | $2,863.17 |

**#463 as adopted (1 NQ per NQ leg, 3 ES).** Only ENGU-Q holds overnight (a multi-day trend rider). ORB and NOISE are flat by the close
(flat_eod), and TTM exits within its end-of-day cutoff.
- **ENGU-Q, 1 NQ:** $46,473 to carry overnight.
- **ORB and NOISE, 1 NQ each:** $1,000 each, day margin.
- **TTM, 3 ES:** $1,500 at the base size, up to $3,500 at its 7-contract tilt.
- **All on at once:** about $52,000 of margin. Add the walk-forward worst drawdown of $44,849 (DD5 $36,095) and the account must hold
  about $96,800 at the worst moment. That leaves about $3,200 inside the $100,000 house account.
- **On the lockbox's $49,855 drawdown it would not fit** (about $101,800). **#463 at its adopted size is at the house account's limit.**

**Fractional sizes, in contracts that exist.**
- **NOISE x1.25:** +0.25 NQ = 2.5 MNQ, so trade 2 MNQ (x1.2) or 3 MNQ (x1.3). That adds $200-300 of day margin.
- **ENGU-Q x0.75 (Q23 report):** 7.5 MNQ, so trade 7 MNQ (x0.70, overnight initial $32,531) or 8 MNQ (x0.80, $37,179), against $46,473
  for 1 NQ. Either frees $9-14k of margin.
- **KEEL's TTM tilts:** up to 7 ES intraday, $3,500 of day margin.

**A basket seat is a separate-account question.**
- **The size:** the RESMOM line's 0.264 x RES is $105,600 of gross stock - $52,800 long and $52,800 short, about $1,056 a name across 100
  names.
- **The margin:** under standard Reg T (not fetched: 50% initial each side; maintenance about 25% long / 30% short) it needs about $52,800
  to open and about $29,000 to hold, in a stock margin account.
- **Whole shares only on the short side:** shorts generally cannot be fractional, so a name priced above about $1,056 cannot be held at
  that size.
- **It does not fit:** with the futures book needing about $96,800 at its worst, the seat does not fit in the $100,000 house account. A
  basket seat that passes the house line goes forward only with its own stock account (about $55,000 or more), or at a size that account
  can carry. A seat that passes only at an untradeable size is a research row (assessment order 5c).

**OWNER'S OWN FIGURES (overwrite these with the account's):** broker ____; NQ day ____ / overnight ____; ES day ____ / overnight ____;
MNQ ____; MES ____; futures account equity ____; stock margin account for basket seats ____.

### 10af. DD5 beside every ROC (owner rule 10-07, MANAGER #105): the open book lines re-read - which wins were one episode (2026-10-07)

**What.** A report on lines already registered and read (script `C:\EdgeLog\_anatomy_cache\bookq\dd5_lines.py`, output
`C:\EdgeLog\_anatomy_cache\dd5\dd5_lines.json`; the lines rebuilt exactly as Q16 rebuilt them, at parity). DD5 = the average depth of the
five deepest non-overlapping drawdown episodes of the same daily curve (augur_engine/drawdowns.dd5); a worst drawdown above 1.3 x DD5 =
the ROC is driven by one episode. "ROC on DD5" = 30 x net a year / DD5, printed only to show how much of a gain the worst episode carries.
Parity: #463 WF DD $44,849 / DD5 $36,095; LB DD $49,855 / DD5 $35,034 (flagged).

| Line (walk-forward) | ROC at $30k | Worst DD | DD5 | DD / DD5 | ROC on DD5 | Net a year |
|---|---|---|---|---|---|---|
| #463 | 93.81 | $44,849 | $36,095 | 1.24 | 116.6 | $140,235 |
| ORB314 | 125.55 | $33,735 | $31,775 | 1.06 | 133.3 | $141,182 |
| Q4 | 110.98 | $36,949 | $31,310 | 1.18 | 131.0 | $136,682 |
| ORB239 | 101.76 | $41,319 | $35,668 | 1.16 | 117.9 | $140,147 |
| NOISE125 | 99.83 | $45,879 | $37,929 | 1.21 | 120.8 | $152,678 |
| KEEL | 119.01 | $41,376 | $36,550 | 1.13 | 134.7 | $164,138 |
| VT | 117.81 | $35,304 | $31,704 | 1.11 | 131.2 | $138,642 |
| NOTTM (#463 without TTM) | 99.56 | $37,825 | $34,798 | 1.09 | 108.2 | $125,527 |
| L = #463 + 0.264 x RES (under restatement) | 120.82 | $36,526 | $34,363 | 1.06 | 128.4 | $147,105 |
| L with ENGU-Q x0.75 | 125.83 | $32,553 | $30,750 | 1.06 | 133.2 | $136,539 |
| L with ENGU-Q x0.50 | 111.59 | $33,868 | $28,972 | 1.17 | 130.4 | $125,972 |

- **No walk-forward line is flagged.** #463 itself sits at 1.24: its March 2020 episode is the one a line can trim.
- **Half of ORB314's, VT's and L's gain is the 2020 crash.** On ROC on DD5 their lead over #463 falls from +31.7 / +24.0 / +27.0 to
  +16.7 / +14.6 / +11.9.
- **Q4, KEEL and NOISE125 gain more broadly:** +17.2 -> +14.4, +25.2 -> +18.2 and +6.0 -> +4.2.
- **ORB239's gain is one episode** (+7.9 -> +1.3).
- **The no-TTM line's gain is ONLY the one episode.** It leads by +5.8 but trails by 8.3 on ROC on DD5, which strengthens the KEEP-TTM
  recommendation (10ad).
- **The ENGU-Q x0.75 gain over L is broad** (+5.0 -> +4.8), but it still costs $10.6k a year (10ad).
- **The lockbox (spent, quoted only):** #463 and six of the seven book lines with a lockbox are flagged, on the June 2026 episode; only VT
  is not (DD $32,941 / DD5 $28,651).

### 10ae. Q21 BAB r1 (scoping item B1): betting against beta and low volatility in single stocks - DEAD at Stage A, both cells (2026-10-06)

**What.** Prereg `docs/PREREG_frontier_bab_2026-10-05.txt` (+ addendum 1 = MANAGER #95's edits; committed 0d43cc58 before any number).
Harness `tools/rocfrontier/r19_bab.py`: it imports STRATEGY-BEATING's RESMOM engine (r17) unchanged and swaps in only the two scores (BETA =
each name's OLS beta to ES over 252 sessions, long the 50 lowest / short the 50 highest, beta-neutral at $400k gross; VOL = 252-session
volatility, low minus high, dollar-neutral), the side sizes and the null's own streams. Output `C:\EdgeLog\_anatomy_cache\rocfrontier\bab_r1\`.
Toy-world selftest passed (BETA's beta rebuilds RESMOM's residual exactly). The synthetic-world smoke was NOT run: r17's smoke is RESMOM-
specific. Dryload: 101 WF rebalances, about 485 eligible names each - RESMOM's pool. Stage A ran 2026-10-06 09:32 MST.

**Stage A: both cells fail.**
- **BETA:** WF net $79,825, ROC at $30k 2.69 (worst DD $98,870, DD5 $50,893 - one episode). It fails ROC >= 15, the null (p95 3.12),
  and profitable without its best 1% of days / name-months. 6 of 9 years are positive; the long side makes $209k, the short side loses
  $129k.
- **VOL:** WF net -$86,979, ROC -1.00; it fails 8 of 9 checks.

**The leak (TTM's post-hoc review #103, MANAGER #104).** The judged reading uses the engine's in-hold removal (names with a hygiene flag
INSIDE the hold are dropped before ranking - the same leak as SHORTINT / RESMOM, now under restatement). It flattered both cells, but
cannot flip the verdict. The kept-names figures are the honest ones: BETA $62,813 (ROC 2.12), VOL -$125,261. Any future seat read on
this engine needs the split-adjusted kept-names fix first.

**The seat read, reported only (a seat line needs Stage A).**
- **BETA loses on R:** -$90,792 against the random-name null's p95 of $23,915. The #70 gate fails, and the book add at 10ab's 0.25 size
  reads 85.3 against L's 120.8.
- **VOL makes $242,936 on R** (null p95 $20,537; #70 gate DO +0.439, a pass). But its realised beta to ES is -0.47 (side betas 0.43 long /
  1.73 short), so that money is plain short-market exposure (prereg WHAT COULD FOOL US 3), on a leg that loses money alone.
- **VOL against TLT:** the low-volatility side correlates with TLT -0.26 in 2016-21 and +0.21 in 2022-25; VOL made $133,529 in 2022.
- **TV's fund BAB in the same frame:** K5 makes $5,985 on R, K3 $14,959 - small.

**Verdict.** BAB is closed in its stock form too (TV closed the fund form); do not re-test. Low volatility's drawdown-day money is short
beta, not a seat. Ledger row in RESEARCH_LEDGER.md; RUNBOARD research row Q21-BAB-R1.

### 10ad. Q22 + Q23 (MANAGER assessment 10-05, owner-ordered): the "#463 without TTM" monitor line is open; the ENGU-Q size ladder over the RESMOM line (2026-10-05)

**Q22 - the TTM seat question gets a forward line.** `book_shadow_nottm` = ORB x1 + ENGU-Q #335 x1 + NOISE #422 x1, i.e. the book
minus 3 x TTM (api/book_shadow.py, 8945adfc; prereg `docs/PREREG_frontier_nottm_2026-10-05.txt`). The runner was restarted at 18:55
MST, so the first forward day is the 2026-10-06 report.
- It is a HARM MONITOR under the paired stops (decision b). Its difference to the book is the TTM leg's own record (-3 x TTM), never a
  second read of it.
- Walk-forward case: without TTM the book reads 99.56 / 3.532 against #463's 93.81 / 3.816 (+5.75 ROC, -0.285 Sortino, -$14,709 a
  year of TTM net).
- Recommendation on the adoption page: KEEP TTM until the line reads.

**Q23 - the ENGU-Q size ladder over L, walk-forward, a REPORT with no verdict.** Prereg
`docs/PREREG_frontier_enguq_ladder_2026-10-05.txt` (6e835d43); script `C:\EdgeLog\_anatomy_cache\bookq\q23_ladder.py`; output
`C:\EdgeLog\_anatomy_cache\q23\ladder.json`. Parity was exact: #463 93.81 / 3.816; L 120.82 / 3.916; #463 without ENGU-Q 75.04 /
3.908 / $39,168.

| ENGU-Q size on L | ROC at $30k | Sortino | Worst drawdown | Net a year | Worst episode |
|---|---|---|---|---|---|
| x1.00 (L as registered) | 120.82 | 3.916 | $36,526 | $147,105 | 2020-03-03..03-27 |
| x0.75 | 125.83 | 4.063 | $32,553 | $136,539 | 2025-05-20..06-20 |
| x0.50 | 111.59 | 4.154 | $33,868 | $125,972 | 2025-04-27..06-20 |
| x0 (reference only: L without ENGU-Q) | 81.81 | 3.922 | $38,444 | $104,839 | 2025-04-27..06-20 |

- **Each quarter of ENGU-Q is worth about $10.5k a year** of walk-forward net.
- **x0.75's gain is drawdown-shaped.** It reads +5.0 ROC and +0.15 Sortino from a $4.0k smaller worst drawdown, while making $10.6k a
  year less. That is the kind of gain Q16 / Q17 say cannot be read forward and that sits inside the 71-look band. Re-sizing is never a
  book-run trigger (decisions b / c, the assessment).
- **It is not one trade.** ENGU-Q's best walk-forward trade ($26,804, exit 2021-11-10) moves the net by under $3k a year at any rung.
- **Where ENGU-Q's money comes from.** On R (the line's 762 drawdown days) ENGU-Q loses $360,558 at x1. It earns $740,691 on the other
  days, for $380,133 net over the walk-forward.

### 10ac. Q20 (scoping item A1) SEAT CAPACITY: size a basket seat at about 10% of the line's volatility; the generator gets the shape, not the level (2026-10-05)

**What.** A planning map, not a test (`docs/PREREG_frontier_a1capacity_2026-10-05.txt` + addendum 1, MANAGER #85 / #90; harness
`C:\EdgeLog\_anatomy_cache\bookq\q20_a1.py`; output `C:\EdgeLog\_anatomy_cache\q20\a1.json`, log `bookq\q20_run.log`). Synthetic
seats from MDL r1's generator on the RESMOM line L (parity: 120.82 / 3.916, 45 episodes, 762 drawdown days), 2,000 draws per cell,
walk-forward only. Nothing is adopted.

**Calibration first (MANAGER's edit): NOT CALIBRATED, so the map is shape only.** The real RESMOM fed as a seat on #463 (parity 93.81,
28 episodes, 460 days; 0.264 x RES = 120.82, which is c0 = 0.175 of the generator's unit seat), beside the generator cell nearest to
it (s 0.516 so its mean matches; daily correlation with #463 on #463's drawdown days -0.153; 0 elsewhere):

| Seat size c | Real RESMOM ROC | Generator median (10-90%) |
|---|---|---|
| 0 | 93.8 | 93.8 |
| 0.10 | 107.9 | 98.6 (91.9-105.5) |
| 0.175 = registered size | 120.8 | 99.9 (85.9-112.6) |
| 0.20 | 123.4 | 99.6 (82.7-114.7) |
| 0.35 = twice the size | 88.0 | 90.8 (63.1-114.7) |
| 0.50 | 67.3 | 77.9 (48.9-106.0) |
| 1.00 | 38.2 | 48.1 (26.8-75.4) |

- **Passes:** the peak is in the right place (real best c 0.20, generator 0.17), and so is the fall at twice the size (88.0, inside
  the band).
- **Fails:** the level at the registered size. 120.8 is above the generator's 90th percentile (112.6).
- **Why:** RESMOM's help is concentrated in March 2020, the one episode that sets the $30k scaling (10ab). The generator spreads the
  same average correlation over all 460 days. Adding RESMOM's own off-drawdown correlation (-0.039) changes nothing (99.8).
- **Oddity RESOLVED (STRATEGY-BEATING's lag test, 2026-10-05, `C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\stamp_lag_test_2026-10-05.py`):**
  RES moves against #463 day by day on the drawdown days (-0.153) but slightly with it week by week (+0.078). This is NOT a stamp lag:
  both series co-move only within the same session, and shifting RES a day either way lowers the line (118.7 / 120.6). RES earns a
  positive level through the drawdowns (weekly DO 0.173).

**The map (shape only).**
- **Seats that earn while the line falls** (rho_dd -0.3) peak at c = 0.10 of L's daily SD each (0.15 at s 0.75). Each extra
  independent seat adds about as much as the first, up to 4: s 0.5 adds +5.6, +7.1, +7.0, +6.4 ROC; s 0.25 adds +3.9 to +4.5; s 0.75
  adds +8.2 to +10.4.
- **Seats unrelated to the line's drawdowns** add 0 to +1.6, at c 0 to 0.05.
- **Cross-seat correlation 0.3 cuts it:** c falls to 0.05-0.10. At s 0.5, seats 2-4 reach 130.9 / 133.0 / 134.4 instead of
  133.5 / 140.5 / 146.9.
- The 71-look band (Q17) applies to any real seat read.

**What it proposes (to MANAGER; not adopted).**
- **Size:** report basket seats at c = 0.10 of L's daily SD. 10ab's 25% is past the peak of every cell of the map, and past RESMOM's
  own real peak on #463 (0.20); keep 25% as a stress row.
- **Count:** aim the queue at several seats, not one more. Only seats that earn on R count, and seats must be checked against each
  other (at correlation 0.3 the 3rd and 4th seat add about half).

### 10ab. Q19 (scoping item A2): the yardstick every monthly stock-basket seat is now scored on - #463 + 0.264 x RESMOM (2026-10-05)

**What.** Construction, not a test (`docs/PREREG_frontier_a2yardstick_2026-10-05.txt` + addenda 1-2, MANAGER #85; harness
`C:\EdgeLog\_anatomy_cache\bookq\q19_a2.py`; output `C:\EdgeLog\_anatomy_cache\q19\`). STRATEGY-BEATING's RESMOM r1 daily file
(read-only, sha256 bed7bf8b...) reproduces #463 to the cent, the line #463 + 0.264 x RES reads 120.82 / 3.916, and RES earns $105,919
over #463's 460 drawdown days. Addendum 2: the drawdown days are the HOUSE rule (peak-to-trough episodes at least a third as deep as the
deepest, the day after the peak through the trough - 28 episodes, 460 days); the first run used Q9-Q15's "more than $15,000 below the
peak" rule and stopped at parity (314 days).

**The line, walk-forward.** ROC at $30k 120.8 (93.8), Sortino 3.916 (3.816), worst drawdown $36,526 ($44,849), net $147,105 a year
($140,235). The gain is mostly the smaller worst drawdown, and most of that is March 2020 (RESMOM +$8,323 inside it). The line now has
two near-equal worst episodes: March 2020 ($36,526) and 20 May - 20 June 2025 ($36,270, where RESMOM adds only $2,124).

**What RESMOM answers.** At its seat size it is positive in 18 of #463's 28 episodes but covers $27,963 of the $662,685 the book loses on
those days (4%). The episodes it leaves almost untouched are ENGU-Q and ORB give-backs: 2025 May-June, 2022 June, 2022 late April,
2025 April, 2024 March.

**The residual drawdown days R** (the line's own episodes by the same house rule, threshold $12,175): 45 episodes, 762 days. On R the line
moves with ENGU-Q (correlation 0.68), ORB (0.58) and NOISE (0.49); TTM (0.23) and RES (0.22) much less. ENGU-Q is the largest loser in
most of them. **That is the target for the next seat:** a monthly basket that earns on R - above the random-name null, without its best
episode, and not just more RESMOM (its correlation to RES printed).

**Definitions fixed for every basket-seat prereg** (cite this section): reference line L = #463 + 0.264 x RES; seat X sized by volatility
(X's daily SD over 2016-07-01..2018-06-29 = 25% of L's); incremental report L + c_X x X vs L on ROC at $30k and Sortino (report only);
incremental earner reading = X's dollars on R > 0, also without its best R episode, and above the random-name null's 95th percentile;
corr(X, RES) on all days and on R.

### 10aa. OWNER DECISIONS 2026-10-05: the lockbox rule, the six forward lines, the NOISE size

The owner, 12:40 MST via MANAGER (#81): "I will take your recommendations", read from the adoption page (https://claude.ai/artifact/62JrTFEnxCnfqZNXovfn8z), which
was built from 10u, 10y, 10z and Q18.
- **(b) The lockbox rule is adopted.** The walk-forward selects. No backtest candidate is ever "passed" on #463's 2025-26 lockbox
  year (71 looks have spent it, 10u). Forward shadow lines are HARM MONITORS under the paired sequential stops, not the deciding test:
  as registered they pass a no-edge line 89% of the time over 12 months, and a gain that is only a smaller drawdown cannot be read
  within 36 months (10y). Adoption rests on the walk-forward plus a stated mechanism and is the owner's call, from an adoption page.
- **(c) Not adopted: ORB314, Q4, VT and ORB239.** Each one's walk-forward gain is a smaller drawdown with no more money, inside the
  71-look chance band (10z; Q18 confirmed the band's width on the walk-forward). They keep running as harm monitors. KEEL stays a
  monitored shadow.
- **(d) NOISE #422 stays at 1.0x in #463.** The x1.25 line (Q8, 10t) is read once, on the dollar rule, at 36 months (2029-10-06):
  about even odds at 24 months and 77% at 36 as an upper bound (10y).
- **(a), recorded here because it sets the forward basis:** the paper ENGU-Q legs move to the roll-corrected master (db_adj_eth)
  and to #463's 0.783 points a round trip, as ONE restatement of the forward record with one board note (PAPER-NT8 / ENGUQ). After
  it, the forward book lines sit on #463's own basis.

**What this changes for every lane.** A new book candidate is judged on the walk-forward with the 71-look chance band and the Q16
power line printed beside it, and with its mechanism written down; lockbox figures appear for reference only. No new forward book
line is opened without saying what it can and cannot detect, and each one raises the bar for the lines already running.

### 10y. Q16 FORWARD BAR r1: no forward line can be decided in 12, 24 or 36 months as the reads stand (2026-10-05)

**What.** If "walk-forward selects, only the 12-month forward shadows decide" (LOOKS r1, 10u), the forward reads need a bar that a
no-edge line rarely clears. Pre-registered in `docs/PREREG_frontier_forwardbar_2026-10-05.txt` with addendum 1 (MANAGER: the paired
sequential stops run inside the simulation, read length is the headline, R0 first), committed before any number; only trade COUNTS of
the forward lines had been read. The six lines (KEEL, VT, Q4, ORB314, ORB239, NOISE125) were rebuilt on the walk-forward at parity with
every recorded figure, and the three frozen stop constants reproduced exactly. 20,000 three-week block draws of the walk-forward rows:
NULL = each line's daily difference from #463 with a random sign per block (no edge, same timing); TRUTH = the walk-forward edge taken
at face value (an UPPER bound - the lines were chosen on the walk-forward). Harness `C:\EdgeLog\_anatomy_cache\bookq\q16_forward_bar.py`.

**The registered rule cannot decide.** "Beats #463 on ROC at $30k AND Sortino" passes at least one of six no-edge lines **89%** of the
time over 12 months (83% over 24, 79% over 36); the stops barely change that. A single no-edge line passes 29-44% of the time, while a
line with its full walk-forward edge passes only 45-72% - the read is close to a coin flip either way.

**A fair bar needs margins nothing reaches.** Holding the family-wise false pass at 5%: the ROC margin over #463 must be 97 points over
12 months (61 over 24, 48 over 36), and the dollar rule needs a summed difference 2.5-2.65 null spreads above zero. Power at those bars,
even at face value:

| line | WF ROC at $30k (vs 93.8) | WF edge in dollars a year | power, 12 / 24 / 36 months (dollar rule) | power (ROC-margin rule) |
|---|---|---|---|---|
| NOISE125 | 99.8 | +$12,021 | 16% / 49% / 77% | under 1% |
| KEEL | 119.0 | +$23,092 | 7% / 8% / 11% | 6-7% |
| ORB314 | 125.6 | +$915 | 1% / 1% / 1% | 1-3% |
| Q4 | 111.0 | -$3,432 | 0% | 2-4% |
| VT | 117.8 | -$1,539 | 0% | 2-4% |
| ORB239 | 101.8 | -$85 | 1% | 0% |

**What it means.** Four of the six lines (ORB314, Q4, VT, ORB239) earn no more money than #463 on the walk-forward - their higher ROC at
$30k is a smaller drawdown. A forward read sees a drawdown difference only if a deep drawdown happens inside it, and even then one
episode is one observation: no 12-36-month read can confirm them. KEEL earns more, but in a few large TTM trades, too lumpy to read.
Only NOISE125 (more of a leg that pays steadily) becomes readable - about even odds at 24 months, 77% at 36, as an upper bound. So the
forward shadows can work as HARM monitors (the paired stops), not as the deciding test. Book decisions rest on the walk-forward plus
mechanism - the owner's call - and each new forward line raises everyone's bar (six share one family). Nor does the walk-forward
settle them: every line's walk-forward gain is inside what 71 looks produce by chance (Q17, 10z). Cost and price basis: the paper
ENGU-Q leg charges 0.533 vs #463's 0.783, and it reproduces the NO-ADJUST master (13 of 13 checked weeks; the registered db_adj_eth
master 1 of 13 - roll weeks, GUARD r1 / PAPER-NT8), so every forward line carrying ENGU-Q has sat on a different basis from #463's
backtest at roll seams since 09-14. Both cancel inside a paired forward read (line and adopted book are both paper) and matter only when
a forward figure is quoted against 93.81 / 155.54; PAPER-NT8 recommends moving the paper leg to 0.783 with the whole record re-priced -
the fix is PAPER-NT8's, ENGUQ's and the owner's.

### 10z. Q17 WF LOOKS r1: every forward line's walk-forward gain is inside what 71 looks produce by chance (2026-10-05)

**What.** MANAGER's question after Q16: is any forward line's walk-forward gain over #463 beyond luck, given that the walk-forward now
does the selecting? Pre-registered in `docs/PREREG_frontier_wflooks_2026-10-05.txt` (committed before the bands were computed). No new
draws: LOOKS r1's registered no-edge nulls (10,000 centred block-bootstrap draws per seat; the 4,202 V2 shifts for sizing), read PER SEAT
on the walk-forward at K = 71 looks. Harness `C:\EdgeLog\_anatomy_cache\bookq\q17_wf_looks.py`. Check: LOOKS r1's pooled +56% is
measured on top of the walk-forward bar's 5% premium (98.50) = +64% over 93.81, which the recompute reproduces.

| line | WF ROC at $30k (gain over 93.8) | 71-look chance band (seat) | verdict | band if the null were as narrow as the real reads | forward months to even odds (Q16) |
|---|---|---|---|---|---|
| ORB314 | 125.5 (+34%) | +49% (ORB) | inside | +15% - outside | > 36 |
| KEEL | 119.0 (+27%) | +30% (TTM) | inside | +10% - outside | > 36 |
| VT | 117.8 (+26%) | +36% (sizing) | inside | +12% - outside | > 36 |
| Q4 | 111.0 (+18%) | +78% (ORB + ENGU-Q) | inside | +22% - inside | > 36 |
| ORB239 | 101.8 (+8%) | +49% (ORB) | inside | +15% - inside | > 36 |
| NOISE125 | 99.8 (+6%) | +64% (NOISE) | inside | +19% - inside | 36 |

**Reading.** No line is shown by the walk-forward, and none can be read in a forward year. ORB314, KEEL and VT clear only the
narrow-null version (LOOKS r1's own flag: its null spreads ~2.9x wider than the ten real one-change reads), so they stand "not refuted,
not shown". With Q16 that is the honest state of the book queue: a change to #463 is now a judgement on mechanism, made by the owner,
with the forward lines watching for harm.

**Q18 (LOOKS r2 calibration, step 1) - the narrow-null column above is WITHDRAWN.** Its r = 0.346 was LOOKS r1's LOCKBOX calibration
and had never been measured on the walk-forward. Measured there (`docs/PREREG_frontier_looksr2_2026-10-05.txt`, committed first; run
under the standing order when MANAGER had not answered within 60 minutes; `C:\EdgeLog\_anatomy_cache\bookq\q18_step1.py`): the ten
real one-change reads spread 0.185 in ln(WF ROC ratio), the N-LEG null 0.157, so r_WF = 1.18 (bootstrap 90% 0.74-1.44), inside the
registered [0.5, 2.0]. The walk-forward null is calibrated, the standard band stands, and ORB314, KEEL and VT are plainly INSIDE - no
longer "not refuted, not shown". Step 2 (a neighbour-swap null) does not run. The owner page was corrected the same day.

### 10x. Q15 the bull steepener, held only while the VIX curve is inverted: FAIL - the family null removes its earner pass (2026-10-05)

**What.** The third seat on Q12/Q13's state (prior close of VIX / VIX3M at or above 1.00): long SHY $100,000 and short TLT in the ratio
of their durations (1.9 / 17.0), a slope bet rather than Q13's level bet. Pre-registered in `docs/PREREG_frontier_steepener_2026-10-05.txt`
with addendum 1 (MANAGER's review: leverage and funding rows, one-family null over Q12 / Q13 / Q15, power first; the SHY + TLT pair
counted as one instrument), committed before any number. Walk-forward only; harness `C:\EdgeLog\_anatomy_cache\bookq\q15_seats.py`;
parity exact; 48 entries (neighbours 92 / 20).

**On its own numbers it passed the earner route** - and that pass did not survive the family test it was registered with.
- Earns where the book loses, a little: +$2.5k in March 2020, +$8.0k over all of #463's drawdown days (+$2.8k without the best one),
  own walk-forward net +$7.4k, both neighbours positive. Book with the leg 98.9 ROC at $30k vs 93.8 (Sortino 3.835 vs 3.816), but the
  book-add report fails A4 (tuning block -3.8 ROC points, 4 of 9 years).
- **Family null: FAIL.** Shifting the inversion dates at random (500 circular shifts) and taking the best of the three legs each
  time, the 95th percentile of that best reaches $6.3k of drawdown-day earnings; Q15's $2.8k sits well inside chance. Standalone
  ROC 1.2 vs a chance level of 7.8.
- It also needs the leverage MANAGER warned about: the 25%-risk scale holds a median $1.3m gross (13x the account, up to 20x); a
  0.5%/yr funding charge on the levered long costs $3.6k of the $7.4k. Without its best episode (April 2025, +$10.8k) the leg loses
  $3.4k. Its residual beta is half a TLT short ($63k of TLT-equivalent per $125k held), so the duration hedge is only half a hedge.

**The family is closed.** Q12, Q13 and Q15 all switch on when the VIX curve inverts; one passes on its own numbers only by the luck the
family test measures. Together with Q9 this says: market-stress hedges do not earn their seat in #463 - its drawdowns are its own legs
giving back in orderly markets. No further leg on this state variable is drafted.

### 10w. Q12 long volatility and Q13 safe havens, held only while the VIX curve is inverted: both FAIL at Stage A (2026-10-05)

**What.** Two state-gated "earns while #463 falls" legs (Q9's lesson: an always-on crisis leg bleeds between crises), pre-registered in
`docs/PREREG_frontier_seats3_2026-10-05.txt` with addendum 1 (MANAGER's review and house line #69, committed before any number; Q14
sector BAB withdrawn as TV's BAB r1). State: the prior close of VIX / VIX3M at or above 1.00 (48 entries in the walk-forward). Q12 =
long VIXY (VIX futures) while inverted; Q13 = equal-risk long TLT + GLD + FXY (yen) while inverted. Walk-forward only, files already on
the box, every series cut at 2025-06-29; scale = 25% of #463's trailing risk measured on the always-on version, capped at 2x its own
recent median. Harness `C:\EdgeLog\_anatomy_cache\bookq\q12_13_seats.py`; parity exact (#463 93.81 / 3.816 / $44,849); VIXY's
reverse splits are inside the adjusted file (largest daily move 43%, 2024-08-05).

**Both fail - neither the standalone route nor the earner route.**
- *Q12 long volatility:* the book's walk-forward ROC at $30k rises to 109.3 (Sortino 3.830) only because the leg cuts March 2020's
  drawdown (+$11.5k there; the Feb-Apr 2020 episode alone +$13.7k). Over all of #463's drawdown days it LOSES $7.1k; the leg loses
  $2.9k over the walk-forward in total, $15.7k without Feb-Apr 2020; August 2024 (the state turned on after the spike) cost $8.6k. The
  named failure shape, 2018-02-05, actually made $3.6k. Neighbours split (0.95 loses $21.6k, 1.05 makes $7.4k).
- *Q13 safe havens:* book ROC 99.2 / Sortino 3.818 for the same reason; the leg loses $3.2k in total and $8.0k over #463's drawdown
  days (February 2022 -$3.2k: bonds, gold and the yen all fell in that sell-off).

**What it teaches.** Every crisis leg tried this week - fund trend (Q9), long volatility (Q12), safe havens (Q13) - helps in exactly one
episode, March 2020, and pays for it elsewhere. #463's other drawdowns (2019, 2022, 2025) are not the kind of market stress these
hedges answer: they are leg-specific give-backs in otherwise orderly markets. A seat that earns in #463's drawdowns has to answer
the BOOK's own losses, not the market's.

### 10v. Q9 - fund trend as a #463 seat, the "earns while #463 falls" leg: FAIL at Stage A (2026-10-05)

**What.** Pre-registration `docs/PREREG_frontier_trendseat_2026-10-05.txt` with addendum 1 (MANAGER's nine edits and ORB's second
review, committed before any number); harness `C:\EdgeLog\_anatomy_cache\bookq\q9_trend_seat.py`, output
`C:\EdgeLog\_anatomy_cache\q9\`. The leg is TREND r1's time-series momentum on 11 bond, gold, currency and commodity funds
(Moskowitz-Ooi-Pedersen), primary = the literature's equal-weight 1 / 3 / 12-month ensemble, sized each month so its risk is 25% of
#463's trailing-year risk (vol only, causal). Walk-forward only; the fund loader cannot reach the lockbox year. Parity was exact
(TREND r1's loop to the cent; #463 93.81 / 3.816 / $44,849).

**Result (walk-forward 2016-07-01..2025-06-29).** #463 plus the leg: ROC at a $30k drawdown 106.36 vs 93.81 (drawdown $40,027 vs
$44,849) but Sortino 3.707 vs 3.816 - **A1 fails**. The leg does what the literature says where it matters: +$9,505 in March 2020,
+$33,586 over #463's 63 drawdown episodes (days $15k+ below its peak), still +$20,835 without the best episode and +$23,341 without
its best fund (GLD), with -0.10 correlation to #463 on those days - **A2 and A3 pass**. But it bleeds the rest of the time: about
$1,700 a year in total, losing in 7 of 9 walk-forward years, so the book's Sortino is better in only 2 of 9 years and the ROC gain
turns negative without Feb-Apr 2020 (-4.31) - **A4 fails**. Stage A FAIL; per BOOK LOOKS r1 there is no lockbox stage.
The twins say the same: the fixed-scale 1 / 3 / 12 version passes A1 narrowly (105.01, Sortino 3.832) but also wins only 2 of 9
years; 1 / 3 / 6 / 12 and the 6-month cell are worse; without USO 112.19 / 3.738. At half size the book reads 107.07 / 3.820 with
breadth still 2 of 9.

**What it teaches.** On the map, a drawdown-week earner helps at almost any return - but this one's cost between crises is larger
than its help inside them, and its help is real only in 2019-20. Crisis alpha from fund trend is genuine and too thin to buy a seat
in #463. No other lookback, universe or scale is tried in its place.

### 10u. BOOK LOOKS r1 - the lockbox year can no longer pass a book candidate (2026-10-05)

**BOOK LOOKS r1 (Q11) - how sure a lockbox pass must be.** Pre-registration `tools/rocfrontier/PREREG_LOOKS_R1.txt` (+ addendum 1, the looks ledger `LOOKS_LEDGER_R1.csv`), harness `tools/rocfrontier/r14_looks.py`, run 2026-10-05 from the RISK r1 cache; one page `docs/LOOKS_R1.md`. Parity was exact (#463 WF 93.81 / LB 155.54, the largest lockbox trade the ENGU-Q $91,152 hold). #463's lockbox year has now been used to judge 71 candidate books (51 seat changes or adds, 20 sizing rules; up to 181 counting aggregate verdicts). On that year a candidate with NO edge clears the lockbox bar about 42% of the time as a seat change and 24% as a sizing rule, so one year cannot tell skill from luck: even a single, first look would need a candidate to beat #463's lockbox ROC by 41% before its pass was under 5% likely to be luck, and after 71 looks no margin up to double is enough. Caveat, in the same breath: the no-edge simulation spreads about three times wider than the ten real one-change reads did (r = 0.35, flagged by the harness), so these margins overstate - but the direction is not in doubt. Every past lockbox pass (58d, #444, #449, round-61 best, V2, V2-500, Q4, Q6) is 'not refuted', none is evidence. The sentence for the owner: **walk-forward selects, only the 12-month forward shadows decide.** Proposed rule (owner decision via MANAGER): a backtest book candidate that clears walk-forward but not the margin is 'not refuted', never 'a pass'; until the owner rules, no lane reads #463's lockbox year for a book candidate (MANAGER #67), and book adds are judged forward.

### 10t. TTM round 23 as a book test, the NOISE x1.25 forward line, and why the NOISE leg stays on no-adjust (2026-10-04/05)

**TTM round 23 (compression sizing on ORB #234 and ENGU-Q #335) - FAIL at Stage A, lockbox never read.** Pre-registration
`tools/TTM_R23_PREREG.txt` (a4260281 + 8f574275); TTM ruled the verdict, this lane ran the books
(`C:\EdgeLog\_anatomy_cache\bookq\ttm23.py`, exports in `C:\EdgeLog\_anatomy_cache\ttm23\`). The tilt is the book engine's
existing leg gate (1.5x size on a trade entered while the last completed hourly squeeze is on), the same code the paper legs use.
Parity was exact (#463 WF 93.81 / LB 155.54, Sortino 3.816 / 4.150). Walk-forward 2016-07-01..2025-06-29, ROC %/yr at a $30k
valued-daily drawdown: #463 93.81 (drawdown $44,849); both legs tilted 90.22 ($50,556, 113% of #463's); ORB only 90.43; ENGU-Q only
93.40. More money (+$106k on both legs) but a deeper drawdown, so none beats #463 at $30k. The tilt fires on only 12.9% of ORB and 17.7%
of ENGU-Q trades. TTM's checks: without Feb-Apr 2020 the tilt would have won by 11.4 - it loads size into the coiled tape just before
the 2020 crash. No lockbox figure was computed for any tilted book.

**Q8 - "#463 + NOISE x1.25" as a forward shadow line** (owner standing order 2026-10-04, MANAGER GO with two edits). Report key
book_shadow_noise125, from the 2026-10-06 report; pre-registration `docs/PREREG_frontier_noise125_2026-10-05.txt`. MDL r1's map
found NOISE the only leg whose plain upsizing lifts both stretches (x1.25: 99.8 / 156.3), but re-weighting has never shown forward
skill (round 56), so this is a forward test only. The line equals the book plus a quarter of the NOISE leg, so it is not a second,
independent read beside the NOISE #422 shadow. Read once after 12 months from per-trade records; a pass is an owner question.

**The NOISE leg stays on no-adjust data by design** (NOISE lane, MANAGER decision #32, 2026-10-04). #463 runs ORB, ENGU-Q and TTM on
the roll-corrected masters and NOISE #422 on `db_noadj_rth`. NOISE #422 on the roll-corrected master differs by -6.0% net in
walk-forward, but 342 of the 408 differing trades come from back-adjustment distorting NOISE's percentage-based band, volatility skip
and stop on older days, not from rolls; the 66 roll-near trades are in NOISE.md (round 69 follow-ups, eb4443a7). No NOISE_1_x file
should run on a roll-corrected master.

### 10s. Round 62 V3 - a learned risk forecast in place of the vol target's 20-day volatility: FAIL at the forecast gate (2026-10-03)

**What.** Owner ask (2026-10-02, "push the frontier ... might have to use an ML"), built and pre-registered by the owner's
cloud session (no market data there) and run on this PC by this lane. Pre-registration
`docs/PREREG_frontier_v3_riskml_2026-10-02.txt` (canonical LF sha256 41b4bb91...), harness `tools/frontier_v3_riskml.py`
(sha256 976354f6...), run from the shared checkout at 415bfded on 2026-10-03, read once. Output:
`C:\EdgeLog\_anatomy_cache\frontier_v3\v3_result.json`. The idea: keep the vol target (V2, the nightly VT line) exactly,
but replace its backward-looking 20-day book volatility with a walk-forward forecast of the next 5 days of book risk, made
from the book's own recent risk and the market's (NQ and ES daily ranges, NQ's 20-day trend). The ML sits on the risk
side because direction has never been forecastable here and volatility usually is.

**Parity was exact.** The rebuild equals the production VT series to $0.0000 on the same day index, its V2 sizes equal
the nightly line's, and #463 reads WF 93.81 / LB 155.54 %/yr at a $30k drawdown, Sortino 3.816 / 4.150, drawdowns
$44,849 / $49,855, lockbox without its biggest trade $167,144.

**STEP 1 (the forecast gate, IS only) FAILS.** On 1,085 in-sample forecasts (2012-09-30..2016-06-24), scored on what the
sizing rule actually uses (each forecast against its own trailing-year median, versus realised risk against its own):
- the pre-specified ridge model's error is 0.942 x the plain 20-day-volatility forecast's (5.8% better, inside the 5%
  edge the bar asks for), but the Diebold-Mariano test gives p = 0.152 against the required 0.05;
- the gradient-boosted model, reported only, is worse than the plain forecast (1.21 x, p 0.99).

**Verdict.** V3 is dead as registered: the walk-forward and lockbox book numbers were never computed, and nothing is
re-tried with other features, horizons or models. The market's ranges add a little to the book's own 20-day volatility
as a forecast of next week's book risk, but over four in-sample years that little cannot be told apart from noise. The
vol target (V2) stays the only volatility line; the nightly VT shadow continues unchanged.

**Side finding (ledger 2.47).** Since the paper report switched to counting money on the day a trade CLOSES (377f0f67,
2026-10-02), the nightly VT figure is that day's multiplier times the exit-day book figure - a monitor, not the tradable
VT line, which sizes each trade at the multiplier of its ENTRY day. The forward read was already specified on per-trade
records with each trade's entry-day multiplier (the shadows pre-registration's correction paragraph), so it is unaffected;
the shadow module's wording now says so.

### 10r. Build review fixes, one ROC convention for every lane, and Q6 (ORB #239) as a forward shadow (2026-10-01)

**The review (MANAGER #44) found three real things; all are fixed.**
- **The agreement tilt (AG) had a same-bar look-ahead.** Round 62's overlap diagnostic compared bar *labels*, so a NOISE
  trade on the same 5-minute label as an ORB trade counted as entering "while ORB was open". But ORB fills at that bar's
  close and NOISE at its open. Compared on fill times, the evidence for AG is gone: the trades it tilts have a profit
  factor of 1.35 against 1.38 for the rest (not 1.56 vs 1.30, as 10o says). With the fix, AG at 1.5x is flat on
  walk-forward (92.8 vs 92.7 on the old convention) and the overlap cap O still fails. The nightly AG line moved to fill times on
  09-30 and was **retired on 10-01** (owner GO via MANAGER #48); its last report is 10-01, and no forward read will be made.
- **The nightly shadow lines could read stale or substitute data.** The vol-target line refuses to size from data more
  than one business day old; any leg rebuilt from a fallback master or with a failed daily valuation is refused; a
  leg that throws is named in the report instead of silently reading $0.
- **The pre-registrations lived only outside git.** They are now committed, hashes below. Future addenda are committed
  before the run they govern.

**One ROC convention for every lane.** The ORB lane and this lane computed ROC differently: closed trades by exit day
over (days + 1) / 365.25 years here, versus the valued-daily net over (last - first) / 365.25 there. From now on both use
the valued-daily net and drawdown inside each stretch, over (last - first).days / 365.25 years. Everything in 10n-10q
was re-scored on it. **No verdict changes.** #463's reference is now **WF 93.8 / LB 155.5 %/yr at a $30k drawdown**
(it was 92.7 / 164.3; the lockbox moves most because ENGU-Q's long holds are now counted while open).

| candidate (#463 with ...) | run | WF ROC at $30k | WF Sortino | WF DD | LB ROC at $30k | LB Sortino | LB DD | LB without its biggest trade | verdict |
|---|---|---|---|---|---|---|---|---|---|
| #463 | #463 | 93.8 | 3.82 | $44,849 | 155.5 | 4.15 | $49,855 | $167,144 | - |
| Q1a ORB #314 in the ORB seat | #473 | 125.6 | 3.95 | $33,735 | 147.3 | 3.95 | $49,855 | $153,500 | FAIL |
| Q1b ORB #257 in the ORB seat | #474 | 108.5 | 3.93 | $39,917 | 146.3 | 3.89 | $49,475 | $150,003 | FAIL |
| Q2 NOISE #398 in the NOISE seat | #472 | 69.6 | 3.30 | $46,445 | 169.0 | 3.75 | $36,484 | $114,214 | FAIL |
| Q2ctx NOISE #304 raw in the NOISE seat | #471 | 85.1 | 3.54 | $44,849 | 145.6 | 3.94 | $49,855 | $150,697 | context |
| Q3 ENGU-Q cash-session gate S1 in the ENGU-Q seat | #475 | 84.5 | 3.89 | $48,172 | 188.4 | 4.61 | $43,341 | $180,859 | FAIL |
| Q4 ORB #314 + ENGU-Q gate S1 (post-hoc) | #476 | 111.0 | 4.03 | $36,949 | 177.6 | 4.37 | $43,670 | $167,216 | **PASS (post-hoc)** |
| Q5 + ENGU-Q on ES #442 as a fifth leg | #477 | 103.1 | 3.49 | $48,667 | 149.6 | 3.68 | $59,238 | $204,016 | FAIL |
| Q6 ORB #239 (breakeven 0.8) in the ORB seat | #478 | 101.8 | 3.84 | $41,319 | 158.7 | 4.23 | $49,855 | $172,469 | **PASS** |

**Q6 - ORB #239 in the ORB seat** (#234's settings with the breakeven trigger at 0.8 R instead of 1.0 R; a survivor of
the ORB lane's round 63). It clears the bar narrowly in both stretches, and the ORB lane's 900-trial validate of #239
passed (their wider-region validate #480 failed). Owner call via MANAGER #41: **shadow first.** The nightly report now
carries book_shadow_orb239 = ORB_239 + ENGUQ_335 + 3 x TTM_299_SSOF2 + NOISE_422, with its bar written before its
first forward day: after 12 months it must beat the adopted book line on ROC at a $30k drawdown and on Sortino.
Custom ML's paired early stop is its own document. #463 stays the adopted book.

**How every forward line is read.** The nightly report counts a trade on its entry day and is written once at about
16:10 ET, which freezes multi-day ENGU-Q holds and never counts ENGU-Q entries after 16:10. So every forward read is
computed from the per-trade paper records, each trade dated by its exit day; the daily figures are a monitor only.

**Pre-registrations in git** (`docs/`, sha256 of the committed file - check with `git show HEAD:<path> | sha256sum`):
- `PREREG_frontier_ttm458_2026-09-28.txt` `c035956c4fcfaf4eb08ded025df80d11a648bae3f89159c8b69b15d81f00aace`
- `PREREG_frontier_keel458_2026-09-28.txt` `72ce7193650adecd56cc6f1a62675cbd0d4d4e95a8e7abb8eeaf42eba964a790`
- `PREREG_frontier_r62_2026-09-28.txt` `e0c4a8f596cb49401e8b3275434557f52ebf78287b7a2b1b4a1dc6f02ddca8a1`
- `PREREG_frontier_ttmsleeve_2026-09-29.txt` `38688f8a3536f04e48739ef64e0f17b7f636a2f59d04f646f7aa433ee8597c3f`
- `PREREG_frontier_shadows_2026-09-29.txt` `bf606dd1a75e3d630470cbb9b1e029b1676afa3b64825cd78cee6d298ad65016` (with the 10-01 AG retirement addendum; before it `3e2061ad988f52407813b18e30ace63e234ce7fa7c8475f0fc5a70eae75de1b7`)
- `PREREG_frontier_bookq_2026-09-30.txt` `3ce3ba43ad4da7ce517de016513dc51c0680c0d18da8d0bae42e67ce001b3542`

### 10q. The standing book queue: Q1-Q4 on the adopted #463 (2026-09-30)

**What.** Owner ask via MANAGER (#34): keep assessing structural book changes as an ongoing queue, fold in any
lane survivor as a candidate leg, and judge each on the leverage line against #463. One standing bar, written
before the first result: `C:\EdgeLog\_anatomy_cache\bookq\PREREG_BOOKQ.txt` (each item was added to it before it
ran). The bar: beat #463 on ROC %/yr at a $30k worst drawdown (each stretch on its own valued-daily drawdown) and
on Sortino, in BOTH WF 2016-07-01..2025-06-29 and LB 2025-06-30..2026-06-30, with the trade minimums. Every
candidate was also run on the runner, and every run equals the local read to the cent.

| candidate (#463 with ...) | run | WF ROC at $30k | WF Sortino | WF DD | LB ROC at $30k | LB Sortino | LB DD | verdict |
|---|---|---|---|---|---|---|---|---|
| #463 (adopted) | #463 | 92.7 | 3.82 | $44,849 | 164.3 | 4.15 | $49,855 | - |
| Q1a ORB #314 in the ORB seat | #473 | 124.1 | 3.95 | $33,735 | 156.1 | 3.95 | $49,855 | FAIL |
| Q1b ORB #257 in the ORB seat | #474 | 107.3 | 3.93 | $39,917 | 155.2 | 3.89 | $49,475 | FAIL |
| Q2 NOISE #398 in the NOISE seat | #472 | 68.6 | 3.30 | $46,445 | 181.1 | 3.75 | $36,484 | FAIL |
| Q2ctx NOISE #304 raw in the NOISE seat | #471 | 84.0 | 3.54 | $44,849 | 154.4 | 3.94 | $49,855 | context |
| Q3 ENGU-Q cash-session gate S1 in the ENGU-Q seat | #475 | 83.5 | 3.89 | $48,172 | 198.5 | 4.61 | $43,341 | FAIL |
| Q4 ORB #314 + ENGU-Q gate S1 (post-hoc) | #476 | 109.6 | 4.03 | $36,949 | 187.6 | 4.37 | $43,670 | **PASS (post-hoc)** |
| Q5 + ENGU-Q on ES #442 as a fifth leg | #477 | 98.4 | 3.49 | $48,667 | 185.7 | 3.68 | $59,238 | FAIL |

- **Q1 - the ORB crown #314 in the ORB seat** (#463 still carries #234): FAIL on the lockbox. The walk-forward
  read is much better: drawdown $33.7k vs $44.8k, and the walk-forward ROC column above. But #314 earned less than
  #234 in the lockbox, where both books' drawdown is the same June ENGU-Q stretch. ORB #257 has the same shape.
- **Q2 - NOISE #398 (the squeeze filter) in the NOISE seat:** FAIL. Walk-forward collapses and Sortino falls in
  both stretches. The raw #304 context row shows the adopted #422 tilt beats its raw twin in both stretches
  inside the book.
- **Q3 - the ENGU-Q lane's cash-session gate (S1) in the ENGU-Q seat** (information only; the gate is that lane's
  forward shadow): FAIL on walk-forward, strong in the lockbox. That is the same split the ENGU-Q lane found.
- **Q4 - Q1 + Q3 together, built after seeing them (post-hoc):** clears the bar in both stretches. It is
  data-mined by construction, so per MANAGER #34 it becomes a forward paper shadow, not an adoption. The report
  key is book_shadow_q4 (ORB_R6 + ENGUQ_335_S1 + 3 x TTM_299_SSOF2 + NOISE_422), with its bar written in the
  pre-registration before its first forward day: read after 12 months against the book line, and void if the
  ENGU-Q lane drops the S1 gate first.
- **Q5 - ENGU-Q on ES (#442, the lane's roll-corrected re-run) added as a fifth leg:** FAIL on Sortino. It lifts ROC at
  $30k in both stretches, but Sortino falls in both and the lockbox drawdown grows to $59.2k. ES and NQ trend
  together, so it adds return with a rougher downside.
- **Pattern worth knowing:** every single-seat swap so far trades one stretch for the other. The book's
  walk-forward drawdown is the 2020 crash, and its lockbox drawdown is an ENGU-Q give-back in June 2026. A seat
  change moves one of them, not both.

### 10p. TTM's multi-cell sleeve as a book test (#469 / #470), and the nightly shadow lines on #463 (2026-09-29)

**Why a book test.** Owner via MANAGER (2026-09-29): TTM candidates are judged on walk-forward plus a book-level test,
because #459's 15-trade lockbox fails the 50-trade minimum. TTM's round-19 sleeve is TTMSQZ_3_0.py at the frozen #299
settings on ES 30m, ES 15m, NQ 30m and NQ 15m, day session, roll-corrected masters pinned, one contract each. It was
tested two ways inside #463, with the bar written first (`C:\EdgeLog\_anatomy_cache\adopt449\PREREG_TTMSLEEVE.txt`).
Both runs equal the local read to the cent.

| book | WF ROC %/yr at $30k | WF Sortino | WF DD (valued daily) | LB ROC %/yr at $30k | LB Sortino | LB DD (valued daily) | trades WF / LB | LB without its biggest trade |
|---|---|---|---|---|---|---|---|---|
| #463 (adopted) | 92.7 | 3.82 | $44,849 | 164.3 | 4.15 | $49,855 | 5,645 / 619 | $182,457 |
| #469 = sleeve IN PLACE of TTM x3 | 82.9 | 3.90 | $50,925 | 149.1 | 3.89 | $52,429 | 6,426 / 689 | $169,891 |
| #470 = sleeve ADDED as a fifth component | 82.6 | 4.08 | $56,477 | 166.9 | 4.37 | $52,429 | 6,638 / 704 | $201,094 |

- **Both FAIL.**
  - *Swap:* it loses ROC at $30k in both stretches.
  - *Add:* it wins the lockbox (and Sortino in both stretches), but the pre-lockbox drawdown grows from $44,849 to
    $56,477, so the walk-forward ROC at $30k falls from 92.7 to 82.6.
- The four cells sum to TTM's own parity totals exactly (1,755 trades, $185,135 over the window).

**The nightly shadow lines** (owner "shadow TTM KEEL" 09-28, and GO on the round-62 calls 09-29). They sit beside the
adopted book figure in every paper report and are never the book figure. Rules are in
`C:\EdgeLog\_anatomy_cache\adopt449\PREREG_SHADOWS_0929.txt`; code in `api/book_shadow.py`.
- **KEEL** (report key book_shadow, from 09-29): #463 with TTM #458 x KEEL v12 (frozen at 2025-07-01) in place of TTM x3.
  Custom ML sets its bar.
- **VT** (book_shadow_vt, from 09-30): the day's book trades x m = clip(median 20-day volatility of the prior 250 days /
  the 20-day volatility, 0.5-2.0). #463's daily series is rebuilt each night from its job legs. The rebuild reproduces
  run #463 to the cent, and a three-year window gives identical multipliers on all 290 recent-year days. The multiplier
  for 2026-09-29 was 0.7.
- **AG - RETIRED 10-01** (book_shadow_ag, 09-30..10-01; see 10r): 1.5x on ORB / NOISE trades that enter while the other leg is in the same way. It
  was found in-sample, so it is judged only on forward data.

**How they will be judged.** Each line against the book line on ROC at a $30k drawdown and Sortino. AG was to be read at
>= 100 tilted trades; it was retired first (10r). VT is read after 12 months, and only if a drawdown deeper than $20k occurred in
that window.

### 10o. Round 62 - structural book alpha on the adopted #463: volatility targeting and an overlap cap (2026-09-28)

**What.** Owner ask via MANAGER (#29): brainstorm book-level alpha from structural changes, not re-weighting;
pre-register the top one or two and triage them. Rules and bar written first:
`C:\EdgeLog\_anatomy_cache\adopt449\PREREG_R62.txt`. Base and raw twin = #463's legs, rebuilt trade by trade. The rebuild
equals run #463 to the cent (whole net, and both valued-daily drawdowns). Stretches: IS 2010-06-07..2016-06-30 (never
judged), WF 2016-07-01..2025-06-29, LB 2025-06-30..2026-06-30. Every size applies to a trade at its entry, from
information up to the day before. Sizes are rounded to 0.1, which micros make tradeable.

| rule | WF ROC %/yr at $30k | WF Sortino | WF DD (valued daily) | LB ROC %/yr at $30k | LB Sortino | LB DD (valued daily) | average size | bar vs #463 |
|---|---|---|---|---|---|---|---|---|
| #463 (raw twin) | 92.7 | 3.82 | $44,849 | 164.8 | 4.15 | $49,855 | 1.00 | - |
| V: vol target fixed in dollars from IS | 95.8 | 3.87 | $22,424 | 164.8 | 4.15 | $24,927 | 0.55 | FAIL |
| **V2: vol target vs its own trailing year** | 116.1 | 3.91 | $35,304 | 259.3 | 4.79 | $32,941 | 0.99 | **PASS** |
| V2 sensitivity: 500-day reference | 111.9 | 3.92 | $34,407 | 239.5 | 4.70 | $33,899 | 0.93 | **PASS** |
| V2 sensitivity: 60-day lookback | 123.3 | 3.76 | $31,232 | 203.5 | 4.10 | $35,907 | 0.97 | FAIL |
| O: ORB x NOISE same-direction overlap at half size | 87.4 | 3.61 | $42,346 | 146.9 | 3.64 | $47,045 | 0.87 | FAIL |
| O sensitivity: skip the overlap | 81.5 | 3.29 | $39,843 | 126.7 | 3.02 | $44,235 | 0.73 | FAIL |

- **O (overlap cap) FAILS, and the risk it named came true.** Trades where ORB and NOISE are in the market the same
  way have a profit factor of 1.56 against 1.30 for the rest, so halving them costs money. (Superseded: that comparison had a same-bar look-ahead; on fill times it is 1.35 vs 1.38 - see 10r.) An *agreement tilt* (more
  size when they agree) is the obvious follow-on. It was found in this data, so only a forward test could judge it.
- **V (as registered) FAILS without testing its mechanism.** Its target was fixed in dollars from 2010-16, but the
  book's dollar volatility grew about tenfold with the NQ price. The size sat on its 0.5 floor almost all the time
  (average 0.55; the lockbox is exactly x0.5).
- **V2 (repair written in an addendum before it ran) PASSES the bar in both stretches.** Size = the book's
  20-day volatility measured against the median of its own previous 250 days, clipped to 0.5-2.0. No constant is
  fitted. The 500-day reference also passes; the 60-day lookback misses only lockbox Sortino (4.10 vs 4.15).
- **But V2 is a tail hedge, not an everyday edge.** It has the better net/drawdown in only 7 of 15 years (2011-2025).
  Trades it sizes up earn about the same as trades it sizes down (raw PF 1.46 vs 1.43). The whole gain is two
  episodes: the March 2020 crash (drawdown $44,849 -> $22,578) and the June 2026 ENGU-Q stretch
  ($49,855 -> $32,941). That is what volatility targeting is for, but here it rests on two events.
- **Not adopted, no validate queued.** The book engine cannot size a whole book from its own volatility, so a real
  run needs a new book-level sizing feature. The next clean step is a nightly paper shadow; that is the owner's call.

**The rest of the brainstorm (not run).**
- Book drawdown brake fixed in advance: path-dependent, and it overlaps V2's tail effect.
- Crash guard on the long-biased ENGU-Q leg: two events in 16 years; it overlaps V2.
- Agreement tilt: see O.
- Already dead: DIP on ES as a seat (10j/10l); NOISE and ORB on ES; ENGU-Q on ES (#370, one trade); the month-end
  flow leg; walk-forward re-weighting (round 56).

### 10n. ADOPTED: BOOK #449 on the fixed legs (run #463) replaces #366; the #397 flip is dropped (2026-09-28)

**The owner's calls (via MANAGER, 2026-09-28).** (1) Adopt BOOK #449 on the fixed TTM files, which is run #463,
over #366, and drop the staged #397 flip. (2) First try #463 with the roll-safe TTM #458 (sized 3 / 4 / 7 ES)
in place of #459. Adopt that version if it holds the book's drawdown and adds return; otherwise adopt #463 as is.

**The TTM #458 check, rule written first** (`C:\EdgeLog\_anatomy_cache\adopt449\PREREG_TTM458.txt`).
"Holds the drawdown" means both valued-daily drawdowns are within +5% of #463's. "Adds return" is read on the
owner's new yardstick: ROC %/yr at a $30k worst drawdown valued daily, better in BOTH stretches.

| book | ROC %/yr pre / lockbox, as run | the same at a $30k drawdown | worst drawdown, valued daily, pre / lockbox | Sortino (valued daily) pre / lockbox | trades pre / lockbox | lockbox net without its biggest trade |
|---|---|---|---|---|---|---|
| **#463 = #449, ADOPTED** | 90.2 / 273.8 | **60.3 / 164.8** | $44,849 / $49,855 | 3.15 / 4.15 | 9,190 / 619 | $182,457 |
| #463 with TTM #458 (run #468) | 90.0 / 271.9 | **72.1 / 163.6** | $37,444 / $49,855 | 3.18 / 4.12 | 9,084 / 616 | $180,531 |
| #460 = #366 re-run (previous) | 79.4 / 252.1 | **57.1 / 151.7** | $41,736 / $49,855 | 2.88 / 3.85 | 9,192 / 620 | $160,764 |

- **The #458 version holds the drawdown and misses on return.** Its pre-lockbox drawdown falls from
  $44,849 to $37,444, so its pre-lockbox ROC at $30k rises (60.3 -> 72.1).
  But it earns less in both stretches as run, and the lockbox reads 163.6 against 164.8 at $30k.
  Both lockbox drawdowns are the same June ENGU-Q stretch. **#463 is adopted as it is.** Run #468
  reproduces the local read to the dollar.
- **Against #366 (re-run #460), #463 is better on every read of the new yardstick.** It wins ROC at $30k and
  Sortino in both stretches. It clears the minimums: well over 100 walk-forward and 50 lockbox trades, and the
  lockbox stays profitable without its biggest trade. That trade is ENGU-Q's 2026-05-12 exit,
  $91,152 of $273,609.
- **What changes on paper.** The nightly book figure = ORB #234 + ENGU-Q #335 + 3 ES of TTM #369 (#459) +
  NOISE #422, at one contract each for the NQ legs. It had still been reading #371 (ORB + ENGU-Q #309 +
  TTM). NOISE #422 is a new paper leg; NOISE #304 keeps running beside it as its control.
- **Dropped:** the staged #397 flip. Branch `stage/adopt-397` is not applied, and
  `docs/BOOK_397_ADOPTION_STAGED.md` is marked DROPPED.

### 10m. The candidate books re-run on the FIXED TTM files (2026-09-28)

**What.** The TTM chat found a stop bug: every structural-stop TTM file booked an entry-bar exit at a price
the bar never traded when the open gapped past the stop. The trades hit were all profits, 17 of 354 on #369.
It is fixed on main in b3242e77. TTM legs #369, #428 and #455 are VOID; the fixed legs are re-validated as
#459 (#369) and #458 (#455), both PASS. Every book below was re-queued with its job legs verbatim on the
fixed files. The runner equals this chat's local re-read to the dollar on all seven, and every ENGU-Q leg is
the roll-corrected paper leg, valued daily.

| re-run | book | whole net, old -> fixed | ROC %/yr pre / lockbox | pre DD (valued daily) | lockbox DD at close / valued daily | lockbox Sortino | lockbox ROC without the ENGU-Q trade | the same at the WF-set $30k size | clause 5 vs #449 |
|---|---|---|---|---|---|---|---|---|---|
| **#466** | #457 (#456 + NOISE fixed tilts) | $2,014,255 -> $1,868,355 | 105.2 / 284.5 | $34,517 | $30,051 / $49,475 | 5.53 | 193.3 | 168.0 | PASS |
| **#462** | #456 (r61 roll-safe combo) | $1,786,012 -> $1,640,112 | 92.0 / 254.7 | $32,826 | $27,310 / $49,475 | 5.26 | 163.5 | 149.4 | PASS |
| **#465** | #450 (#397 + TTM R347) | $1,614,411 -> $1,468,511 | 80.6 / 254.4 | $34,449 | $27,797 / $49,855 | 5.48 | 163.1 | 142.1 | PASS |
| **#464** | #448 (#366 + TTM R347) | $1,631,189 -> $1,485,289 | 81.7 / 255.4 | $37,444 | $27,506 / $49,855 | 5.43 | 164.2 | 131.6 | PASS |
| **#463** | #449 (#396 + NOISE #422) | $1,778,706 -> $1,632,381 | 90.2 / 273.8 | $44,849 | $27,506 / $49,855 | 5.65 | 182.6 | 122.1 | - |
| **#461** | #437 (= #397, staged) | $1,620,275 -> $1,473,950 | 80.8 / 256.3 | $41,853 | $27,771 / $49,855 | 5.51 | 165.1 | 118.3 | FAIL |
| **#460** | #435 (= #366, adopted) | $1,548,011 -> $1,447,529 | 79.4 / 252.1 | $41,736 | $28,066 / $49,855 | 5.32 | 160.9 | 115.6 | FAIL |

**The ranking, restated** (sorted by the concentration-cleaned lockbox at matched risk; no decision taken):
- **#457 leads on every read**, but its lockbox gain from the NOISE tilts is not clean. It is followed by
  **#456** and the two R347 books (#450, #448), and then by #449, #437 and #435.
- **#397's case has mostly gone.** Its roll-corrected twin (#437) now reads 80.8 / 256.3 %/yr against #366's
  (#435) 79.4 / 252.1. Much of the gap the TTM #369 swap bought was the stop bug. It still fails clause 5
  against #449.
- **On the round-61 four-clause bar vs #449** (common windows, valued daily), no book clears. #456 and #457
  clear clauses 1-3 and fail clause 4 (lockbox drawdown at the WF-matched size).
- **Staged flip:** the #397 flip (docs/BOOK_397_ADOPTION_STAGED.md) is still ready. Its evidence is now
  weak; the choice is the owner's.

### 10b. An open item this audit turned up: two day-stamping rules disagree

The recorded finding put the baseline's worst stretch in **2020-02-21..2020-03-25 at $34,903**; the
stored BOOK runs record **2022-04-27..2022-05-24 at $34,329**. Same legs, same params, same master,
**net identical to the cent**. The difference is how a trade is stamped to a day. `augur_engine/
book.py` pools with `np.asarray(index, dtype="datetime64[D]")`, and numpy truncates a US/Eastern
index *in UTC*, so a 24h leg's trade exiting at or after 20:00 ET (19:00 in winter) is booked on the
NEXT day; the TTM driver used the ET calendar day. **227 of the ENGU-Q ETH leg's 1,179 exit days**
carry their dollars on a different day under the two rules. Day-session legs are unaffected.

Neither rule is the CME trade-date convention (which rolls at 18:00 ET). Nothing was changed on
this account: every stored book run is on the engine's rule, so moving it would move every recorded
book drawdown at once. `tools/book_dd_attribution.leg_daily(..., day_mode="session")` computes the
other one on demand, and section 0 of the audit prints both. **The finding does not depend on it —
under BOTH rules the TTM leg traded the stretch zero times.**

**MADE VISIBLE 2026-09-09** (owner: *"make the day-stamping rule an owner decision I can see"*).
Every book run now scores BOTH readings and stores them on `book.day_rule`: the rule that produced
the result (`utc_truncated` — unchanged), the session-day net, drawdown and worst stretch, and two
flags, `net_differs` and `drawdown_differs`. COMPARE ▸ RUNBOARD's BOOKS row prints the second
reading beside the first **whenever they differ**, which is never for a book that only trades the
day session. Verified by re-running run #337's own legs: engine rule **$34,329.21**
(2022-04-27..05-24), session rule **$34,903.00** (2020-02-26..03-25), **net identical to the cent**.

**Nothing was switched, and that is the point.** Every stored figure is still the engine rule,
because changing it would move the recorded drawdown of every book at once and make old and new
runs incomparable. What changed is that the disagreement now sits on the row instead of in this
file. Adopting the session rule is not a patch — it is a re-scoring of every stored book, and it
should be decided as that. **Owner call.**

Guards: `tests/test_book_worst_stretch.py` pins the contract (both rules must report the SAME net —
a restamp moves trades, it never loses them — and a restamp that carries a loss across a peak must
raise `drawdown_differs`); `tools/runboard_books_probe.py` pins that the row prints the second
reading when the rules differ, and prints nothing for an older book that carries no block.

---

## 9. 2026-08-18 — the headline net on a book run was 20x too large (FIXED, forward-only)

### What the headline field on a book run means

A book run's headline net — the field `best_pnl_usd`, which is what the Past Runs card and
the run-report KPI row print — is **the pooled book's net dollars over the stretch BEFORE
the lockbox**. Not the whole window, and not points. Two separate things about it were being
misread, and only one of them was a bug.

**The bug (now fixed).** A book result arrives at the save layer *already denominated in
dollars*, because `augur_engine/book.py` converts each leg's trades with that leg's own
contract multiplier during pooling (a book can mix instruments, so there is no single
book-wide multiplier). The save layer in `api/runner.py::_persist_run` did
`pnl_usd = best.total_pnl * mult` — the ordinary points-to-dollars conversion — which for a
book multiplies a second time. The web app's "＋ RUN A BOOK" button always passed `mult:1`
and was therefore always correct. A book queued by a script that wrote the job doc straight
into Firestore — which is how `tools/queue_t8_books.py` did it — omitted `mult` and fell
through to the runner's default of **20**.

**The scope (by design, not a bug).** `best` deliberately carries the PRE-LOCKBOX stats,
matching the convention a validate run uses for `best_pnl_usd`: the headline describes the
stretch that is *not* the holdout. The whole-window total lives in `book.whole` and is what
`tools/t8_noise_book.py` prints.

### The arithmetic, on the actual saved run documents

Divide each stored headline by exactly 20 and it lands on `book.pre_lockbox` to the cent:

| Run | reported net | ÷ 20 | `book.pre_lockbox` net | reported max DD | ÷ 20 | `book.pre_lockbox` DD |
|---|---|---|---|---|---|---|
| 238 | $10,944,883.00 | $547,244.15 | $547,244.15 | $547,690.40 | $27,384.52 | $27,384.52 |
| 258 | $10,629,181.80 | $531,459.09 | $531,459.09 | $638,890.60 | $31,944.53 | $31,944.53 |
| 261 | $19,684,006.20 | $984,200.31 | $984,200.31 | $1,121,803.60 | $56,090.18 | $56,090.18 |
| 262 | $12,980,663.20 | $649,033.16 | $649,033.16 | $1,163,416.80 | $58,170.84 | $58,170.84 |
| 263 | $10,869,453.00 | $543,472.65 | $543,472.65 | $535,918.80 | $26,795.94 | $26,795.94 |

The error factor is a **constant 20**, on every run, on both net and drawdown. It only looks
like a variable "roughly 15x" when the headline is compared against the WHOLE-window book
total this document reports, because that comparison stacks the constant 20x on top of the
pre-lockbox scope fraction, which varies with how much of each window the lockbox covers:

```
#238  10,944,883 / 716,089   = 15.28x  = 20 x 0.7642
#258  10,629,182 / 756,729   = 14.05x  = 20 x 0.7023
#261  19,684,006 / 1,245,994 = 15.80x  = 20 x 0.7899
#262  12,980,663 / 850,825   = 15.26x  = 20 x 0.7628
#263  10,869,453 / 770,619   = 14.11x  = 20 x 0.7052
```

The harness is the correct number. `tools/t8_noise_book.py` reproduced run #238's saved book
block to the dollar, and every one of those book blocks is intact in the run documents.

### Blast radius — what was wrong and what was always right

Wrong (all inflated by exactly 20): `best_pnl_usd`, `best_dd_usd`, `best_pnl_per_day`, the
stored `multiplier` field (20, where a book has no single multiplier), and any MAR derived
from that net-and-drawdown pair. `best_pnl_pts` is labelled "pts" but holds dollars.

**Never wrong:** everything that reads the book's own pooled block — `book.whole`,
`book.pre_lockbox`, `book.lockbox`, `book.legs[].net`, `book.slices`, the equity curve
(stored in real dollars), `validate.lockbox`, `best_pf`, `best_trades`, `best_win_rate`, and
the PASS / WEAK / FAIL verdict. The verdict is computed inside `book.py` from the lockbox
P&L, the lockbox profit factor and the eight-stretch consistency count, and never touches the
headline, so **no pass/fail gate depended on the broken field**. That is why run #261 carries
a correct $261,794 lockbox next to a $19.7M headline in the same document.

In the web app, the RUNBOARD **BOOKS** tile and the 1E matrix are book-aware — they read the
book block directly and always showed the truth. The inflated field is what fed the **Past
Runs** card, the run-report headline KPIs, the COMPARE tab's curve scaling
(`equity × multiplier`), and the funnel's net and MAR ranking. Anyone reading run #261 off a
Past Runs card saw $19.7M for a book that made $984,200 pre-lockbox.

### The fix (web v73.135)

`api/runner.py::_persist_run` now pins `mult = 1.0` whenever the result carries a `book`
block, so the unit is a property of the RESULT rather than of whoever wrote the job doc.
`tools/queue_t8_books.py` also sets `mult:1` explicitly. Regression test:
`tests/test_book_net_units.py` — a book stays in dollars for any job `mult`, and a normal
points-denominated run still converts.

**Effective from the next book run onward.** Historical run documents were deliberately NOT
rewritten. To read runs #238, #258, #261, #262 and #263 as saved, divide their headline net,
drawdown and dollars-per-day by 20 — or just read the BOOKS table on the RUNBOARD, which was
right all along.

**Open recommendation, not shipped, needs an owner call:** the web app could prefer the book
block over `best_pnl_usd` for any run carrying one, which would make those five historical
cards read correctly everywhere without touching a stored document. It was left out on
purpose because it changes numbers the owner has already seen on already-saved runs.

### The read-side display correction (web v73.142, 2026-08-18)

The five affected documents were never rewritten. Instead the web app corrects them **as it
reads them**, in `_bookUnitsOnRead()`, applied once in the Past-Runs Firestore listener — the
single place run documents enter the app — so every view downstream (Past Runs card, run
report headline, COMPARE curves and funnel ranking, the RUNBOARD strategy list) agrees
automatically.

**How a legacy run is detected — from the data, never from a run number or a date.** Every
book run carries its own pooled block, and that block was always correct. The app asks which
of two things the stored headline equals:

* it equals `book.pre_lockbox.total_pnl` (falling back to `book.whole.total_pnl`) → saved
  correctly, left completely alone;
* it equals that same figure **times the stored `multiplier`** → saved before the fix, divided
  back down by that multiplier.

Anything else — no book block, no pooled net, `multiplier <= 1`, or a headline matching
neither branch — is left untouched rather than guessed at. Tolerance is
`max(1, |pooled x mult| x 1e-6)`. Run **#204** (saved with `mult:1`) takes the first branch and
is a real, saved control for it; **#238 / #258 / #261 / #262 / #263** take the second. Every
future book run saves with `mult:1` and therefore matches its own block, so it is never touched.

**Adjusted:** `best_pnl_usd`, `best_dd_usd`, `best_pnl_per_day`, and `multiplier` (pinned to 1,
which is what the engine now writes). Pinning the multiplier is what fixes the COMPARE equity
scaling and the RUNBOARD `_mcOf`-scaled aggregates, since those multiply the already-in-dollars
curve. Every MAR / net-per-drawdown figure in the app is derived from the net-and-drawdown pair,
so it follows automatically.

**Deliberately NOT adjusted:** the `book` block itself, `equity`, `validate.lockbox`, `best_pf`,
`best_trades`, `best_win_rate` and the verdict. The RUNBOARD **BOOKS** tile and the 1E matrix
read `r.book.*` directly and were always correct — correcting them here as well would make them
20x too *small*. They are untouched because the correction only ever rewrites top-level headline
fields.

**Transparency:** a corrected run shows a small amber "⚖ units corrected" chip in the Past Runs
row, on the RUNBOARD strategy list and in its report header, whose hover text says what was
adjusted and what was left as saved.

**Verified 2026-08-18:** the predicate was run over every run document — the five legacy books
classify as legacy and their corrected net and drawdown reproduce their own `book.pre_lockbox`
to the cent; #204 classifies as already-correct and is untouched; runs #226/#230/#234/#259/#260
(no book block) are untouched. `tools/preflight_boot.py` PASS before and after.
