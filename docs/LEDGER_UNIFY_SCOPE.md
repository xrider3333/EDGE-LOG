# LEDGER unify - scope (2026-10-02)

Scope only. Nothing here gets built until the owner approves it.
Owner ask (2026-10-01, via MANAGER): "make the HOME tab (rename as LEDGER?) a consistent UI between the REAL, NT8 and WEBULL tabs, and potentially any improvements".
Written by TRADING-LOG from the live code (web v73.969) plus the two paper-board inventories:
`C:\EdgeLog\manager\nt8_paper_board_inventory.md` (PAPER-NT8) and `C:\EdgeLog\manager\ledger_unify_1001\WEBULL_PAPER_board_inventory.md` (PAPER-WB).
Layout facts come from the code, not from screenshots. Step 0 of the build takes the real screenshots.

## Summary

- The three boards show the same kinds of things (a money number, a curve, stats, a trade list, a trade view), but each was built on its own and they share almost no layout code, so the same idea looks and behaves differently on each.
- The proposal is one layout with the same parts in the same places on all three boards, and each board keeps its own special sections folded underneath.
- The rename is cheap and safe if only the button text changes to LEDGER and every internal name stays as it is.
- The most valuable fixes to do along the way are: one rule for which day a trade belongs to, one range control counted from today, NT8 loading all its trades, NT8's hidden strategies, and the trade list near the top on a phone.
- The build is about 12 small ships, REAL first, each checked in the owner's Chrome on a laptop (1366x768) and a phone (375 wide) in both themes, and three owner decisions come first (see section 6).

---

## 1. Today's differences, element by element

REAL is your real trades (NinjaTrader and Webull accounts). NT8 PAPER is the NinjaTrader shadow strategies on futures. WEBULL PAPER is the QQQ paper book run by the cloud box.
"Full viewer" means the big candle chart window that all three boards already share.

