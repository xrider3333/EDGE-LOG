# FRONTIER scoping doc - the BOOK question, scoped deeply (2026-10-05)

Owner standing order addendum 2 (10-05 12:45 MST, "push and scope out deeply this time"), FRONTIER's scope per MANAGER #81: the leg mix
under the yardstick (with the 71-look caveat), the seat pipeline for monthly stock baskets, and stock-event families as seats. This is a
scoping doc, not a pre-registration: nothing below has been run, and every item becomes its own prereg, reviewed by MANAGER, before any
number. Owner decisions b / c / d (BOOK.md 10aa) are in force: the walk-forward selects, forward lines are harm monitors, adoption is the
owner's call on walk-forward plus mechanism.

## 0. What the book needs, and what today taught

- **The map (MDL r1, docs/MDL_MAP_R1.md).** A new seat lifts #463 if it earns about $15k a year at a $30k drawdown of its own and does not
  fall with #463 in #463's drawdown weeks. A seat that EARNS in those weeks helps at under $5k a year. A seat that falls with the book
  cannot help at any realistic size.
- **Market-stress hedges do not earn the seat.** Fund trend (Q9), long volatility (Q12), safe havens (Q13) and the bull steepener (Q15) each
  help in March 2020 and pay for it elsewhere. #463's other drawdowns (2019, 2022, 2025) are its own legs giving back in orderly markets
  (BOOK.md 10v-10x). The VIX-inversion state family is closed.
