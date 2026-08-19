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