| Element | REAL | NT8 PAPER | WEBULL PAPER |
|---|---|---|---|
| How fresh the data is | Live: updates the moment a trade syncs. | Read once per visit; REFRESH re-reads. | Live: the box rebuilds one status record every few seconds. |
| How many trades it holds | All of them. | Only the newest 500 of 965, so "All" starts around 09-15, not 08-11. | At most 500; the oldest are dropped. |
| Page shape on a laptop | One column, at most 1080 px wide. | Two columns: main plus a 380 px strategy rail on the right (drag to resize). | Two columns: main plus a 340 px strategy list on the right, at most 1320 px wide. |
| Page shape on a phone | One column. | One column below 1080 px. | One column below 1100 px. |
| Top row of tabs | The ACCOUNT switch (ALL / each broker) sits at the right of the tab row. | No ACCOUNT switch, so the tab row changes width when you switch boards. | Same as NT8. |
| Big number | Account balance (EQUITY view, the default) or running P&L (P&L view) for the chosen account. | Net P&L of the strategies switched on, for the chosen range. | Book P&L since the start, including open trades. |
| Line under the big number | Change over the range, in dollars and percent, with deposits taken out. | "+$X today", range, trade count, "N of M strategies". | "+$X today" (no percent), a since-start line, and an amber "broker made $X" line when some trades never filled at Webull. |
| Status chips next to the number | Sync badges for the NinjaTrader and Webull imports. | Live-in-NinjaTrader count, open or flat, gate up/down, auto-recover switch, REFRESH. | A status strip under the chart: paper mode, market, feed, ratio, "updated N s ago", plus alarm chips only when something is wrong. |
| Range control | 1W, 1M, 3M, YTD, 1Y, ALL, counted back from today; it drives the number, chart, stats and trade list. | 1W, 1M, All counted back from the newest trade, plus a separate Today / All time switch in the rail; the rail totals always stay all-time. | 1W, 1M, 3M, ALL counted back from the newest trade; it only crops the chart, while the number and stats stay all-time. |
| Equity chart | One line, green when up and red when down, with an EQUITY / P&L toggle; one point per trade, not per day; no dates and no price scale. | A bold total line plus one faint line per strategy, a price scale on the right and up to 7 dates. | A TOTAL line plus one line per strategy with legend toggles, amber columns on caveat days and version markers. |
| Reading the chart | Mouse only; moving the mouse changes the big number. | Mouse and finger; moving changes the big number. | Mouse only; a readout box shows the day. |
| Chart size | A fixed 260 px tall box; on a phone the line probably draws much shorter inside it (to confirm in step 0). | 30% of the screen height (180 to 380 px). | 300 px on a laptop, 220 px on a phone. |
| Headline stats | 4 tiles: Win rate, Profit factor, Max DD, Today. | 10 cells: Trades, Win rate, Profit factor, Avg trade, Avg win, Avg loss, Best day, Worst day, Max drawdown, Green days. | 4 tiles: Win rate, Profit factor, Trades, Max DD. |
| More stats | MORE STATS fold with Returns, Risk, Mix and Account (including vs SPY). | None. | "More stats" fold with Ratios, Performance and Risk. |
| What a $0 trade counts as | Not a win in the stats, but the WINS filter chip and BY DAY rows count it as a win. | Neither a win nor a loss. | A loss. |
| Calendar | None (it moved to ANALYTICS). | Month calendar with a WK totals column; clicking a day selects that day's trades. | Month calendar with hatched caveat days; tapping a day scrolls to the trade list. |
| Which day a trade belongs to | The trade's date. | The day it was entered (a week-long hold lands on its entry day). | The day it closed (New York time). |
| Strategy or account list | The ACCOUNT switch in the tab row only. | A rail with one row per strategy (live dot, name, sub-line, net, on/off switch) and filters (family, raw/ML, baselines, archived). | A list with one row per strategy (side, small curve, P&L, live position line); no switches. |
| Trade list views | FEED (BY TRADE or BY DAY) or TABLE, and the TABLE has SIMPLE or FULL. | One table. | List or Table (the choice is forgotten on reload). |
| Trade list columns | SIMPLE: date, in time, symbol, side, contracts, points, net, SCORE, POINTS, grade, setup, notes, CHART, edit, delete. FULL adds out time, hold, prices, gross, fees, account balance, timeframe, tags and 9 optional extras. | Strategy, side, entry to exit time, entry to exit price, hold and points, SLIP, delta $, $, running total, ENGINES, CHART. | 16 columns in Table view, with chips for fill parity, book-only and P&L source. |
| Search and filters | Search box, 7 chips (ALL, LONG, SHORT, WINS, LOSSES, FUTURES, STOCKS), and sort or filter menus on the column headers. | The strategy switches and rail filters; sortable headers. | None. |
| Day headers in the list | Yes in the feed (day net); none in the table. | Yes, with the day total and trade count. | None; the date sits under each row. |
| Rows shown | All in range. | 200 at most ("showing 200"). | 50 at a time with SHOW MORE. |
| Clicking a trade | Opens the trade panel. | Selects the row (click, drag, shift-click) so ALL CHARTS can open several charts; the CHART cell opens the full viewer. | List: opens the trade sheet. Table: opens a drawer inside the table. |
| Trade panel | Slides in from the right, 440 px wide; full width on a phone. Holds the chart, POINTS, IGNORE IN METRICS, 22 detail rows, tags, notes, and EDIT, SNAPSHOT, OPEN IN TV, DELETE. | None. | Slides up from the bottom, up to 720 px wide and 86% of the screen tall. Holds the chart and the fill breakdown. |
| EL chart in the panel | 1M or 10S candles with EXPAND to the full viewer (EXPAND hidden on a phone). | Not in a panel; the CHART cell opens the full viewer directly. | About 20 bars either side with four layers of marks (signal, backtest fill, book in/out, Webull attempts) and EXPAND. |
| OPEN IN TV | Yes. | No. | No. |
| TradingView snapshot link and PASTE box | Yes. | No. | No. |
| POINTS (point score) | Yes, in the table and the panel. | No. | No. |
| SHOULD HAVE TRADED | Shipped in v73.971: setups you did not take, under the ledger, kept apart from P&L, with EL chart and points. | No. | No. |
| Notes, grade, setup, tags | Yes, editable in place. | No. | No. |
| Export | Import / export sits behind the settings gear. | None. | CSV button on the trade list. |
| Board-only sections | Deposits strip, AI ASSESSMENT box, JOURNAL fold, NEW TRADE, ADD DEPOSIT, SCAN DUPLICATES, OPEN ALL. | NinjaTrader detail, cross-engine reconcile, gate audit, daily reports, capture health, data feed warning. | Account, System fold (status, orders, readiness, integrity), Rails, event timeline, model reference. |
| Money colours in the MONO theme | Follow the theme (green turns white, red turns grey). | Always green and red. | Follow the theme. |
| Phone: how far down the trade list starts | About two screens (estimate): the AI ASSESSMENT box, the toolbar and the 7 chips all sit above it. | About three screens: the full strategy rail sits above it. | About two screens: strategies, account and stats sit above it. |
| Phone: trade list width | SIMPLE drops columns as the screen narrows; at 375 px it keeps date, symbol, side, net, grade and edit, so the CHART icon disappears. | All 11 columns in a sideways scroll. | The Table view scrolls sideways. |

**What the table says in one line each:**

- The same idea gets a different name, position, size and rule on each board.
- Only the full candle viewer, a few small helpers (tiles, sparklines, saved preferences) and the download helper are shared today.
- The biggest behaviour gaps are the range control, the day a trade belongs to, and what happens when you click a trade.

---

## 2. One shared layout

### 2.1 The same parts in the same places

Laptop, top to bottom (main column on the left, list on the right):