- **The one class that earned in #463's drawdown weeks across episodes is a MONTHLY cross-sectional stock basket.** STRATEGY-BEATING's
  RESMOM r1 (residual 12-1 momentum, the 500 largest US stocks, 50/50 dollar-neutral, monthly, next-open fills): dead standalone (7.1 at
  $30k), but sized by volatility (0.264 x) it lifts #463's walk-forward 93.8 -> 120.8 (Sortino 3.92), earns $106k over the 460
  drawdown days in 18 of 28 episodes ($74k outside March 2020, $59.9k without its best episode), correlation -0.06, beating all 500
  random-name draws. Its forward line (#463 + 0.264 x RES) opens from the 2026-10-30 rank as a harm monitor.
- **Why monthly.** Every daily or weekly stock family died on cost today: SIPORB (edge under a cent a share), ATTN (+7 bps a night under
  a 10 bps round trip), DDW L1 / L2 (break-even at 10 bps; reversal under 15 bps), XGAP (the whole loss was cost). A monthly basket pays
  the round trip 12 times a year; published cross-sectional premia are hundreds of bps a year.
- **Realistic route.** Since 2016, single US large-cap anomalies run Sharpe roughly 0.3-0.8 after costs, i.e. ROC at $30k about 5-12 -
  under the standalone 15. So the route that matters is the EARNER / book-add route (house line #45), judged INCREMENTAL over the RESMOM
  line, not "a new standalone leg".

## 1. Rules that bind every item (beyond the house's)

1. Walk-forward only, 2016-07-01 .. 2025-06-29. Stock data starts in 2016, so there is no 2010-16 tuning block: say so in every prereg,
   and print the regime halves 2016-21 / 2022-25 instead.
2. Point-in-time universe exactly as DDW r1 / RESMOM [T2] (prior raw close >= $10, the 500 largest by trailing dollar volume, registered
   split handling, gap scan, Alpaca inactive names kept), the SIPORB / RESMOM SIP daily cache; no new pull unless the item says so.
3. Next-open fills; costs 5 bps a side base, stress 10 and 20; borrow 0.25%/yr base, stress 1% and 3%.
4. Family null = random-name baskets of the same size from the same eligible pool (RESMOM's), statistic = the MAX over the family's cells.
5. Power line first (tools/power_line.py): with ~8.5 WF years a 12-cell family is under-powered; cells are kept to 2-4 per family.
6. Diagnostics every Stage A prints (addendum 2): event-time path, regime halves, cost curve 0 / 5 / 10 / 20 bps, per-year and
   per-episode rows (#463's 28 drawdown episodes), long vs short side, beta to ES on #463's drawdown days.
7. The book-add report is sized by volatility (25% of #463's daily SD over the first two WF years) and judged INCREMENTAL over the
   RESMOM line: #463 + 0.264 x RES is the reference, and a candidate must add to THAT (its own drawdown-day dollars net of what RESMOM
   already earns there, and its correlation to RESMOM printed). The 71-look band and the Q16 forward power line are printed beside it.

## 2. (A) The leg mix under the yardstick - mostly closed; two planning items remain

What is settled: re-weighting has no forward skill (book round 56); trading more of ORB, ENGU-Q or TTM lowers the walk-forward return
(MDL r1); NOISE upsizing is the only plain re-size that lifts both stretches, and the owner kept NOISE at 1.0x (10aa); every weight change
is another look at the same walk-forward, whose 71-look band runs +30% (TTM seat) to +78% (ORB + ENGU-Q) (10z); a forward year cannot
decide a drawdown-shaped gain (10y). **So no further weight grid on the four legs is proposed.**

| # | item | question | data | output | rank |
|---|---|---|---|---|---|
| A1 | Seat capacity | How much volatility share can a near-zero-correlated, drawdown-week-earning seat take before the book's ROC at $30k peaks, and how many such seats fit? (RESMOM at 2x already pulls the book to 88.) Synthetic seats on #463's real rows, MDL r1's machinery - a planning curve, no new real look | held (MDL cache) | the c-curve and the "N seats at share s" table the stock seats are sized from | 1 |
| A2 | The incremental yardstick | Build #463 + 0.264 x RES once, at parity with STRATEGY-BEATING's report: WF figures, the drawdown-day profile, what is LEFT unearned in each of #463's 28 episodes after RESMOM | resmom_cells_daily_wf.csv (exists) | the reference line and the "residual drawdown days" every basket seat is scored on | 2 |
| A3 | Leave-one-out restated | Each leg's contribution under the yardstick with the 71-look caveat (MDL r1 numbers, no new run) | held | one table in the scoping review | report |

## 3. (B) Monthly stock baskets as seats - the mechanism list

All: 500 largest, dollar-neutral (or beta-neutral where stated), monthly rebalance at the month's last close, next-open fills, the rules
in section 1. "DD-week" = a published or plausible reason to earn while #463's legs give back in orderly markets.

| # | mechanism (literature) | data | dead-list cross-check | map placement / why it might earn in #463's drawdown weeks | expected size since 2016 | rank |
|---|---|---|---|---|---|---|
| B1 | Betting against beta / low volatility in single stocks (Frazzini-Pedersen 2014; Ang-Hodrick-Xing-Zhang 2006) | held (price only) | TV BAB r1 on 11 equity FUNDS: dead standalone (-3.0) but earned in #463's drawdown days (+17.8k, above the null, holds without the best episode) - the stock form is the published, stronger one | DD-week earner (short high beta) | Sharpe ~0.5, crash-prone in junk rallies (2020 Q2, 2021) - check | 1 |
| B2 | Same-calendar-month seasonality (Heston-Sadka 2008) | held | never tested | independent of momentum; earner unknown | Sharpe ~0.4-0.6 historically; weaker recently | 3 |
| B3 | 52-week-high momentum (George-Hwang 2004) | held | momentum family: judged INCREMENTAL over RESMOM | likely same days as RESMOM | high correlation to RESMOM expected | 6 |
| B4 | Lottery / MAX effect (Bali-Cakici-Whitelaw 2011) | held | overlaps B1 | DD-week earner (short lottery names) | small in large caps | 8 |
| B5 | Monthly short-term reversal, beta-neutral (Jegadeesh 1990) | held | DDW L1 weekly reversal: earned, but long last week's losers = long beta in crashes (wrong weeks) | only a beta-neutral form could fix L1's flaw | cost-sensitive | 9 |
| B6 | Gross profitability / quality (Novy-Marx 2013; Asness-Frazzini-Pedersen QMJ 2019) | PUBLIC NO KEYS: SEC EDGAR XBRL company facts, point-in-time by filing date (TV scout catalogs first) | never tested | flight-to-quality = the classic sell-off earner | Sharpe ~0.4-0.7 | 2 |
| B7 | Net share issuance (Pontiff-Woodgate 2008; Daniel-Titman 2006) | EDGAR XBRL shares outstanding | never tested | standalone-ish; earner unknown | robust, Sharpe ~0.4 | 7 |
| B8 | Asset growth / investment (Cooper-Gulen-Schill 2008) | EDGAR XBRL | never tested | earner unknown | weaker since 2010 | 10 |
| B9 | Value, book-to-market (Fama-French 1992) | EDGAR XBRL | never tested | FELL in March 2020 and 2016-20: likely the wrong weeks | poor since 2016 | 12 |
| B10 | Short interest (Rapach-Ringgold-Zhou 2016) | PUBLIC NO KEYS: FINRA twice-monthly short interest | never tested | short-side crowding unwinds in sell-offs: mixed | moderate | 5 |
| B11 | Industry momentum within stocks (Moskowitz-Grinblatt 1999) | held price + SIC codes from EDGAR | SECTOR r1 (ETF sector momentum 2/24) dead - partly overlaps | same days as RESMOM likely | moderate | 11 |
| B12 | Information discreteness / frog in the pan (Da-Gurun-Warachka 2014) | held | momentum refinement: incremental over RESMOM only | same as B3 | small increment | 13 |
| - | Analyst revisions, ownership breadth, options-implied signals | no free source | - | - | - | out |

## 4. (C) Stock-event families as seats

Event-time holds of weeks to months, so each name trades a few times a year; timing from public filings, no keys.

| # | event mechanism (literature) | event data | dead-list cross-check | map placement | expected size | rank |
|---|---|---|---|---|---|---|
| C1 | Post-earnings drift by the announcement return (Chan-Jegadeesh-Lakonishok 1996; Brandt et al. 2008) - long the top, short the bottom 3-day reaction, hold ~60 sessions | EDGAR 8-K Item 2.02 filing timestamps (public); reaction from the held price cache | never tested (the 09-09 event scan was futures calendars) | the largest published event drift; earner unknown | Sharpe ~0.5-1 historically, smaller in large caps | 1 |
| C2 | Earnings-announcement premium (Frazzini-Lamont 2007; Savor-Wilson 2016) - long names announcing next month, short the rest, monthly | same EDGAR dates (expected from each firm's prior cycle) | never tested | monthly, market-neutral; earner unknown | ~ 50-100 bps a month spread published | 2 |
| C3 | Opportunistic insider purchases (Cohen-Malloy-Pomorski 2012) | EDGAR Form 4 (public) | never tested | long-side drift; low turnover | moderate, long side | 3 |
| C4 | Activist 13D filings (Brav-Jiang-Partnoy-Thomas 2008) | EDGAR SC 13D (public) | never tested | long-only drift; few events in the 500 largest | small N | 6 |
| C5 | Dividend initiations / omissions (Michaely-Thaler-Womack 1995) | Alpaca corporate-actions calendar (RESMOM addendum R1 already uses it) | never tested | small N in large caps | small | 7 |
| C6 | S&P 500 additions / deletions | needs a reliable historical change list | the index effect has shrunk since ~2010 | - | small | 8 |
| C7 | Buyback announcements (Ikenberry-Lakonishok-Vermaelen 1995) | 8-K text parsing | never tested | - | moderate; parsing cost high | 9 |

## 5. The ranked queue (never below three live preregs)

1. **A2 incremental yardstick** (one evening; everything else is scored on it) and **A1 seat capacity** (planning curve).
2. **B1 stock BAB / low volatility** - held data, two cells (beta-neutral 50/50; volatility-sorted), the fund version already showed the
   drawdown-week shape.
3. **C1 post-earnings drift by announcement return** - needs the EDGAR 8-K index (TV catalogs it; MANAGER's wrapper pulls, provenance
   photographed); two cells (hold 20 / 60 sessions).
4. **B6 quality / profitability** - the biggest data build (XBRL point-in-time); queued behind the TV catalog.
5. **B2 seasonality**, **C2 announcement premium** (shares C1's dates), **B10 short interest**, then the rest in the table order.

## 6. Shared machinery - build once, with STRATEGY-BEATING

One stock-seat harness, reusing RESMOM's (point-in-time universe, monthly engine, costs and borrow, random-name family null, the
volatility-sized book-add report, the diagnostics pack) rather than a FRONTIER fork; FRONTIER adds the incremental-over-RESMOM yardstick
and the seat reads. Lane split to agree with STRATEGY-BEATING through MANAGER: they keep standalone stock research; FRONTIER runs the
seat reads and the book-level items. Data: EDGAR (8-K index, Form 4, XBRL company facts) and FINRA short interest are public with no
keys; each pull gets URL / time / size / sha256 provenance and is used as a photograph (memory: pull provenance).

## 7. What would change this plan

- A2 shows RESMOM already earns in nearly all of #463's residual drawdown days -> seats must then be standalone-strong, and the queue
  re-ranks toward B6 / C1 (the published high-Sharpe items).
- A1 shows the book saturates at one seat -> the queue becomes "replace RESMOM if something is better", judged forward.
- Any seat that passes is a forward HARM-MONITOR line plus an owner question - never an adoption (10aa).
