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
- **Open oddity, routed to STRATEGY-BEATING:** on the drawdown days RES moves against #463 day by day (-0.153) but slightly WITH it
  week by week (+0.078; the generator's seats read -0.050). A one-day stamp lag between #463's UTC days and stock closes would do this.

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