1. **Board switch:** REAL · NT8 PAPER · WEBULL PAPER, unchanged.
2. **Hero:** a small label naming the board and its scope, the big number, a "today" line, a range line, and a status chip row on the right. Alarm chips go here on every board, so a problem is never hidden inside a closed card.
3. **Equity chart:** one chart component everywhere, with one point per day, a price scale on the right, dates along the bottom, a bold total line, optional faint lines per strategy or account with legend toggles, and scrub by mouse or finger that moves the big number.
4. **Range pills under the chart:** Today · 1W · 1M · 3M · YTD · ALL, counted back from today, driving the hero, chart, stats, calendar and trade list on every board.
5. **Stats strip:** the same four headline tiles everywhere (Win rate, Profit factor, Max drawdown, Trades), then one "More stats" fold with the same groups (Returns, Risk, Mix) plus one group of the board's own (Account on REAL and WEBULL, Strategy vs control on NT8).
6. **Calendar:** one month calendar everywhere (day money, a WK totals column, month total); clicking a day jumps the trade list to that day.
7. **Strategy or account list (right column):** one row style everywhere (dot, name, short sub-line, net, on/off switch), sticky on a laptop.
8. **Trade list:** one frame everywhere: a toolbar (count, search, filter chips, List or Table, remembered), day headers with day totals, the same common columns first (date, time in and out, symbol or strategy, side, size, points, net, running total, chart), then the board's own columns.
9. **Trade panel:** one panel everywhere, opened by clicking a trade: header (symbol or strategy, side, date, net), the compact chart with EXPAND, the point breakdown, the detail rows, then the board's own blocks and actions.
10. **Board sections:** each board's special sections become folds at the bottom, closed by default, each showing a one-line summary while closed.

Phone, top to bottom:

- The hero, the chart, the range pills, then the four stat tiles in a 2 by 2 grid.
- The strategy or account list shrinks to one line ("4 of 18 on · edit") that opens the full list as a sheet.
- The trade list starts within about one screen of the top, with five columns (time, symbol or strategy, side, net, chart) and the rest in the panel.
- The calendar, More stats and the board sections sit below the trade list, folded.
- The trade panel becomes a bottom sheet the full width of the screen.

### 2.2 The same rules everywhere

- **Range:** counted back from today in New York time, with Today · 1W · 1M · 3M · YTD · ALL.
- **Which day a trade belongs to:** the day it closed (owner decision 2, section 6).
- **A $0 trade:** neither a win nor a loss.
- **Colours:** one rule for money under the MONO theme (owner decision 8), and amber caveats always shown with a pattern as well as a colour so they survive MONO.
- **Screen sizes:** one set of breakpoints for all three boards: two columns from 1100 px, compact from 760 px, phone chart and sheet from 600 px.
- **Saved choices:** range, List or Table, SIMPLE or FULL, open folds and switches are remembered per browser on every board.
- **Escape hatch:** each step keeps the old layout reachable for one version by adding `?oldboards=1` to the address, the same way `?oldtabs=1` works today.

### 2.3 What each board keeps for itself

**REAL keeps:**

- The EQUITY / P&L toggle, deposits and withdrawals, and account balance after each trade.
- SCORE, POINTS, grade, setup, timeframe, tags and notes, all editable in place.
- The PASTE box for TradingView snapshot links, SNAPSHOT, OPEN IN TV, EDIT and DELETE in the panel.
- IGNORE IN METRICS, NEW TRADE, ADD DEPOSIT, SCAN DUPLICATES, OPEN ALL.
- The JOURNAL fold, and the SHOULD HAVE TRADED section (shipped in v73.971).
- The SIMPLE / FULL table choice.

**NT8 PAPER keeps:**

- One row per strategy with its matched control and the dollar gap, crowns and chips, and the forward versus backfilled split.
- The live NinjaTrader dot per strategy, the roster, demo cash and the auto-recover switch.
- SLIP, delta $ and the EL / NT / TV agreement chips on each trade.
- The nightly reconcile, the live gate state and the "did the gate do its job" audit.
- Capture health and the data feed warning.
- ROLL marks, the "incl. roll artifact" note and the look-ahead warning on ORB engine rows.
- Multi-select of trades to open a gallery of charts.
- The adopted book figure, which belongs here but is not shown yet (improvement 9).

**WEBULL PAPER keeps:**

- P&L of record (Webull fill first, book price second) with its source label on every row.
- Book-only trades: the BOOK ONLY chip, the amber "broker made $X" line and the chart swatch.
- Fill parity against the backtest (FILL GAP, CHECK FILL, NOT COMPARED) and the FILLS BEHIND BACKTEST alarm.
- The Robinhood-style hero from v73.891 to v73.894: the big total moves with the live price, and "today" counts the same book as the total.
- One account with netting: the OK / MISMATCH share check and internal crosses.
- The mode pill (PAPER, LIVE, OFF, HALTED, BLOCKED), the one-computer check, the feed heartbeat, KEEL state, the daily loss stop and breaker, and the readiness checklist.
- The four-layer candle marks in the trade panel.
- Shadow legs, if the owner wants them shown, in their own group that is never added to the account number.

---

## 3. Renaming HOME to LEDGER

**Recommendation:** change only the text on the button from HOME to LEDGER, and keep every internal name exactly as it is. The button text is made from the internal name today, so this is a one-line change to how that one name is printed.

**Why not rename the internal names too:** the internal name "home" is saved in every browser's last-view memory, is checked in about 34 places in the app, starts about 125 helper names and 120 page-element names, and is part of three saved settings. Renaming all of that buys nothing you can see and risks landing on a blank tab after a reload.

**What changes with the label-only rename:**

- The tab button reads LEDGER, and its tooltip and help text say LEDGER.
- The word LEDGER already means deposits and withdrawals in two places, so those get new words: the strip above the trade list becomes DEPOSITS, and the Settings button "CLEAR LEDGER" becomes "CLEAR DEPOSITS". Otherwise "CLEAR LEDGER" could read like "wipe all my trades".
- The CLAUDE.md vocabulary gains LEDGER in the same commit, because only the owner renames established terms.
- Five notes outside the app that name HOME are updated to say LEDGER: "HOME > WEBULL PAPER" in the Webull candle publisher and its probe, "HOME ledger" in the trade bars script, "HOME's MORE STATS" in the SPY daily script, and "TRADING LOG > HOME table" in the scoring routine notes.

**What stays as it is, and why that is safe:**

- **Saved settings in each browser** (last view, last board, SIMPLE/FULL, JOURNAL open, account choice, a held snapshot link): unchanged, so nobody's saved state is lost.
- **The `?oldtabs=1` escape hatch:** unchanged; it still shows the old tabs.
- **The four paper-board test probes:** they open the boards by internal name, not by the button text, so they keep working. No probe looks for the word HOME.
- **The paper EOD review routine and the other scheduled routines:** none of them names a tab, so nothing to change.
- **The CHANGELOG:** old entries keep saying HOME because that was the name at the time.
- **Other chats' past messages and MANAGER's notes:** they say HOME and stay as history; MANAGER should tell every lane the new name once.
- **Deployment scripts under `deploy/cloud`:** they say HOME only as the Linux home folder, which is unrelated.

**Risks of the rename:**

- **Phone tab row:** LEDGER is two letters longer than HOME, and the tab row was tuned to fit one line at phone width. Check it at 375 px; if it wraps, tighten the spacing.
- **Habit:** the owner and the other chats are used to HOME. MANAGER's one-line notice covers the chats.
- **Full internal rename (not recommended):** it would break saved views, the four paper probes and every jump into the trade list from ANALYTICS unless each one is migrated.

---

## 4. Improvements worth doing while unifying, ranked

Value and effort: S is about one working session, M is two or three, L is a week of sessions. The lane in brackets is the chat that owns that board.

1. **Add a test probe for the REAL board** (TRADING-LOG). Value high, effort S. Both paper boards have render probes that block a broken ship, but nothing checks REAL, which is where the owner spends the most time.
2. **NT8 loads every paper trade, not the newest 500** (PAPER-NT8). Value high, effort S to M. Today every all-time NT8 number quietly covers only about three weeks; the fix pages the read or keeps a running summary, and must watch the Firestore read quota.
3. **NT8's big number, bold line and strategy list agree** (PAPER-NT8). Value high, effort S. 31 of 47 strategies have no row and no switch, yet their trades count in the big NET, so the number and the line disagree; list them in a closed "Other / shadow" group with switches, or leave them out (owner decision 3).
4. **One rule for which day a trade belongs to** (all lanes). Value high, effort M. NT8 files a week-long hold on its entry day, so the calendar, Today, best and worst day and the nightly book figure all lean on the wrong day; use the closing day everywhere, or label entry-day figures plainly (owner decision 2).
5. **The trade list within one screen of the top on a phone** (all lanes). Value high, effort M. Fold NT8's strategy rail into one line, move REAL's AI ASSESSMENT into a fold, and show five columns with the rest in the panel.
6. **One range control counted from today** (all lanes). Value high, effort M. Today Webull's range only crops the chart, NT8 has two range controls that fight, and NT8 and Webull count back from the newest trade instead of today.
7. **Read the chart with a finger** (TRADING-LOG builds it once, all boards get it). Value medium, effort S. REAL and Webull charts only respond to a mouse today.
8. **REAL chart with one point per day, dates and a price scale** (TRADING-LOG). Value medium, effort S. Today a busy day and a quiet week take the same width and nothing on the chart says when.
9. **Show the adopted book figure on NT8** (PAPER-NT8). Value medium, effort S. It is written into every nightly report but the board never shows it; the "BLEND $" column is the old ORB plus ENGU-Q baseline, not the book.
10. **Warnings in the hero, not in closed cards** (PAPER-NT8, PAPER-WB). Value medium, effort S. A dead NT8 runner can show green chips while the only warning sits in a closed card.
11. **REAL says "YESTERDAY" for today's trades after 8 pm New York time** (TRADING-LOG). Value medium, effort S. The feed works out "today" from the UTC date; the stats tile already uses New York time correctly.
12. **One rule for a $0 trade** (all lanes). Value low, effort S. It is a win in one REAL filter, not a win in REAL's stats, a loss on Webull and neither on NT8.
13. **Every Webull money figure uses P&L of record** (PAPER-WB). Value medium, effort S. The strategy TODAY figure, the daily-stop bar and the CSV still use the book price; the daily-stop bar should show the breaker's own number.
14. **Calendar back on REAL** (TRADING-LOG). Value medium, effort S once the calendar is shared. Both paper boards have one and REAL does not (owner decision 4).
15. **Remember every view choice** (all lanes). Value low, effort S. Webull forgets List or Table on reload, and NT8 forgets its Today / All time choice and its sort.
16. **Fix stale wording** (PAPER-NT8, PAPER-WB). Value low, effort S. Examples are NT8's "TODAY" reconcile tab that can be yesterday, the guessed "5m · RTH" labels, the hand-typed FULL HISTORY table, and Webull's wrong Rails sentence and old model reference.
17. **Remove code the boards no longer draw** (all lanes). Value low, effort S. Examples are NT8's retired MATRIX and card layout and Webull's unused strategy cards and ratio toggle; do this last.

Already done and only listed for completeness: Webull's broker order file being cut to 100 rows is fixed on main and ships to the box.

---

## 5. Build order

Each step is one ship (or one ship per board where marked). Each one leaves the app working. REAL goes first because this lane owns it and it is the board the owner uses most.
Two pieces of REAL work landed in v73.971 (2026-10-02) and are the base for step 4: the SHOULD HAVE TRADED section, and the ledger chart work (timeframe that matches the ledger, TradingView-style pan and zoom-out, the point breakdown inside the chart view). The chart work touches the full viewer that all three boards share, so the shared trade panel in step 9 builds on top of it.

| Step | What ships | Lane | Effort | What could break | How it is checked |
|---|---|---|---|---|---|
| 0 | Groundwork, no visible change: a render probe for the REAL board added to the ship gate; "before" screenshots of all three boards; a sheet of each board's headline numbers (big number, today, trade count, win rate, profit factor, max drawdown). | TRADING-LOG | S | Nothing visible. | The new probe passes on today's main and fails on a deliberately broken copy. |
| 1 | The tab button reads LEDGER; the deposits strip and the Settings button say DEPOSITS; CLAUDE.md and the five outside notes updated. | TRADING-LOG | S | The phone tab row could wrap onto two lines. | Clean start in the owner's Chrome; LEDGER returns to the last board; a reload lands on the same board; the tab row fits at 375 px. |
| 2 | Shared number rules, no layout change: range from today, the trade-day rule, the $0 rule, the shared stats set; REAL adopts them first; fixes the 8 pm "YESTERDAY" label. | TRADING-LOG | M | REAL figures can move slightly at range edges or on evenings. | The numbers sheet before and after; every difference is explained line by line in the MANAGER post. |
| 3 | NT8 data fixes: load every paper trade; the hidden-strategies decision; warnings into the hero. | PAPER-NT8 | M | Firestore reads go up; slower first load. | All-time trade count equals the stored count; the big NET equals the strategy list total equals the end of the bold line. |
| 4 | Shared hero and range pills, one ship per board: REAL, then WEBULL, then NT8. | TRADING-LOG builds; PAPER-WB and PAPER-NT8 review their boards | M | REAL's chart hover writes into the hero; Webull redraws every few seconds; NT8's chips. | Numbers match the step 0 sheet (apart from agreed rule changes); laptop and phone, both themes. |
| 5 | Shared equity chart: per-day points, price scale, dates, total plus faint lines, finger scrub, no squashed line on a phone. One ship per board. | TRADING-LOG builds; paper lanes review | L | Webull's caveat columns, version markers and book-only swatch; REAL's deposit-adjusted balance; NT8's per-strategy lines. | Scrub by mouse on the laptop and by finger on the phone; the last point equals the big number. |
| 6 | Shared stats strip and More stats fold. | TRADING-LOG builds; paper lanes review | S to M | NT8 loses its ten-cell grid (the values move into the fold). | Every value matches the step 0 sheet. |
| 7 | Shared calendar; added to REAL if the owner says yes; NT8 and Webull switch to it. | TRADING-LOG builds; paper lanes review | M | Webull's caveat hatching; NT8's click-a-day selection. | Month total equals the sum of that month's trades; clicking a day jumps the list there. |
| 8 | Shared trade list frame: toolbar, search and chips, day headers, common columns first, phone five-column rows, remembered List or Table. One ship per board. | TRADING-LOG builds REAL; each paper lane moves its own board | L | REAL: inline grade, setup and notes edits, header sort and filter menus, the PASTE box, jumps in from the ANALYTICS calendar. NT8: drag-select for ALL CHARTS. Webull: SHOW MORE and CSV. | All probes pass; on REAL edit a grade and a note, paste a snapshot link, jump from ANALYTICS; on NT8 drag-select three rows and open ALL CHARTS; on Webull export the CSV. |
| 9 | Shared trade panel: a right-side panel on a laptop and a bottom sheet on a phone, with slots for each board's blocks; NT8 gets a panel for the first time. Room for SHOULD HAVE TRADED entries. | TRADING-LOG builds; paper lanes fill their slots | L | Webull's sheet is tied to the trade itself, not the row position; REAL's half-typed notes, IGNORE IN METRICS and DELETE; Esc and tap-outside to close. | Open and close a trade on every board at both widths; save a note; Esc closes; the chart and EXPAND work. |
| 10 | Shared strategy or account list, and the one-line version on a phone. | TRADING-LOG builds; paper lanes review | M | NT8's switches and filters; Webull's live position line; where REAL's ACCOUNT switch goes (owner decision 10). | Flipping a switch changes the big number, chart, stats, calendar and list together. |
| 11 | Each board's own sections become closed folds with a summary line, in a fixed order; one set of breakpoints; old code and the `?oldboards=1` escape hatch removed one version later. | All three lanes | M | Something from a "must stay" list could go missing. | Tick through the three "keeps" lists in section 2.3 and both inventories' "must stay" lists; every fold opens. |

**Checks that apply to every step:**

- The pre-push boot gate passes, and so do the four existing paper probes and the new REAL probe.
- The deployed page loads cleanly in the owner's Chrome (`?fresh=` address, console shows a clean start).
- Each changed board is looked at on a laptop at 1366x768 and on a phone at 375 wide, in both themes, plus MONO wherever a meaning depends on colour.
- The numbers sheet from step 0 is compared before and after, and any difference is explained.
- The MANAGER post carries the version number and before and after screenshots.

**Who builds what:** TRADING-LOG builds the shared parts and the REAL board. PAPER-NT8 and PAPER-WB move their own boards onto the shared parts and keep their own sections, because they know what must not break. MANAGER sets the order across lanes.

---

## 6. Owner decisions

The first three are needed before step 2; the rest can wait until their step.

1. **Rename (top 3):** show LEDGER on the button and keep every internal name (recommended), or do a full internal rename (not recommended). Also confirm the board names stay REAL, NT8 PAPER and WEBULL PAPER.
2. **One day rule and one range rule (top 3):** every trade belongs to the day it closed, ranges count back from today (Today, 1W, 1M, 3M, YTD, ALL), and the curve restarts at zero at the start of the range. This also changes how NT8's nightly book figure is dated.
3. **What the big number counts (top 3):** on NT8, show the 31 hidden strategies in an "Other / shadow" group or leave them out of the number; on WEBULL, shadows (if shown at all) stay in their own group and never add to the account number; on REAL, the big number stays the account balance or switches to P&L like the paper boards.
4. **Calendar on REAL:** bring it back to the board (it is also on ANALYTICS), or leave it on ANALYTICS only.
5. **Trade panel position:** a right-side panel on a laptop and a bottom sheet on a phone for all three boards.
6. **NT8 row click:** open the trade panel (selection for ALL CHARTS moves to tick boxes), or keep click-to-select.
7. **AI ASSESSMENT on REAL:** keep it where it is, move it into a fold, or move it to ANALYTICS.
8. **Money colours under MONO:** follow the theme (green turns white, red turns grey) or always green and red.
9. **WEBULL's ENGU-Q #335 row:** keep it for history, or move it into a "retired" group now that it is flat.
10. **REAL's ACCOUNT switch:** keep it in the tab row, or move it into the board's own list like the paper boards' strategy lists.

---

## Appendix: where things live in the code (web v73.969)

For the builders, not the owner. Line numbers drift with every ship.

**Navigation:**

- Tab list, tab row and HOME subtabs: `LOG_TABS_STRIP`, `NAV_ROW`, `HOME_SUBS` (index.html about 2326-2349).
- Button text: `_logLbl` makes the label from the internal id (about 13832); the button itself is `_navBtn` (about 13862); the board pills are drawn at about 13871-13880.
- `?oldtabs=1`: `LOG_OLDTABS_ESCAPE_HATCH` and `_liveLogTab` (about 2650).
- Saved view: `_saveView` writes `el_view` (about 2376); restore block about 2607; `el_homeSub` written at about 13648 and read by the HOME button at about 13926; `el_paperSub` at about 13640.
- REAL renders under the internal tab id `home`; the paper boards render under the backtester id with sub-ids `paper2` (NT8) and `qqqpaper` (WEBULL). The ACCOUNT switch only draws on the trading-log side (`_master==='log'`, about 13828), which is why it vanishes on the paper boards.

**REAL board:**

- Entry point `_hmRenderHome` (about 12894), called from `renderApp` (about 13951). Styles are the `.hm-*` block (about 618-785).
- Hero and chart: `_hmHeroLabel`, `_hmRenderHeroDefault`, `_hmRenderChartInto`, `_hmWireChart` (about 11952-12050); series `_hmRangeSeries`, `_hmEquitySeriesForRange`, `_hmFullSeries`; range cut `_hmCutoff` (about 11679).
- Stats: `_hmStatStrip` (about 12051), `_hmMoreStats` (about 12105), shared `calcStats` (about 2898).
- Trade list: `_hmFeedList`, `_hmRenderFeedTrade`, `_hmRenderFeedDay`, `_hmRenderTable` (about 12499); FULL `_hmTableHeader` / `_hmTableRow`; SIMPLE `_hmTableHeaderSimple` / `_hmTableRowSimple` (about 12383-12412); header menus `_hmThCell`; toolbar `_hmToolbarHtml` (about 12538); PASTE box `hmFileChartLink` (about 12644); SIMPLE/FULL state `homeLedger` (about 2450).
- Trade panel: `_hmSheetHtml` (about 12227); POINTS `_hmPtsSheetHtml` (about 12353); EL chart `_rtSheetCandlesHtml` / `_rtSheetCandlesFill` (about 6842); EXPAND and chart icon `_hmOpenCandles` (about 6890); OPEN IN TV `hmOpenInTv` (about 12598).
- The "YESTERDAY after 8 pm" issue: `_hmDayLabel` (about 11936) uses the UTC date.
- Journal fold `_hmJournalSectionHtml` (about 12803); jumps from other tabs `hmShowTrades` (about 12856).
- Data: the real trades listener (about 4076); NT8's `paper_trades` read with the 500 limit (about 4158).

**Paper boards:** see the two inventories named at the top. NT8 branch starts at about 38098; WEBULL branch at about 36012.

**Probes that open the paper boards by internal id:** `tools/paper_render_probe.py`, `tools/qqq_candles_probe.py`, `tools/qqq_orders_probe.py`, `tools/qqq_overview_probe.py`.

## Appendix B: shared parts - adoption contract (TRADING-LOG, 2026-10-05)

Owner of these parts: TRADING-LOG. Paper lanes call them from their OWN board sections and never edit them;
need a change? one inbox line to TRADING-LOG and it ships in the shared code. Everything lives in index.html at
global scope, next to `calcStats` (search for "LEDGER number rules"). Each board keeps its previous layout behind
`LEDGER_OLDBOARDS` (`?oldboards=1`) for one version, then the old code is removed (step 11).

## 1. Rules (step 2, live)
- `ledgerTodayNY()` -> 'YYYY-MM-DD' in New York. `ledgerShiftDay(ds, n)` -> ds moved n days.
- `ledgerCutoff(range)` -> first NY day inside the range ('TODAY','1W'=7d,'1M'=30d,'3M'=90d,'YTD','ALL'->null), counted from today.
- `ledgerCloseDay(t)` -> the NY day a trade CLOSED: `t.exitDate` if set, else `t.date` moved on by the midnights
  `t.entryTime` + `t.durationMins` cross, else `t.date`. A paper board whose rows carry a close day under another
  name maps it into `exitDate` (or passes its own day function to `ledgerStats`, section 4).
- `ledgerByClose(list)`, `ledgerInRange(list, range)`.
- A $0 trade is neither a win nor a loss. Money colours follow the theme (decision 8): `var(--green)` / `var(--red)`
  on changes and rows only, never a fixed hex; the big number stays `var(--text)`; direction is always ALSO carried by
  an arrow (▲/▼) and a sign (+/-) so MONO reads.

## 2. Hero + range pills (step 4, live on REAL v73.1012)
- `ledgerHeroHtml({ids:{label,big,today,range,chips}, label, big, today, range, chips})` -> `.lg-hero` markup:
  `.lg-hero-label` (board + scope, e.g. "BOOK #463 · NT8 FUTURES PAPER"), `.lg-hero-big`, `.lg-hero-today`,
  `.lg-hero-range`, `.lg-hero-chips` (status + alarm chips; wrap each in `<span class="lg-chip">`; the row hides itself
  when empty and drops under the number on a phone). Give the ids so your scrub code can write into them.
- `ledgerTodayHtml(v)` -> "▲ +$12.50 today" (signed + arrowed). `ledgerMoney(v)` -> "$1,234.56" / "-$1,234.56".
- `ledgerRangePillsHtml(active, attrName)` -> `.lg-pills` with one button per `LEDGER_RANGES`
  (TODAY 1W 1M 3M YTD ALL), each carrying `attrName="<range>"`; you wire the clicks and remember the choice.
  Labels: `LEDGER_RANGE_LABEL[range]` ("past 3 months" ...). A saved range not in the list opens on ALL.
- The range drives the hero, chart, stats, calendar AND trade list; the curve restarts at $0 at the range start.

## 3. Equity chart (step 5, shipping today on REAL)
`ledgerChartRender(wrapEl, o)` draws into `wrapEl` (an empty div you own) at its real pixel width (200 px tall on a
phone, 260 on a laptop; `o.height` overrides) and redraws itself when the width changes.
- `o.pts = [{v, date}]` - the total line; first point = the range start (date may be null). Reduce per-trade points with
  `ledgerDailyPoints(pts)` (keeps every trade when the range has only 1-2 days).
- `o.up` - false paints the total red. `o.id` - unique per board (gradient ids). `o.aria` - a label.
- `o.lines = [{name, color, vals, on, dash?}]` - faint lines (vals: one per point, null = gap) with a legend that
  switches each; `o.onToggle(name, on)` lets you remember it. Each line gets its own dash so MONO keeps them apart.
- `o.bands = [{i, title}]` - hatched amber column on point i (caveat days). `o.marks = [{i, label}]` - dotted marker.
- `o.onScrub(i, point)` / `o.onLeave()` - mouse hover or finger drag; write the hero from them, never re-render.
- `o.fmtAxis(v)` - price-scale labels (default "$4,650").
- Probe markers in the svg: `[data-lgdate]` (dates), `[data-lgtick]` (price labels), `[data-lgband]`, `[data-lgmark]`,
  `.lg-legend [data-lgline]`. The drawn height is the svg viewBox height (no scaling).

## 4. Stats strip + More stats (step 6, shipping today on REAL)
- `ledgerStats(list, {pnl, net, include, day, sorted})` -> null for no trades, else `{trades, excluded, wins, losses,
  flat, winRate (0-1 or null), pf (Infinity = no losses, null = nothing won or lost), net, grossWin, grossLoss,
  avgTrade, avgWin, avgLoss (negative), payoff, maxDD (POSITIVE), largestLoss (POSITIVE), recovery, sharpe,
  bestDay {date,v}, worstDay {date,v}, greenDays, days, longs, shorts, longNet, shortNet, avgHoldMins,
  streak {n, dir}}`.
  `pnl(t)` decides win / loss / profit factor (default `t.pnl`); `net(t)` is the money for net, drawdown and day
  totals (default `pnl`); `include(t)` false = out of win rate / PF / streak / day stats but still in net and
  drawdown; `day(t)` defaults to `ledgerCloseDay`; trades are walked in close order unless `sorted:true`.
  Long / short read `t.type` / `t.side` / `t.direction` (LONG, SHORT, BUY, SELL, L, S). Hold reads `t.durationMins`.
  Parity: on REAL it matches the old engine on all 19 shared figures, gross and net (headless check, 300 trades).
- `ledgerStatStripHtml(s, {id, winNote})` -> `.lg-stats`, four tiles in this order, same on every board: WIN RATE,
  PROFIT FACTOR ("no losses" when nothing lost), MAX DRAWDOWN (positive), TRADES; each `[data-lgstat=
  "winrate|pf|maxdd|trades"]` with `.lg-stat-val` + a small `.lg-stat-sub`. Today's money lives in the hero.
- `ledgerMoreStatsHtml(s, ownGroups, {open, id, note})` -> the `.lg-more` button (`data-lgmore="<id>"`,
  `aria-expanded`) + panel `#<id>-more`: groups Returns / Risk / Mix (`[data-lgmsgroup]`), then your own
  `ownGroups = [{title, rows:[[label, valueHtml, cls]]}]` (REAL and WEBULL "Account", NT8 "Strategy vs control").
  You wire `[data-lgmore="<id>"]` clicks, keep open / closed, and re-render; the body is built only while open.
- Small helpers: `ledgerPfText(pf)`, `ledgerSigned(v)` ("+$1.00" / "-$1.00"), `ledgerCls(v)` (`lg-up` / `lg-down`,
  theme colours), `ledgerMsRow(label, valueHtml, cls)`.

## 4b. Calendar (step 7, shipping today on REAL)
- `ledgerCalDays(list, {pnl, net, include, day})` -> `{date: {v, n, w, l}}` (v = money, n = trades closed that day).
- `ledgerCalendarHtml({id, month, days, caveats, open, note})` -> a `.lg-more` fold button `[data-lgcalfold="<id>"]`
  + panel `#<id>-cal`: one month, Sunday-first, a WEEK column (empty week = empty cell, never $0), each traded day a
  `button[data-lgcalday="YYYY-MM-DD"]` with signed short money and a trade count; `caveats = {date: reason}` hatches
  that day amber with a dot (Webull: book-priced / repriced / parity / feed days). Arrows
  `[data-lgcal="<id>"][data-lgcalmo="-1|1"]` are disabled at the first / last month with trades.
- Helpers: `ledgerCalPick(days, want)` (the month to show: wanted, else newest with trades, else this month),
  `ledgerCalStep(days, month, n)` (arrow), `ledgerCalMonths(days)`, `ledgerShortMoney(v)` ("+$1.2k").
- The board decides what a day tap does (REAL: scroll the list to that day; NT8: select that day's rows) and
  remembers open / closed and the month. The calendar takes the chosen RANGE's trades, like everything else.

## 5. Per-board render probe (each lane, in its own probe)
Check: hero ids present, the four `[data-lgstat]` tiles in order with drawdown a positive dollar amount, More
stats opening with Returns, Risk, Mix + your groups, and the big number reads as money; pills read TODAY 1W 1M 3M YTD ALL; chart drawn height
>= 150 px on a 375 px phone and >= 200 px on a laptop; >= 2 `[data-lgdate]` and >= 2 `[data-lgtick]`; no page that
scrolls sideways on a phone. `tools/home_render_probe.py` does exactly this for REAL - copy its checks.

## 6. Review
Before a paper-board adoption ships, post TRADING-LOG one inbox line (worktree + what changed); TRADING-LOG answers with
one line (go / fix X) and checks the landing in the owner's Chrome.
