#!/usr/bin/env python3
"""
tools/webull_board_probe.py -- render gate for LEDGER > WEBULL PAPER (augurSub 'qqqpaper').

WHY THIS EXISTS
---------------
tools/home_render_probe.py gates REAL's LEDGER board on every ship that touches index.html. The
WEBULL PAPER board moved onto the same shared parts (hero + range pills in step 4, the shared
equity chart in step 5) but its only probe then, tools/qqq_overview_probe.py (retired 2026-10-08, its record pass moved here),
was a long hand-run verification tool, not a gate. This is the per-board render probe the LEDGER adoption contract
asks for (SHARED_PARTS_CONTRACT.md section 5, LEDGER_UNIFY_SCOPE.md appendix B), short enough for
`wt.py ship`, wired in exactly as REAL's is.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe the way the HOME gate does, waits
for the signed-out screen and keeps it off the page, then hands the board a fixed copy of the
box's status doc (tools/fixtures/qqq_exec_box1005.json: the box's own _build_doc output on
2026-10-05 from a read-only copy of its files, account ids scrubbed; 47 trades from 2026-09-03,
data-caveat days, the NOISE #304 -> #382 run change, ENGU-Q flat since 2026-09-28). Nothing
touches the network or Firestore.

Cases: laptop 1366x768 | phone 375x812, x dark | mono, each a fresh render on ALL. Then one
interaction run on the laptop (Retired group open / close, a chart scrub writing the hero and
putting it back, a legend switch remembered), the FRESHNESS variants below, and one render with
?oldboards=1 (a flag that changes nothing any more). The page's clock is pinned (window.__qbNowMs) so the fixed doc is judged the same
way on every run: the plain cases see it 24 s after it was written, in the session.

FRESHNESS variants (laptop, dark; sweep 2026-10-05 findings 8, 9, 20-24), each the fixture with
a few fields moved and the clock pinned: fresh in the session; 5 minutes old in the session;
Saturday noon with Friday's 15:58 doc; Monday 08:50 before the open with Friday's doc; a quiet
evening doc 6 minutes old (must NOT read silent); a quiet Saturday doc written after Friday's
close (not silent, but its today figures are Friday's); a weekend wedge (Saturday 17:11 doc on
Sunday, with the box's promised 10-minute cadence); KEEL 4 sessions old; publish failures and a
75 s stall; a gap before the latest save with no failed-save event (UPDATES PAUSED, never
UPDATES FAILING); orders halted; Monday 09:30:30 with Friday's doc (the 90 s after the open must
not hide a frozen doc); Monday 09:31 with a 09:25 doc (the 90 s grace after the open holds);
Friday's doc seen Monday 08:50 with the book armed (PAPER, lease ok) and the System section open
(neither Orders view may still say PAPER / Sending orders); and the same doc on a page whose own
read failed (the top chip blames the page, not the box). Third pass (review 2026-10-05): saves
still failing after the box's 10-minute publish_down event (the page remembers the count going
up); KEEL one session behind on Saturday (the rebuild did not land) and on Monday at 17:00 (the
rebuild is still to come); Tuesday 08:00 before the open with the last session's 75 s stall
(never 'TODAY'); and HOME with Friday's doc on Saturday, laptop and phone (the top bar WEBULL
chip must read STALE away from the board). Fourth pass (review 2026-10-05): the doc listener is
the BOARD's only again (it must not want to run on HOME, and must on the board), so away from the
board the top chip judges its copy as of the page's last check and says 'checked HH:MM' (HOME
checked 30 min ago on a fresh doc: FLAT, never STALE; a .get() landing on HOME redraws the chip in
place); a page that comes back hours later with a higher failed-save count, and a cached first
copy, never raise UPDATES FAILING; Monday 08:50 with a Saturday 17:11 doc and no promised cadence
reads silent; a pause whose last good save was on an earlier day leaves its length out; this
page's own read failure reads THIS PAGE CANNOT READ in the hero and strip, never BOX SILENT; an
open position (WEBULL 1 OPEN, leg pill in colour) and the same position on a silent box (leg pill
grey); a blocked book (WEBULL BLOCKED); Thanksgiving noon with a fresh doc (market closed, not
silent); the 30 s freshness timer exists and its body, run with the clock 5 min on and no new
doc, turns the chip and the hero silent; and the calendar (Thanksgiving closed, the day after a
13:00 close, Friday 2027-12-31 open). The top chip must be drawn, visible, inside the viewport
and not covered, in every case. The
System LAST TICK verdict is read on the quiet evening (fresh) and the armed Monday (stale), and
the box's own NOT READY flag must be greyed on every silent doc. Each asserts the hero's freshness chips
(BOX SILENT / KEEL / UPDATES FAILING / UPDATES PAUSED / BOX STALLED), the status strip, the
hero's today word, the daily-stop caption, the orders header, the leg's TODAY label, the dimming
of every figure from an earlier day, the Account 'as of' + STALE + the dated change + the grey
reconcile line, the NOISE KEEL sentence, the Orders pill, and the top bar WEBULL chip.
Sixth pass (review 2026-10-05): one failed save (a publish_down event with a count of 1, or a rise
of 1 between two saves) never raises UPDATES FAILING; KEEL counts only closed sessions (Monday 08:00
on Thursday's data is 1 session old; Monday in the session on Tuesday's data is 3) and a missed
rebuild raises its chip on Saturday; a cached listener snapshot after a read error still reads THIS
PAGE CANNOT READ; a page shown again away from the board reads at most once per 5 min (30 s on the
board); an open position on a silent box says 'last seen $600.52 at 10:03', never 'now', with its
Open and UNREALIZED figures grey; and three key variants again in MONO at 390x844 (Saturday with
Friday's doc, the page's own failed read, the open position on a silent box). Every variant: no
NaN / undefined / [object Object] on the page, and a phone variant does not scroll sideways.

WHAT IT ASSERTS
---------------
Per case:
  * renderApp returned, no uncaught exception, unhandled rejection or console.error
  * the hero ids are there and the big number reads as money; the pills read TODAY 1W 1M 3M YTD ALL
  * the shared chart is drawn at >= 200 px on the laptop and >= 150 px on the phone, with
    >= 2 [data-lgdate] and >= 2 [data-lgtick], [data-lgband] (caveat days) and [data-lgmark]
    (the run change, named with its family), the three strategy lines ORB #314 / ENGU-Q #335 /
    NOISE #382 in the legend with 16 px icons, and the caveat / book-only key under it
  * the Retired group is there, collapsed by default, says 'flat since 2026-09-28', and only
    ORB and NOISE are live rows
  * every trade row names family + run number ('NOISE #382'), never a bare 'ENGUQ' / 'ORB', and the
    run is the one that took the trade (counts per name match the fixture: NOISE #304 / #382 ...)
  * the three faint lines carry three different dashes (MONO turns every colour grey)
  * on a phone the page does not scroll sideways
  * no BOX SILENT chip on the fresh doc, and the top bar carries the WEBULL chip (FLAT)
Interaction run: the Retired group opens (ENGU-Q's row appears, the choice is stored) and closes;
a scrub at the left edge writes $0.00 and 'start of the range' into the hero, at the right edge
the closed P&L of record, and leaving puts the hero back; a legend switch is remembered.

STATS (LEDGER unify step 6, 2026-10-05): the board's own stat tiles are TRADING-LOG's shared strip now.
Every plain case: the four [data-lgstat] tiles (WIN RATE, PROFIT FACTOR, MAX DRAWDOWN, TRADES) in that
order under the chart, a percent / a ratio / a positive dollar amount / a count, each equal to a
recomputation here from the fixture (P&L of record, close day, walked in exit order), the PROFIT FACTOR
line ('$276 won · $304 lost') and the MAX DRAWDOWN line included. Nine stats cases (the ninth, the unlisted strategy leg, is described under STEPS 7 + 10) with today pinned to
2026-10-05: ALL; 1W (trades that closed on or after 09-28) on the laptop; 1W again on a 390x844 phone in
MONO with More stats open; ALL with one September loss turned into a $0 trade, which must be neither a
win nor a loss in the tiles ('1 even') and in the calendar's month '% won'; TODAY (one trade); 1M on a
375x812 phone with More stats open; TODAY with today pinned to 2026-10-06 (no trade closed yet) with More
stats open, which must still show the Account rows (equity, cash, Open exposure, Daily loss limit,
slippage) under 'No trades in this range.'; and ALL with a shadow row worth $5,000 closed today, which
must leave the tiles, More stats, the hero and the trade list unchanged (the board drops a shadow row once,
where its trade list is built). Each 'More stats open' case opens it the way a reload
does (stored '1', nothing in memory) and must draw it open; its values are checked against the fixture
(Net P&L, Max drawdown, Current streak walked in exit order, Broker made, Book figure over the same trades,
Book-only trades, Fill coverage, best and worst trade, an Average hold that is not '--'), the account's change
is named for its day ('today' on the fresh doc; the TODAY-before-the-first-exit case runs its clock at
2026-10-06 08:00, so it must read 'Account change on Mon 10-05'), under MONO no value or bar has a hue,
'No trades in this range.' keeps at least 8 px above the Account heading, and on a phone it must not scroll
sideways. Every case: the stat strip can be seen (shown, of real size) and starts under the chart, above
Account and History, and on a phone above the Strategies list. The interaction run opens and closes
the More stats fold (aria-expanded true then false, the choice stored for this viewer, Returns / Risk /
Mix / Account with the Webull rows, and on ALL every value worked out here, the current streak too).

LEDGER STEPS 7 + 10 (2026-10-06): the board's month calendar and its strategy list are TRADING-LOG's shared parts now
(ledgerCalendarHtml, ledgerListHtml). CALENDAR: one month over the chosen range's trades at the P&L of record on the day each
closed, so a month's total, every day's money and the week cells are recomputed here from the fixture for each case, range and
month shown (ALL, 1W, 1M, TODAY, the empty range, September after the earlier arrow, a $0 trade, a shadow row that must not
enter it); the caveat days (a tape-priced exit, a failed parity check, a book-only trade, a feed flagged invalid - that last one
needs no trade) are hatched amber with the dot; the arrows are disabled at the first and last month with trades; the fold is
open on a laptop and closed on a phone until chosen, and the fold and the month are remembered per viewer (a reload finds
them); a tap on a day scrolls the trade list to that day's newest trade and flashes it (a day whose rows are not on the page yet, because the list shows only its newest rows, draws every row
first). LIST: three groups in order, BOOK
(ORB #314, NOISE #382: family + run number from the leg definitions, the range's P&L of record, trades and win rate, the side;
no switch), Retired (ENGU-Q #335, a fold closed until opened, 'flat since 2026-09-28') and Shadow - not counted (a fold,
closed, its rows faded and never in anything above); BOOK + Retired add up to the account's range figure; a tap on a leg opens
its detail under the row. On a phone every row is one line, the status line, the list and the Account section sit under the
trade list, and the trade list starts within one viewport of the board top (mistake #12); on a laptop the list is the
frame's right-hand panel (LEDGER STEP 12 below). The Table view carries a run number on every row too. A tap on a row's note toggle (the little i beside a run
number) shows that leg's note under the row and leaves its detail shut; a copy of the fixture whose last two ORB trades
belong to a strategy the board has no row for (375x812, both folds open) must draw an Other legs row, so BOOK + Retired +
Other legs still add up to the account's range figure; a copy with ENGU-Q long 10 (375x812 and 1366x768) has no Retired group,
ENGU-Q is a BOOK row reading LONG with its live position line, and the rows still add up. Under MONO no calendar or list value
has a hue.

LEDGER STEP 8 (2026-10-06): the board's trade list (History) is TRADING-LOG's shared frame (ledgerTradeListHtml / ledgerTradeListWire), as REAL's
is. Every plain and stats case: ONE [data-lglist-frame] with the count ('N / 47 trades'), the LIST | TABLE switch, the search box and the chips
ALL / LONG / SHORT / WINS / LOSSES then ORB / ENGU-Q / NOISE (with their run numbers) / BOOK ONLY; a header for each New York close day, newest first,
with that day's signed net; the rows under it in close order, every cell recomputed here from the fixture (family + run number, side, shares, P&L of
record, points, the entry time with its date when the trade closed later, exit reason and chips, the flagged-row mark, the chart glyph); in the TABLE this
board's own columns after the common ones (exit time, entry / exit price, running total, real P&L, slip; the NinjaTrader three only while a trade carries
NT data); a phone row draws five cells. TRADE LIST RUNS, one page each: the laptop (every chip, a search typed a letter at a time that keeps its focus and
caret but is not given the focus back after the viewer left the box (the phone keyboard's Done), the sheet for the TAPPED trade after a chip / after a search and clear / after a redraw / from the table, the chart glyph, SHOW MORE paging that
never cuts a day in two, LIST | TABLE remembered and found by a page that comes back, the CSV: its file name, the 50 columns it always had, the trades
the list matches in the list's order, a calendar tap on a day the chip hides); a doc with a $0 trade (WINS and LOSSES leave it out); a doc with a shadow
row (in the list, the count, a day net and the CSV nowhere); a trade held over a weekend (under its close day); phones 375x812 and 390x844 MONO (five
cells in the LIST and the TABLE, the flagged-row mark drawn, the list starts at most 792 px under the board top, no sideways page); and widths 375 to
1366 in the LIST and the TABLE (the PAGE never wider than the window; no list row wider than its box; no strategy name cut).

LEDGER STEP 9 (2026-10-06): a tap on a trade row opens TRADING-LOG's shared trade panel (ledgerTradePanelOpen, id wb) in place of the board's own
bottom sheet: a right-hand panel above 600 px, a bottom sheet at 600 px and under, nothing in the page while it is closed. Seven runs (TRADE PANEL):
the laptop 1366x768 and the phone 375x812 in glass / paper / MONO, and the widths 375, 600, 601, 700, 800, 1000, 1366 in the LIST and the TABLE.
Every run: a tap on the row of the newest trade opens the panel for THAT trade (its key, strategy with run number, side tag, entry day, entry to exit
time ET, shares, the signed P&L of record in its colour class, the caveat chips the row carries), 440 px wide and the full height on a laptop, the full
width on the bottom edge with a strip of page left above it on a phone, in <body>, slots in the order head / chart / numbers / notes / actions, focus
inside; the page exactly as wide and tall before the first open, with the panel open and after Escape / a tap outside / the close button (no panel
node left, <body> holding the same elements); a tap inside does not close it; the candles drawn in the chart slot (the box's bars stubbed), EXPAND
(a laptop only) and OPEN CANDLES open the full viewer for that trade stepping through the list rows; the numbers rows by label, each worked out here
from the fixture (shares, notional, entry / exit price, the Webull fill on each side, hold time through durStr on whole seconds, P&L of record with its
source word, backtest and book P&L, the running total, real P&L, slip a share, fill coverage, and the NT POINTS / EXPECTED $ / TRACK ERR / NT ENTRY /
NT EXIT rows only on a trade that carries NinjaTrader data); the notes slot says it is read-only, holds no box and spells out the exit reason, each
flag in words, the parity note, the trade's own note and the KEEL size note; the actions slot is OPEN CANDLES alone; a tap on the chart glyph opens the
candles and not the panel; nine trades (each kind of caveat: BOOK ONLY, FILL GAP / CHECK FILL, EOD, a part-book price, NinjaTrader figures, a KEEL
size, a note, a plain one) each open a panel with the right chips, rows and words, a book-only trade's panel carries BOOK ONLY; in MONO no colour in
the panel (text, background, border, outline, svg fill and stroke, the chart and its legend included) carries a hue. The glass laptop and the glass
phone also: the board redraws (renderApp, and the board's own throttled live redraw with a new snapshot) while the panel is open on a scrolled body:
the same panel node, the same slot nodes, not one thing inside rewritten (a MutationObserver), the scroll kept, the same trade; an old trade that a
short page leaves out stays open through that page, SHOW MORE, a search for nothing, the search cleared, a search for noise, a chip that hides it,
LIST | TABLE and back, its chart drawn though the list does not show its row; the trade leaving the board rows (the range TODAY) closes the panel and
the board forgets it; the viewer leaving the board (HOME) closes it. The width run: the page never wider than the window with the panel closed or
open, at every width, in the LIST and the TABLE.

LEDGER STEP 11 (2026-10-06): one page order, every own section a closed fold with a one-line summary, one set of breakpoints.
PAGE ORDER, by the page's own markers, top to bottom (as step 12 left it): hero (#qb-hero-label), the status line (directly under the hero, never folded,
with its box-updated line and Refresh), range pills (.qbx-range-row), chart (#qb-lg-chart), the stats strip, the More stats fold, the calendar fold, the strategy
list (up to 600 px a one-line fold; from 1100 px the frame's right-hand panel beside the top block, see STEP 12), the trade list ([data-lglist-frame="wb"]), then
the own sections: Orders (the
PAPER breaker line), Account, Today's orders, Feed & signals, System, Rails, Event timeline, Model reference, in that order, every one below the end of the trade
list. Every plain case and every stats case. FOLDS (every plain case): each own fold is there, shut as first drawn (aria-expanded false, its panel hidden and not
on the page), its header one line (under 40 px, its summary under 22 px) with a title and a summary that is not empty, not 'undefined' / 'NaN', and says the
number the fixture says (the daily stop used out of its limit, the equity and its change, the order count, the feed uptime, NOT READY with its open checks,
the daily limit and shares a leg, the event count); under MONO no header or panel frame draws a hue. The strategy list's phone fold is drawn up to 600 px (shut)
and not above. PHONE: the trade list (the frame) starts at most 760 px under the board top at 375x812 (784 before step 11 and 12; step 12's page puts it at 757,
and it must not grow). STEP 11 RUN
(laptop 1366x768, then phone 375x812): each own fold is tapped open and shows its content (the daily stop bar and mode pill, the account equity and its as-of
line, the order rows, the feed strip, the status / orders / integrity blocks, the rails, the events, the model reference), the choice is stored for this viewer
(el_qb_fold_<key>), a reload (nothing in memory) finds it open, a live redraw leaves it open, a second tap shuts it and a reload finds it shut; the phone list
fold opens onto its rows, one line each; storage that throws for the fold keys changes nothing but the memory copy; and with EVERY fold open the page never
scrolls sideways at 375, 601, 700, 800, 1000 and 1366 px. BREAKPOINTS: read from the page source, every media / container query that styles this board uses
only 600, 740, 800, 920 or 1100 px (no board-private width survives; the flagged-row mark is a container query at 800).
?oldboards=1 (one more page load, case 'flagpage') draws the NEW board like the plain page: the fold layout, the shared tiles, chart, calendar,
strategy list and trade list frame, the same markup skeleton and page order as the plain laptop / MONO case, none of the removed previous board's
markers (OLD_MARKS) and no LEDGER_OLDBOARDS name left in the page. STATIC LINT (tools/ledger_removed.py): none of the identifiers the clean-up
removed is back in index.html.

LEDGER STEP 12 (2026-10-07): ONE PAGE FRAME, shared with REAL and NT8 PAPER (ledgerFrameHtml, ledgerStatusHtml, ledgerChartFootHtml, ledgerFiltersHtml).
Every plain and stats case: exactly one [data-lgframe="qb"] holding one top block (hero, status line, pills, chart, stats, More stats, calendar), one side panel
and one rest (the trade list, then the own folds); its computed max-width is 1320 px and it is centred in its parent (left gap = right gap within 2 px). From
1100 px the frame is a grid: the strategy list is inside [data-lgframe-side], to the right of the top block, the panel's top level with the top block's, never
taller than it (the list scrolls inside the panel) and not sticky; the trade list and the own folds run the full frame width under both. Under 1100 px there is
no grid and the list sits between the calendar and the trade list. The status line [data-lgstatus="qb"] sits directly under the hero (after .qbx-hero, above the
pills and the chart), one or two lines tall, with the Refresh button [data-qqqrefresh] in it. The chart foot [data-lgchartfoot="qb"] comes right after the chart
box and holds the caption (the only .qbx-chart-cap on the page) and the key; the caption takes the shared foot style (the font size of the shared .lg-chart-cap
rule). The list's Filters row [data-lgfilters="qb"] comes right after the list header, closed (aria-expanded false, its body hidden), its summary 'none' and the
no-filters line in its body (WEBULL has nothing to filter). The interaction run taps it open (in place: the list is not redrawn; stored el_lg_filters_qb = '1'),
a redraw (all a reload has: the choice lives in storage only) keeps it open, a second tap closes it ('0') and a redraw keeps it closed. The step 11 run also
draws the board in a 1680 px window, where the frame must be exactly 1320 px wide and centred, the list still the right-hand panel.

KEEPS CHECKLIST (2026-10-07; post-landing review WEBULL_LEDGER_POSTLANDING_REVIEW.md section 4 items 1-9 and its fixes M1, L1-L6, merged 2026-10-08):
the board features a checklist audit found on the page with no check to notice them breaking. HERO: the amber line 'broker made $X of that (N book-only
trades excluded)' - X and N are the PAGE'S OWN sum over its trades (shadow rows dropped, book-only ones left out: review L3, the same rule as More stats'
Broker made), 'trade' for one, no line at all when no trade is book-only (every plain case, every variant, plus one variant each for none and one made by
changing the trades' own flags, and one whose box summary says something else - the page must not follow it); the probe also checks its fixture's box
summary agrees with its trades. The chips BREAKER TRIPPED, KILL ACTIVE, PARITY MISMATCH ('N PARITY MISMATCHES' / '1 PARITY MISMATCH': checked minus ok
of the NinjaTrader-mirror summary) and FILLS BEHIND BACKTEST (the rolling flag), each drawn when its condition holds and left out when it does not, in
colour on a fresh doc and grey on a silent box. SYSTEM fold: 'Running on <host> . one-computer check OK' with the doc's host name in green on a fresh
doc ([data-qbhost] ok), grey with '(last known, as of Mon 10:03)' and no green on a silent box (stale, review L2), and its failing form (another computer
holds the lease, or the lease cannot be verified: the reason in words, never OK; blocked). The Orders card's sentences of the retired
tools/qqq_orders_probe.py: OFF 'Simulated only', PAPER 'Sending orders to the Webull paper (practice) account.', BLOCKED "can't confirm this is the only
computer trading", HALTED "positions at Webull don't match the notebook". ACCOUNT fold: the share check [data-qbrecon], its attribute, its word (OK /
MISMATCH) and both share counts from positions_live. The NOISE row's TODAY figure is today.legs_record's, and on an older box with no legs_record the
page's own sum on the box's day. The daily stop: a Friday doc whose breaker sent its own figure (-$120), seen on Saturday, reads '$120.00 of $400.00
daily stop used', 'from Fri 10-02' and 'breaker figure', never 'estimate'; the fixture's own null figure reads 'estimate'. TRADE LIST: a flagged row
carries ONE caveat word under its strategy name (data-qbcav; BOOK ONLY, CHECK FILL, FILL GAP, BOOK PRICE, PART BOOK PRICE, NOT COMPARED, the first of
these its own flags hold), shown wherever the flags column is not (L1); the CSV's file name carries the list's scope (ALL: qqq_shadow_book_closed_trades.csv;
LONG: ..._LONG.csv; a search: ..._search-orb.csv; 1W + LONG: ..._1W_LONG.csv, L5). TRADE PANEL: the numbers rows RECORD vs BACKTEST (P&L of record minus
the backtest's), FILL GAP $ / DESIGN GAP $ / SLIPPAGE + UNEXPLAINED $ (the box's fp dollars), the reason beside a missing BACKTEST P&L (never a
parenthesis inside a parenthesis), and the FILLS vs BACKTEST line with FLAGGED exactly on a flagged trade, its reason following the cause (a fill that
does not fit the tape, a resting fill the backtest did not have, or a fill more than 15 cents a share worse - never the 15-cent sentence on a fill that
came out better) (M1). The candles: every layer's own mark by its data-mk (signal bar = dashed rect, backtest fill = ring, backtest exit = dashed square,
book in / out = tick / open square, Webull attempts = triangle / filled square) with its hover title and its legend row, for every panel the runs open (the
set is exactly what the stub fed); a NETTED attempt (both sides): its diamond titled 'no Webull order - netted against another leg at <px>' and its
legend rows; and three caveat trades whose Webull exit try came back REFUSED, NETTED and UNKNOWN, each drawn as its own mark with its own words.
STATIC: the chart key says 'book only = order never reached Webull' and 'book price = no Webull fill price' (L6; the phone key keeps its one short line, the 757 px phone list limit), and
the page never says Webull has no paper API (L4).

Exit codes as preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks). A non-PASS
attempt is rendered once more before it blocks; a retry that passes prints a FLAKE line.

Usage:
  python tools/webull_board_probe.py                # gates this repo's index.html
  python tools/webull_board_probe.py --file X.html  # gates X as if it were index.html
  python tools/webull_board_probe.py --selftest     # deliberately broken copies (MUTANTS) must
                                                    # FAIL, then the real file must PASS
  python tools/webull_board_probe.py --selftest --only NAME[,NAME...]   # just those broken copies (no final run on the real file), each printed
                                                    # caught / NOT caught with the probe's first two problem lines; an unknown NAME is an error
  python tools/webull_board_probe.py --selftest --jobs 1   # the same, one broken copy at a time (the default is four at a time, or fewer on a
                                                           # small machine: 285 copies run one by one would take several hours)

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import collections
import http.server
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_box1005.json')

VIEWPORTS = {'laptop': [1366, 768], 'phone': [375, 812], 'phone390': [390, 844]}
CASES = [['%s/%s' % (vp, th), {'vp': vp, 'theme': th}] for vp in ('laptop', 'phone') for th in ('dark', 'mono')]
LEDGER_RANGES = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']
WANT_LINES = ['ORB #314', 'ENGU-Q #335', 'NOISE #382']
WANT_LIVE = ['ORB', 'NOISE']
RETIRED_SINCE = '2026-09-28'
LEG_RE = re.compile(r'^(ORB|ENGU-Q|NOISE) #\d+$')
MONEY_RE = re.compile(r'^-?\$[\d,]+\.\d\d$')
# LEDGER step 6: the shared stat tiles, in this order on every board
STAT_KEYS = ['winrate', 'pf', 'maxdd', 'trades']
STAT_TODAY = '2026-10-05'      # the stats cases pin ledgerTodayNY() to the fixture's own day
ACCOUNT_ROWS = ['Account equity', 'Cash', 'Open exposure', 'Daily loss limit', 'Broker made',
                'Book figure', 'Book-only trades', 'Fill coverage', 'Slippage vs backtest']
# the Account rows that do not depend on the range: there even when no trade closed in it
ACCOUNT_ROWS_ANY_RANGE = ['Account equity', 'Cash', 'Open exposure', 'Daily loss limit', 'Slippage vs backtest']



def et_ms(s):
    """'YYYY-MM-DD HH:MM:SS' New York time -> epoch ms, with the US daylight saving rule (second
    Sunday of March 02:00 to first Sunday of November 02:00 is UTC-4, else UTC-5). Stdlib only, no
    tz database needed."""
    import datetime as _dt
    w = _dt.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')

    def nth_sunday(y, m, n):
        d = _dt.datetime(y, m, 1)
        return d + _dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    start = nth_sunday(w.year, 3, 2).replace(hour=2)
    end = nth_sunday(w.year, 11, 1).replace(hour=2)
    off = -4 if start <= w < end else -5
    return int(w.replace(tzinfo=_dt.timezone(_dt.timedelta(hours=off))).timestamp() * 1000)


FRESH_NOW = '2026-10-05 10:03:30'   # 24 s after the fixture's updated_at, in the session


def broker_line_want(doc):
    """The hero's broker line (index.html qbBrokerInfo): the page's own sum of the P&L of record over its trades (shadow rows out), book-only ones left out."""
    rows = [t for t in doc.get('trades_all') or [] if not _is_shadow(t)]
    n = sum(1 for t in rows if t.get('book_only'))
    if not n:
        return None
    net = _js_round(sum(qe_pnl_of(t) for t in rows if not t.get('book_only')) * 100) / 100
    return 'broker made %s of that (%d book-only trade%s excluded)' % (qe_money(net), n, '' if n == 1 else 's')


def leg_today_want(doc, leg):
    """A strategy row's TODAY figure: today.legs_record's when the box sends it, else the page's own sum on the box's day (the last day of today's
    trades, else of today's orders, else the day the doc was written) at the P&L of record."""
    today = doc.get('today') or {}
    rec = today.get('legs_record')
    if isinstance(rec, dict):
        v = (rec.get(leg) or {}).get('pnl')
        x = _num(v) if v is not None else 0.0
        return qe_money(x if x is not None else 0.0)
    ok = lambda s: bool(re.match(r'^\d{4}-\d{2}-\d{2}$', s))
    days = sorted(d for d in (str((t or {}).get('exit_ts') or '')[:10] for t in today.get('trades') or []) if ok(d))
    if not days:
        days = sorted(d for d in (str((o or {}).get('ts_et') or '')[:10] for o in today.get('orders') or []) if ok(d))
    box_day = days[-1] if days else str(doc.get('updated_at') or '')[:10]
    return qe_money(sum(qe_pnl_of(t) for t in doc.get('trades_all') or [] if not _is_shadow(t) and t.get('leg') == leg and _close_day(t) == box_day))


def _variant_docs(fixture):
    """[(name, now, doc, expect)] -- the freshness variants. expect keys: silent / keel / publish /
    tickgap = the chip text or None (absent); today = the hero today word; top = (state, text) of
    the top bar chip; strip_has / strip_lacks; stop / orders / legtoday = the day word on the
    daily-stop caption / orders header / opened NOISE leg; asof_has; eq_stale."""
    import copy

    def base(keel='2026-10-02'):
        d = copy.deepcopy(fixture)
        d['keel']['NOISE']['trained_through'] = keel
        return d

    def move_to(d, updated, day, as_of, last_ok, fails=0):
        d['updated_at'] = updated
        d['trade_ids']['day'] = day
        d['orb_resting']['day'] = day
        for o in d['today']['orders']:
            o['ts_et'] = day + o['ts_et'][10:]
        for t in d['today']['trades']:
            t['entry_ts'] = day + t['entry_ts'][10:]
            t['exit_ts'] = day + t['exit_ts'][10:]
        d['equity']['as_of_et'] = as_of
        d['health'] = {'publish_fail_today': fails, 'last_publish_ok_et': last_ok, 'tick_gap_max_s_today': 4.2}
        return d

    def fri(d):
        return move_to(d, '2026-10-02 15:58:40', '2026-10-02', '2026-10-02 15:58:10', '15:57:40')

    out = []
    none = {'silent': None, 'keel': None, 'publish': None, 'pubgap': None, 'tickgap': None, 'noread': None}
    out.append(('fresh in the session', FRESH_NOW, base(), dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['box updated 24 s ago', 'feed OK'], strip_lacks=['BOX SILENT'], stop='today',
               orders='today', legtoday='TODAY', asof_has='as of 10:01:35', eq_stale=False, calendar=True,
               # keeps checklist: the page's own figures on the fixture, with the System fold open for its host line and Orders sentence
               system=True, broker_line='broker made -$3.98 of that (8 book-only trades excluded)', par_chip=None, fills_chip=False,
               hostline='Running on PROBE-PC \u00b7 one-computer check OK', host=('ok', ['Running on PROBE-PC', 'one-computer check OK'], True),
               recon=('ok', 'OK \u2014 Webull holds flat \u00b7 legs sum to flat'),
               legtodayval=leg_today_want(base(), 'NOISE'), ordmode_has=['OFF', 'Simulated only'], stop_has=['estimate'],
               flags_lacks=['BREAKER TRIPPED', 'KILL ACTIVE', 'FILLS BEHIND BACKTEST', 'PARITY MISMATCH'])))
    out.append(('5 minutes old in the session', '2026-10-05 10:08:06', base(), dict(none, silent='BOX SILENT 5 min',
               today='today', top=('stale', 'WEBULL STALE 5 min'),
               strip_has=['BOX SILENT 5 min', 'last update from the box Mon 10:03'], strip_lacks=['feed OK'],
               stop='today', orders='today', legtoday='TODAY', asof_has='as of 10:01:35', eq_stale=True,
               eq_why='the box has been silent', mini_silent='Last known: OFF, as of Mon 10:03.')))
    out.append(("Saturday noon, Friday's doc", '2026-10-03 12:00:00', fri(base()), dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', asof_has='as of Fri 10-02 15:58:10', eq_stale=True)))
    out.append(("Monday 08:50 before the open, Friday's doc", '2026-10-05 08:50:00', fri(base()), dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', asof_has='as of Fri 10-02', eq_stale=True,
               keelline='the next session is Mon Oct 5 - up to date')))
    # KEEL rebuilt that evening (a missed rebuild would raise its own chip): only the doc's age is under test
    out.append(('quiet evening, 6 minutes old', '2026-10-05 20:41:00',
               move_to(base('2026-10-05'), '2026-10-05 20:35:00', '2026-10-05', '2026-10-05 15:59:30', '20:25:00', fails=111),
               dict(none, today='today', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 6 min ago', 'feed OK'],
                    strip_lacks=['BOX SILENT'], stop='today', orders='today', legtoday='TODAY',
                    asof_has='as of 15:59:30', eq_stale=False, system=True, lasttick='ok')))
    out.append(('quiet Saturday, written after the close', '2026-10-03 12:00:00',
               move_to(base(), '2026-10-03 11:55:00', '2026-10-02', '2026-10-02 15:59:30', '11:45:00'),
               dict(none, today='Fri 10-02', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 5 min ago'],
                    strip_lacks=['BOX SILENT'], stop='Fri 10-02', orders='Fri 10-02', legtoday='FRI 10-02',
                    asof_has='as of Fri 10-02 15:59:30', eq_stale=False)))
    wedge = move_to(base(), '2026-10-03 17:11:40', '2026-10-02', '2026-10-02 15:59:30', '17:01:40')
    wedge['lease']['renew_every_sec'] = 600.0
    out.append(('weekend wedge, Saturday 17:11 doc on Sunday', '2026-10-04 10:00:00', wedge, dict(none,
               silent='BOX SILENT since Sat 17:11', today='Fri 10-02', top=('stale', 'WEBULL STALE since Sat 17:11'),
               strip_has=['BOX SILENT since Sat 17:11'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', eq_stale=True)))
    # Monday in the session on Tuesday's data: 3 CLOSED sessions old (Wed, Thu, Fri), Monday's is under way
    out.append(("KEEL on Tuesday's data, Monday in the session", FRESH_NOW, base('2026-09-29'), dict(none,
               keel='KEEL on Sep 29 data - 3 sessions old', keelwarn='KEEL on Sep 29 data - 3 sessions old',
               keelline='the last closed session is Fri Oct 2, so it is 3 sessions behind',
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False)))
    pf = base()
    pf['health'] = {'publish_fail_today': 5, 'last_publish_ok_et': '10:00:41', 'tick_gap_max_s_today': 75.0}
    pf['events'] = [{'ts_et': '2026-10-05 10:02:50', 'kind': 'publish_down',
                     'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 5 failure(s) today'}] + pf['events']
    out.append(('publish failures + a 75 s stall', FRESH_NOW, pf, dict(none, publish='UPDATES FAILING (5 today)',
               tickgap='BOX STALLED 75 s TODAY', today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['saves failing (5 today)'], strip_lacks=['BOX SILENT'], eq_stale=False)))
    ht = base()
    ht['broker']['halted'] = True
    ht['broker']['halt_reason'] = 'kill file present'
    out.append(('orders halted', FRESH_NOW, ht, dict(none, today='today', top=('halted', 'WEBULL HALTED'),
               ordsum_start='HALTED', ordsum_has=['daily stop used'])))
    # LEDGER step 11: the Orders fold's one-line header carries the daily stop's state (the figure the breaker counts, out of the limit)
    nl = base()
    nl['today']['breaker_input'] = -330.0
    out.append(('daily stop 83% used', FRESH_NOW, nl, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               ordsum_start='OFF', ordsum_has=['$330.00 of $400.00 daily stop used', 'near the limit'], ordsum_lacks=['stopped for the day'])))
    st = base()
    st['today']['breaker_input'] = -410.0
    out.append(('daily stop reached', FRESH_NOW, st, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               ordsum_start='OFF', ordsum_has=['$410.00 of $400.00 daily stop used', 'stopped for the day'], ordsum_lacks=['near the limit'])))
    tr_ = base()
    tr_['breaker_tripped'] = True
    out.append(('breaker tripped, no figure', FRESH_NOW, tr_, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               ordsum_start='OFF', ordsum_has=['daily stop used', 'stopped for the day'], ordsum_lacks=['near the limit'])))
    # review fixes (2026-10-05, second pass)
    out.append(("Monday 09:30:30 just after the open, Friday's doc", '2026-10-05 09:30:30', fri(base()), dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', eq_stale=True)))
    out.append(('Monday 09:31 just after the open, a 09:25 doc', '2026-10-05 09:31:00',
               move_to(base(), '2026-10-05 09:25:00', '2026-10-05', '2026-10-05 09:24:30', '09:24:40'),
               dict(none, today='today', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 6 min ago', 'feed OK'],
                    strip_lacks=['BOX SILENT'], stop='today', orders='today', legtoday='TODAY')))
    armed = fri(base())
    armed['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'lease_ok_to_send': True})
    out.append(("armed book, Friday's doc seen Monday 08:50 (System open)", '2026-10-05 08:50:00', armed, dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], stop='Fri 10-02', orders='Fri 10-02',
               mini_silent='Last known: PAPER, as of Fri 15:58.', ordmode='BOX SILENT', eq_stale=True,
               lasttick='stale')))
    gap = base()
    gap['health'] = {'publish_fail_today': 111, 'last_publish_ok_et': '10:00:41', 'tick_gap_max_s_today': 4.2}
    gap['events'] = [e for e in gap['events'] if e.get('kind') != 'publish_down']
    out.append(('a gap before this save, no failed-save event', FRESH_NOW, gap, dict(none, pubgap='UPDATES PAUSED 2 min',
               today='today', top=('flat', 'WEBULL FLAT'), strip_has=['updates paused 2 min before this one'],
               strip_lacks=['BOX SILENT', 'saves failing'], eq_stale=False)))
    # the page's own read failed: the hero and strip blame the page, never the box (review 4th pass)
    out.append(("the page's own read failed, Friday's doc on Monday 08:50", '2026-10-05 08:50:00', fri(base()), dict(none,
               noread='THIS PAGE CANNOT READ (copy from Fri 15:58)', today='Fri 10-02', top=('noread', 'WEBULL NO STATUS'),
               strip_has=['THIS PAGE CANNOT READ', 'its last copy is from Fri 15:58'], strip_lacks=['BOX SILENT', 'feed OK'],
               eq_stale=True, eq_why='this page cannot read', liveErr=True, system=True)))
    # review fixes (2026-10-05, third pass)
    # saves kept failing after the box's one publish_down event (it logs one per 10 min at most):
    # the event is 13.5 min old, but this page saw the count go 5 -> 7 on the 10:03:06 save
    mem_prev = base()
    mem_prev['updated_at'] = '2026-10-05 10:01:06'
    mem_prev['health'] = {'publish_fail_today': 5, 'last_publish_ok_et': '09:57:46', 'tick_gap_max_s_today': 4.2}
    mem = base()
    mem['health'] = {'publish_fail_today': 7, 'last_publish_ok_et': '10:02:46', 'tick_gap_max_s_today': 4.2}
    mem['events'] = [{'ts_et': '2026-10-05 09:50:00', 'kind': 'publish_down',
                      'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 3 failure(s) today'}] + \
        [e for e in mem['events'] if e.get('kind') != 'publish_down']
    out.append(("saves still failing after the box's 10-minute event", FRESH_NOW, mem, dict(none,
               publish='UPDATES FAILING (7 today)', today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['saves failing (7 today)'], strip_lacks=['BOX SILENT'], eq_stale=False, prev=mem_prev)))
    out.append(("quiet Saturday, KEEL missed Friday's rebuild", '2026-10-03 12:00:00',
               move_to(base('2026-10-01'), '2026-10-03 11:55:00', '2026-10-02', '2026-10-02 15:59:30', '11:45:00'),
               dict(none, today='Fri 10-02', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
                    keel='KEEL on Oct 1 data - 1 session old', keelwarn='KEEL on Oct 1 data - 1 session old',
                    keelline='the latest session is Fri Oct 2, so it is 1 session behind - the last rebuild')))
    out.append(('Monday 17:00 after the close, KEEL rebuild still to come', '2026-10-05 17:00:00',
               move_to(base(), '2026-10-05 16:58:00', '2026-10-05', '2026-10-05 15:59:30', '16:57:00'),
               dict(none, today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
                    keelline='the latest session is Mon Oct 5 - 1 session behind until tonight')))
    pre = move_to(base('2026-10-05'), '2026-10-06 07:55:00', '2026-10-06', '2026-10-06 07:54:30', '07:45:00')
    pre['health']['tick_gap_max_s_today'] = 75.0
    out.append(("Tuesday 08:00 before the open, the last session's stall", '2026-10-06 08:00:00', pre, dict(none,
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
               keelline='the next session is Tue Oct 6 - up to date')))
    for vp in ('laptop', 'phone'):
        # a phone keeps 'checked HH:MM' in the tooltip while the check is fresh (the chip still takes a row of
        # its own in the phone top bar, 70 to 90 px, even when short: a shared top bar call, routed to TRADING-LOG)
        out.append(("HOME tab (%s), Friday's doc on Saturday" % vp, '2026-10-03 12:00:00', fri(base()), dict(none,
                   tab='home', vp=vp, top=('stale', 'WEBULL STALE since Fri 15:58' + (', checked 12:00' if vp == 'laptop' else '')))))
    # review fixes (2026-10-05, fourth pass)
    # a page back hours later the same day with a higher failed-save count: not two saves in a row
    back_prev = move_to(base(), '2026-10-05 10:00:00', '2026-10-05', '2026-10-05 09:59:30', '09:59:40', fails=0)
    back = move_to(base(), '2026-10-05 14:00:00', '2026-10-05', '2026-10-05 13:59:30', '13:59:40', fails=6)
    back['events'] = [{'ts_et': '2026-10-05 11:00:00', 'kind': 'publish_down',
                       'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 1 failure(s) today'}] + \
        [e for e in back['events'] if e.get('kind') != 'publish_down']
    out.append(('page back hours later, more failed saves since', '2026-10-05 14:00:20', back, dict(none,
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['saves failing', 'BOX SILENT'], eq_stale=False,
               prev=back_prev)))
    # the first copy this page saw came from the browser's cache: never a starting count
    cache_prev = base()
    cache_prev['updated_at'] = '2026-10-05 10:02:46'
    cache_prev['health'] = {'publish_fail_today': 5, 'last_publish_ok_et': '10:02:36', 'tick_gap_max_s_today': 4.2}
    out.append(('a cached first copy, then a higher count', FRESH_NOW, mem, dict(none, today='today',
               top=('flat', 'WEBULL FLAT'), strip_lacks=['saves failing'], eq_stale=False, prev=cache_prev, prev_cache=True)))
    # no promised cadence in the doc: the box's slowest rule (10 min) still catches a weekend wedge
    nocad = move_to(base(), '2026-10-03 17:11:40', '2026-10-02', '2026-10-02 15:59:30', '17:01:40')
    nocad['lease'].pop('renew_every_sec', None)
    out.append(('Monday 08:50, a Saturday 17:11 doc, no promised cadence', '2026-10-05 08:50:00', nocad, dict(none,
               silent='BOX SILENT since Sat 17:11', today='Fri 10-02', top=('stale', 'WEBULL STALE since Sat 17:11'),
               strip_has=['BOX SILENT since Sat 17:11'], strip_lacks=['feed OK'], eq_stale=True)))
    # the last good save was on an earlier day (time of day only): the pause's length is left out
    over = move_to(base(), '2026-10-05 09:35:00', '2026-10-05', '2026-10-05 09:34:30', '17:01:40', fails=3)
    over['events'] = [e for e in over['events'] if e.get('kind') != 'publish_down']
    out.append(('a pause from an earlier day (the Sat-Mon wedge)', '2026-10-05 09:35:20', over, dict(none,
               pubgap='UPDATES PAUSED', today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['updates paused since 17:01:40 before this one'], strip_lacks=['BOX SILENT'], eq_stale=False)))
    # an open position: the chip counts it; on a silent box its leg pill turns grey
    def opened(d):
        d['positions'] = {'NOISE': {'side': 'long', 'shares': '10', 'entry_px': '600.10',
                                    'entry_ts': '2026-10-05 10:00:05', 'unrealized': '4.20'}}
        d['positions_live'] = {'legs': [{'leg': 'NOISE', 'side': 'long', 'shares': 10, 'entry_px': 600.1,
                                         'live_px': 600.52, 'live_source': 'stream', 'live_age_s': 1.0,
                                         'open_pnl': 4.2, 'time_in_trade_min': 3}],
                               'total_open_pnl': 4.2, 'legs_net_qty': 10, 'broker_net_qty': 10, 'mismatch': False}
        return d
    out.append(('an open position', FRESH_NOW, opened(base()), dict(none, today='today', top=('open', 'WEBULL 1 OPEN'),
               legpill='colour', live_has='now $600.52', live_lacks='last seen', openpnl='colour', unreal='colour', eq_stale=False,
               recon=('ok', 'OK \u2014 Webull holds long 10 \u00b7 legs sum to long 10'))))
    # silent: no current price - 'last seen ... at' the box's time, never 'now', and the open figures grey
    out.append(('an open position, box silent 5 min', '2026-10-05 10:08:06', opened(base()), dict(none,
               silent='BOX SILENT 5 min', today='today', top=('stale', 'WEBULL STALE 5 min'), legpill='grey',
               live_has='last seen $600.52 at 10:03', live_lacks=' now ', openpnl='grey', unreal='grey', eq_stale=True)))
    blk = base()
    blk['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'lease_ok_to_send': False,
                          'lease_block_reason': 'lease held by another host'})
    out.append(('a blocked book', FRESH_NOW, blk, dict(none, today='today', top=('blocked', 'WEBULL BLOCKED'), eq_stale=False,
               # keeps checklist: another computer holds the lease -> the System fold's host line names the reason, never OK
               system=True, hostline='Running on PROBE-PC \u00b7 one-computer check lease held by another host',
               host=('blocked', ['one-computer check lease held by another host'], False))))
    # a holiday is not a session: Thanksgiving noon with a doc written 5 min ago reads quiet, not silent
    out.append(('Thanksgiving noon, a fresh quiet doc', '2026-11-26 12:00:00',
               move_to(base('2026-11-25'), '2026-11-26 11:55:00', '2026-11-25', '2026-11-25 15:59:30', '11:45:00'),
               dict(none, today='Wed 11-25', top=('flat', 'WEBULL FLAT'), strip_has=['market closed', 'box updated 5 min ago'],
                    strip_lacks=['BOX SILENT', 'market open'], stop='Wed 11-25', orders='Wed 11-25', legtoday='WED 11-25',
                    asof_has='as of Wed 11-25 15:59:30', eq_stale=False,
                    keelline='the latest session is Wed Nov 25 - up to date')))
    # the 30 s timer: a page left open while the box goes quiet (finding 8). Rendered fresh, then the
    # clock moves 5 min on and only the timer's body runs - no new doc, no renderApp from the probe
    out.append(('page left open, the box goes quiet (timer)', '2026-10-05 10:08:36', base(), dict(none,
               silent='BOX SILENT 5 min', today='today', top=('stale', 'WEBULL STALE 5 min'),
               strip_has=['BOX SILENT 5 min'], eq_stale=True, tick=True, render_at=FRESH_NOW)))
    # HOME: the chip judges its copy as of the page's last check and says when that was
    out.append(('HOME tab, checked 30 min ago on a fresh doc', '2026-10-05 10:33:30', base(), dict(none,
               tab='home', vp='laptop', top=('flat', 'WEBULL FLAT, checked 10:03'), checked_at=FRESH_NOW)))
    # review fixes (2026-10-05, fifth pass)
    # 09:25 the box goes from every 10 min to every minute: the gap before the first faster save ran
    # under the 10 min rule, so a day with failed saves must not flash UPDATES PAUSED
    flash = move_to(base(), '2026-10-05 09:25:05', '2026-10-05', '2026-10-05 09:24:30', '09:16:40', fails=5)
    flash['lease']['renew_every_sec'] = 60.0
    flash['events'] = [e for e in flash['events'] if e.get('kind') != 'publish_down']
    out.append(('09:25 switch to the faster cadence, failed saves earlier today', '2026-10-05 09:25:20', flash, dict(none,
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['updates paused', 'BOX SILENT'], eq_stale=False)))
    # the clocks go back: a doc written at 01:30 in the repeated (winter time) hour, seen at 01:35 winter time
    dst = move_to(base('2026-10-30'), '2026-11-01 01:30:00', '2026-10-30', '2026-10-30 15:59:30', '01:20:00')
    out.append(('the repeated 01:00 hour when the clocks go back', et_ms('2026-11-01 01:35:00') + 3600000, dst, dict(none,
               today='Fri 10-30', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 5 min ago'], strip_lacks=['BOX SILENT'],
               stop='Fri 10-30', orders='Fri 10-30', eq_stale=False)))
    # this device lost its own network: no listener error arrives, the copy just ages
    out.append(('this device offline, its copy 5 min old in the session', '2026-10-05 10:08:06', base(), dict(none,
               noread='THIS PAGE CANNOT READ (copy from Mon 10:03)', today='today', top=('noread', 'WEBULL NO STATUS'),
               strip_has=['THIS PAGE CANNOT READ'], strip_lacks=['BOX SILENT', 'feed OK'], eq_stale=True,
               eq_why='this page cannot read', offline=True)))
    # a HOME tab left visible overnight: the check is from yesterday and says which day
    eve = move_to(base(), '2026-10-05 19:55:00', '2026-10-05', '2026-10-05 15:59:30', '19:45:00')
    for vp in ('laptop', 'phone'):
        out.append(('HOME tab (%s) left open overnight, checked the evening before' % vp, '2026-10-06 10:00:00', eve, dict(none,
                   tab='home', vp=vp, top=('flat', 'WEBULL FLAT, checked Mon 19:56'), checked_at='2026-10-05 19:56:00')))
    # an account with no Webull paper box: no chip at all
    out.append(('HOME tab, an account with no Webull box', FRESH_NOW, base(), dict(none,
               tab='home', vp='laptop', top=None, top_hidden=True, missing=True)))
    # a phone's first read lands a stale doc away from the board: the longer chip wraps the top bar,
    # and the sticky sub-tab strip must move down with it (scrolled 600 px)
    out.append(('HOME tab (phone), the first read lands a stale doc', '2026-10-03 12:00:00', fri(base()), dict(none,
               tab='home', vp='phone', top=('stale', 'WEBULL STALE since Fri 15:58'), unloaded=True, fetch=fri(base()), pin=True)))
    halted = base()
    halted['updated_at'] = '2026-10-05 10:19:50'
    halted['broker'].update({'halted': True, 'halt_reason': 'kill file present'})
    out.append(('HOME tab, a .get() lands a halted doc', '2026-10-05 10:20:00', base(), dict(none,
               tab='home', vp='laptop', top=('halted', 'WEBULL HALTED, checked 10:20'), checked_at=FRESH_NOW,
               fetch=halted)))
    # review fixes (2026-10-05, sixth pass)
    # one failed save, logged by the box (its publish_down comes on the FIRST failure), the next save
    # worked 60 s later: a blip, not UPDATES FAILING (and a 60 s gap is not UPDATES PAUSED either)
    one = base()
    one['health'] = {'publish_fail_today': 1, 'last_publish_ok_et': '10:02:06', 'tick_gap_max_s_today': 4.2}
    one['events'] = [{'ts_et': '2026-10-05 10:02:30', 'kind': 'publish_down',
                      'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 1 failure(s) today'}] + \
        [e for e in one['events'] if e.get('kind') != 'publish_down']
    out.append(('one failed save, the box logged it', FRESH_NOW, one, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               strip_lacks=['saves failing', 'updates paused', 'BOX SILENT'], eq_stale=False)))
    # this page saw the count go 0 -> 1 between two saves in a row: also a blip
    rise_prev = base()
    rise_prev['updated_at'] = '2026-10-05 10:02:06'
    rise_prev['health'] = {'publish_fail_today': 0, 'last_publish_ok_et': '10:01:56', 'tick_gap_max_s_today': 4.2}
    rise_prev['events'] = [e for e in rise_prev['events'] if e.get('kind') != 'publish_down']
    rise1 = base()
    rise1['health'] = {'publish_fail_today': 1, 'last_publish_ok_et': '10:02:46', 'tick_gap_max_s_today': 4.2}
    rise1['events'] = [e for e in rise1['events'] if e.get('kind') != 'publish_down']
    out.append(('one failed save seen save to save', FRESH_NOW, rise1, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               strip_lacks=['saves failing'], eq_stale=False, prev=rise_prev)))
    # Monday 08:00 on Thursday's data: only Friday's rebuild was missed (1 closed session), and it is flagged
    out.append(("Monday 08:00, KEEL on Thursday's data", '2026-10-05 08:00:00',
               move_to(base('2026-10-01'), '2026-10-05 07:55:00', '2026-10-02', '2026-10-02 15:59:30', '07:45:00'),
               dict(none, today='Fri 10-02', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
                    keel='KEEL on Oct 1 data - 1 session old', keelwarn='KEEL on Oct 1 data - 1 session old',
                    keelline='the last closed session is Fri Oct 2, so it is 1 session behind')))
    # the board's listener re-attaches after an error and its first snapshot is this browser's cached
    # copy: that is not a read, so the page still cannot read (it must not start blaming the box)
    out.append(('a cached listener snapshot after a read error', '2026-10-05 08:50:00', fri(base()), dict(none,
               noread='THIS PAGE CANNOT READ (copy from Fri 15:58)', today='Fri 10-02', top=('noread', 'WEBULL NO STATUS'),
               strip_has=['THIS PAGE CANNOT READ'], strip_lacks=['BOX SILENT'], eq_stale=True, liveErr=True, cachesnap=True)))
    # shown again away from the board: one read per 5 min at most there (each read is the whole doc), 30 s on the board
    out.append(('page shown again, HOME and the board', FRESH_NOW, base(), dict(none,
               tab='home', vp='laptop', top=('flat', 'WEBULL FLAT, checked 10:03'), visread=[0, 1, 1])))
    # KEEPS CHECKLIST (2026-10-07, post-landing review 2026-10-08): the hero's amber broker line (none / one / the fixture's eight, above / a box summary
    # that disagrees), the alarm chips (each drawn and left out; grey on a silent box), the Account fold's share check when Webull and the legs disagree,
    # the System fold's host line and Orders sentences, a strategy row's TODAY, the daily stop's own figure
    nobo = base()
    for t in nobo['trades_all']:
        t['book_only'] = False
    out.append(('no book-only trade', FRESH_NOW, nobo, dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False,
               broker_line=False)))
    onebo = base()
    kept = False
    for t in onebo['trades_all']:
        if t.get('book_only') and not _is_shadow(t) and not kept:
            kept = True
        else:
            t['book_only'] = False
    out.append(('one book-only trade', FRESH_NOW, onebo, dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False,
               broker_line='broker made -$23.58 of that (1 book-only trade excluded)')))
    bx = base()
    bx['book_only_summary'] = dict(bx['book_only_summary'], book_only_count=3, broker_net=12.34)    # as if the box summed a shadow row, or before a trim
    out.append(("the box's own broker figure disagrees", FRESH_NOW, bx, dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False,
               broker_line='broker made -$3.98 of that (8 book-only trades excluded)')))
    ntp = base()
    ntp['parity'] = dict(ntp['parity'], checked=5, ok=3, failed=2, worst_err_usd=4.2, note='the NinjaTrader mirror check: 2 of 5 trades are off')
    out.append(('NT parity: 2 of 5 mismatched', FRESH_NOW, ntp, dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False,
               par_chip='2 PARITY MISMATCHES', fills_chip=False)))
    fbb = base()
    fbb['broker_parity'] = dict(fbb['broker_parity'], board_flag=True)
    out.append(('fills behind the backtest (rolling flag)', FRESH_NOW, fbb, dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False,
               par_chip=None, fills_chip=True)))
    sbx = base()
    sbx['parity'] = dict(sbx['parity'], checked=5, ok=4, failed=1, worst_err_usd=2.1, note='the NinjaTrader mirror check: 1 of 5 trades is off')
    sbx['broker_parity'] = dict(sbx['broker_parity'], board_flag=True)
    out.append(('one parity mismatch + fills behind, box silent 5 min', '2026-10-05 10:08:06', sbx, dict(none, silent='BOX SILENT 5 min',
               today='today', top=('stale', 'WEBULL STALE 5 min'), strip_has=['BOX SILENT 5 min'], strip_lacks=['feed OK'], stop='today',
               orders='today', legtoday='TODAY', eq_stale=True, mini_silent='Last known: OFF, as of Mon 10:03.',
               par_chip='1 PARITY MISMATCH', fills_chip=True)))
    shr = base()
    shr['positions_live'] = dict(shr['positions_live'], mismatch=True, broker_net_qty=10, legs_net_qty=0)
    out.append(('Webull holds 10 shares the legs do not', FRESH_NOW, shr, dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False,
               recon=('mismatch', 'MISMATCH \u2014 Webull holds long 10 \u00b7 legs sum to flat'))))
    # the host line on a silent box: grey, last known with its time, never a green OK (review L2)
    out.append(('the box silent 5 min, System open', '2026-10-05 10:08:06', base(), dict(none, silent='BOX SILENT 5 min',
               today='today', top=('stale', 'WEBULL STALE 5 min'), eq_stale=True, system=True,
               hostline='Running on PROBE-PC \u00b7 one-computer check OK (last known, as of Mon 10:03)',
               host=('stale', ['Running on PROBE-PC', 'one-computer check OK (last known, as of Mon 10:03)'], False))))

    def alarms(d):
        d['breaker_tripped'] = True
        d['kill'] = True
        d['broker_parity']['board_flag'] = True
        d['parity'] = dict(d['parity'], checked=3, ok=1, failed=2)
        return d
    chips = ['BREAKER TRIPPED', 'KILL ACTIVE', 'FILLS BEHIND BACKTEST', '2 PARITY MISMATCHES']
    out.append(('the hero alarm chips', FRESH_NOW, alarms(base()), dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               eq_stale=False, flags_has=dict((c, 'colour') for c in chips), par_chip='2 PARITY MISMATCHES', fills_chip=True)))
    out.append(('the hero alarm chips, box silent 5 min', '2026-10-05 10:08:06', alarms(base()), dict(none, silent='BOX SILENT 5 min',
               today='today', top=('stale', 'WEBULL STALE 5 min'), eq_stale=True, flags_has=dict((c, 'grey') for c in chips),
               par_chip='2 PARITY MISMATCHES', fills_chip=True)))
    old = base()
    old['today'].pop('legs_record', None)
    out.append(('an older box with no legs_record', FRESH_NOW, old, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               eq_stale=False, legtodayval=leg_today_want(old, 'NOISE'), stop_has=['estimate'])))
    sysfresh = dict(none, today='today', top=('flat', 'WEBULL FLAT'), eq_stale=False, strip_lacks=['BOX SILENT'], system=True)
    pp = base()
    pp['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'lease_ok_to_send': True, 'lease_block_reason': None})
    out.append(('PAPER, sending orders, System open', FRESH_NOW, pp, dict(sysfresh,
               ordmode_has=['PAPER', 'Sending orders to the Webull paper (practice) account.'],
               hostline='Running on PROBE-PC \u00b7 one-computer check OK', host=('ok', ['Running on PROBE-PC', 'one-computer check OK'], True))))
    bl = base()
    bl['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'lease_ok_to_send': False,
                         'lease_block_reason': "lease unverifiable: host 'CLOUD-VM' claims the lease but its timestamp is missing"})
    out.append(('BLOCKED (lease unverifiable), System open', FRESH_NOW, bl, dict(sysfresh, top=('blocked', 'WEBULL BLOCKED'),
               ordmode_has=['BLOCKED', "can't confirm this is the only computer trading"],
               host=('blocked', ["one-computer check can't confirm this is the only computer trading"], False))))
    hr = base()
    hr['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'halted': True,
                         'halt_reason': "reconcile mismatch: [{'symbol': 'QQQ', 'broker': 12.0, 'believed': 22.0}]"})
    out.append(('HALTED, System open', FRESH_NOW, hr, dict(sysfresh, top=('halted', 'WEBULL HALTED'),
               ordmode_has=['HALTED', "positions at Webull don't match the notebook"])))
    fb = fri(base())
    fb['today']['breaker_input'] = -120.0
    out.append(("Friday's doc with the breaker's own figure, Saturday noon", '2026-10-03 12:00:00', fb, dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'), stop='Fri 10-02',
               eq_stale=True, stop_has=['$120.00 of $400.00 daily stop used', 'from Fri 10-02', 'breaker figure'], stop_lacks=['estimate'])))
    # three key variants again in MONO at 390x844
    for nm, now, doc, ex in [o for o in out if o[0] in ("Saturday noon, Friday's doc",
                                                        "the page's own read failed, Friday's doc on Monday 08:50",
                                                        'an open position, box silent 5 min')]:
        out.append((nm + ' (MONO, 390x844)', now, doc, dict(ex, vp='phone390', theme='mono')))
    return out


# Builds this gate must catch, made from the CURRENT index.html by one string replacement each.
# LEDGER step 12: the board's body is ledgerFrameHtml({id:'qb', top, side, rest}); qbTop holds the top block's sections and LEDGER_TOP_ORDER picks their
# order (hero, status, pills, chart, stats, more, cal; this board's pills ride in its chart section, its More stats in its stats section)
_CRLF = '\r\n'
_QBTOP1 = "        const qbTop={hero:'<div class=\"qbx-hero\">'+qbHeroHtml+'</div>',status:qbStatusSec,pills:'',chart:'<div class=\"qbx-chart\">'+equityHtml+'</div>',"
_QBTOP2 = "          stats:'<div class=\"qbx-stats qbx-lgstats\">'+qbLgStatsHtml+'</div>',more:'',cal:'<div class=\"qbx-activity\">'+qbCalHtml+'</div>'};"
_FR_BODY = "body=ledgerFrameHtml({id:'qb',cls:'qb-shell qbx-lg6',"
_FR_TOP = "top:LEDGER_TOP_ORDER.map(k=>qbTop[k]||'').join(''),side:qbSideNew,"
_FR_HIST = "            rest:'<div class=\"qbx-history qbx-section\"><div class=\"qb-section-hd\">History</div>'+qbTradesCard+'</div>'"
_FR_OWN = "              +'<div class=\"qbx-own\">'+qbOwnSecs+'</div>'})"
# the chart section: the pills, the chart box, then the shared chart foot (the caption and the key)
_EQA = "            equityHtml='<div class=\"qb-chart-wrap\">'+periodTabsHtml"
_EQB = "              +'<div class=\"qbx-lgchart\" id=\"qb-lg-chart\"></div>'"
_EQC = ("              +ledgerChartFootHtml({id:'qb',cap:'<span class=\"qbx-chart-cap'+((qbRange&&qbRange!=='ALL')?'':' qbx-cap-all')+'\">'+qbRangeCap+'</span>',"
        "key:keyHtml})+'</div>';")
# the strategy list's Filters row (passed to ledgerListHtml as o.filters)
_QB_FILT = (_CRLF + "            filters:ledgerFiltersHtml({id:'qb',none:'This list has no filters: every strategy counts. Retired and Shadow are the folds below.'})});")

MUTANTS = [
    ('chart-not-drawn',
     "if(window._qbLgChart){const lgw=content.querySelector('#qb-lg-chart');if(lgw)ledgerChartRender(lgw,window._qbLgChart);}",
     '',
     'the shared chart is never drawn into its box (no error thrown)'),
    ('retired-open-by-default',
     'let qbRetOpen=!!window._qbRetiredOpen;',
     'let qbRetOpen=true;',
     'the Retired group opens by default'),
    ('bare-leg-on-rows',
     "'<span class=\"qb-trade-leg\" title=\"the strategy (family and run number) that took this trade\">'+qeTradeLegName(t)+'</span>'",
     "'<span class=\"qb-trade-leg\">'+naS(t&&t.leg)+'</span>'",
     "trade rows name the box's bare leg key again ('ENGUQ')"),
    ('caveat-days-lost',
     "bands.push({i:i,title:tip+'. These trades still count.'});",
     '',
     'the data-caveat days are no longer hatched on the chart'),
    ('scrub-leaves-hero',
     'h.big.textContent=_hmMoney(qbBase+p.v+(atNow?openMarkPnl:0));',
     '',
     'a chart scrub no longer writes the big number'),
    ('phone-overflow',
     '<div class="qbx-lgchart" id="qb-lg-chart"></div>',
     '<div class="qbx-lgchart" id="qb-lg-chart" style="min-width:640px"></div>',
     'the chart is wider than a phone and the page scrolls sideways'),
    ('wrong-run',
     "if(dg)return '#'+dg[1];",
     "if(dg)return '#999';",
     'trade rows name a run that did not take the trade (the run lookup broke)'),
    ('lines-same-dash',
     "const _LG_DASHES=['none','5 3','1.5 3','7 2 1.5 2'];",
     "const _LG_DASHES=['none','none','none','none'];",
     'the three faint lines share one dash, so MONO cannot tell them apart'),
    # freshness (sweep 2026-10-05)
    ('silent-chip-never-shown',
     "        if(QF.stale&&!qbNoRead)out.push(qbFreshChip(",
     "        if(false)out.push(qbFreshChip(",
     'a silent box never gets its BOX SILENT chip'),
    ('fetch-clock-age',
     "  const t=qbEtWallMs(QE.updated_at,nowMs);",
     "  const t=window._qqqExecFetchedAt||qbNowMs();",
     "the doc's age is measured from when the page fetched it, not when the box wrote it (finding 8)"),
    ('evening-false-alarm',
     "    r.stale=nowMs>=lc+900e3?t<lc:t<lc-90e3;",
     "    r.stale=r.ageS>90;",
     'a quiet evening doc reads silent again (the fixed 90 s rule, finding 20)'),
    ('old-day-reads-today',
     "  r.isToday=r.docDay===r.todayNY;",
     "  r.isToday=true;",
     "an earlier trading day's figures are labelled today again (finding 9)"),
    ('keel-age-ignored',
     "    const behind=qbSessionsAfter(th,r.lastSession);",
     "    const behind=0;",
     'a KEEL model 4 sessions old reads current (finding 21)'),
    ('top-chip-gone',
     "${typeof qbTopChipHtml==='function'?qbTopChipHtml():''}",
     "",
     'the top bar has no WEBULL chip (finding 23)'),
    # review fixes (second pass)
    ('open-grace-hides-frozen-doc',
     "    r.stale=(nowMs-(okAtOpen?Math.max(t,openMs):t))/1000>90;",
     "    r.stale=(nowMs-Math.max(t,openMs))/1000>90;",
     "for 90 s after the open a doc frozen since Friday reads fresh again"),
    ('no-grace-after-open',
     "    r.stale=(nowMs-(okAtOpen?Math.max(t,openMs):t))/1000>90;",
     "    r.stale=(nowMs-t)/1000>90;",
     "a healthy pre-open doc reads silent in the first 90 s after the open"),
    ('orders-summary-pill-not-silent',
     "            if(QF.stale){pillTxt=qbSilentWord;pillCol=qbNoRead?'var(--attn-amber)':'var(--attn-red)';filled=true;}",
     "",
     "the sidebar Orders pill keeps PAPER while the box is silent (finding 8)"),
    ('orders-card-not-silent',
     "if(QF.stale){sentence=(qbNoRead?",
     "if(false){sentence=(qbNoRead?",
     "the full Orders card keeps PAPER / 'Sending orders' while the box is silent (finding 8)"),
    ('past-day-not-dimmed',
     "const qbDimCss=QF.isToday?'':'opacity:.55;';",
     "const qbDimCss='';",
     "figures from an earlier trading day are no longer dimmed (finding 9)"),
    ('keel-sentence-never-behind',
     "(kf.stale?(', so it is <b>'",
     "(false?(', so it is <b>'",
     "the KEEL line never says how many sessions behind it is (finding 21)"),
    ('account-change-undated',
     "const chgDay=(",
     "const chgDay=null,chgDayWas=(",
     "the Account change reads as today's on an earlier day's doc (finding 24)"),
    ('reconcile-reads-current',
     ":(QF.stale\r\n",
     ":(false\r\n",
     "the Account reconcile line stays OK-green on a silent box"),
    ('cant-read-blames-box',
     "else if(Fnow.stale&&cantRead){",
     "else if(false){",
     "a page whose own read failed tells the owner the box is silent"),
    ('pause-chip-never-shown',
     "if(QF.pubGap)out.push(qbFreshChip(",
     "if(false)out.push(qbFreshChip(",
     "a gap in the box's saves is never shown (finding 22)"),
    # review fixes (third pass)
    ('top-chip-board-only',
     "${typeof qbTopChipHtml==='function'?qbTopChipHtml():''}",
     "${(typeof qbTopChipHtml==='function'&&activeTab==='augur'&&augurSub==='qqqpaper')?qbTopChipHtml():''}",
     'the top bar WEBULL chip is drawn only on the WEBULL PAPER board (finding 23)'),
    ('listener-always-on',
     "return !!(db&&auth&&auth.currentUser&&activeTab==='augur'&&augurSub==='qqqpaper'&&document.visibilityState==='visible');",
     "return !!(db&&auth&&auth.currentUser&&document.visibilityState==='visible');",
     'the full-doc listener runs on every tab (about 0.7 GB a day per visible device against the 10 GiB a month cap)'),
    ('fail-memory-ignored',
     "  if(PM&&PM.riseMs!=null&&PM.day===r.docDate&&nowMs-PM.riseMs<=600e3&&PM.riseMs-nowMs<=60e3)r.pubFailing=true;",
     "",
     "saves that keep failing after the box's one 10-minute event go unreported (finding 22)"),
    ('keel-missed-reads-up-to-date',
     "(kf.rebuild==='missed'?', so it is",
     "(false?', so it is",
     "KEEL one session behind after a missed rebuild says 'up to date' (finding 21)"),
    ('stall-last-session-as-today',
     "  const gapToday=r.isToday&&dp.date===np.date&&qbIsSessionDay(dp.date)&&dp.mins>=565;",
     "  const gapToday=r.isToday;",
     "before the open the last session's longest pause reads 'BOX STALLED ... TODAY' (finding 22)"),
    ('box-flags-not-greyed',
     "const qbChipG=(txt,col)=>qbChip(txt,QF.stale?'var(--text4)':col);",
     "const qbChipG=(txt,col)=>qbChip(txt,col);",
     "the box's own flags (NOT READY, BREAKER, FEED STALE) stay red / amber on a silent box (finding 8)"),
    ('system-tick-fixed-90s',
     "const tickStale=QF.ok&&QF.stale;",
     "const tickStale=QF.ok&&QF.ageS>90;",
     'System LAST TICK goes back to the fixed 90 s rule and calls a quiet evening STALE (finding 20)'),
    # review fixes (fourth pass)
    ('fail-memory-not-in-a-row',
     "if(rise>0&&inARow){",
     "if(rise>0){",
     'a page back hours later reads every failed save since as UPDATES FAILING (false alarm)'),
    ('cached-copy-counts',
     "    if(!QE||fromCache)return;",
     "    if(!QE)return;",
     "the browser's cached first copy becomes the starting count for UPDATES FAILING"),
    ('no-cadence-fallback',
     "const cadEff=(isFinite(cad)&&cad>0)?cad:600;",
     "const cadEff=(isFinite(cad)&&cad>0)?cad:1e9;",
     'a doc without its promised cadence, frozen after the close, reads fresh until the next open'),
    ('pause-length-across-days',
     "'UPDATES PAUSED'+(QF.pubGapDayUnknown?'':(' '+qbAgoText(QF.pubGap)))",
     "'UPDATES PAUSED'+(' '+qbAgoText(QF.pubGap))",
     "a pause from an earlier day shows a length the box cannot know ('16 h' after a 40 h wedge)"),
    ('board-blames-box-on-read-failure',
     "const qbNoRead=QF.ok&&QF.stale&&qbCantRead();",
     "const qbNoRead=false;",
     "the hero and strip say BOX SILENT when it is this page that cannot read"),
    ('new-year-saturday-holiday',
     "return w===6?((m===1&&d===1)?null:qbAddDays(s,-1))",
     "return w===6?(qbAddDays(s,-1))",
     'Friday Dec 31 before a Saturday New Year is treated as a holiday (NYSE is open)'),
    ('holidays-ignored',
     "if(w===0||w===6)return false;return !_qbHolidays(+s.slice(0,4))[s];}",
     "if(w===0||w===6)return false;return true;}",
     'market holidays read as sessions (Thanksgiving noon would call a quiet box silent)'),
    ('top-chip-hidden',
     "'<span id=\"qb-top-chip\" style=\"display:inline-flex;",
     "'<span id=\"qb-top-chip\" style=\"display:none;",
     'the top bar WEBULL chip is in the page but not drawn'),
    ('fresh-timer-removed',
     "window._qbFreshTimer=setInterval(qbFreshTick,30000);",
     "",
     'nothing re-judges the doc while the box is silent, so a page left open never turns stale (finding 8)'),
    ('top-chip-refresh-noop',
     "function qbTopChipRefresh(){try{const el=",
     "function qbTopChipRefresh(){return;try{const el=",
     'the top bar chip is never redrawn in place (a read landing away from the board is not shown)'),
    ('tick-no-board-redraw',
     "!==window._qbFreshDrawnKey)_qqqExecLiveRender();",
     "!==window._qbFreshDrawnKey){}",
     'the board is not redrawn when the box goes quiet with the page open (finding 8)'),
    ('top-chip-judged-now-off-board',
     "const F=live?Fnow:qbFreshness(QE,chk?Math.min(chk,nowMs):nowMs);",
     "const F=Fnow;",
     'away from the board the chip calls a copy it has not re-checked STALE (it claims more than it knows)'),
    ('leg-pill-not-greyed',
     "const badgeColor=QF.stale?'var(--text4)':(",
     "const badgeColor=false?'var(--text4)':(",
     "the strategy rows' position pills stay in colour on a silent box (finding 8)"),
    ('top-chip-always-flat',
     "txt=(nOpen>0?('WEBULL '+nOpen+' OPEN'):'WEBULL FLAT')+chkTxt",
     "txt='WEBULL FLAT'+chkTxt",
     "the top bar chip says FLAT with a position open"),
    # review fixes (fifth pass)
    ('pause-judged-by-new-cadence',
     "const cadOk=Math.max(Number(QE.lease&&QE.lease.renew_every_sec)||0,qbBoxRuleS(okMs));",
     "const cadOk=qbCadenceS(QE,okMs);",
     "the 09:25 switch to the faster cadence flashes UPDATES PAUSED on any day with a failed save"),
    ('fallback-hour-read-early',
     "if(typeof refMs==='number'&&isFinite(refMs)&&refMs-t>1800e3){",
     "if(false){",
     "a doc written in the repeated 01:00 hour in November reads an hour old (BOX SILENT for about 70 min)"),
    ('offline-blames-box',
     "try{if(typeof navigator!=='undefined'&&navigator.onLine===false)return true;}catch(e){}",
     "",
     "a viewer whose own network dropped is told the box is silent"),
    ('check-day-left-out',
     "chkOld=!!chkP&&chkP.date!==qbNyParts(nowMs).date;",
     "chkOld=false;",
     "a HOME tab left open overnight shows yesterday's check as 'checked 19:56', which reads as today"),
    ('chip-for-no-box',
     "if(!QE&&window._qqqExecMissing)return empty;",
     "",
     "an account with no Webull box gets a 'WEBULL ?' chip on every tab"),
    ('sub-strip-not-repinned',
     "if(tb&&sb&&sb.style.position==='sticky')sb.style.top=tb.offsetHeight+'px';",
     "",
     "on a phone the chip wraps the top bar after a read and the sticky sub-tab strip slides under it"),
    ('noread-pill-red',
     "if(QF.stale){pillTxt=qbSilentWord;pillCol=qbNoRead?'var(--attn-amber)':'var(--attn-red)';filled=true;}",
     "if(QF.stale){pillTxt=qbSilentWord;pillCol='var(--attn-red)';filled=true;}",
     "the Orders pill says NO STATUS in BOX SILENT's red when it is this page that cannot read"),
    ('noread-card-pill-red',
     "That may no longer be true.';pillTxt=qbSilentWord;pillCol=qbNoRead?'var(--attn-amber)':'var(--attn-red)';",
     "That may no longer be true.';pillTxt=qbSilentWord;pillCol='var(--attn-red)';",
     "the System Orders card says NO STATUS in BOX SILENT's red when it is this page that cannot read"),
    ('account-stale-blames-box',
     "const eqStaleWhy=qbNoRead?(",
     "const eqStaleWhy=false?(",
     "the Account STALE flag says the box is silent when it is this page that cannot read"),
    ('blocked-never-shown',
     "else if((mode==='PAPER'||mode==='LIVE')&&BR.lease_ok_to_send===false){st='blocked'",
     "else if(false){st='blocked'",
     'a blocked book reads FLAT in the top bar'),
    # review fixes (sixth pass)
    ('one-event-alarms',
     "r.pubFails>=2&&nowMs-lastFail",
     "nowMs-lastFail",
     "one failed save (the box logs publish_down on the first one) shows UPDATES FAILING for 10 min"),
    ('one-rise-alarms',
     ">=2)m.riseMs=t;",
     ">=1)m.riseMs=t;",
     "a failed-save count going up by 1 between two saves shows UPDATES FAILING"),
    ('keel-counts-open-session',
     "    const done=qbSessionsAfter(th,r.lastDone);",
     "    const done=behind;",
     "KEEL's age counts the session under way ('2 sessions old' on Monday morning when only Friday's rebuild was missed)"),
    ('keel-missed-no-chip',
     "warn:behind>1||rebuild==='missed',",
     "warn:behind>1,",
     "a rebuild missed on Friday evening raises no KEEL chip until Monday"),
    ('cached-snapshot-reads',
     "if(!fc){window._qqqExecFetchedAt=Date.now();window._qqqExecTriedAt=Date.now();",
     "if(true){window._qqqExecFetchedAt=Date.now();window._qqqExecTriedAt=Date.now();",
     "a cached listener snapshot after a read error clears THIS PAGE CANNOT READ, so the page blames the box"),
    ('vis-read-30s-everywhere',
     "(onBoard?30000:300000)",
     "30000",
     "every tab reads the whole doc each time the page is shown again, up to twice a minute"),
    ('live-line-says-now',
     "(QF.stale?liveLastSeen:(' · now '",
     "(false?liveLastSeen:(' · now '",
     "an open position on a silent box still says 'now' with a price the page does not have"),
    ('open-pnl-not-greyed',
     "<b data-qbopenpnl=\"'+key+'\" style=\"color:'+(QF.stale?",
     "<b data-qbopenpnl=\"'+key+'\" style=\"color:'+(false?",
     "the Open figure of a position on a silent box stays green / red"),
    ('unreal-not-greyed',
     "data-qbunreal=\"'+key+'\" style=\"font-size:14px;font-weight:600;color:'+(p?(QF.stale?",
     "data-qbunreal=\"'+key+'\" style=\"font-size:14px;font-weight:600;color:'+(p?(false?",
     "the UNREALIZED figure of a position on a silent box stays green / red"),
    # LEDGER step 6 (shared stats strip + More stats)
    ('stats-ignore-range',
     "const qbStatRows=qbRangeTrades.map(",
     "const qbStatRows=trades.map(",
     "the stat tiles count every trade whatever range is chosen"),
    ('zero-is-a-loss',
     "}else if(v<0){losses++;gl-=v;",
     "}else if(v<=0){losses++;gl-=v;",
     "a $0 trade counts as a loss in the win rate (TRADING-LOG mistake item 5)"),
    ('stats-book-pnl',
     "{pnl:qePnlOf,day:qeTradeDate,sorted:true}",
     "{pnl:t=>+t.pnl||0,day:qeTradeDate,sorted:true}",
     "the tiles add up the book's own pnl instead of the P&L of record"),
    ('more-stats-not-wired',
     "content.querySelectorAll('[data-lgmore=\"qb\"]').forEach(",
     "content.querySelectorAll('[data-lgmore=\"qb-off\"]').forEach(",
     "the More stats fold never opens"),
    # LEDGER step 6 review fixes
    ('more-stats-not-remembered',
     "const qbMoreOpen=(()=>{let o=window._qbMoreStatsOpen!=null?!!window._qbMoreStatsOpen:!!(APREF.qqqMoreStatsOpen!=null&&+APREF.qqqMoreStatsOpen);try{const sv=localStorage.getItem('el_qb_morestats_open');if(sv!=null)o=sv==='1';}catch(e){}return o;})();",
     "const qbMoreOpen=!!window._qbMoreStatsOpen;",
     "an open More stats fold is closed again after a reload"),
    ('account-gone-on-empty-range',
     "+((qbMoreOpen&&!qbLs)?qbMoreEmptyHtml():",
     "+(false?qbMoreEmptyHtml():",
     "with no trade closed in the range (TODAY before the first exit) More stats loses equity, open exposure and the loss limit"),
    ('book-figure-counts-book-only',
     "if(t.book_only)bo++;else{broker+=v;const a=qeFinRec(t.pnl),r=qeFinRec(t.real_pnl);book+=a!==null?a:(r!==null?r:0);}",
     "const a=qeFinRec(t.pnl),r=qeFinRec(t.real_pnl);book+=a!==null?a:(r!==null?r:0);if(t.book_only)bo++;else{broker+=v;}",
     "Book figure adds up the book-only trades that Broker made leaves out, so the two rows are not like for like"),
    ('shadow-on-board',
     "const trades=(QE.trades_all||[]).filter(t=>!qbIsShadowRow(t));",
     "const trades=(QE.trades_all||[]).filter(t=>true);",
     "a shadow row enters the hero, the chart, the stat tiles, More stats and the trade list"),
    ('pf-line-swapped',
     "ledgerShortMoney(s.grossWin).slice(1)+' won &middot; '+ledgerShortMoney(s.grossLoss).slice(1)+' lost'",
     "ledgerShortMoney(s.grossLoss).slice(1)+' won &middot; '+ledgerShortMoney(s.grossWin).slice(1)+' lost'",
     "the PROFIT FACTOR line swaps what was won and what was lost"),
    ('best-trade-is-worst',
     "best=Math.max.apply(null,pv)",
     "best=Math.min.apply(null,pv)",
     "More stats' best trade shows the worst one"),
    # LEDGER step 6 review fixes, round 2
    ('stats-strip-hidden',
     ".qbx-lgstats{padding:16px 0 0}",
     ".qbx-lgstats{padding:16px 0 0;display:none}",
     "the stat strip and the More stats fold are on the page but cannot be seen"),
    ('stats-below-history',
     _FR_TOP + _CRLF + _FR_HIST,
     _FR_TOP.replace('.map(', ".filter(k=>k!=='stats').map(") + _CRLF + _FR_HIST + '+qbTop.stats',
     "the stat strip is drawn under the History section (on a phone, under the whole trade list)"),
    ('stats-reverse-order',
     ".sort((a,b)=>qbTsOf(a)<qbTsOf(b)?-1:(qbTsOf(a)>qbTsOf(b)?1:0));",
     ".sort((a,b)=>qbTsOf(a)<qbTsOf(b)?1:(qbTsOf(a)>qbTsOf(b)?-1:0));",
     "the stats walk the trades newest first, so the current streak is the oldest one"),
    ('more-stats-change-undated',
     "acct.push(['Account change '+(chgDay?('on '+chgDay):'today'),",
     "acct.push(['Account change '+(false?('on '+chgDay):'today'),",
     "More stats calls an earlier day's account change 'today'"),
    ('hold-missing',
     "Object.assign({},t,{durationMins:qbHoldMins(t)})",
     "Object.assign({},t,{durationMins:null})",
     "More stats' Average hold reads '--' with every trade's times in the doc"),
    ('mono-hue-in-fold',
     ".qbx-lgstats{padding:16px 0 0}",
     ".qbx-lgstats{padding:16px 0 0}\r\n[data-theme=mono] .qbx-lgstats .lg-ms-row .v.lg-up{color:#e33}",
     "a More stats value is drawn in a colour under MONO (MONO has no hue)"),
    ('empty-fold-no-gap',
     "'<div class=\"lg-ms-grid\" style=\"margin-top:16px\">'",
     "'<div class=\"lg-ms-grid\">'",
     "with no trade in the range, 'No trades in this range.' runs into the ACCOUNT heading"),
    # LEDGER steps 7 + 10 (shared calendar and strategy list on the board)
    ('calendar-wrong-total',
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:qePnlOf,day:qeTradeDate});",
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:t=>+t.pnl||0,day:qeTradeDate});",
     "the calendar adds up the book's own pnl instead of the P&L of record, so a month's total is not the sum of its trades"),
    ('calendar-ignores-range',
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:qePnlOf,day:qeTradeDate});",
     "const qbCalDays=ledgerCalDays(trades,{pnl:qePnlOf,day:qeTradeDate});",
     'the calendar counts every trade whatever range is chosen'),
    ('shadow-in-calendar',
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:qePnlOf,day:qeTradeDate});",
     "const qbCalDays=ledgerCalDays(qbRangeTrades.concat(qbShadowRange),{pnl:qePnlOf,day:qeTradeDate});",
     "a shadow leg's trades are added into the calendar's days and month total"),
    ('caveat-not-hatched',
     "days:qbCalDays,caveats:qbCalCav,open:qbCalOpen,",
     "days:qbCalDays,caveats:{},open:qbCalOpen,",
     'the data-caveat days are no longer hatched amber with the dot on the calendar'),
    ('caveat-feed-days-lost',
     "if(fd&&fd.valid===false&&(!cut||d>=cut))why.push(",
     "if(false&&fd&&fd.valid===false&&(!cut||d>=cut))why.push(",
     'a day whose feed was flagged invalid is no longer hatched on the calendar'),
    ('day-tap-noop',
     "const t=el||document.getElementById('qe-trades-section');",
     "const t=null;",
     'a tap on a calendar day no longer scrolls the trade list'),
    ('cal-month-not-remembered',
     "try{localStorage.setItem('el_qb_cal_month',mo);}catch(e){}",
     "",
     'the month a viewer stepped to is forgotten on a reload'),
    ('cal-open-not-remembered',
     "try{localStorage.setItem('el_qb_cal_open',o?'0':'1');}catch(e){}",
     "",
     'the calendar fold opens again after a reload whatever the viewer chose'),
    ('cal-open-on-a-phone',
     "const qbCalOpen=(()=>{let o=window._qbCalOpen!=null?!!window._qbCalOpen:(window.innerWidth||1200)>=760;",
     "const qbCalOpen=(()=>{let o=window._qbCalOpen!=null?!!window._qbCalOpen:true;",
     'the calendar is open by default on a phone and pushes the rest of the page down'),
    ('cal-arrows-never-disabled',
     "const i=ms.indexOf(mo),atFirst=i<=0,atLast=i<0||i>=ms.length-1;",
     "const i=ms.indexOf(mo),atFirst=false,atLast=false;",
     'the calendar month arrows stay live past the first and last month with trades'),
    ('list-group-order',
     "[gBook,gRet,gShadow].filter(Boolean)",
     "[gRet,gBook,gShadow].filter(Boolean)",
     'the strategy list draws Retired above BOOK'),
    ('shadow-group-missing',
     "[gBook,gRet,gShadow].filter(Boolean)",
     "[gBook,gRet].filter(Boolean)",
     'the strategy list has no Shadow - not counted group'),
    ('shadow-in-list-total',
     "const fg=qbRangeFigs(qbRangeTrades.filter(t=>t.leg===key));",
     "const fg=qbRangeFigs(qbRangeTrades.concat(qbShadowRange).filter(t=>t.leg===key));",
     "a shadow leg's money is added into a BOOK row (and so into the list's total)"),
    ('row-without-run-number',
     "row:{key:key,name:label+' '+qeLegShortTag(key,runNo),",
     "row:{key:key,name:label,",
     'a strategy list row names its family but not its run number'),
    # LEDGER step 11 replaced step 10's phone order (the list and Account under the trade list, the status line after it): these three are its
    # opposites on the new page. The list is a one-line fold ABOVE the trade list, the own sections come after it, the status line is near the top
    # (step 12: directly under the hero). Re-anchored on step 12's frame call (the side html moves into the rest, the rest's two parts swap).
    ('list-below-trades-on-phone',
     _FR_TOP + _CRLF + _FR_HIST,
     _FR_TOP.replace('side:qbSideNew,', "side:'',") + _CRLF + _FR_HIST + '+qbSideNew',
     'the strategy list sits under the trade list (step 11 puts it above, on a phone a one-line fold)'),
    ('own-sections-above-trades-on-phone',
     _FR_HIST + _CRLF + _FR_OWN,
     "            rest:'<div class=\"qbx-own\">'+qbOwnSecs+'</div>'" + _CRLF
     + "              +'<div class=\"qbx-history qbx-section\"><div class=\"qb-section-hd\">History</div>'+qbTradesCard+'</div>'})",
     'on a phone the own sections (Orders, Account ...) sit above the trade list'),
    ('status-strip-below-stats',
     _QBTOP1 + _CRLF + _QBTOP2,
     _QBTOP1.replace('status:qbStatusSec,', "status:'',") + _CRLF + _QBTOP2.replace("+qbLgStatsHtml+'</div>',", "+qbLgStatsHtml+'</div>'+qbStatusSec,"),
     'the status line is drawn under the stats strip instead of directly under the hero'),
    ('status-line-gone',
     "const qbStatusSec='<div class=\"qbx-statusline\">'+qbStatusStripHtml+'</div>';",
     "const qbStatusSec='';",
     'the status line (feed, box age, Refresh) is not on the page at all'),
    ('key-long-on-phone',
     "@media(max-width:600px){.qbx-lg-key .qbx-lg-long{display:none}.qbx-lg-key .qbx-lg-short{display:inline}}",
     "@media(max-width:600px){.qbx-lg-key .qbx-lg-short{display:none}}",
     'the chart key is four lines on a phone and the trade list starts more than a screen down'),
    ('list-has-switch',
     "value:fg.n?ledgerSigned(fg.net):'&mdash;',cls:fg.n?ledgerCls(fg.net):'',value2:qbFigsLine(fg)},",
     "value:fg.n?ledgerSigned(fg.net):'&mdash;',cls:fg.n?ledgerCls(fg.net):'',value2:qbFigsLine(fg),sw:{on:true}},",
     'the strategy list draws a switch on each row (this board has none: every leg counts)'),
    ('shadow-open-by-default',
     "let qbShadowOpen=!!window._qbShadowOpen;",
     "let qbShadowOpen=true;",
     'the Shadow - not counted group opens by default'),
    ('folds-not-remembered',
     "try{localStorage.setItem(g[1],o?'0':'1');}catch(e){}",
     "",
     'the Retired and Shadow folds do not keep the open / closed choice'),
    ('row-tap-noop',
     "if(k.charAt(0)==='~')return;   // 'Other legs' and the shadow rows have no detail to open",
     "return;",
     "a tap on a strategy row no longer opens its detail"),
    ('list-total-ignores-range',
     "count:qbRangeTrades.length?(ledgerSigned(qbRangePnl)+' &middot; '+qbRangeWord):qbRangeNone",
     "count:qbRangeTrades.length?(ledgerSigned(closedSum)+' &middot; '+qbRangeWord):qbRangeNone",
     "the list's header total is the all-time figure whatever range is chosen"),
    # (list-not-sticky is gone: step 12's list panel is not sticky any more. Its opposite, list-panel-sticky, is with the step 12 mutants below)
    ('phone-row-two-lines',
     ".qbx-side .lg-row{grid-template-columns:minmax(0,1fr) auto}",
     ".qbx-side .lg-row{display:block}",
     'a strategy row is two lines tall on a phone (the money drops under the name)'),
    ('list-mono-hue',
     ".qbx-side .lg-list{margin-bottom:0}",
     ".qbx-side .lg-list{margin-bottom:0}\r\n[data-theme=mono] .qbx-side .lg-row-val{color:#e33}",
     'a strategy row draws its money in a colour under MONO (MONO has no hue)'),
    ('cal-mono-hue',
     ".qbx-side .lg-list{margin-bottom:0}",
     ".qbx-side .lg-list{margin-bottom:0}\r\n[data-theme=mono] .lg-cal-day .m{color:#e33!important}",
     'a calendar day draws its money in a colour under MONO (MONO has no hue)'),
    ('phone-calendar-overflow',
     ".qbx-side .lg-list{margin-bottom:0}",
     ".qbx-side .lg-list{margin-bottom:0}\r\n.lg-cal-panel{min-width:640px}",
     'the open calendar is wider than a phone and the page scrolls sideways'),
    # LEDGER steps 7 + 10, round 2: the note toggle and the strategy the board has no row for
    ('other-legs-row-missing',
     "if(oth.n)bookRows.push({key:'~other'",
     "if(false&&oth.n)bookRows.push({key:'~other'",
     "a strategy the board has no row for is left out of the list, which no longer adds up to the account's range figure"),
    ('info-toggle-opens-row',
     "ev.stopPropagation();\r\n        const k=el.getAttribute('data-qbleginfo');",
     "const k=el.getAttribute('data-qbleginfo');",
     "a tap on a row's note toggle also opens the row's detail"),
    ('info-toggle-noop',
     "const m=window._qbLegNoteOpen||(window._qbLegNoteOpen={});",
     "const m={};",
     "a tap on a row's note toggle shows no note"),
    ('day-tap-no-show-more',
     "if(!el&&(window._qeTradesShown||50)<1e6){window._qeTradesShown=1e6;renderApp();el=document.querySelector('[data-qbday=\"'+ds+'\"]');}",
     "",
     "a tap on a calendar day whose rows are not on the page yet (the list shows only its newest rows) lands on the top of the list"),
    ('enguq-stays-retired',
     "const qbRetiredNow=QE_LEGS_RETIRED.indexOf(key)>=0&&!p&&!qbHeldLive&&!legTodayN;",
     "const qbRetiredNow=QE_LEGS_RETIRED.indexOf(key)>=0&&!legTodayN;",
     "a retired leg that holds a position stays in the Retired fold instead of going back to BOOK"),
    ('retired-group-always-drawn',
     "const gRet=retModels.length?{key:'retired'",
     "const gRet=true?{key:'retired'",
     "an empty Retired group is drawn when no leg is retired"),
    # LEDGER step 8 (2026-10-06): the trade list on the shared frame
    ('frame-missing',
     '\'<div id="qe-trades-section"></div><div class="qbx-tl">\'+qbFrameHtml+qbMoreHtml+\'</div>\'',
     '\'<div id="qe-trades-section"></div><div class="qbx-tl">\'+qbMoreHtml+\'</div>\'',
     'the trade list frame is not drawn: no list, no toolbar, no day headers (the rest of the board still is)'),
    ('daynet-wrong',
     'const net2=list=>Math.round(list.reduce((s,t)=>s+(+N(t)||0),0)*100)/100;',
     'const net2=list=>Math.round(list.slice(1).reduce((s,t)=>s+(+N(t)||0),0)*100)/100;',
     "a day header's net leaves out the first trade of its day"),
    ('wins-includes-zero',
     "if(chip==='WINS')return p>0;",
     "if(chip==='WINS')return p>=0;",
     'the WINS chip keeps a $0 trade (a $0 trade is neither a win nor a loss)'),
    ('losses-includes-zero',
     "if(chip==='LOSSES')return p<0;",
     "if(chip==='LOSSES')return p<=0;",
     'the LOSSES chip keeps a $0 trade'),
    ('tl-csv-ignores-list',
     'window._qeTradesForExport=qbMatchedVm.map(v=>v._t);',
     'window._qeTradesForExport=trades;',
     'the CSV saves every closed trade whatever chip, search or range the list shows (the old behaviour)'),
    ('csv-count-mismatch',
     'window._qeTradesForExport=qbMatchedVm.map(v=>v._t);',
     'window._qeTradesForExport=qbMatchedVm.slice(1).map(v=>v._t);',
     'the CSV holds one trade fewer than the list shows'),
    ('tl-csv-has-shadow-row',
     'window._qeTradesForExport=qbMatchedVm.map(v=>v._t);',
     'window._qeTradesForExport=qbMatchedVm.map(v=>v._t).concat(qbShadowRange);',
     'the CSV carries a shadow row the list leaves out'),
    ('tl-sheet-by-row-number',
     "onRow:rk=>{window._qbPanelKey=rk;_qbSyncPanel();}});",
     "onRow:rk=>{window._qbPanelKey=((window._qeCandleRows||[])[0]||{})._no;_qbSyncPanel();}});",
     'a tap on a row opens the trade panel for the first trade on the page, not the one tapped'),
    ('sheet-wrong-trade-after-rerender',
     "const t=qbRangeTrades.find(q=>window._qeRowKey(q)===key);",
     "const _pp=(window._qbPanelPos==null?(window._qbPanelPos=[].map.call(document.querySelectorAll('[data-lgtrade]'),e=>e.getAttribute('data-lgtrade')).indexOf(key)):window._qbPanelPos),t=(qbShownVm[_pp]||{})._t;",
     "the panel remembers a row position instead of the trade (wrong as soon as a chip or a search changed the rows)"),
    ('tl-row-tap-noop',
     "onRow:rk=>{window._qbPanelKey=rk;_qbSyncPanel();}});",
     'onRow:rk=>{}});',
     'a tap on a row opens no trade panel'),
    ('shadow-in-list',
     'const qbAllVm=qbRangeTrades.map(qbVm);',
     'const qbAllVm=qbRangeTrades.concat(qbShadowRange).map(qbVm);',
     'a shadow row is drawn in the trade list and counted in it'),
    ('phone-list-too-low',
     '.qbx-lg6 .qbx-history.qbx-section{padding-top:0;border-top:0}',
     '.qbx-lg6 .qbx-history.qbx-section{padding-top:14px;border-top:0}',
     'on a phone the trade list starts 14 px lower than the 784 px it started at'),
    ('tl-phone-heading-back',
     '.qbx-lg6 .qbx-history>.qb-section-hd{display:none}',
     '.qbx-lg6 .qbx-history>.qb-section-hd{display:block}',
     'on a phone the History heading is back above the list, which starts 25 px lower'),
    ('tl-phone-six-cells',
     '.qbx-tl .lg-tl-row .lg-c-chart{min-width:30px}',
     '.qbx-tl .lg-tl-row .lg-c-chart{min-width:30px}\r\n@media(max-width:600px){.qbx-tl .lg-tl-row .lg-c-size{display:block}}',
     'a phone row draws six cells (the shares too), not the five of the shared list'),
    ('tl-phone-table-six-cells',
     '.qbx-tl .lg-tl-row .lg-c-chart{min-width:30px}',
     '.qbx-tl .lg-tl-row .lg-c-chart{min-width:30px}\r\n@media(max-width:600px){.qbx-tl .lg-tl-table .lg-c-size{display:table-cell}}',
     'a phone table row draws six cells, not the five of the shared list'),
    ('tl-own-chips-missing',
     'chips:qbOwnChips,',
     'chips:[],',
     'the strategy chips and BOOK ONLY are not on the list'),
    ('tl-leg-chip-no-filter',
     "if(qbChipSel!=='ALL'&&qbOwnChips.some(c=>c.k===qbChipSel))return v._t.leg===qbChipSel;",
     "if(qbChipSel!=='ALL'&&qbOwnChips.some(c=>c.k===qbChipSel))return true;",
     'a strategy chip (ORB, ENGU-Q, NOISE) leaves every trade in the list'),
    ('tl-bookonly-chip-no-filter',
     "if(qbChipSel==='BOOKONLY')return !!v._t.book_only;",
     "if(qbChipSel==='BOOKONLY')return true;",
     'the BOOK ONLY chip leaves every trade in the list'),
    ('tl-view-not-remembered',
     "window._qeTradesView=ledgerTradeViewGet('wb','list');",
     "window._qeTradesView='list';",
     'a page that comes back opens the LIST whatever view the viewer chose'),
    ('tl-show-more-noop',
     'smore.onclick=()=>{window._qeTradesShown=(window._qeTradesShown||50)+50;renderApp();};',
     'smore.onclick=()=>{window._qeTradesShown=(window._qeTradesShown||50);renderApp();};',
     'SHOW MORE shows no more rows'),
    ('tl-page-cuts-a-day',
     'while(qbCut<qbMatchedVm.length&&ledgerCloseDay(qbMatchedVm[qbCut])===ledgerCloseDay(qbMatchedVm[qbCut-1]))qbCut++;',
     '',
     "SHOW MORE can cut a day in two (the day's header then covers only some of its trades)"),
    ('tl-search-ignored',
     'if(!ledgerTradeMatch(v,qbChipSel,qbQuery,{pnl:x=>x.pnl,hay:qbHay}))return false;',
     "if(!ledgerTradeMatch(v,qbChipSel,'',{pnl:x=>x.pnl,hay:qbHay}))return false;",
     'typing in the search box filters nothing'),
    ('tl-search-loses-focus',
     'try{sbx.focus({preventScroll:true});sbx.setSelectionRange(qbHold.s,qbHold.e);}catch(e){}',
     'try{sbx.setSelectionRange(qbHold.s,qbHold.e);}catch(e){}',
     'the search box loses its focus on every redraw, so the first letter typed ends the typing'),
    ('tl-keyboard-done-refocuses',
     'if(sbx&&(window._qbSearchFocused||(qbBlur&&qbBlur.inRedraw))){',
     'if(sbx){',
     "the search box takes its focus back at the next redraw after the viewer left it (the phone keyboard's Done), so the keyboard comes back"),
    ('tl-own-columns-missing',
     'cols:qbCols,',
     'cols:[],',
     "the table has none of this board's own columns (exit time, prices, running total, real P&L, slip)"),
    ('csv-column-dropped',
     "'fill_gap_usd','design_gap_usd','execution_gap_usd'];",
     "'fill_gap_usd','design_gap_usd'];",
     'the CSV loses its last column'),
    ('tl-day-attr-missing',
     'rowAttr:v=>\'data-qbday="\'+qbEsc(qeTradeDate(v._t)||\'\')+\'"\',',
     "rowAttr:v=>'',",
     'the frame rows carry no day, so a calendar tap cannot land on that day'),
    ('tl-table-day-attr-missing',
     'rowAttr:v=>\'data-qbday="\'+qbEsc(qeTradeDate(v._t)||\'\')+\'"\',',
     'rowAttr:v=>(qbTradesView===\'table\'?\'\':\'data-qbday="\'+qbEsc(qeTradeDate(v._t)||\'\')+\'"\'),',
     'the Table rows carry no day, so a calendar tap cannot land on them'),
    ('tl-groups-by-entry-day',
     "exitTime:ex.slice(11,19),exitDate:qeTradeDate(t)||'',",
     "exitTime:ex.slice(11,19),exitDate:'',",
     'a trade held over a weekend sits under the day it entered, not the day it closed'),
    ('tl-bare-leg-on-rows',
     "return '<span style=\"color:'+legColorQE(v._t.leg)+'\">'+qeTradeLegHtml(v._t)+'</span>'",
     "return '<span style=\"color:'+legColorQE(v._t.leg)+'\"><span class=\"qb-trade-leg\">'+naS(v._t.leg)+'</span></span>'",
     "a frame row names the box's bare leg key (ENGUQ) with no run number"),
    ('tl-caveat-mark-hidden',
     '@container qbtl (max-width:800px){.qbx-tl .qbx-cav{display:block}}',
     '@container qbtl (max-width:800px){.qbx-tl .qbx-cav{display:none}}',
     'a flagged trade carries no mark on a phone (the flags column is not one of the five cells)'),
    ('tl-caveat-mark-lost',
     "+(cw?'<span class=\"qbx-cav\" data-qbcav=\"'+cw+'\" title=\"'+qbEsc(qbFlagsText(v._t))+'\">'+cw+'</span>':'');},",
     "+'';},",
     'no row carries its caveat word (a phone row cannot say which caveat a trade has)'),
    ('tl-caveat-bang-only',
     "title=\"'+qbEsc(qbFlagsText(v._t))+'\">'+cw+'</span>':'');},",
     "title=\"'+qbEsc(qbFlagsText(v._t))+'\">!</span>':'');},",
     "a flagged row shows only a '!' whose words are in a tooltip a phone cannot show (review L1)"),
    ('tl-caveat-word-order',
     "const QB_CAV_ORDER=['BOOK ONLY','CHECK FILL','FILL GAP','BOOK PRICE','PART BOOK PRICE','NOT COMPARED'];",
     "const QB_CAV_ORDER=['NOT COMPARED','BOOK ONLY','CHECK FILL','FILL GAP','BOOK PRICE','PART BOOK PRICE'];",
     'a book-only row says NOT COMPARED instead of BOOK ONLY'),
    ('tl-caveat-in-time-cell',
     "return qbEsc(a?((ed&&cd&&ed!==cd?ed.slice(5)+' ':'')+a):'--')+(b?'<small>&rarr; '+qbEsc(b)+'</small>':'');",
     "return qbEsc(a?((ed&&cd&&ed!==cd?ed.slice(5)+' ':'')+a):'--')+(b?'<small>&rarr; '+qbEsc(b)+'</small>':'')+(qbCavWord(t)?'<span class=\"qbx-cav\" data-qbcav=\"'+qbCavWord(t)+'\">'+qbCavWord(t)+'</span>':'');",
     'the caveat word sits in the 44 px time cell too (two words on a row)'),
    # ---- post-landing keeps (review 2026-10-07 section 4, fixes M1 / L2-L6) ----
    ('csv-name-no-scope',
     "_libDownload('qqq_shadow_book_closed_trades'+(window._qeExportScope?('_'+window._qeExportScope):'')+'.csv',csv);",
     "_libDownload('qqq_shadow_book_closed_trades.csv',csv);",
     'a 1W or LONG export is saved under the whole book\'s file name (review L5)'),
    ('csv-scope-misses-range',
     "const qbExportScope=[qbRange!=='ALL'?qbRange:'',",
     "const qbExportScope=['',",
     'the CSV file name leaves out the range'),
    ('broker-line-from-box',
     'const qbHero=qbHeroBuild(sinceStartPnl,qbSinceLabel,parFailed,qbBrokerInfo,heroTodayVal,',
     'const qbHero=qbHeroBuild(sinceStartPnl,qbSinceLabel,parFailed,(QE.book_only_summary||null),heroTodayVal,',
     "the hero's broker line is the box's figure, not the page's own sum (review L3)"),
    ('broker-line-counts-book-only',
     'trades.forEach(t=>{if(t.book_only)n++;else net+=qePnlOf(t);});',
     'trades.forEach(t=>{if(t.book_only)n++;net+=qePnlOf(t);});',
     "the hero's broker line counts the book-only trades"),
    ('host-green-on-silent-box',
     "+' · one-computer check '+(QF.stale",
     "+' · one-computer check '+(false",
     "the one-computer check stays a green OK on a silent box (review L2)"),
    ('hero-no-breaker-chip',
     "if(QE&&QE.breaker_tripped)chips.push(qbChipG('BREAKER TRIPPED','var(--attn-red)'));",
     '',
     'the hero has no BREAKER TRIPPED chip'),
    ('hero-no-kill-chip',
     "if(QE&&QE.kill)chips.push(qbChipG('KILL ACTIVE','var(--attn-red)'));",
     '',
     'the hero has no KILL ACTIVE chip'),
    ('hero-alarm-chips-colour-when-silent',
     "if(QE&&QE.kill)chips.push(qbChipG('KILL ACTIVE','var(--attn-red)'));",
     "if(QE&&QE.kill)chips.push(qbChip('KILL ACTIVE','var(--attn-red)'));",
     'KILL ACTIVE stays red on a silent box'),
    ('leg-today-not-legs-record',
     '          ?QE.today.legs_record' + _CRLF,
     '          ?{}' + _CRLF,
     "a strategy row's TODAY ignores the box's legs_record"),
    ('leg-today-fallback-book-pnl',
     "b.pnl+=qePnlOf(t);b.n++;",
     "b.pnl+=(Number(t.pnl)||0);b.n++;",
     "on an older box a strategy row's TODAY sums the book price, not the P&L of record"),
    ('stop-always-breaker-figure',
     "const dllStopShort=qeStopIn!==null?'breaker figure':'estimate, box not updated yet';",
     "const dllStopShort='breaker figure';",
     "the daily stop calls an estimate the breaker's own figure"),
    ('stop-ignores-breaker-figure',
     'const stopPnl=qeStopIn!==null?qeStopIn:todayPnl;',
     'const stopPnl=todayPnl;',
     "the daily stop ignores the breaker's own figure"),
    ('orders-paper-sentence',
     "sentence='Sending orders to the Webull paper (practice) account.';",
     "sentence='Paper.';",
     "the Orders card no longer says orders go to the Webull paper account"),
    ('orders-halt-reason-raw',
     "if(/reconcile mismatch/i.test(s))return 'positions at Webull don'+\"'\"+'t match the notebook';",
     '',
     "a reconcile halt shows the box's raw reason, not plain words"),
    ('panel-no-fill-usd',
     "usdRow('FILL GAP $',gU),usdRow('DESIGN GAP $',dU),usdRow('SLIPPAGE + UNEXPLAINED $',xU),",
     '',
     'the trade panel lost the fill gap dollar split (review M1)'),
    ('panel-design-usd-is-gap',
     "dU=usd('dsg_usd')",
     "dU=usd('gap_usd')",
     "the panel's DESIGN GAP $ shows the whole gap"),
    ('panel-no-record-vs-backtest',
     'const rvb=bt!==null?Math.round((pnl-bt)*100)/100:null;',
     'const rvb=null;',
     'the trade panel lost the record vs backtest line'),
    ('panel-backtest-why-lost',
     "bt!==null?ledgerSigned(bt):('— &middot; '+qbEsc(btWhy))",
     "bt!==null?ledgerSigned(bt):'—'",
     'a missing backtest P&L no longer says why'),
    ('panel-backtest-why-code',
     "return c?qeWhyTxt(c):'not on record';",
     "return c?c:'not on record';",
     "a missing backtest P&L gives the box's code word (noexit), not its plain words"),
    ('panel-fills-fixed-sentence',
     "+(fp.flag?' - '+qbFpCause(fp):'')+'</div>'):'')",
     "+(fp.flag?' - Webull\\u2019s fills came out more than 15 cents a share worse than the backtest once the known design gap is taken out':'')+'</div>'):'')",
     "every flagged trade's FILLS vs BACKTEST line says '15 cents worse', also on a CHECK FILL trade whose fills came out better"),
    ('panel-fills-cause-tape-lost',
     "if(odd.length)return odd.every(s=>s.why==='diverged')?",
     "if(false)return odd.every(s=>s.why==='diverged')?",
     "a trade flagged for a fill that does not fit the tape is explained as 'the box flagged this trade'"),
    ('panel-backtest-why-nested-parens',
     "bt!==null?ledgerSigned(bt):('— &middot; '+qbEsc(btWhy))",
     "bt!==null?ledgerSigned(bt):('— ('+qbEsc(btWhy)+')')",
     "the reason beside a missing BACKTEST P&L is wrapped in parentheses again (and nests the box's own)"),
    ('panel-no-flagged-word',
     "+(fp.flag?' &middot; FLAGGED':'')+'</span>'",
     "+'</span>'",
     'the panel no longer says FLAGGED on a flagged trade'),
    ('panel-candles-netted-as-fill',
     "if(k==='netted')put('wb_netted'",
     "if(k==='netted')put('wb_out'",
     'a netted exit try is drawn as a Webull fill, not its own diamond'),
    ('key-book-only-old-wording',
     "hasBookOnly?'book only = order never reached Webull':''",
     "hasBookOnly?'book only = a side priced from the book because no Webull fill was captured':''",
     'the chart key mixes BOOK ONLY up with BOOK PRICE again (review L6)'),
    ('rails-no-paper-api',
     'Whether orders also go to the Webull paper (practice) account is the Orders mode under System;',
     'WEBULL PAPER is not used — Webull has no paper API, so nothing is ever sent there;',
     'the Rails fold says Webull has no paper API again (review L4)'),
    ('tl-calendar-tap-keeps-chip',
     'if(!el&&(window._qeTradesQuery||(window._qeTradesChip&&window._qeTradesChip!==\'ALL\'))){window._qeTradesQuery=\'\';window._qeTradesChip=\'ALL\';window._qeTradesShown=1e6;renderApp();el=document.querySelector(\'[data-qbday="\'+ds+\'"]\');}',
     '',
     'a calendar tap on a day the chip or the search hides lands nowhere'),
    ('tl-glyph-not-wired',
     "content.querySelectorAll('[data-qbchartkey]').forEach(b=>{",
     "content.querySelectorAll('[data-qbchartkeyx]').forEach(b=>{",
     'the chart glyph on a row does nothing'),
    ('tl-count-total-wrong',
     'total:closedN,',
     'total:matchedN,',
     'the count reads shown / matched instead of shown / all trades'),
    ('tl-list-wider-than-window-601-800',
     '.qbx-tl .lg-tl-row .lg-c{flex-shrink:1}',
     '.qbx-tl .lg-tl-row .lg-c{flex-shrink:1}\r\n@media(min-width:601px) and (max-width:800px){.qbx-tl .lg-tl-row{min-width:900px}}',
     'between 601 and 800 px the list rows are wider than the window and the page scrolls sideways'),
    ('tl-table-wider-than-window',
     '.qbx-tl .lg-tl-row .lg-c{flex-shrink:1}',
     '.qbx-tl .lg-tl-row .lg-c{flex-shrink:1}\r\n.qbx-tl .lg-tl-wrap{overflow:visible;max-height:none}',
     'the table is not held in its own scrolling box and the page scrolls sideways'),
    ('tl-mono-hue',
     '.qbx-tl .lg-tl-row .lg-c{flex-shrink:1}',
     '.qbx-tl .lg-tl-row .lg-c{flex-shrink:1}\r\n[data-theme=mono] .qbx-tl .lg-tl-daynet{color:#e33!important}',
     'a day net is drawn in colour under MONO (MONO has no hue)'),
    ('tl-flags-lost',
     "strat:(v,mode)=>mode==='table'?(qbEsc(naS(v._t.exit_reason))+qbFlagsHtml(v._t)):(qbFlagsHtml(v._t).trim()+' '+qbEsc(naS(v._t.exit_reason))),",
     'strat:(v,mode)=>qbEsc(naS(v._t.exit_reason)),',
     'the BOOK ONLY / FILL GAP / EOD chips are gone from the rows'),
    ('tl-running-wrong',
     'tcol(\'run\',\'RUNNING\',v=>\'<span style="color:var(--text3)">\'+qeMoney(qbRun[v.id])+\'</span>\')',
     'tcol(\'run\',\'RUNNING\',v=>\'<span style="color:var(--text3)">\'+qeMoney(v.pnl)+\'</span>\')',
     "the RUNNING column shows each trade's own P&L, not the running total"),
    ('tl-list-oldest-first',
     'const qbMatchedVm=ledgerByClose(qbAllVm.filter(qbMatch)).reverse();',
     'const qbMatchedVm=ledgerByClose(qbAllVm.filter(qbMatch));',
     'the page and the CSV take the OLDEST trades first'),
    # LEDGER step 9 (2026-10-06): the trade panel
    ('wb-panel-missing',
     "const spec=typeof window._qbPanelSpec==='function'?window._qbPanelSpec(String(key)):null;",
     'const spec=null;',
     'the board builds nothing for the panel: a tap on a row draws no trade panel'),
    ('wb-panel-takes-room-closed',
     "onClose:()=>{if(String(window._qbPanelKey)===key)window._qbPanelKey=null;}};",
     "onClose:()=>{if(String(window._qbPanelKey)===key)window._qbPanelKey=null;document.getElementById('app').style.paddingBottom='140px';}};",
     'a closed panel leaves 140 px of room under the board (the page is 140 px taller)'),
    ('wb-closed-panel-node-left',
     "onClose:()=>{if(String(window._qbPanelKey)===key)window._qbPanelKey=null;}};",
     "onClose:()=>{if(String(window._qbPanelKey)===key)window._qbPanelKey=null;document.body.insertAdjacentHTML('beforeend','<div class=\"lg-panel-layer\" style=\"display:none\"></div>');}};",
     'a closed panel leaves an empty layer node in <body>'),
    ('wb-esc-dead',
     'function _qbSyncPanel(){',
     "function _qbSyncPanel(){if(!window._qbEscKill){window._qbEscKill=1;document.addEventListener('keydown',function(e){if(e.key==='Escape'&&ledgerTradePanelOf('wb')!=null)e.stopImmediatePropagation();},true);}",
     'Escape no longer closes the trade panel'),
    ('wb-outside-click-dead',
     'function _qbSyncPanel(){',
     "function _qbSyncPanel(){if(!window._qbOutKill){window._qbOutKill=1;document.addEventListener('click',function(e){if(e.target&&e.target.classList&&e.target.classList.contains('lg-panel-layer'))e.stopImmediatePropagation();},true);}",
     'a tap on the dimmed page outside the panel no longer closes it'),
    ('wb-glyph-opens-panel',
     'const openCandles=ev=>{ev.stopPropagation();',
     "const openCandles=ev=>{window._qbPanelKey=b.getAttribute('data-qbchartkey');_qbSyncPanel();ev.stopPropagation();",
     'the chart glyph of a row opens the trade panel as well as the candles'),
    ('wb-wrong-trade-after-redraw',
     '  const key=window._qbPanelKey;',
     "  const key=ledgerTradePanelOf('wb')!=null?((window._qeCandleRows||[])[0]||{})._no:window._qbPanelKey;",
     'the first redraw after a tap puts the open panel on the first trade of the page, not the one that was tapped'),
    ('wb-panel-lost-on-showmore',
     'const t=qbRangeTrades.find(q=>window._qeRowKey(q)===key);',
     'const t=qbShownVm.map(v=>v._t).find(q=>window._qeRowKey(q)===key);',
     'the panel finds its trade among the rows on the page only, so a short page (SHOW MORE) or a search closes it'),
    ('wb-bookonly-chip-missing',
     'const chips=qbFlagPairs(t).map(',
     "const chips=qbFlagPairs(t).filter(p=>p[0]!=='BOOK ONLY').map(",
     "a book-only trade's panel header leaves out the BOOK ONLY chip"),
    ('wb-mono-hue-in-panel',
     '.lg-panel .qb-sheet-candles{margin:0!important}',
     '.lg-panel .qb-sheet-candles{margin:0!important}\r\n[data-theme="mono"] .lg-panel .qbx-pn-chip{border-color:#e33;color:#e33}',
     'a caveat chip in the panel is drawn in colour under MONO (MONO has no hue)'),
    ('wb-panel-chart-missing',
     "{k:'chart',html:row._et?window._qbSheetCandlesHtml(row):'',",
     "{k:'chart',html:'',",
     'the panel has no chart slot: the candles are not drawn in it'),
    ('wb-expand-dead',
     "el.querySelectorAll('[data-qbcandlesexpand]').forEach(b=>{b.onclick=ev=>{ev.stopPropagation();qbOpenCandles(row,b);};});}},",
     "el.querySelectorAll('[data-qbcandlesexpand]').forEach(b=>{});}},",
     "EXPAND in the panel's chart does nothing"),
    ('wb-expand-wrong-trade',
     'window._openTradeCandles(x,btn,{B:{},all:()=>all,order:()=>all});',
     'window._openTradeCandles(rows[rows.length-1]||x,btn,{B:{},all:()=>rows,order:()=>rows});',
     'EXPAND and OPEN CANDLES open the candle viewer on another trade than the one in the panel'),
    ('wb-hold-wrong-unit',
     'durStr({durationSecs:secs})',
     'durStr({durationMins:secs})',
     'the hold time reads whole seconds as minutes (20m 1s shows as 20h 1m)'),
    ('wb-net-unsigned',
     "sub:qbEsc(shares)+' sh'+(chips?(' '+chips):''),net:qePnlOf(t)},",
     "sub:qbEsc(shares)+' sh'+(chips?(' '+chips):''),net:Math.abs(qePnlOf(t))},",
     "the panel header shows every trade's net as a gain"),
    ('wb-notes-editable',
     "return '<div class=\"qbx-pn-hint\" data-qbpnotes>WEBULL PAPER keeps no notes.",
     "return '<textarea rows=\"2\"></textarea><div class=\"qbx-pn-hint\" data-qbpnotes>WEBULL PAPER keeps no notes.",
     'the notes slot holds a box that can be typed in, though the board keeps no notes'),
    ('wb-actions-destructive',
     "OPEN CANDLES &#8599;</button>':'')",
     "OPEN CANDLES &#8599;</button><button type=\"button\" class=\"del\">DELETE</button>':'')",
     'the actions slot has a DELETE button'),
    ('wb-nt-rows-always',
     'if(t.nt_points!=null||t.expected_usd!=null||t.track_err_usd!=null)rows.push(',
     'if(true)rows.push(',
     'the NT POINTS / EXPECTED $ / TRACK ERR rows show on every trade, not only a trade that carries NinjaTrader figures'),
    ('wb-nt-rows-missing',
     'if(t.nt_points!=null||t.expected_usd!=null||t.track_err_usd!=null)rows.push(',
     'if(false)rows.push(',
     "a trade with NinjaTrader figures shows none in the panel"),
    ('wb-running-wrong',
     "['RUNNING',qeMoney(qbRun[key])],",
     "['RUNNING',qeMoney(pnl)],",
     "the panel's RUNNING row shows the trade's own P&L, not the running total"),
    ('wb-slip-precision',
     "['SLIP/SH',sp!=null?qeNum(sp,3):'\u2014'],",
     "['SLIP/SH',sp!=null?qeNum(sp,2):'\u2014'],",
     'the slip a share is rounded to cents in the panel (the table shows it to a tenth of a cent)'),
    ('wb-fill-coverage-wrong',
     "(src==='webull'?'Webull both sides':",
     "(src==='webull'?'none (book prices)':",
     'a trade priced from Webull fills on both sides reads as having no fill'),
    ('wb-leave-keeps-panel',
     "try{if(!(activeTab==='augur'&&augurSub==='qqqpaper'))ledgerTradePanelClose('wb','leave');}catch(e){}",
     '',
     'the panel stays on the page after the viewer leaves the board'),
    ('wb-gone-keeps-panel',
     "if(!spec){window._qbPanelKey=null;ledgerTradePanelClose('wb','gone');return;}",
     'if(!spec)return;',
     'the panel stays open after its trade left the board rows'),
    ('wb-panel-flickers',
     'return ledgerTradePanelRows(rows)',
     "return '<!--'+Math.random()+'-->'+ledgerTradePanelRows(rows)",
     'the numbers slot is rewritten on every redraw of the board, so the panel flickers'),
    ('wb-flags-not-in-words',
     "ln('FLAGS',fl.length?fl.map(p=>'<b>'+p[0]+'</b>: '+(QB_FLAG_WORDS[p[0]]||'')+(p[1]&&p[1]!==pnT?' ('+p[1]+')':'')).join('<br>'):'none');",
     "ln('FLAGS','none');",
     'the notes slot does not spell the flags out in words'),
    ('wb-keel-note-lost',
     "if(t.size!=null&&String(t.size)!==''&&Number(t.size)!==1)ln('SIZE (KEEL)',",
     "if(false)ln('SIZE (KEEL)',",
     'the KEEL size note is left out of the panel'),
    # ── LEDGER step 11: the fixed page order, the own folds, one set of breakpoints ──
    ('section-order-wrong',
     _QBTOP2,
     "          stats:'<div class=\"qbx-activity\">'+qbCalHtml+'</div>',more:'',cal:'<div class=\"qbx-stats qbx-lgstats\">'+qbLgStatsHtml+'</div>'};",
     'the calendar fold is drawn above the stats strip (the fixed page order is broken)'),
    # step 12: the laptop order is the shared frame's grid (the top block in row 1, the trade list and the own folds in row 2)
    ('laptop-grid-order-wrong',
     '.lg-frame-2>.lg-frame-top{grid-column:1;grid-row:1}',
     '.lg-frame-2>.lg-frame-top{grid-column:1;grid-row:3}',
     'on a laptop the top block (hero to the calendar) sits under the trade list'),
    ('pills-below-chart',
     _EQA + _CRLF + _EQB,
     "            equityHtml='<div class=\"qb-chart-wrap\">'" + _CRLF + _EQB + '+periodTabsHtml',
     'the range pills are drawn under the chart (they go between the hero and the chart)'),
    ('own-folds-order-wrong',
     "const qbOwnSecs=qbFoldHtml('orders','Orders',qbMiniSum,'<div class=\"qbx-orders-mini\">'+qbOrdersCompactHtml+'</div>',true)" + _CRLF
     + "          +qbFoldHtml('account','Account',qbAcctSum,qbAccountHtml,true)",
     "const qbOwnSecs=qbFoldHtml('account','Account',qbAcctSum,qbAccountHtml,true)" + _CRLF
     + "          +qbFoldHtml('orders','Orders',qbMiniSum,'<div class=\"qbx-orders-mini\">'+qbOrdersCompactHtml+'</div>',true)",
     'the own folds run Account, Orders instead of Orders, Account'),
    ('fold-summary-empty',
     "+(sum||'&nbsp;')+",
     "+''+",
     'a fold header has no summary line'),
    ('fold-summary-undefined',
     "return parts.join(' &middot; ');",
     "return parts.join(' &middot; ')+' '+undefined;",
     "the Account fold's summary ends in the word undefined"),
    ('fold-does-not-open',
     "(window._qbFolds||(window._qbFolds={}))[k]=o;",
     "return;",
     'a tap on a fold header does nothing'),
    ('fold-not-remembered',
     "try{localStorage.setItem('el_qb_fold_'+k,o?'1':'0');}catch(e){}",
     "",
     'an open fold is not stored: a reload finds it shut'),
    ('fold-open-state-never-read',
     "try{const sv=localStorage.getItem('el_qb_fold_'+k);if(sv!=null)o=sv==='1';}catch(e){}",
     "",
     'the stored open state is never read back: a reload finds every fold shut'),
    ('fold-storage-unguarded',
     "try{const sv=localStorage.getItem('el_qb_fold_'+k);if(sv!=null)o=sv==='1';}catch(e){}",
     "{const sv=localStorage.getItem('el_qb_fold_'+k);if(sv!=null)o=sv==='1';}",
     'reading the fold state is not inside try / catch: a browser that blocks storage breaks the board'),
    ('fold-click-unguarded',
     "try{localStorage.setItem('el_qb_fold_'+k,o?'1':'0');}catch(e){}",
     "localStorage.setItem('el_qb_fold_'+k,o?'1':'0');",
     'storing the fold state is not inside try / catch: a browser that blocks storage cannot open a fold'),
    ('fold-open-by-default',
     "'<div class=\"lg-more-panel qbx-fold-panel\" id=\"qbf-'+k+'\"'+(o?'':' hidden')",
     "'<div class=\"lg-more-panel qbx-fold-panel\" id=\"qbf-'+k+'\"'+(true?'':' hidden')",
     'every fold shows its panel though its header says it is shut'),
    ('fold-content-lost',
     "((o||keep)?body:'')",
     "(keep?body:'')",
     'a fold opens onto an empty panel (System, Rails, Events, Feed, Model)'),
    ('own-section-removed',
     "          +qbFoldHtml('account','Account',qbAcctSum,qbAccountHtml,true)" + _CRLF,
     "",
     'the Account section is gone from the page (own sections are folded, never removed)'),
    ('stop-state-not-in-header',
     "(dllTripped?' &middot; stopped for the day':(dllNearLimit?' &middot; near the limit':''))+(QF.isToday?'':(' &middot; from '+QF.dayLabel)))",
     "''+(QF.isToday?'':(' &middot; from '+QF.dayLabel)))",
     'the Orders fold header never says the daily stop is near its limit or reached'),
    ('breaker-line-removed',
     "const qbOwnSecs=qbFoldHtml('orders','Orders',qbMiniSum,'<div class=\"qbx-orders-mini\">'+qbOrdersCompactHtml+'</div>',true)",
     "const qbOwnSecs=''",
     'the PAPER breaker line (mode and daily stop) is gone from the page'),
    ('todays-orders-removed',
     "          +(ordersHtml?qbFoldHtml('todayorders',QF.isToday?'Today&rsquo;s orders':('Orders on '+QF.dayLabel),qbOrdTodaySum,ordersHtml,true):'')" + _CRLF,
     "",
     "Today's orders are gone from the page"),
    ('rails-removed',
     "          +qbFoldHtml('rails','Rails',qbRailsSum,railsHtml)" + _CRLF,
     "",
     'the Rails fold is gone from the page'),
    ('fold-header-wraps',
     ".qbx-fold-sum{flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
     ".qbx-fold-sum{flex:0 1 auto;min-width:0;overflow:visible;white-space:normal;",
     'a fold header wraps to two lines on a phone (the summary is not one line)'),
    ('breaker-summary-wrong',
     "qeMoney(usedS)+' of '",
     "qeMoney(0)+' of '",
     "the Orders fold says $0.00 of the daily stop is used whatever the breaker's figure is"),
    ('account-summary-no-change',
     "if(chg!==null)parts.push('<span class=\"'+ledgerCls(chg)+'\">'",
     "if(false)parts.push('<span class=\"'+ledgerCls(chg)+'\">'",
     "the Account fold says the equity but not its change"),
    ('list-fold-on-laptop',
     ".qbx-lg6 .qbx-list-fold{display:none}",
     ".qbx-lg6 .qbx-list-fold{display:flex}",
     'the strategy list shows its fold header above 600 px, where the list is drawn open'),
    ('list-fold-open-on-phone',
     "const qbListOpen=qbFoldOpen('list');",
     "const qbListOpen=true;",
     'the strategy list starts open on a phone and pushes the trade list down'),
    ('phone-list-fold-gap',
     ".lg-more.qbx-fold-btn{padding:7px 4px}",
     ".lg-more.qbx-fold-btn{padding:7px 4px;margin-bottom:24px}",
     'the one-line fold headers carry a 24 px gap again, so on a phone the trade list starts lower than it did before step 11'),
    ('private-breakpoint',
     ".qbx-fold-t{flex:0 0 auto;white-space:nowrap}",
     ".qbx-fold-t{flex:0 0 auto;white-space:nowrap}" + _CRLF + "@media(max-width:760px){.qbx-fold-sum{letter-spacing:.3px}}",
     'a board-private breakpoint (760 px) is back'),
    ('cav-mark-private-width',
     "@container qbtl (max-width:800px){.qbx-tl .qbx-cav{display:block}}",
     "@container qbtl (max-width:1000px){.qbx-tl .qbx-cav{display:block}}",
     'the flagged-row mark uses a width (1000 px) that is no house breakpoint'),
    ('status-strip-folded',
     "const qbStatusSec='<div class=\"qbx-statusline\">'+qbStatusStripHtml+'</div>';",
     "const qbStatusSec=qbFoldHtml('status','Status','paper only',qbStatusStripHtml);",
     'the status strip is folded away under a header instead of staying visible under the chart'),
    # the clean-up of v73.1125: ?oldboards=1 and the previous board are gone, and nothing of them may come back
    ('oldflag-changes-the-board',
     _FR_BODY,
     "body=ledgerFrameHtml({id:'qb',cls:'qb-shell'+(location.search.indexOf('old'+'boards=1')>=0?'':' qbx-lg6'),",
     '?oldboards=1 changes the board again: the page behind the flag is not the plain page'),
    ('old-marker-back-in-page',
     _FR_BODY,
     _FR_BODY + "handle:'<span data-qb'+'traderow=\"0\"></span>',",
     'a piece of the removed previous trade rows ([data-qbtraderow]) is back in the page'),
    # step 12: the chart caption takes the shared foot style now, so the rule the old comment guarded (.qbx-chart-cap) no longer shows; the same slip
    # in the shared frame's comment swallows the rule right after it, .lg-frame (the frame's max width and centring)
    ('css-comment-closes-early',
     '(.lg-filters, closed until opened). Tokens only. */',
     '(.lg-filters, closed until opened)*/. Tokens only. */',
     "a css comment closes early (a star-slash inside it), so the rule after it is swallowed and the page frame loses its 1320 px width and centring"),
    ('removed-flag-defined-again',
     "const LEDGER_RANGES=['TODAY','1W','1M','3M','YTD','ALL'];",
     "const LEDGER_RANGES=['TODAY','1W','1M','3M','YTD','ALL'];\nconst LEDGER_OLDBOARDS=false;",
     'LEDGER_OLDBOARDS is defined again (the static lint of removed identifiers must fail)'),
    ('mono-hue-in-fold-header',
     "<span class=\"qbx-fold-sum\" data-qbfoldsum=\"'+k+'\">",
     "<span class=\"qbx-fold-sum\" style=\"color:#e33\" data-qbfoldsum=\"'+k+'\">",
     'a fold summary is drawn in a hard-coded red (MONO has no hue)'),
    ('mono-hue-in-fold-panel',
     ".lg-more-panel.qbx-fold-panel{margin:0 0 14px;padding:14px 16px}",
     ".lg-more-panel.qbx-fold-panel{margin:0 0 14px;padding:14px 16px;border-top:1px solid #e33}",
     'a fold panel has a red edge (MONO has no hue)'),
    ('folds-open-scroll-sideways',
     ".lg-more-panel.qbx-fold-panel{margin:0 0 14px;padding:14px 16px}",
     ".lg-more-panel.qbx-fold-panel{margin:0 0 14px;padding:14px 16px;min-width:640px}",
     'an open fold is wider than a phone and the page scrolls sideways'),
    # ── LEDGER step 12 (2026-10-07): the one page frame, the status line under the hero, the chart foot, the Filters row ──
    ('list-not-in-side-panel',
     _FR_TOP,
     "top:LEDGER_TOP_ORDER.map(k=>qbTop[k]||'').join('')+qbSideNew,side:'',",
     "from 1100 px the strategy list is drawn in the top block under the calendar, not in the frame's right-hand panel"),
    ('list-panel-sticky',
     '.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1;align-self:stretch;position:relative;min-height:320px}',
     '.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1;align-self:stretch;position:sticky;top:54px;min-height:320px}',
     'on a laptop the list panel is sticky again (step 12: it sits beside the top block, its list scrolling inside it)'),
    ('side-panel-taller-than-top',
     'align-self:stretch;position:relative;min-height:320px}',
     'align-self:stretch;position:relative;min-height:4000px}',
     'from 1100 px the list panel is taller than the top block and pushes the trade list down'),
    ('trades-not-full-width',
     '.lg-frame-2>.lg-frame-rest{grid-column:1/-1;grid-row:2}',
     '.lg-frame-2>.lg-frame-rest{grid-column:1;grid-row:2}',
     'from 1100 px the trade list and the own folds keep to the left column instead of the full width under both'),
    ('frame-not-centred',
     '.lg-frame{max-width:1320px;margin:0 auto;box-sizing:border-box}',
     '.lg-frame{max-width:1320px;margin:0;box-sizing:border-box}',
     'in a window wider than the frame, the frame sits at the left instead of centred'),
    ('frame-too-wide',
     '.lg-frame{max-width:1320px;margin:0 auto;box-sizing:border-box}',
     '.lg-frame{max-width:1600px;margin:0 auto;box-sizing:border-box}',
     'the page frame is wider than the shared 1320 px'),
    ('status-under-chart',
     'const LEDGER_STATUS_UNDER_HERO=true;',
     'const LEDGER_STATUS_UNDER_HERO=false;',
     'the status line sits under the chart (the step 11 place), not directly under the hero'),
    ('status-no-refresh',
     "act:'<button class=\"qb-hero-refresh lg-status-btn\" data-qqqrefresh>'",
     "act2:'<button class=\"qb-hero-refresh lg-status-btn\" data-qqqrefresh>'",
     'the status line has no Refresh button'),
    ('status-line-many-lines',
     '-webkit-line-clamp:2;overflow-wrap:anywhere}',
     '-webkit-line-clamp:none;overflow-wrap:anywhere;max-width:70px}',
     'the status line is not held to one or two lines (it wraps on and on)'),
    ('caption-off-chart-foot',
     _EQA + _CRLF + _EQB + _CRLF + _EQC,
     _EQA + "+'<div class=\"qbx-chart-cap'+((qbRange&&qbRange!=='ALL')?'':' qbx-cap-all')+'\">'+qbRangeCap+'</div>'" + _CRLF + _EQB + _CRLF
     + "              +ledgerChartFootHtml({id:'qb',key:keyHtml})+'</div>';",
     'the chart caption is back above the chart, out of the shared chart foot (and off its style)'),
    ('filters-open-by-default',
     'const LEDGER_FILTERS_OPEN=false;',
     'const LEDGER_FILTERS_OPEN=true;',
     "the strategy list's Filters row starts open"),
    ('filters-row-missing',
     _QB_FILT,
     _CRLF + '            });',
     'the strategy list has no Filters row'),
    ('filters-not-remembered',
     "function ledgerFiltersSet(id,on){try{localStorage.setItem('el_lg_filters_'+id,on?'1':'0');}catch(e){}}",
     'function ledgerFiltersSet(id,on){}',
     "the Filters row's open / closed choice is not stored: a reload finds it closed"),
    ('filters-body-stays-hidden',
     '  if(p)p.hidden=!on;',
     '',
     'a tap on Filters flips its header to open but its body stays hidden'),
    # KEEPS CHECKLIST (2026-10-07): the hero's amber broker line, the PARITY MISMATCH / FILLS BEHIND BACKTEST chips, the System fold's host line, the Account
    # fold's share check, the candle layers of the trade panel's chart, and a netted Webull attempt
    ('broker-made-line-gone',
     "const brokerLine=(brokerInfo&&brokerInfo.book_only_count>0)?(",
     "const brokerLine=(false&&brokerInfo&&brokerInfo.book_only_count>0)?(",
     "the hero's amber 'broker made $X of that (N book-only trades excluded)' line is never drawn"),
    ('broker-made-wrong-figure',
     "broker made '+qeMoney(brokerInfo.broker_net)+' of that ('",
     "broker made '+qeMoney(brokerInfo.book_net)+' of that ('",
     "the hero's broker line quotes the book's net instead of what the broker made"),
    ('broker-made-line-at-zero',
     "brokerInfo.book_only_count>0)?('<div data-qbbroker style=\"color:var(--attn-amber)\"",
     "brokerInfo.book_only_count>=0)?('<div data-qbbroker style=\"color:var(--attn-amber)\"",
     "the hero's broker line is drawn although no trade is book-only"),
    ('broker-made-plural-wrong',
     "' book-only trade'+(brokerInfo.book_only_count===1?'':'s')+' excluded)",
     "' book-only trade'+'s'+' excluded)",
     "the hero's broker line says '1 book-only trades excluded'"),
    ('fills-behind-chip-gone',
     "if(QBPAR&&QBPAR.board_flag)chips.push(qbChipG('FILLS BEHIND BACKTEST','var(--attn-red)'));",
     '',
     'the hero never shows FILLS BEHIND BACKTEST'),
    ('fills-behind-chip-always',
     "if(QBPAR&&QBPAR.board_flag)chips.push(qbChipG('FILLS BEHIND",
     "if(QBPAR)chips.push(qbChipG('FILLS BEHIND",
     'the hero shows FILLS BEHIND BACKTEST whenever the box sends a broker parity summary, flag up or not'),
    ('parity-chip-gone',
     "if(parFailedForHero>0)chips.push(qbChipG(parFailedForHero+' PARITY MISMATCH'+(parFailedForHero===1?'':'ES'),'var(--attn-red)'));",
     '',
     'the hero never shows PARITY MISMATCH'),
    ('parity-chip-at-zero',
     "if(parFailedForHero>0)chips.push(",
     "if(parFailedForHero>=0)chips.push(",
     'the hero shows 0 PARITY MISMATCHES when nothing mismatched'),
    ('parity-chip-plural-wrong',
     "(parFailedForHero===1?'':'ES')",
     "''",
     'the hero says 2 PARITY MISMATCH (no -ES) for several'),
    ('host-line-gone',
     "+modeRow+lossRow+sizeRow+hostRow+lastRow;",
     "+modeRow+lossRow+sizeRow+lastRow;",
     "the System fold has no 'Running on <host> . one-computer check' line"),
    ('host-name-unknown',
     "(hostTxt||'an unknown computer')",
     "('an unknown computer')",
     "the System fold names no computer ('an unknown computer') although the box sent its host"),
    ('lease-check-always-ok',
     "const leaseOk=BR.lease_ok_to_send!==false;",
     "const leaseOk=true;",
     "the System fold's one-computer check reads OK while another computer holds the lease"),
    ('share-check-word-wrong',
     "+(QPOSLIVE.mismatch?'<b>MISMATCH</b>",
     "+(false?'<b>MISMATCH</b>",
     "the Account fold's share check says OK when Webull and the legs disagree"),
    ('share-check-attr-swapped',
     "(QPOSLIVE.mismatch?'mismatch':'ok')",
     "(QPOSLIVE.mismatch?'ok':'mismatch')",
     "the Account fold's share check is tagged ok when it mismatches, and the reverse"),
    ('share-check-counts-swapped',
     "'Webull holds '+bw+' &middot; legs sum to '+lw",
     "'Webull holds '+lw+' &middot; legs sum to '+bw",
     "the Account fold's share check swaps the Webull share count and the legs' sum"),
    ('netted-mark-gone',
     "if(k==='netted')put('wb_netted',a.t,px!=null?px:ref,'diamond',",
     "if(false)put('wb_netted',a.t,px!=null?px:ref,'diamond',",
     'a netted Webull attempt draws no diamond on the chart'),
    ('netted-label-wrong',
     "'diamond','no Webull order - netted against another leg'+(px!=null?",
     "'diamond','netted'+(px!=null?",
     "the diamond of a netted attempt is not titled 'no Webull order - netted against another leg'"),
    ('netted-legend-row-gone',
     "if(k==='netted'){rows.push(item('diamond',",
     "if(k==='netted'){return;rows.push(item('diamond',",
     'the legend under the chart has no row for a netted Webull attempt'),
    ('signal-layer-gone',
     "if(mk.signal&&mk.signal.t)sigBar('signal',mk.signal.t,'signal bar');",
     '',
     'the signal bar is never outlined on the chart'),
    ('fill-layer-gone',
     "if(mk.bt_in)put('bt_in',mk.bt_in.t,num(mk.bt_in.px),'ring','backtest fill '+(num(mk.bt_in.px)!=null?num(mk.bt_in.px).toFixed(2):''),-1);",
     '',
     'the backtest fill ring is never drawn on the chart'),
    ('fill-layer-wrong-shape',
     "'ring','backtest fill '",
     "'tick','backtest fill '",
     "the backtest fill is drawn as the book's tick instead of its own ring"),
    ('book-layer-gone',
     "if(mk.book_in)put('book_in',mk.book_in.t,num(mk.book_in.px),'tick','book fill '+(num(mk.book_in.px)!=null?num(mk.book_in.px).toFixed(2):''),0);",
     '',
     'the book fill tick is never drawn on the chart'),
    ('book-out-mark-gone',
     "if(mk.book_out)put('book_out',mk.book_out.t,bOut,'sq-open','book exit '+(bOut!=null?bOut.toFixed(2):''),0,true);",
     '',
     'the book exit square is never drawn on the chart'),
    ('attempt-layer-gone',
     "(mk.wb_in||[]).forEach(a=>att(a,false));",
     '',
     'the Webull entry attempt is never drawn on the chart'),
    ('attempt-exit-gone',
     "(mk.wb_out||[]).forEach(a=>att(a,true));",
     '',
     'the Webull exit attempt is never drawn on the chart'),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>webull board probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1366px;height:768px;border:0;display:block"></iframe>
<pre id="o" style="display:none"></pre>
<script>
var CASES=__CASES__, VP=__VP__, FIX=__FIX__, NOW=__NOW__, VARS=__VARS__, STATS=__STATS__, TLS=__TLS__, OLDMARKS=__OLDMARKS__;
(function(){
  var out={cases:{},notes:[]}, reported=false, t0=Date.now(), sink=null, phase=0, PS0=null;
  function finish(why){
    if(reported)return; reported=true;
    out.why=why; out.ms=Date.now()-t0;
    document.getElementById('o').textContent='WEBULLPROBE: '+JSON.stringify(out);
  }
  setTimeout(function(){finish('backstop');},200000);
  var fr=document.getElementById('f');
  function W(){return fr.contentWindow;}
  function D(){return fr.contentDocument;}
  function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  async function waitFor(fn,ms){
    var a=Date.now();
    while(Date.now()-a<ms){var v=false;try{v=fn();}catch(_e){} if(v)return true; await sleep(40);}
    try{return !!fn();}catch(_e2){return false;}
  }
  function hook(w){
    if(w.__probeSink)return w.__probeSink;
    var s=w.__probeSink={errors:[],uncaught:[],loadErr:[]};
    var orig=w.console.error;
    w.console.error=function(){
      var p=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];p.push(a&&a.stack?String(a.stack):String(a));}
      s.errors.push(p.join(' '));
      try{orig.apply(w.console,arguments);}catch(_){}
    };
    w.addEventListener('error',function(ev){
      if(/ResizeObserver loop/.test(String(ev&&ev.message||'')))return;
      s.uncaught.push(String(ev&&ev.message||ev)+(ev&&ev.error&&ev.error.stack?' :: '+ev.error.stack:''));});
    w.addEventListener('unhandledrejection',function(ev){
      var r=ev&&ev.reason;s.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    var le=w._loadError;
    w._loadError=function(err,stage){
      s.loadErr.push(String(err&&err.message||err)+' (stage '+stage+')');
      if(typeof le==='function')return le.apply(this,arguments);
    };
    return s;
  }
  function drain(){
    return {errors:sink.errors.splice(0).slice(0,12),uncaught:sink.uncaught.splice(0).slice(0,12),
            loadErr:sink.loadErr.splice(0).slice(0,12)};
  }
  function overlays(){
    var d=D(),n=0;
    [].slice.call(d.body.children).forEach(function(e){
      if(/^\\s*LOAD ERROR/.test(e.textContent||'')){n++;e.remove();}});
    return n;
  }
  async function setVp(name){
    var v=VP[name];
    fr.style.width=v[0]+'px';fr.style.height=v[1]+'px';
    await waitFor(function(){return W().innerWidth===v[0];},2000);
    await sleep(60);
  }
  function q(sel){return D().querySelector(sel);}
  // the opacity an element is drawn at: its own times every ancestor's (null when it is not there)
  function effOp(e){if(!e)return null;var o=1,w=W();for(var n=e;n&&n.nodeType===1;n=n.parentElement){o*=parseFloat(w.getComputedStyle(n).opacity)||0;}return Math.round(o*100)/100;}
  function txt(sel){var e=q(sel);return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;}
  // LEDGER steps 7 + 10: the shared calendar (fold, panel, month, summary, every day cell, the week cells, the arrows)
  function calRead(){
    var w=W(),fold=q('[data-lgcalfold="qb"]'),pn=q('#qb-cal'),cal=q('.lg-cal[data-lgcal="qb"]');
    var c={fold:fold?fold.getAttribute('aria-expanded'):null,foldText:fold?(fold.textContent||'').replace(/\\s+/g,' ').trim():null,
      panel:pn?(pn.hasAttribute('hidden')?'hidden':'shown'):null,oldDays:D().querySelectorAll('[data-qcalday]').length,oldNav:D().querySelectorAll('[data-qcalmo]').length};
    if(!cal)return c;
    var sm=cal.querySelector('.lg-cal-sum'),t=cal.querySelector('.lg-cal-title'),grid=cal.querySelector('.lg-cal-grid'),kids=grid?[].slice.call(grid.children):[];
    c.month=cal.getAttribute('data-lgcalmonth');c.title=t?(t.textContent||'').trim():null;
    c.sum=sm?(sm.textContent||'').replace(/\\s+/g,' ').trim():null;
    c.nav=[].map.call(cal.querySelectorAll('[data-lgcalmo]'),function(b){return [b.getAttribute('data-lgcalmo'),!!b.disabled];});
    // 8 header cells (S M T W T F S WEEK), then rows of 7 day slots + 1 week cell
    c.days=[];c.weeks=[];
    kids.slice(8).forEach(function(e,i){
      if(i%8===7){var wm=e.querySelector('.m'),wn=e.querySelector('.n');
        c.weeks.push({title:e.getAttribute('title'),m:wm?(wm.textContent||'').trim():null,n:wn?(wn.textContent||'').trim():null});return;}
      var d=e.querySelector('.d');if(!d)return;
      var m=e.querySelector('.m'),n=e.querySelector('.n'),cs=w.getComputedStyle(e),af=w.getComputedStyle(e,'::after');
      c.days.push({d:+(d.textContent||'').trim(),traded:e.tagName==='BUTTON',ds:e.getAttribute('data-lgcalday'),
        cav:e.classList.contains('cav'),hatch:(cs.backgroundImage||'').indexOf('repeating-linear-gradient')>=0,
        dot:af.content!=='none'&&af.width==='5px',title:e.getAttribute('title'),m:m?(m.textContent||'').trim():null,n:n?(n.textContent||'').trim():null,
        mColor:m?w.getComputedStyle(m).color:null,up:e.classList.contains('up'),down:e.classList.contains('down')});
    });
    c.sumColors=[].map.call(cal.querySelectorAll('.lg-cal-sum span'),function(e){return w.getComputedStyle(e).color;});
    var pr=pn?pn.getBoundingClientRect():null;
    c.box=pr?{l:Math.round(pr.left),r:Math.round(pr.right),w:Math.round(pr.width)}:null;
    c.gridW=grid?Math.round(grid.getBoundingClientRect().width):null;
    return c;
  }
  // the strategy list on the shared list: title and count, the groups in order with their header, fold state and rows, where it sits
  function listRead(){
    var w=W(),lst=q('.qbx-side [data-lglist="qb"]');
    if(!lst)return null;
    function rowRead(b){
      var nm=b.querySelector('.lg-row-name'),cn=nm?nm.cloneNode(true):null,tg=null,tag=cn?cn.querySelector('.lg-row-tag'):null;
      if(tag){tg=(tag.textContent||'').replace(/\\s+/g,' ').trim();tag.parentNode.removeChild(tag);}
      var v=b.querySelector('.lg-row-val'),vc=v?v.cloneNode(true):null,sm=vc?vc.querySelector('small'):null,sm0=v?v.querySelector('small'):null,v2=null;
      if(sm){v2=(sm.textContent||'').replace(/\\s+/g,' ').trim();sm.parentNode.removeChild(sm);}
      var sb=b.querySelector('.lg-row-sub'),rc=b.getBoundingClientRect(),ex=b.nextElementSibling;
      return {key:b.getAttribute('data-lgrow'),name:cn?(cn.textContent||'').replace(/\\s+/g,' ').trim():null,tag:tg,
        sub:sb?(sb.textContent||'').replace(/\\s+/g,' ').trim():null,subShown:sb?w.getComputedStyle(sb).display!=='none':false,
        value:vc?(vc.textContent||'').replace(/\\s+/g,' ').trim():null,value2:v2,value2Shown:sm0?w.getComputedStyle(sm0).display!=='none':false,
        off:b.classList.contains('off'),h:Math.round(rc.height),sw:b.querySelectorAll('[data-lgsw]').length,
        valColor:v?w.getComputedStyle(v).color:null,expanded:b.getAttribute('aria-expanded'),
        extra:(ex&&ex.classList&&ex.classList.contains('qbx-lg-extra'))?ex.getAttribute('data-qbextra'):null};
    }
    var hd=lst.querySelector('.lg-list-hd'),hs=hd?hd.querySelectorAll('span'):[],box=lst.getBoundingClientRect();
    var side=q('.qbx-side'),hist=q('.qbx-history'),acct=q('.qbx-account'),sh=q('.qb-shell'),fr=q('[data-lgtrade]')||q('[data-qbtraderow]'),sy=w.scrollY||0;
    var fpn=q('[data-lgframe-side="qb"]'),ftp=q('[data-lgframe-top="qb"]');
    var top=function(e){return e?Math.round(e.getBoundingClientRect().top+sy):null;},bot=function(e){return e?Math.round(e.getBoundingClientRect().bottom+sy):null;};
    return {title:hs[0]?(hs[0].textContent||'').trim():null,count:hs[1]?(hs[1].textContent||'').replace(/\\s+/g,' ').trim():null,
      groups:[].map.call(lst.querySelectorAll('.lg-grp'),function(g){
        var h=g.querySelector('.lg-grp-hd'),f=g.querySelector('[data-lggrp]'),n=g.querySelector('.lg-grp-note');
        return {key:g.getAttribute('data-lggroup'),head:h?(h.textContent||'').replace(/\\s+/g,' ').trim():null,fold:!!f,
          expanded:f?f.getAttribute('aria-expanded'):null,note:n?(n.textContent||'').replace(/\\s+/g,' ').trim():null,
          rows:[].map.call(g.querySelectorAll('[data-lgrow]'),rowRead)};}),
      sw:lst.querySelectorAll('[data-lgsw]').length,
      geo:{listTop:top(lst),listBottom:bot(lst),listLeft:Math.round(box.left),listRight:Math.round(box.right),sideTop:top(side),
        histTop:top(hist),histBottom:bot(hist),histLeft:hist?Math.round(hist.getBoundingClientRect().left):null,
        histRight:hist?Math.round(hist.getBoundingClientRect().right):null,acctTop:top(acct),shellTop:top(sh),rowTop:top(fr),
        vh:w.innerHeight,sticky:side?w.getComputedStyle(side).position:null,
        inSide:!!lst.closest('[data-lgframe-side="qb"]'),topRight:ftp?Math.round(ftp.getBoundingClientRect().right):null,
        panelTop:top(fpn),panelBottom:bot(fpn),panelPos:fpn?w.getComputedStyle(fpn).position:null}};
  }
  // markers of the removed previous board (none may be in the page, with or without ?oldboards=1), the name of the removed flag, and what the new page shows
  function oldReads(){
    var d=D(),w=W();
    return {oldMarks:OLDMARKS.filter(function(s){return !!d.querySelector(s);}),
      flagConst:(function(){try{return w.eval('typeof LEDGER_OLDBOARDS');}catch(e){return 'error';}})(),
      sharedCalFold:!!q('[data-lgcalfold]'),sharedList:!!q('[data-lglist="qb"]'),
      order:[].map.call(d.querySelectorAll('.qb-shell .qbx-side, .qb-shell .qbx-account, .qb-shell .qbx-history, .qb-shell .qbx-stats'),function(e){return e.className.split(' ')[0];}).filter(function(c){return /^qbx-(side|account|history|stats)$/.test(c);})};
  }
  // the More stats panel: shown or hidden, its groups, and every row as 'Group|Label' -> value text
  function moreRead(){
    var mp=q('#qb-more'),m={panel:mp?(mp.hasAttribute('hidden')?'hidden':'shown'):null,groups:[],vals:{},
      empty:!!mp&&(mp.textContent||'').indexOf('No trades in this range.')>=0,hued:[],gap:null};
    if(mp)[].forEach.call(mp.querySelectorAll('[data-lgmsgroup]'),function(g){
      var gt=g.getAttribute('data-lgmsgroup');m.groups.push(gt);
      [].forEach.call(g.querySelectorAll('.lg-ms-row'),function(row){
        var l=row.querySelector('.l'),v=row.querySelector('.v');
        m.vals[gt+'|'+(l?(l.textContent||'').replace(/\\s+/g,' ').trim():'')]=v?(v.textContent||'').replace(/\\s+/g,' ').trim():null;});});
    if(mp&&!mp.hasAttribute('hidden')){
      // MONO has no hue: every value and every bar segment must come out grey (r = g = b)
      var w=W(),chk=function(e,prop){var c=w.getComputedStyle(e)[prop]||'',p=c.replace(/[^0-9.,]/g,'').split(',').map(Number);
        if(p.length>=3&&!(p[0]===p[1]&&p[1]===p[2])&&!(p.length>3&&p[3]===0)&&m.hued.length<6)
          m.hued.push(e.tagName.toLowerCase()+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(' ').join('.'):'')+' '+prop+' '+c);};
      [].forEach.call(mp.querySelectorAll('.lg-ms-row .v, .lg-ms-row .v *'),function(e){chk(e,'color');});
      [].forEach.call(mp.querySelectorAll('.lg-ms-bar > *'),function(e){chk(e,'backgroundColor');});
      // with no trade in the range: the room between 'No trades in this range.' and the Account heading
      var nt=null;[].forEach.call(mp.querySelectorAll('.lg-ms-note'),function(e){if(!nt&&(e.textContent||'').indexOf('No trades in this range.')>=0)nt=e;});
      var gh=mp.querySelector('.lg-ms-group h4');
      if(nt&&gh)m.gap=Math.round(gh.getBoundingClientRect().top-nt.getBoundingClientRect().bottom);
    }
    return m;
  }
  // wait until the top bar has kept one height for three checks in a row (a busy machine draws late)
  async function settleTopbar(){
    var last=-1,same=0,a=Date.now();
    while(Date.now()-a<3000){var t=D().querySelector('#app .topbar'),h=t?t.offsetHeight:0;
      if(h===last){if(++same>=3)return;}else{same=0;last=h;}await sleep(50);}
  }
  function offenders(d){
    var cw=d.documentElement.clientWidth,res=[],fix=[];
    var all=d.querySelectorAll('body *');
    for(var i=0;i<all.length&&res.length<4;i++){
      var e=all[i],r=e.getBoundingClientRect();
      if(r.width<=0||r.right<=cw+1)continue;
      var p=e.parentElement,pr=p?p.getBoundingClientRect():null;
      if(pr&&pr.right>cw+1)continue;
      var pos=d.defaultView.getComputedStyle(e).position;
      (pos==='fixed'?fix:res).push(e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(/\\s+/).join('.'):'')
               +' right='+Math.round(r.right)+(pos!=='static'?' ('+pos+')':''));
    }
    return res.length?res:fix.slice(0,3);
  }
  function seed(cfg){
    var w=W();
    if(PS0){var d0=D();[[d0.documentElement,PS0[0]],[d0.body,PS0[1]],[d0.getElementById('app')||d0.body,PS0[2]]].forEach(function(p){
      if(!p[0])return;if(p[1]==null)p[0].removeAttribute('style');else p[0].setAttribute('style',p[1]);});}
    w.__probeFixJson=JSON.stringify(cfg.fix||FIX);
    w.__qbNowMs=cfg.nowMs||NOW;
    w.__probeOpenLeg=cfg.openLeg||null;
    w.__probeSystemOpen=cfg.systemOpen?1:0;
    w.__probeLiveErr=!!cfg.liveErr;
    w.__probePrevJson=cfg.prev?JSON.stringify(cfg.prev):null;
    w.__probePrevCache=!!cfg.prevCache;
    w.__probeTab=cfg.tab||null;
    w.__probeCheckedMs=cfg.checkedMs||cfg.nowMs||NOW;
    w.__probeOffline=!!cfg.offline;w.__probeMissing=!!cfg.missing;w.__probeUnloaded=!!cfg.unloaded;
    w.__probeRange=cfg.range||null;w.__probeTodayNY=cfg.todayNY||null;w.__probeCalMonth=cfg.calMonth||null;
    w.__probeMoreOpen=!!cfg.moreOpen;
    w.__probeCalOpen=cfg.calOpen||null;w.__probeFolds=!!cfg.folds;w.__probeFoldOpen=cfg.foldOpen||null;
    return w.eval("(function(){try{"
      +"if(!window.__probeLTN)window.__probeLTN=ledgerTodayNY;"
      +"ledgerTodayNY=window.__probeTodayNY?function(){return window.__probeTodayNY;}:window.__probeLTN;"
      // More stats open is stored for this viewer but not in memory: the way a reload finds it
      +"try{if(window.__probeMoreOpen)localStorage.setItem('el_qb_morestats_open','1');else localStorage.removeItem('el_qb_morestats_open');}catch(e){}window._qbMoreStatsOpen=false;"
      +"try{delete navigator.onLine;}catch(e){}"
      +"if(window.__probeOffline)Object.defineProperty(navigator,'onLine',{configurable:true,get:function(){return false;}});"
      +"try{localStorage.removeItem('el_qb_retired_open');localStorage.removeItem('el_lg_lines_webull');}catch(e){}"
      +"window._qbRetiredOpen=false;"
      +"try{localStorage.removeItem('el_qb_cal_open');localStorage.removeItem('el_qb_cal_month');localStorage.removeItem('el_qb_shadow_open');}catch(e){}window._qbCalOpen=null;window._qbShadowOpen=false;"
      +"try{if(window.__probeCalOpen)localStorage.setItem('el_qb_cal_open',window.__probeCalOpen);if(window.__probeFolds){localStorage.setItem('el_qb_retired_open','1');localStorage.setItem('el_qb_shadow_open','1');}}catch(e){}"
      +"prefs.theme="+JSON.stringify(cfg.theme)+";applyTheme();"
      +"window._qqqExec=JSON.parse(window.__probeFixJson);"
      +"window._qbPubFailSeen=null;if(typeof qbNotePubFails==='function'){if(window.__probePrevJson)qbNotePubFails(JSON.parse(window.__probePrevJson),window.__probePrevCache);qbNotePubFails(window._qqqExec);}"
      +"window._qbCheckedMs=window.__probeCheckedMs;window._qqqExecTriedAt=0;"
      +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;window._qqqExecMissing=false;"
      +"if(window.__probeMissing){window._qqqExec=null;window._qqqExecMissing=true;}"
      +"if(window.__probeUnloaded){window._qqqExec=null;window._qqqExecLoaded=false;window._qbCheckedMs=0;}"
      +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
      +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
      +"window._qbSheet=null;window._qbLegOpen=new Set(window.__probeOpenLeg?[window.__probeOpenLeg]:[]);window._qeTradesView='list';window._qeChartPeriod='ALL';"
      // LEDGER step 9: no trade panel open, none remembered
      +"window._qbPanelKey=null;window._qbPanelPos=null;try{ledgerTradePanelClose('wb','probe');}catch(e){}"
      // the trade list's own state: the view stored for this board, the search text, the chip, the search box's held focus
      +"try{localStorage.removeItem('el_lg_view_wb');}catch(e){}window._qeTradesQuery='';window._qeTradesChip='ALL';window._qbSearchHold=null;"
      +"window._qbLegNoteOpen={};if(window.__probeOpenLeg)window._qbLegNoteOpen[window.__probeOpenLeg]=true;"
      +"try{var ap=JSON.parse(localStorage.getItem('augurPrefs')||'{}');ap.qqqSystemOpen=window.__probeSystemOpen;ap.qqqRailsOpen=0;ap.qqqEventsOpen=0;ap.qqqFeedSigOpen=0;ap.qqqModelOpen=0;localStorage.setItem('augurPrefs',JSON.stringify(ap));}catch(e){}"
      // LEDGER step 11: every own fold starts shut (nothing stored, nothing in memory), unless a case opens some
      +"try{['orders','account','todayorders','feedsig','system','rails','events','model','list'].forEach(function(k){localStorage.removeItem('el_qb_fold_'+k);});}catch(e){}window._qbFolds=null;"
      // LEDGER step 12: the list's Filters row starts with nothing stored (so it is drawn closed unless the build opens it)
      +"try{localStorage.removeItem('el_lg_filters_qb');}catch(e){}"
      +"try{var fo=window.__probeFoldOpen;if(fo==='all')fo=['orders','account','todayorders','feedsig','system','rails','events','model','list'];if(fo)fo.forEach(function(k){localStorage.setItem('el_qb_fold_'+k,'1');});}catch(e){}"
      +"window._qqqExecLive=false;window._qqqExecLiveErrorAt=window.__probeLiveErr?Date.now():null;window._qqqExecFetchedAt=window.__probeLiveErr?0:Date.now();"
      +"window._qbChartHoverActive=false;"
      +"if(window.__probeCalMonth)window._qqqCalMonth=window.__probeCalMonth;"
      +"homeRange=window.__probeRange||'ALL';currentUser=currentUser||{uid:'probe-uid'};"
      +"activeTab=window.__probeTab||'augur';augurSub='qqqpaper';window._lastRenderTab=activeTab;"
      +"try{window.scrollTo(0,0);}catch(e){}"
      +"renderApp();return 'OK';"
      +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
  }
  function sample(withTl){
    var d=D(),w=W(),r={};
    r.innerW=w.innerWidth;
    r.theme=d.documentElement.getAttribute('data-theme');
    r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
    r.heroMissing=['qb-hero-label','qb-hero-value','qb-hero-today','qb-hero-range','qb-hero-chips'].filter(function(i){return !d.getElementById(i);});
    r.heroBig=txt('#qb-hero-value');
    r.heroToday=txt('#qb-hero-today');
    r.pills=[].map.call(d.querySelectorAll('.qbx-range-row [data-qbrange]'),function(b){return b.getAttribute('data-qbrange');}).join(',');
    var csv=d.querySelector('#qb-lg-chart svg');
    r.chart=!!csv;
    r.chartH=0;
    if(csv){var cr=csv.getBoundingClientRect(),vb=(csv.getAttribute('viewBox')||'').split(/[ ,]+/).map(Number);
      r.chartH=Math.round(vb.length===4&&vb[2]>0&&vb[3]>0?vb[3]*Math.min(cr.width/vb[2],cr.height/vb[3]):cr.height);}
    r.chartDates=csv?csv.querySelectorAll('[data-lgdate]').length:0;
    r.chartTicks=csv?csv.querySelectorAll('[data-lgtick]').length:0;
    r.chartBands=csv?csv.querySelectorAll('[data-lgband]').length:0;
    r.chartMarks=csv?csv.querySelectorAll('[data-lgmark]').length:0;
    var mk=csv?csv.querySelector('[data-lgmark]'):null;
    r.markText=mk&&mk.nextElementSibling?(mk.nextElementSibling.textContent||'').trim():null;
    r.lines=[].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend [data-lgline]'),function(b){return (b.textContent||'').trim();});
    r.lineDashes=[].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend svg line'),function(l){return l.getAttribute('stroke-dasharray')||'none';});
    r.lineIconW=Math.max.apply(null,[0].concat([].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend svg'),function(s){return Math.round(s.getBoundingClientRect().width);})));
    r.key=txt('.qbx-lg-key');
    r.liveRows=[].map.call(d.querySelectorAll('.qbx-side [data-qblegrow]'),function(e){return e.getAttribute('data-qblegrow');});
    var rb=d.querySelector('.qbx-side [data-qbretired]');
    r.retired=!!rb;
    r.retiredExpanded=rb?rb.getAttribute('aria-expanded'):null;
    r.retiredText=rb?(rb.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.retiredRows=d.querySelectorAll('.qbx-side [data-qbretiredrow]').length;
    var rows=d.querySelectorAll('[data-lgtrade]');
    if(!rows.length)rows=d.querySelectorAll('[data-qbtraderow]');
    r.tradeRows=rows.length;
    r.tradeLegs=[].map.call(rows,function(e){var s=e.querySelector('.qb-trade-leg');return s?(s.textContent||'').trim():null;});
    r.oldChart=!!d.querySelector('#qbCrossCapture');
    r.stats=[].map.call(d.querySelectorAll('.qbx-lgstats [data-lgstat]'),function(e){
      var v=e.querySelector('.lg-stat-val'),s=e.querySelector('.lg-stat-sub');
      return [e.getAttribute('data-lgstat'),v?(v.textContent||'').replace(/\\s+/g,' ').trim():null,s?(s.textContent||'').replace(/\\s+/g,' ').trim():null];});
    r.statTilesAll=d.querySelectorAll('[data-lgstat]').length;
    // the strip must be SEEN, right under the chart: shown, of real size, below the chart box and above the
    // Account and History sections (and on a phone above the Strategies list)
    var sbx=q('.qbx-lgstats');
    if(sbx){var sbr=sbx.getBoundingClientRect(),sbs=w.getComputedStyle(sbx),cbx=q('.qbx-chart');
      var topOf=function(sel){var e=q(sel);return e?Math.round(e.getBoundingClientRect().top):null;};
      r.statBox={disp:sbs.display,vis:sbs.visibility,op:effOp(sbx),w:Math.round(sbr.width),h:Math.round(sbr.height),top:Math.round(sbr.top),
        tileH:Math.min.apply(null,[9999].concat([].map.call(sbx.querySelectorAll('[data-lgstat]'),function(e){return Math.round(e.getBoundingClientRect().height);}))),
        chartBottom:cbx?Math.round(cbx.getBoundingClientRect().bottom):null,sideTop:topOf('.qbx-side'),acctTop:topOf('.qbx-account'),histTop:topOf('.qbx-history')};}
    r.oldStats=!!d.querySelector('.qbx-stat-strip');
    var mbt=q('[data-lgmore="qb"]');r.moreBtn=mbt?mbt.getAttribute('aria-expanded'):null;
    r.more=moreRead();
    var act=q('.qbx-activity'),mwon=act?(act.textContent||'').match(/(\\d+)% won/):null;r.calWon=mwon?+mwon[1]:null;
    r.lgcal=calRead();r.lg=listRead();r.old=oldReads();r.s11=s11Read();
    if(withTl)r.tl=tlRead();
    r.scrollW=d.documentElement.scrollWidth;
    r.clientW=d.documentElement.clientWidth;
    if(r.scrollW>r.clientW+1)r.wide=offenders(d);
    r.overlay=overlays();
    // freshness readouts (sweep 2026-10-05)
    r.fresh={};
    [].forEach.call(d.querySelectorAll('#qb-hero-chips [data-qbfresh]'),function(e){r.fresh[e.getAttribute('data-qbfresh')]=(e.textContent||'').trim();});
    r.strip=txt('.qbx-status-strip');
    var tc=d.querySelector('[data-qbtopchip]');
    r.top=tc?[tc.getAttribute('data-qbtopchip'),(tc.textContent||'').slice(1).trim()]:null;
    // the chip must be DRAWN where the owner can see it: shown, inside the viewport, not covered
    var tcw=d.getElementById('qb-top-chip');
    if(tcw){var br=tcw.getBoundingClientRect(),cs=w.getComputedStyle(tcw),cx=br.left+br.width/2,cy=br.top+br.height/2;
      var hit=(br.width>0&&br.height>0&&cx>=0&&cy>=0&&cx<w.innerWidth&&cy<w.innerHeight)?d.elementFromPoint(cx,cy):null;
      r.topBox={l:Math.round(br.left),t:Math.round(br.top),r:Math.round(br.right),b:Math.round(br.bottom),w:Math.round(br.width),h:Math.round(br.height),
        disp:cs.display,vis:cs.visibility,op:effOp(tcw),vw:w.innerWidth,vh:w.innerHeight,
        covered:hit?!(hit===tcw||tcw.contains(hit)):null,coveredBy:hit&&!(hit===tcw||tcw.contains(hit))?(hit.tagName.toLowerCase()+(hit.id?'#'+hit.id:'')):null};}
    r.timer=typeof w._qbFreshTimer;
    r.vis=d.visibilityState;
    var lp=q('[data-qblegpill="NOISE"]');r.legPill=lp?(w.getComputedStyle(lp).color===greyCol()?'grey':'colour'):null;r.legPillTxt=lp?(lp.textContent||'').trim():null;
    r.liveLine=txt('[data-qblive="NOISE"]');
    var op=q('[data-qbopenpnl="NOISE"]');r.openPnl=op?(w.getComputedStyle(op).color===greyCol()?'grey':'colour'):null;
    var ur=q('[data-qbunreal="NOISE"]');r.unreal=ur?(w.getComputedStyle(ur).color===greyCol()?'grey':'colour'):null;
    var at=(d.getElementById('app')||{innerText:''}).innerText||'';r.badTok=(at.match(/NaN|undefined|\\[object Object\\]/g)||[]).slice(0,4);
    try{r.cantRead=w.eval('qbCantRead()');}catch(e){r.cantRead='ERR '+e;}
    r.visRead=w.__probeVisRead||null;w.__probeVisRead=null;
    try{r.cal=w.eval("JSON.stringify([qbIsSessionDay('2026-11-26'),qbIsSessionDay('2027-12-31'),qbIsSessionDay('2027-12-30'),qbCloseMins('2026-11-27'),qbIsSessionDay('2026-10-05')])");}catch(e){r.cal=null;}
    var sp=d.querySelector('[data-qbstop]');r.stop=sp?sp.getAttribute('data-qbstop'):null;r.stopTxt=sp?(sp.textContent||'').trim():null;
    var od=d.querySelector('[data-qbordersday]');r.orders=od?od.getAttribute('data-qbordersday'):null;r.ordersTxt=od?(od.textContent||'').trim():null;
    r.legtoday=txt('[data-qblegtoday]');
    // post-landing keeps: the hero's broker line, the NOISE row's TODAY figure, the System fold's host line (state, words, any green in it)
    r.legTodayVal=txt('[data-qblegtodayval="NOISE"]');
    var hb=q('[data-qbhost]');
    if(hb){var okc=cssCol('var(--attn-ok)');r.host=[hb.getAttribute('data-qbhost'),(hb.textContent||'').replace(/\\s+/g,' ').trim(),
      [].some.call(hb.querySelectorAll('*'),function(e){return w.getComputedStyle(e).color===okc;})];}else r.host=null;
    r.asof=txt('[data-qbasof]');
    r.eqStale=!!d.querySelector('[data-qbeqstale]');
    r.keelwarn=txt('[data-qbkeelwarn]');
    r.miniSilent=txt('[data-qbminisilent]');
    r.miniPill=txt('[data-qbminipill]');
    r.ordSum=txt('[data-qbfold="orders"] [data-qbfoldsum]');
    var mp=q('[data-qbminipill]');r.miniPillHtml=mp?mp.innerHTML:null;
    var om=q('[data-qbordmode]');r.ordModeHtml=om?om.innerHTML:null;
    var eqs=q('[data-qbeqstale]');r.eqWhy=eqs?eqs.getAttribute('title'):null;
    r.pin=w.__probePin||null;w.__probePin=null;
    r.onLine=w.navigator.onLine;
    r.miniTxt=txt('.qbx-orders-mini');
    r.ordMode=txt('[data-qbordmode]');
    r.keelLine=txt('[data-qbkeelline="NOISE"]');
    var ec=q('[data-qbeqchg]');r.eqChg=ec?ec.getAttribute('data-qbeqchg'):null;r.eqChgOp=effOp(ec);
    var rc=q('[data-qbrecon]');r.recon=rc?rc.getAttribute('data-qbrecon'):null;r.reconTxt=rc?(rc.textContent||'').replace(/\\s+/g,' ').trim():null;
    // KEEPS CHECKLIST: the hero's note (the since line, then the amber broker line when a trade is book-only) with each child's tooltip, and the System fold's host line
    var hn=q('#qb-hero-note');
    r.heroNote=[].map.call(hn?hn.children:[],function(e){return (e.textContent||'').replace(/\\s+/g,' ').trim();});
    r.heroNoteTitles=[].map.call(hn?hn.children:[],function(e){return e.getAttribute('title')||'';});
    var hl=null;[].forEach.call(d.querySelectorAll('#qbf-system div'),function(e){if(hl===null&&!e.querySelector('div')&&/^Running on /.test((e.textContent||'').trim()))hl=(e.textContent||'').replace(/\\s+/g,' ').trim();});
    r.hostLine=hl;
    r.opNotToday=effOp(q('[data-qbnottoday]'));
    r.opStop=effOp(q('[data-qbstop]'));
    r.opLegToday=effOp(q('[data-qblegtoday]'));
    r.lastTick=(q('[data-qblasttick]')||{getAttribute:function(){return null;}}).getAttribute('data-qblasttick');
    r.tab=w.eval('activeTab');
    // the box's own flags in the hero (not the freshness chips): drawn grey (--text4) or not
    var grey=greyCol();
    r.flags={};
    [].forEach.call(d.querySelectorAll('#qb-hero-chips span:not([data-qbfresh])'),function(e){
      var t=(e.textContent||'').trim();if(t&&!(t in r.flags))r.flags[t]=w.getComputedStyle(e).color===grey?'grey':'colour';});
    // would the full-doc listener run on HOME / on the board (signed in, page visible)? It must be the
    // board's only (QUOTA in index.html). db/auth/visibility stubbed, then put back
    function wants(tab,sub){return w.eval("(function(){var sd=db,sa=auth,st=activeTab,ss=augurSub;try{db={};auth={currentUser:{uid:'probe-uid'}};activeTab='"+tab+"';augurSub='"+sub+"';"
      +"Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});"
      +"return _qqqExecWantsLive();}catch(e){return 'ERR '+e;}finally{db=sd;auth=sa;activeTab=st;augurSub=ss;try{delete document.visibilityState;}catch(e2){}}})()");}
    r.wantsLiveHome=wants('home','qqqpaper');
    r.wantsLiveBoard=wants('augur','qqqpaper');
    return r;
  }
  function greyCol(){var d=D(),w=W(),p=d.createElement('span');p.style.color='var(--text4)';d.body.appendChild(p);var g=w.getComputedStyle(p).color;p.remove();return g;}
  function cssCol(v){var d=D(),w=W(),p=d.createElement('span');p.style.color=v;d.body.appendChild(p);var g=w.getComputedStyle(p).color;p.remove();return g;}
  // after the seed render: run the 30 s timer's body with the clock moved on, or land a .get() on HOME
  async function after(cfg){
    var w=W();
    if(cfg.visread){
      // the page shown again: on HOME 60 s and 400 s after the last read, then on the board 60 s after it.
      // loadQqqExec is swapped for a counter (no Firestore), qbOnPageShown is the visibility hook's body
      w.__probeVisRead=w.eval("(function(){var orig=loadQqqExec,n=0,res=[];try{loadQqqExec=function(){n++;};"
        +"Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});"
        +"[['home',60000],['home',400000],['augur',60000]].forEach(function(c){activeTab=c[0];window._qqqExecLoading=false;window._qqqExecTriedAt=Date.now()-c[1];n=0;qbOnPageShown();res.push(n);});"
        +"return res;}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}finally{loadQqqExec=orig;activeTab=window.__probeTab||'augur';window._qqqExecTriedAt=0;try{delete document.visibilityState;}catch(e2){}}})()");
      return 'OK';
    }
    if(cfg.cachesnap){
      // the listener error was 61 s ago, so the board's listener re-attaches; its first snapshot is cached
      var rc=w.eval("(function(){var sd=db,sa=auth;window.__probeRestore=function(){db=sd;auth=sa;try{delete document.visibilityState;}catch(e2){}};try{"
        +"window._qqqExecLiveErrorAt=Date.now()-61000;window._qqqExecUnsub=null;window._qqqExecLive=false;"
        +"var doc=JSON.parse(window.__probeFixJson),snap={exists:true,data:function(){return doc;},metadata:{fromCache:true}};"
        +"var ref={get:function(){return new Promise(function(){});},onSnapshot:function(a,b){var next=typeof a==='function'?a:b;setTimeout(function(){next(snap);},0);return function(){};}};"
        +"db={collection:function(){return {doc:function(){return {collection:function(){return {doc:function(){return ref;}};}};}};}};"
        +"auth={currentUser:{uid:'probe-uid'}};"
        +"Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});"
        +"_qqqExecEnsureLive();window.__probeRestore();return window._qqqExecUnsub?'OK':'the listener did not attach';"
        +"}catch(e){window.__probeRestore();return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      await sleep(150);
      w.eval("window._qqqExecUnsub=null;window._qqqExecLastRenderAt=0;if(typeof qbFreshTick==='function')qbFreshTick();renderApp();");
      return rc;
    }
    if(cfg.tick){
      w.__qbNowMs=cfg.tickTo;w._qqqExecLastRenderAt=0;
      return w.eval("(function(){try{qbFreshTick();return 'OK';}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    }
    if(cfg.fetch){
      var pinTb0=null;
      if(cfg.pin){
        // let renderApp's own pins (rAF, 400 ms, fonts.ready) all run first: only the chip's refresh may re-pin after the read
        try{var fr0=D().fonts;if(fr0&&fr0.ready)await Promise.race([fr0.ready,sleep(5000)]);}catch(e){}
        await sleep(700);
        await settleTopbar();
        var tb0=D().querySelector('#app .topbar');pinTb0=tb0?tb0.offsetHeight:null;
        // Measured in the same turn as the read, right after the page's own handler (the next callback on
        // the same promise), scrolled 600 px with layout forced. Nothing else can run in between: on a busy
        // machine headless Chrome delivers the phone resize event and renderApp's first-frame pin late, and
        // either one landing after the read re-pinned the strip and hid a chip that does not (review 6).
        w.__probeMeasurePin=function(){
          var d=D(),tb=d.querySelector('#app .topbar'),sb=tb&&tb.nextElementSibling,ct=d.querySelector('#app .content'),sp=d.createElement('div');
          sp.style.height='3000px';if(ct)ct.appendChild(sp);
          w.scrollTo(0,600);
          var pin={tbH0:pinTb0,scrollY:Math.round(w.scrollY)};
          if(tb&&sb){var tr=tb.getBoundingClientRect(),sr=sb.getBoundingClientRect();
            pin.tbH1=tb.offsetHeight;pin.tbBottom=Math.round(tr.bottom);pin.subTop=Math.round(sr.top);pin.subStyleTop=sb.style.top;pin.subPos=sb.style.position;}
          w.scrollTo(0,0);sp.remove();
          return pin;
        };
      }
      w.__probeFetchJson=JSON.stringify(cfg.fetch);w.__qbNowMs=cfg.tickTo;w.__probePinNow=!!cfg.pin;
      var res=w.eval("(function(){var sd=db,sa=auth;window.__probeRestore=function(){db=sd;auth=sa;};try{"
        +"var doc=JSON.parse(window.__probeFetchJson),snap={exists:true,data:function(){return doc;},metadata:{fromCache:false}};"
        +"var got=Promise.resolve(snap),ref={get:function(){return got;},onSnapshot:function(){return function(){};}};"
        +"db={collection:function(){return {doc:function(){return {collection:function(){return {doc:function(){return ref;}};}};}};}};"
        +"auth={currentUser:{uid:'probe-uid'}};window._qqqExecLoading=false;loadQqqExec(null,true);"
        +"if(window.__probePinNow)got.then(function(){try{window.__probePin=window.__probeMeasurePin();}catch(e){window.__probePin={err:String(e)};}});"
        +"return 'OK';"
        +"}catch(e){window.__probeRestore();return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      await sleep(150);
      try{w.__probeRestore();}catch(e){}
      w.__probePinNow=false;
      return res;
    }
    return null;
  }
__TLJS__
__S11JS__
  async function runCase(nm,cfg){
    var r={};
    await setVp(cfg.vp);
    drain();
    try{r.call=seed(cfg);}catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    if(cfg.tick||cfg.fetch||cfg.visread||cfg.cachesnap){try{r.after=await after(cfg);}catch(e){r.after='ERR '+(e&&e.stack?e.stack:e);}await sleep(300);}
    try{Object.assign(r,sample(cfg.tl!==false));}catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
    Object.assign(r,drain());
    out.cases[nm]=r;
  }
  async function interact(){
    var w=W(),d=D(),res={};
    await setVp('laptop');
    drain();
    try{res.seed=seed({vp:'laptop',theme:'dark'});}catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    try{
      // 1. the Retired group (a fold of the shared list) opens and closes, and the choice is kept for this viewer; opened it lists
      // ENGU-Q #335 and the rows add up (the whole list is read open, for the judge to add up against the account's figure)
      var none={getAttribute:function(){return null;}};
      var rb=q('.qbx-side [data-lggrp="retired"]');
      if(rb){rb.click();await sleep(80);}
      var st=null;try{st=w.localStorage.getItem('el_qb_retired_open');}catch(e){}
      res.open={expanded:(q('.qbx-side [data-lggrp="retired"]')||none).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-lggroup="retired"] [data-lgrow]').length,engu:!!q('.qbx-side [data-lggroup="retired"] [data-lgrow="ENGUQ"]'),stored:st,list:listRead()};
      rb=q('.qbx-side [data-lggrp="retired"]');
      if(rb){rb.click();await sleep(80);}
      res.closed={expanded:(q('.qbx-side [data-lggrp="retired"]')||none).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-lggroup="retired"] [data-lgrow]').length};
      // 1b. the Shadow group opens (this doc has no shadow leg, so its note says so), closes, and is remembered
      var sb2=q('.qbx-side [data-lggrp="shadow"]'),sd={};
      var grp=function(k){var l=listRead();return l?l.groups.filter(function(g){return g.key===k;})[0]||null:null;};
      if(sb2){sb2.click();await sleep(80);
        sd.open=grp('shadow');
        try{sd.stored=w.localStorage.getItem('el_qb_shadow_open');}catch(e){}
        var sb3=q('.qbx-side [data-lggrp="shadow"]');if(sb3){sb3.click();await sleep(80);}
        sd.closed=grp('shadow');
        try{sd.stored2=w.localStorage.getItem('el_qb_shadow_open');}catch(e){}}
      res.shadow=sd;
      // 1c. a leg row opens its detail right under it and closes again
      var lr=q('.qbx-side [data-lgrow="NOISE"]'),ld={};
      if(lr){lr.click();await sleep(80);
        var r2=q('.qbx-side [data-lgrow="NOISE"]'),ex=q('.qbx-side [data-qbextra="NOISE"]');
        ld.expanded=r2?r2.getAttribute('aria-expanded'):null;
        ld.detail=ex?(ex.textContent||'').replace(/\\s+/g,' ').trim():null;
        lr=q('.qbx-side [data-lgrow="NOISE"]');if(lr){lr.click();await sleep(80);}
        var r3=q('.qbx-side [data-lgrow="NOISE"]');
        ld.expandedAfter=r3?r3.getAttribute('aria-expanded'):null;
        ld.detailAfter=!!q('.qbx-side [data-qbextra="NOISE"] .qb-leg-detail');}
      res.legrow=ld;
      // 1d. the note toggle beside a run number shows that leg's note under its row and leaves the row's detail shut; a second tap hides it
      var ib=q('.qbx-side [data-qbleginfo="NOISE"]'),inf={};
      if(ib){
        var ex0=q('.qbx-side [data-qbextra="NOISE"]');
        inf.titleBefore=ib.getAttribute('title');inf.noteBefore=ex0?(ex0.textContent||''):'';
        ib.click();await sleep(80);
        var rw1=q('.qbx-side [data-lgrow="NOISE"]'),ex1=q('.qbx-side [data-qbextra="NOISE"]'),ib1=q('.qbx-side [data-qbleginfo="NOISE"]');
        inf.expanded=rw1?rw1.getAttribute('aria-expanded'):null;
        inf.note=ex1?(ex1.textContent||''):'';
        inf.detail=!!q('.qbx-side [data-qbextra="NOISE"] .qb-leg-detail');
        inf.title=ib1?ib1.getAttribute('title'):null;
        if(ib1){ib1.click();await sleep(80);}
        var rw2=q('.qbx-side [data-lgrow="NOISE"]'),ex2=q('.qbx-side [data-qbextra="NOISE"]');
        inf.expandedAfter=rw2?rw2.getAttribute('aria-expanded'):null;
        inf.noteAfter=ex2?(ex2.textContent||''):'';
      }
      res.info=inf;
      // 2. a scrub writes the hero and leaving puts it back (no re-render)
      var sv=q('#qb-lg-chart svg'),sc={};
      if(sv){
        var rc=sv.getBoundingClientRect(),y=rc.top+rc.height/2;
        sc.big0=txt('#qb-hero-value');sc.today0=txt('#qb-hero-today');
        sv.dispatchEvent(new w.PointerEvent('pointermove',{clientX:rc.left+2,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigStart=txt('#qb-hero-value');sc.todayStart=txt('#qb-hero-today');sc.held=!!w._qbChartHoverActive;
        sc.sameSvg=q('#qb-lg-chart svg')===sv;
        sv.dispatchEvent(new w.PointerEvent('pointermove',{clientX:rc.right-1,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigEnd=txt('#qb-hero-value');sc.rangeEnd=txt('#qb-hero-range');
        sv.dispatchEvent(new w.PointerEvent('pointerleave',{clientX:rc.right+5,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigAfter=txt('#qb-hero-value');sc.todayAfter=txt('#qb-hero-today');sc.heldAfter=!!w._qbChartHoverActive;
      }
      res.scrub=sc;
      // 3. a legend switch is remembered for this viewer
      var lb=q('#qb-lg-chart .lg-legend [data-lgline="0"]'),lg={};
      if(lb){lb.click();await sleep(60);
        var lb2=q('#qb-lg-chart .lg-legend [data-lgline="0"]');lg.off=!!(lb2&&lb2.classList.contains('off'));
        try{lg.stored=w.localStorage.getItem('el_lg_lines_webull');}catch(e){}}
      res.legend=lg;
      // 4. the More stats fold (LEDGER step 6) opens with the shared groups + Account, closes, and is remembered
      var mb=q('[data-lgmore="qb"]'),fo={};
      if(mb){
        fo.before=mb.getAttribute('aria-expanded');mb.click();await sleep(80);
        var mb2=q('[data-lgmore="qb"]');fo.open=mb2?mb2.getAttribute('aria-expanded'):null;
        var pn=q('#qb-more');fo.panel=pn?(pn.hasAttribute('hidden')?'hidden':'shown'):null;
        fo.groups=[].map.call(d.querySelectorAll('#qb-more [data-lgmsgroup]'),function(g){return g.getAttribute('data-lgmsgroup');});
        fo.acct=[].map.call(d.querySelectorAll('#qb-more [data-lgmsgroup="Account"] .lg-ms-row .l'),function(e){return (e.textContent||'').trim();});
        fo.vals=moreRead().vals;
        fo.bad=((pn&&pn.innerText)||'').match(/NaN|undefined|\\[object Object\\]/g)||[];
        try{fo.stored=w.localStorage.getItem('el_qb_morestats_open');}catch(e){}
        if(mb2){mb2.click();await sleep(80);}
        var mb3=q('[data-lgmore="qb"]');fo.closed=mb3?mb3.getAttribute('aria-expanded'):null;
        var pn3=q('#qb-more');fo.panelAfter=pn3?(pn3.hasAttribute('hidden')?'hidden':'shown'):null;
        try{fo.stored2=w.localStorage.getItem('el_qb_morestats_open');}catch(e){}
      }
      res.fold=fo;
      // 5. the shared calendar (LEDGER step 7): its day taps, month arrows, fold and what a reload finds
      var ca={};
      ca.start=calRead();
      var spy=[],proto=w.Element.prototype,so=proto.scrollIntoView;
      proto.scrollIntoView=function(o){spy.push({day:this.getAttribute?this.getAttribute('data-qbday'):null,id:this.id||null,opt:o||null});};
      try{
        var db=q('[data-lgcalday="2026-10-02"]');
        if(db){db.click();await sleep(60);var rr=q('[data-qbday="2026-10-02"]');ca.tapOct=spy.slice();ca.flashOct=!!(rr&&rr.classList.contains('lg-flash'));
          var all=d.querySelectorAll('[data-qbday="2026-10-02"]');ca.octRows=all.length;ca.octFirstIsTapped=!!(rr&&all[0]===rr);}
        var eb=q('[data-lgcal="qb"][data-lgcalmo="-1"]');
        if(eb){eb.click();await sleep(80);}
        ca.sept=calRead();
        try{ca.storedMonth=w.localStorage.getItem('el_qb_cal_month');}catch(e){}
        ca.memMonth=w._qqqCalMonth||null;
        spy.length=0;
        var d2=q('[data-lgcalday="2026-09-23"]');
        if(d2){d2.click();await sleep(60);ca.tapSep=spy.slice();}
        var fb=q('[data-lgcalfold="qb"]');
        if(fb){fb.click();await sleep(80);}
        ca.closed=calRead();
        try{ca.storedOpen=w.localStorage.getItem('el_qb_cal_open');}catch(e){}
        // a reload: nothing in memory, the stored choices kept
        w.eval("window._qqqCalMonth=null;window._qbCalOpen=null;renderApp();");await sleep(120);
        ca.reload=calRead();
        fb=q('[data-lgcalfold="qb"]');
        if(fb){fb.click();await sleep(80);}
        ca.reopen=calRead();
        try{ca.storedOpen2=w.localStorage.getItem('el_qb_cal_open');}catch(e){}
        var lb=q('[data-lgcal="qb"][data-lgcalmo="1"]');
        if(lb){lb.click();await sleep(80);}
        ca.oct=calRead();
        // 5b. the trade list shows only its newest rows until SHOW MORE: a tap on a day whose rows are not on the page yet draws every
        // row first, then scrolls to that day's newest trade
        w.eval("window._qeTradesShown=1;renderApp();");await sleep(120);
        var fd=q('[data-lgcal="qb"] button[data-lgcalday]');
        ca.moreDay=fd?fd.getAttribute('data-lgcalday'):null;
        ca.moreRowsBefore=rowsN();
        ca.moreHadRow=!!(ca.moreDay&&q('[data-qbday="'+ca.moreDay+'"]'));
        spy.length=0;
        if(fd){fd.click();await sleep(100);}
        ca.moreSpy=spy.slice();
        ca.moreRowsAfter=rowsN();
        ca.moreHasRow=!!(ca.moreDay&&q('[data-qbday="'+ca.moreDay+'"]'));
        w.eval("window._qeTradesShown=null;renderApp();");await sleep(80);
      }finally{proto.scrollIntoView=so;}
      res.cal=ca;
      // 6. the Table view names every strategy with its run number too (family + run number on every trade row). LEDGER step 8: the shared
      // frame's LIST | TABLE switch replaces the old segmented control
      var tb=q('[data-lgview="table"]'),tv={};
      if(tb){tb.click();await sleep(100);
        tv.legs=[].map.call(d.querySelectorAll('tr[data-lgtrade] .qb-trade-leg'),function(e){return (e.textContent||'').trim();});
        tv.days=[].map.call(d.querySelectorAll('tr[data-lgtrade]'),function(e){return e.getAttribute('data-qbday');});
        var lb2=q('[data-lgview="list"]');
        if(lb2){lb2.click();await sleep(100);}}
      res.table=tv;
      // 7. LEDGER step 12: the list's Filters row opens in place, is remembered, closes
      try{res.filt=await filtCycle();}catch(e){res.filt={threw:String(e&&e.stack?e.stack:e)};}
    }catch(e){res.threw=String(e&&e.stack?e.stack:e);}
    await sleep(60);
    res.errs=drain();
    out.inter=res;
  }
  async function boot(){
    var w=W();
    try{
      out.VERSION=out.VERSION||w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.renderApp=typeof w.renderApp;
      sink=hook(w);
    }catch(e){out.err=String(e);finish('hookfail');return false;}
    if(out.renderApp!=='function'){finish('noboot');return false;}
    out.authSettled=await waitFor(function(){return !!D().getElementById('tsu');},12000);
    try{w.eval('renderAuth=function(){};');}catch(e){out.notes.push('renderAuth stub: '+e);}
    await sleep(200);
    drain();
    overlays();
    // the page's own inline styles (<html>, <body>, #app) before anything ran: every seed puts them back, so a panel that leaves room behind
    // (a padding, a margin) in one run is measured against the pristine page in the next
    try{var d1=D();PS0=[d1.documentElement.getAttribute('style'),d1.body.getAttribute('style'),(d1.getElementById('app')||d1.body).getAttribute('style')];}catch(e){PS0=null;}
    return true;
  }
  fr.addEventListener('load',function(){
    setTimeout(async function(){
      if(phase===0){
        phase=1;
        if(!(await boot()))return;
        for(var i=0;i<CASES.length;i++)await runCase(CASES[i][0],CASES[i][1]);
        try{await interact();}catch(e){out.inter={threw:String(e&&e.stack?e.stack:e)};}
        // LEDGER step 11: the own folds, the list's phone fold, storage that throws, every fold open at six widths
        try{out.s11=await s11Run();}catch(e){out.s11={threw:String(e&&e.stack?e.stack:e)};}
        // the trade list on the shared frame (LEDGER step 8): each run seeds its own page
        out.tl={};
        for(var tn=0;tn<TLS.length;tn++){
          try{out.tl[TLS[tn].name]=await runTl(TLS[tn]);}catch(e){out.tl[TLS[tn].name]={threw:String(e&&e.stack?e.stack:e)};}
        }
        out.stats={};
        for(var k=0;k<STATS.length;k++){
          var S=STATS[k];
          await runCase('__st'+k,{vp:S.vp,theme:S.theme,fix:S.doc,range:S.range,todayNY:S.today,calMonth:S.calMonth,moreOpen:S.more,calOpen:S.calOpen,folds:S.folds,nowMs:S.nowMs});
          out.stats[S.name]=out.cases['__st'+k];delete out.cases['__st'+k];
        }
        try{W().eval("ledgerTodayNY=window.__probeLTN||ledgerTodayNY;");}catch(e){}
        out.vars={};
        for(var j=0;j<VARS.length;j++){
          var V=VARS[j];
          await runCase('__var'+j,{vp:V.vp||'laptop',theme:V.theme||'dark',fix:V.doc,nowMs:V.renderMs||V.nowMs,openLeg:'NOISE',systemOpen:V.systemOpen,
            liveErr:V.liveErr,prev:V.prev,prevCache:V.prevCache,tab:V.tab,checkedMs:V.checkedMs,tick:V.tick,tickTo:V.nowMs,fetch:V.fetch,
            offline:V.offline,missing:V.missing,unloaded:V.unloaded,pin:V.pin,visread:V.visread,cachesnap:V.cachesnap,tl:false});
          out.vars[V.name]=out.cases['__var'+j];delete out.cases['__var'+j];
        }
        try{W().eval('delete navigator.onLine');}catch(e){}
        try{var ap0=JSON.parse(W().localStorage.getItem('augurPrefs')||'{}');ap0.qqqSystemOpen=0;W().localStorage.setItem('augurPrefs',JSON.stringify(ap0));}catch(e){}
        fr.src='../index.html?oldboards=1';     // a second page load: the flag changes nothing
        return;
      }
      if(phase===1){
        phase=2;
        if(!(await boot()))return;
        // ?oldboards=1 no longer changes anything: this page must be the plain laptop / MONO board
        await runCase('flagpage',{vp:'laptop',theme:'mono'});
        finish('done');
      }
    },2500);
  });
})();
</script>
</body></html>
"""


TL_JS = r"""  // ── LEDGER step 8: this board's trade list is the shared frame (ledgerTradeListHtml). tlRead = everything the judge needs from one
  // drawn frame; SCEN = what a viewer does to it (chips, search, sheet, paging, LIST | TABLE, CSV, a calendar tap, the glyph); runTl runs one. ──
  function tx2(e){return e?(e.textContent||'').replace(/\s+/g,' ').trim():null;}
  function uniq(a){var s={},o=[];a.forEach(function(x){if(!s[x]){s[x]=1;o.push(x);}});return o;}
  function rowsN(){var d=D(),a=d.querySelectorAll('[data-lgtrade]');return a.length||d.querySelectorAll('[data-qbtraderow]').length;}
  function tlKeys(){return [].map.call(D().querySelectorAll('[data-lgtrade]'),function(e){return e.getAttribute('data-lgtrade');});}
  // the cells of a row that are drawn (not display:none), by their column key: a phone row keeps five
  function visCells(row){
    var w=W(),out=[];
    [].forEach.call(row.children,function(c){
      if(w.getComputedStyle(c).display==='none')return;
      var m=/lg-c-([a-z]+)/.exec(c.className||'');out.push(m?m[1]:'?');});
    return out;
  }
  // every cell of a row by its column key (the common eight, then this board's own in the table)
  // (a cell's text without the row's caveat word, which is read on its own: cav)
  function cellMap(row){
    var m={};
    [].forEach.call(row.children,function(c){var k=/lg-c-([a-z]+)/.exec(c.className||'');if(!k)return;
      if(c.querySelector('.qbx-cav')){var cl=c.cloneNode(true);[].forEach.call(cl.querySelectorAll('.qbx-cav'),function(x){x.parentNode.removeChild(x);});m[k[1]]=tx2(cl);}
      else m[k[1]]=tx2(c);});
    return m;
  }
  // the row's caveat word: its data-qbcav, its text, the cell it sits in
  function cavRead(r){var e=r.querySelector('.qbx-cav');if(!e)return null;var c=e.closest('[class*="lg-c-"]'),k=c?/lg-c-([a-z]+)/.exec(c.className||''):null;
    return {w:e.getAttribute('data-qbcav'),t:tx2(e),cell:k?k[1]:null,n:r.querySelectorAll('.qbx-cav').length};}
  function tlRead(){
    var d=D(),w=W(),fr=q('[data-lglist-frame="wb"]'),t={frames:d.querySelectorAll('[data-lglist-frame]').length,
      oldSeg:d.querySelectorAll('[data-qbseg="tradesview"]').length,oldRows:d.querySelectorAll('[data-qbtraderow],[data-qetraderow]').length};
    if(!fr)return t;
    t.mode=fr.getAttribute('data-lgmode');
    t.count=tx2(fr.querySelector('[data-lgcount]'));
    t.chips=[].map.call(fr.querySelectorAll('[data-lgchip]'),function(b){return {k:b.getAttribute('data-lgchip'),t:tx2(b),on:b.classList.contains('active'),p:b.getAttribute('aria-pressed')};});
    t.views=[].map.call(fr.querySelectorAll('[data-lgview]'),function(b){return {k:b.getAttribute('data-lgview'),on:b.classList.contains('active'),p:b.getAttribute('aria-pressed')};});
    var inp=fr.querySelector('input[data-lgsearch]');t.search=inp?{id:inp.id,val:inp.value}:null;
    t.csv=!!fr.querySelector('[data-qeexportcsv]');
    t.more=tx2(d.querySelector('[data-qeshowmore]'));
    t.empty=tx2(fr.querySelector('.lg-tl-empty'));
    t.heads=[].map.call(fr.querySelectorAll('thead th'),tx2);
    var days=[],cur=null;
    if(t.mode==='table'){
      [].forEach.call(fr.querySelectorAll('tbody tr'),function(tr){
        if(tr.hasAttribute('data-lgday')){cur={day:tr.getAttribute('data-lgday'),hdr:tr,rows:[]};days.push(cur);}
        else if(tr.hasAttribute('data-lgtrade')&&cur)cur.rows.push(tr);});
    }else{
      [].forEach.call(fr.querySelectorAll('.lg-tl-day[data-lgday]'),function(g){days.push({day:g.getAttribute('data-lgday'),hdr:g,rows:[].slice.call(g.querySelectorAll('[data-lgtrade]'))});});
    }
    t.days=days.map(function(g){
      var net=g.hdr.querySelector('.lg-tl-daynet'),meta=g.hdr.querySelector('.lg-tl-daymeta'),lbl=g.hdr.querySelector('.lg-tl-daylbl');
      return {day:g.day,label:tx2(lbl),net:tx2(net),netCls:net?net.className:null,meta:tx2(meta),
        rows:g.rows.map(function(r){
          var gl=r.querySelector('[data-qbchartkey]');
          return {id:r.getAttribute('data-lgtrade'),qbday:r.getAttribute('data-qbday'),cells:cellMap(r),legSpans:r.querySelectorAll('.qb-trade-leg').length,
            cav:cavRead(r),glyph:gl?gl.getAttribute('data-qbchartkey'):null};})};
    });
    var all=[].slice.call(fr.querySelectorAll('[data-lgtrade]')),first=all[0],last=all[all.length-1];
    t.vis=first?visCells(first):null;t.visLast=last?visCells(last):null;
    var cavs=[].slice.call(fr.querySelectorAll('.qbx-cav'));
    t.cavN=cavs.length;t.cavShown=cavs.filter(function(e){return w.getComputedStyle(e).display!=='none';}).length;
    var col=function(sel){return uniq([].map.call(fr.querySelectorAll(sel),function(e){return w.getComputedStyle(e).color;}));};
    t.colors={net:col('.lg-tl-daynet'),pnl:col('.lg-c-pnl span'),side:col('.lg-side')};
    t.noRows=all.length?null:tx2(fr);
    var sh=q('.qb-shell'),hs=q('.qbx-history'),fb=fr.getBoundingClientRect(),sb=sh?sh.getBoundingClientRect():null,hb=hs?hs.getBoundingClientRect():null;
    t.geo={frameTop:sb?Math.round(fb.top-sb.top):null,histTop:(sb&&hb)?Math.round(hb.top-sb.top):null,vh:w.innerHeight,docSW:d.documentElement.scrollWidth,iw:w.innerWidth};
    return t;
  }
  // the page and the rows against the viewport: the page never wider than the window, no row wider than its box, a strategy name never cut
  function wRead(){
    var d=D(),w=W(),f=q('[data-lglist-frame="wb"]'),rows=[].slice.call(d.querySelectorAll('[data-lgtrade]')),over=0,clip=0,worst=0;
    rows.forEach(function(r){
      var o=r.scrollWidth-r.clientWidth;if(o>1){over++;if(o>worst)worst=o;}
      var s=r.querySelector('.lg-c-sym');if(s&&s.scrollWidth>s.clientWidth+1)clip++;});
    var cavs=[].slice.call(d.querySelectorAll('.qbx-cav'));
    return {iw:w.innerWidth,frameW:f?Math.round(f.getBoundingClientRect().width):null,docSW:d.documentElement.scrollWidth,bodySW:d.body.scrollWidth,mode:f?f.getAttribute('data-lgmode'):null,rows:rows.length,
      rowsOver:over,worst:worst,symClip:clip,cav:[cavs.length,cavs.filter(function(e){return w.getComputedStyle(e).display!=='none';}).length],
      wide:d.documentElement.scrollWidth>w.innerWidth?offenders(d):[]};
  }
  function tlSimple(){
    var d=D(),fr=q('[data-lglist-frame="wb"]');
    return {mode:fr?fr.getAttribute('data-lgmode'):null,rows:tlKeys(),count:tx2(fr&&fr.querySelector('[data-lgcount]')),
      active:[].map.call(d.querySelectorAll('[data-lgchip].active'),function(b){return b.getAttribute('data-lgchip');}),
      more:tx2(d.querySelector('[data-qeshowmore]')),empty:tx2(fr&&fr.querySelector('.lg-tl-empty')),query:(q('#wb-search')||{}).value};
  }
  // typing into the search box the way a viewer does: focus it, set the text and the caret, fire input; then read where focus and caret ended up
  async function typeIn(text){
    var w=W(),inp=q('#wb-search');
    inp.focus();inp.value=text;inp.setSelectionRange(text.length,text.length);
    inp.dispatchEvent(new w.Event('input',{bubbles:true}));await sleep(110);
    var i2=q('#wb-search');
    return {focus:D().activeElement===i2,val:i2.value,sel:[i2.selectionStart,i2.selectionEnd]};
  }
  async function clickChip(k){var b=q('[data-lgchip="'+k+'"]');if(!b)return null;b.click();await sleep(100);return tlRead();}
  // ── LEDGER step 9: a row opens TRADING-LOG's shared trade panel (id wb) in place of the board's own sheet ──
  var PNQ='.lg-panel[data-lgpanel="wb"]';
  // a headless page may never produce the frames a CSS animation needs: finish the slide-in so the panel is measured where it ends up
  function pFinish(){try{D().getAnimations().forEach(function(a){try{a.finish();}catch(e1){}});}catch(e){}}
  function tx3(e){return e?(e.innerText||'').replace(/\s+/g,' ').trim():null;}
  function panelNow(){pFinish();var p=q(PNQ);if(!p)return null;
    return {trade:p.getAttribute('data-lgpanel-trade'),sym:tx2(p.querySelector('[data-lgpanel-sym]')),side:tx2(p.querySelector('[data-lgpanel-side]')),
      net:tx2(p.querySelector('[data-lgpanel-net]')),when:tx2(p.querySelector('[data-lgpanel-when]'))};}
  async function closePanel(){var b=q('[data-lgpanel-close]');if(b){b.click();await sleep(100);}return !q('.lg-panel,.lg-panel-layer');}
  function pgeo(){var d=D(),de=d.documentElement;
    return {sw:de.scrollWidth,cw:de.clientWidth,sh:de.scrollHeight,nodes:d.querySelectorAll('.lg-panel,.lg-panel-layer').length,
      kids:[].map.call(d.body.children,function(e){return e.tagName+'#'+e.id;}).join('|')};}
  // every colour the panel draws (text, background, borders, outline, svg fill and stroke) must be a grey: MONO has no hue
  function pHue(root){
    var cv=document.createElement('canvas');cv.width=1;cv.height=1;var cx=cv.getContext('2d');
    function rgba(css){try{cx.clearRect(0,0,1,1);cx.fillStyle='#000';cx.fillStyle=css;cx.fillRect(0,0,1,1);var a=cx.getImageData(0,0,1,1).data;return [a[0],a[1],a[2],a[3]];}catch(e){return null;}}
    var w=W(),els=[root].concat([].slice.call(root.querySelectorAll('*'))),n=0,bad=[];
    var lay=root.closest?root.closest('.lg-panel-layer'):null;if(lay)els.push(lay);
    els.forEach(function(e){
      var cs=w.getComputedStyle(e),props=[['color',cs.color],['background',cs.backgroundColor]];
      ['Top','Right','Bottom','Left'].forEach(function(s){
        if(cs['border'+s+'Style']!=='none'&&parseFloat(cs['border'+s+'Width'])>0)props.push(['border-'+s.toLowerCase(),cs['border'+s+'Color']]);});
      if(cs.outlineStyle!=='none'&&parseFloat(cs.outlineWidth)>0)props.push(['outline',cs.outlineColor]);
      if(e instanceof w.SVGElement){
        if(cs.fill&&cs.fill!=='none')props.push(['fill',cs.fill]);
        if(cs.stroke&&cs.stroke!=='none')props.push(['stroke',cs.stroke]);}
      props.forEach(function(p){
        var c=rgba(p[1]);n++;
        if(!c||c[3]<8)return;
        if(Math.max(c[0],c[1],c[2])-Math.min(c[0],c[1],c[2])>16)
          bad.push((e.tagName||'').toLowerCase()+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(' ')[0]:'')+' '+p[0]+'='+p[1]);
      });
    });
    return {checked:n,bad:bad.slice(0,6)};
  }
  // what the open panel says and where it is: header, slots in order, the numbers rows by label, the notes, the buttons, the chart
  function pRead(hue){
    pFinish();
    var d=D(),w=W(),p=q(PNQ);if(!p)return null;
    var r=p.getBoundingClientRect(),b=p.querySelector('[data-lgpanel-body]'),nel=p.querySelector('[data-lgpanel-net]'),o={};
    o.trade=p.getAttribute('data-lgpanel-trade');o.mode=p.getAttribute('data-lgpanel-mode');
    o.rect={l:Math.round(r.left),t:Math.round(r.top),r:Math.round(r.right),b:Math.round(r.bottom),w:Math.round(r.width),h:Math.round(r.height)};
    o.vw=w.innerWidth;o.vh=w.innerHeight;o.role=p.getAttribute('role');o.modal=p.getAttribute('aria-modal');
    o.sym=tx2(p.querySelector('[data-lgpanel-sym]'));o.side=tx2(p.querySelector('[data-lgpanel-side]'));o.when=tx2(p.querySelector('[data-lgpanel-when]'));
    o.net=tx2(nel);o.netCls=nel?nel.className:'';o.sub=tx2(p.querySelector('[data-lgpanel-sub]'));
    o.chips=[].map.call(p.querySelectorAll('.qbx-pn-chip'),tx2);
    o.slots=[].map.call(p.querySelectorAll('[data-lgpanel-slot]'),function(e){return e.getAttribute('data-lgpanel-slot');});
    o.rows={};o.rowCls={};
    [].forEach.call(p.querySelectorAll('.lg-panel-row'),function(row){
      var dt=row.querySelector('.lg-panel-dt'),dd=row.querySelector('.lg-panel-dd'),k=tx2(dt);o.rows[k]=tx2(dd);o.rowCls[k]=dd?dd.className:'';});
    var ns=p.querySelector('[data-lgpanel-slot="notes"]'),as=p.querySelector('[data-lgpanel-slot="actions"]'),cs=p.querySelector('[data-lgpanel-slot="chart"]'),nus=p.querySelector('[data-lgpanel-slot="numbers"]');
    o.notes=tx3(ns);o.numbersText=tx3(nus);o.editable=p.querySelectorAll('textarea,input,select').length;
    o.buttons=[].map.call(as?as.querySelectorAll('button'):[],tx2);o.delBtn=as?as.querySelectorAll('button.del').length:0;o.actionsText=tx2(as);
    o.chartText=tx2(cs);o.chartDrawn=!!(cs&&cs.querySelector('.qb-sheet-candles-svg svg'));o.expand=!!(cs&&cs.querySelector('[data-qbcandlesexpand]'));
    // KEEPS CHECKLIST: every candle layer's own mark (data-mk, its hover title, the shape element it draws), the legend rows under the chart, what the stub
    // fed, and the FILLS vs BACKTEST line of the numbers slot (its data-qbpfp and its words)
    o.marks=cs?[].map.call(cs.querySelectorAll('.qb-sheet-candles-svg svg [data-mk]'),function(g){
      var ti=g.querySelector('title'),sh=null;
      [].forEach.call(g.children,function(c){if(!sh&&c.tagName.toLowerCase()!=='title')sh=c.tagName.toLowerCase();});
      return {k:g.getAttribute('data-mk'),t:ti?(ti.textContent||'').trim():null,sh:sh};}):[];
    o.legend=tx2(cs?cs.querySelector('.qb-candle-legend'):null);
    o.fed=w.__stubFed||null;
    o.fpHead=(function(){var e=p.querySelector('[data-qbpfp]');return e?[e.getAttribute('data-qbpfp'),tx2(e)]:null;})();
    o.inApp=!!p.closest('#app');o.focusIn=p.contains(d.activeElement);o.bodyWide=b?b.scrollWidth>b.clientWidth+1:null;
    o.oldSheet=!!q('.qb-sheet');o.g=pgeo();
    if(hue)o.hue=pHue(p);
    return o;
  }
  async function pStep(res,name,fn){var st={};try{await fn(st);}catch(e){st.threw=String(e&&e.stack?e.stack:e);}res.steps[name]=st;}
  function pRowEl(key){return [].filter.call(D().querySelectorAll('[data-lgtrade]'),function(e){return e.getAttribute('data-lgtrade')===key;})[0]||null;}
  // a tap on the row of one trade (its strategy cell), then a moment for the panel to draw
  async function pOpen(key){var row=pRowEl(key);if(!row)return false;(row.querySelector('.lg-c-sym')||row).click();await sleep(170);return true;}
  async function pEsc(){D().dispatchEvent(new (W().KeyboardEvent)('keydown',{key:'Escape',bubbles:true,cancelable:true}));await sleep(90);return !q('.lg-panel,.lg-panel-layer');}
  async function pShut(){if(q('.lg-panel,.lg-panel-layer'))await pEsc();if(q('.lg-panel,.lg-panel-layer'))await closePanel();return !q('.lg-panel,.lg-panel-layer');}
  // candles for any trade without the network: bars for the trade's day with the entry and exit marked, and the box's marks (the four-layer legend)
  function stubBarsFn(x){
    var et=String(x._et||'').slice(0,16),xt=String(x._xt2||x._et||'').slice(0,16),day=et.slice(0,10);
    function mins(s){return (+s.slice(11,13))*60+(+s.slice(14,16));}
    var bars=[],i=0,p=750,m0=9*60+30,ep0=Date.UTC(+day.slice(0,4),+day.slice(5,7)-1,+day.slice(8,10),13,30,0)/1000;
    for(var m=m0;m<=15*60+55;m+=5,i++){
      var o=p+Math.sin(i/6)*0.8,c=o+Math.cos(i/4)*0.5;
      bars.push({t:day+' '+('0'+Math.floor(m/60)).slice(-2)+':'+('0'+(m%60)).slice(-2),o:o,h:Math.max(o,c)+0.2,l:Math.min(o,c)-0.2,c:c,v:100,ep:ep0+i*300});p=c;}
    var ei=Math.floor((mins(et)-m0)/5),xi=xt.slice(0,10)===day?Math.floor((mins(xt)-m0)/5):-1;
    if(ei<0||ei>=bars.length)ei=null;
    if(xi<0||xi>=bars.length)xi=null;
    var px=function(k){return k==null?750:bars[k].c;};
    var net=!!window.__stubNetted,oc=(window.__pnOutcome||{})[x._no]||null;
    window.__stubFed={entry:ei!=null,exit:xi!=null,netted:net,outcome:net?null:oc};
    return Promise.resolve({bars:bars,entry_idx:ei,exit_idx:xi,tf:'5m',src:'box',asof:'15:55',meta:{},
      marks:{side:String(x._side||'long'),tf:'5m',signal:{t:et,rule:'recorded'},book_in:{t:et,px:px(ei)},bt_in:{t:et,px:px(ei)},
        wb_in:[{t:et,px:px(ei)+0.02,ok:true,sent:!net,outcome:net?'NETTED':'FILLED'}],book_out:xi==null?null:{t:xt,px:px(xi)},
        bt_out:xi==null?null:{t:xt,px:px(xi)-0.01},
        wb_out:xi==null?[]:[(function(oc){
          if(net)return {t:xt,px:px(xi)+0.03,ok:true,sent:false,outcome:'NETTED'};
          if(oc==='REFUSED')return {t:xt,px:null,ok:false,sent:true,outcome:'REFUSED',side:'SELL',why:'probe: refused by Webull'};
          if(oc==='NETTED')return {t:xt,px:px(xi),ok:true,sent:false,outcome:'NETTED',side:'SELL',why:'flatten: crossed internally against ORB'};
          if(oc==='UNKNOWN')return {t:xt,px:null,ok:false,sent:true,outcome:'UNKNOWN',side:'SELL',why:'hard timeout: no answer after 25s'};
          return {t:xt,px:px(xi)+0.03,ok:true,sent:true,outcome:'FILLED'};})(oc)],lines:[]}});
  }
  function pStubOn(){
    var w=W();
    w.eval('window.__origBars=window.__origBars||window._qqqBarsForTrade;window._qqqBarsForTrade=('+stubBarsFn.toString()+');'
      +'window.__opened=[];window.__origOpen=window.__origOpen||window._openTradeCandles;'
      +'window._openTradeCandles=function(x,b,c){window.__opened.push({no:x._no,label:x._label,n:(c&&c.all)?c.all().length:null,has:(c&&c.all)?c.all().some(function(q){return q._no===x._no;}):null});};');
  }
  function pStubOff(){
    W().eval('if(window.__origBars){window._qqqBarsForTrade=window.__origBars;window.__origBars=null;}if(window.__origOpen){window._openTradeCandles=window.__origOpen;window.__origOpen=null;}');
  }
  async function setVpWH(wd,ht){
    fr.style.width=wd+'px';fr.style.height=ht+'px';
    await waitFor(function(){return W().innerWidth===wd;},2000);
    await sleep(60);
  }
  // the CSV button with the download stubbed: what would have been saved
  function stubDownload(){var w=W();w.eval('window.__csvs=[];if(!window.__origDownload)window.__origDownload=_libDownload;_libDownload=function(n,t){window.__csvs.push({n:n,t:t});};');}
  function unstubDownload(){W().eval('if(window.__origDownload){_libDownload=window.__origDownload;window.__origDownload=null;}');}
  async function csvNow(){var w=W();w.__csvs.length=0;var b=q('[data-qeexportcsv]');if(b)b.click();await sleep(60);return w.__csvs.length?{n:w.__csvs[0].n,t:w.__csvs[0].t}:null;}
  var SCEN={};
  // the default doc on a laptop: chips, search and focus, the sheet after a filter and after a search, SHOW MORE, LIST | TABLE, the CSV, a calendar tap past a chip, the glyph
  SCEN.main=async function(T,res){
    var w=W();
    res.start=tlRead();
    res.chips={};
    var keys=[].map.call(D().querySelectorAll('[data-lgchip]'),function(b){return b.getAttribute('data-lgchip');});
    for(var i=0;i<keys.length;i++)res.chips[keys[i]]=await clickChip(keys[i]);
    await clickChip('ALL');
    // a search typed a character at a time keeps its focus and its caret across the redraws
    res.typed=[await typeIn('o'),await typeIn('or'),await typeIn('orb')];
    res.search=tlRead();
    await typeIn('noise');res.searchNoise=tlRead();
    await typeIn('');res.cleared=tlSimple();
    // the viewer leaves the box (the phone keyboard's Done is a blur outside any redraw): the next redraw must not bring it back; typing again keeps it
    var bx=q('#wb-search');bx.focus();await sleep(30);bx.blur();await sleep(60);
    w.eval('renderApp();');await sleep(120);
    res.doneKept={focus:D().activeElement===q('#wb-search'),hold:!!w._qbSearchHold};
    res.retyped=await typeIn('o');await typeIn('');
    // the trade panel opens for the trade that was tapped: after a chip changed the rows, and after a search then clear
    await clickChip('SHORT');
    var p1=D().querySelectorAll('[data-lgtrade]')[1];
    res.sheet1={key:p1.getAttribute('data-lgtrade')};
    p1.click();await sleep(150);res.sheet1.now=panelNow();res.sheet1.closed=await closePanel();
    await clickChip('ALL');
    await typeIn('noise');await typeIn('');
    var p2=D().querySelectorAll('[data-lgtrade]')[2];
    res.sheet2={key:p2.getAttribute('data-lgtrade')};
    p2.click();await sleep(150);res.sheet2.now=panelNow();
    // a redraw while it is open (a new snapshot) leaves it on the same trade; Escape closes it
    w.eval('renderApp();');await sleep(120);res.sheet2.afterRender=panelNow();
    D().dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await sleep(120);res.sheet2.escClosed=!q('.lg-panel,.lg-panel-layer');
    // the panel opens from the TABLE too
    q('[data-lgview="table"]').click();await sleep(150);
    var p3=D().querySelectorAll('tr[data-lgtrade]')[4];
    res.sheet3={key:p3.getAttribute('data-lgtrade')};
    p3.click();await sleep(150);res.sheet3.now=panelNow();res.sheet3.closed=await closePanel();
    q('[data-lgview="list"]').click();await sleep(150);
    // the chart glyph opens the candles for its trade and not the panel
    w.eval('window.__opened=null;window.__origOpen=window._openTradeCandles;window._openTradeCandles=function(x,b){window.__opened={no:x._no,label:x._label};};');
    var gl=[].slice.call(D().querySelectorAll('[data-qbchartkey]'))[3];
    res.glyph={key:gl?gl.getAttribute('data-qbchartkey'):null};
    if(gl){gl.click();await sleep(100);}
    res.glyph.opened=w.__opened;res.glyph.sheet=!!q('.qb-sheet,.lg-panel,.lg-panel-layer');
    w.eval('window._openTradeCandles=window.__origOpen;');
    // SHOW MORE: the newest trades first, a day never cut in two, then the rest
    w.eval('window._qeTradesShown='+T.page+';renderApp();');await sleep(150);
    res.page=tlRead();
    stubDownload();res.csvPage=await csvNow();
    var sm=q('[data-qeshowmore]');if(sm){sm.click();await sleep(150);}
    res.afterMore=tlRead();res.shownState=w.eval('window._qeTradesShown');
    w.eval('window._qeTradesShown=50;renderApp();');await sleep(100);
    // LIST | TABLE: switches, is stored for this board, and a page that comes back with nothing in memory finds it
    q('[data-lgview="table"]').click();await sleep(150);
    res.table=tlRead();res.tableStored=w.localStorage.getItem('el_lg_view_wb');
    w.eval('window._qeTradesView=null;renderApp();');await sleep(150);
    res.reloadMode=(q('[data-lglist-frame="wb"]')||{getAttribute:function(){return null;}}).getAttribute('data-lgmode');
    q('[data-lgview="list"]').click();await sleep(150);
    res.listAgain=tlRead();res.listStored=w.localStorage.getItem('el_lg_view_wb');
    // the CSV export: every trade the list matches, today's columns
    res.csvAll=await csvNow();
    await clickChip('LONG');res.csvLong=await csvNow();res.longRows=tlKeys();
    await clickChip('ALL');await typeIn('orb');res.csvOrb=await csvNow();res.orbRows=tlKeys();await typeIn('');
    w.eval("homeRange='1W';renderApp();");await sleep(150);await clickChip('LONG');res.csv1wLong=await csvNow();res.w1LongRows=tlKeys();
    await clickChip('ALL');w.eval("homeRange='ALL';renderApp();");await sleep(150);
    unstubDownload();
    // a calendar tap on a day the chip hides clears the chip and lands on that day
    await clickChip('SHORT');
    var cd=q('[data-lgcal="qb"] [data-lgcalday="2026-10-05"]');
    res.calTap={had:!!cd,rowBefore:!!q('[data-qbday="2026-10-05"]')};
    if(cd){cd.click();await sleep(150);}
    var ts=tlSimple();res.calTap.active=ts.active;res.calTap.rowAfter=!!q('[data-qbday="2026-10-05"]');res.calTap.query=ts.query;res.calTap.rows=ts.rows.length;
    // a search that matches nothing says so, with a way back
    await typeIn('zzzz');res.none=tlSimple();
    var cl=q('[data-qbclear]');if(cl){cl.click();await sleep(110);}
    res.noneCleared=tlSimple();
  };
  // a doc with one $0 trade: WINS and LOSSES leave it out
  SCEN.zero=async function(T,res){
    res.start=tlRead();
    res.wins=await clickChip('WINS');res.losses=await clickChip('LOSSES');res.all=await clickChip('ALL');
  };
  // a doc with a shadow row: the list, the count and the CSV leave it out
  SCEN.shadow=async function(T,res){
    res.start=tlRead();
    stubDownload();res.csv=await csvNow();unstubDownload();
    q('[data-lgview="table"]').click();await sleep(150);
    res.table=tlRead();
  };
  // a trade held over a weekend sits under the day it closed
  SCEN.overnight=async function(T,res){
    res.start=tlRead();
    q('[data-lgview="table"]').click();await sleep(150);
    res.table=tlRead();
  };
  // a phone: five cells a row in the LIST and the TABLE, the flagged-row mark shown, where the list starts, no sideways page
  SCEN.phone=async function(T,res){
    res.list=tlRead();
    q('[data-lgview="table"]').click();await sleep(150);
    res.table=tlRead();
    q('[data-lgview="list"]').click();await sleep(120);
  };
  // the widths: the page and the rows at each width in the LIST, then in the TABLE (one render each: only the CSS answers to the window width)
  SCEN.width=async function(T,res){
    res.list={};res.table={};
    for(var i=0;i<T.widths.length;i++){var a=T.widths[i];await setVpWH(a[0],a[1]);res.list[a[0]]=wRead();}
    q('[data-lgview="table"]').click();await sleep(150);
    for(var j=0;j<T.widths.length;j++){var b=T.widths[j];await setVpWH(b[0],b[1]);res.table[b[0]]=wRead();}
    q('[data-lgview="list"]').click();await sleep(100);
  };
  // LEDGER step 9: the trade panel on a laptop or a phone, in one theme. T.k1 = a trade on the first page (flagged), T.k2 = an older one that a short page
  // leaves out, T.hideChip = a chip that hides k2, T.variety = trades that carry each kind of caveat, T.page = the short page, T.theme = the theme.
  SCEN.panel=async function(T,res){
    var w=W(),mono=T.theme==='mono';
    res.steps={};
    w.__pnOutcome=T.outcomes||{};
    pStubOn();
    await sleep(60);
    res.base=pgeo();
    // 1. a tap on a row opens the panel for that trade; what it says, where it sits, its slots, the chart drawn (the box's candles stubbed)
    await pStep(res,'open',async function(st){
      st.clicked=await pOpen(T.k1);
      st.drew=await waitFor(function(){return !!q(PNQ+' .qb-sheet-candles-svg svg');},6000);
      st.read=pRead(mono);
      // EXPAND (a laptop only) and OPEN CANDLES open the full viewer for this trade, stepping through the list
      w.__opened.length=0;
      var ex=q(PNQ+' [data-qbcandlesexpand]'),oc=q(PNQ+' [data-qbpcandles]');
      st.hasExpand=!!ex;st.hasOpen=!!oc;
      if(ex){ex.click();await sleep(60);}
      st.expandOpened=w.__opened.slice();w.__opened.length=0;
      if(oc){oc.click();await sleep(60);}
      st.openOpened=w.__opened.slice();w.__opened.length=0;
      st.stillOpen=!!q(PNQ);
    });
    // 2. Esc closes it; the page is exactly as it was before the first open
    await pStep(res,'esc',async function(st){
      st.closed=await pEsc();st.g=pgeo();st.key=w.eval('window._qbPanelKey');
    });
    // 3. a tap outside closes it (the press and the click on the dimmed page), a tap inside does not
    await pStep(res,'outside',async function(st){
      st.clicked=await pOpen(T.k1);
      st.opened=!!q(PNQ);
      var s=q(PNQ+' [data-lgpanel-sym]');
      if(s){s.click();await sleep(40);}
      st.keptOnInside=!!q(PNQ);
      var pt=T.vp==='phone'?[Math.round(w.innerWidth/2),20]:[30,Math.round(w.innerHeight/2)];
      var el=D().elementFromPoint(pt[0],pt[1]);
      st.hit=(el&&el.classList&&el.classList.contains('lg-panel-layer'))?'layer':(el?el.tagName+'.'+el.className:null);
      if(el){el.dispatchEvent(new w.PointerEvent('pointerdown',{bubbles:true,pointerType:T.vp==='phone'?'touch':'mouse'}));el.click();}
      await sleep(90);
      st.open=!!q('.lg-panel,.lg-panel-layer');st.g=pgeo();
      await pShut();
    });
    // 4. the close button
    await pStep(res,'button',async function(st){
      st.clicked=await pOpen(T.k1);
      var x=q(PNQ+' [data-lgpanel-close]');st.btn=!!x;
      if(x)x.click();
      await sleep(90);
      st.open=!!q('.lg-panel,.lg-panel-layer');st.g=pgeo();
      await pShut();
    });
    // 4b. KEEPS CHECKLIST: a Webull attempt netted against another leg needs no order: the chart draws its diamond (titled) and the legend names it
    await pStep(res,'netted',async function(st){
      w.__stubNetted=true;
      try{
        st.clicked=await pOpen(T.k1);
        st.drew=await waitFor(function(){return !!q(PNQ+' .qb-sheet-candles-svg svg');},6000);
        st.read=pRead(false);
      }finally{w.__stubNetted=false;}
      await pShut();
    });
    // 5. the chart glyph of a row opens the candles and not the panel
    await pStep(res,'glyph',async function(st){
      w.__opened.length=0;
      var gl=[].slice.call(D().querySelectorAll('[data-qbchartkey]'))[2];
      st.key=gl?gl.getAttribute('data-qbchartkey'):null;
      if(gl){gl.click();await sleep(110);}
      st.opened=w.__opened.slice();w.__opened.length=0;
      st.panel=!!q('.lg-panel,.lg-panel-layer');st.keyState=w.eval('window._qbPanelKey');
      await pShut();
    });
    // 6. the board redraws every few seconds: the open trade stays, the panel is the same node, nothing in it is rewritten, the scroll stays
    if(T.heavy)await pStep(res,'redraw',async function(st){
      await pOpen(T.k1);
      await waitFor(function(){return !!q(PNQ+' .qb-sheet-candles-svg svg');},6000);
      var p=q(PNQ),b=p?p.querySelector('[data-lgpanel-body]'):null;
      if(!p||!b){st.threw='no panel to redraw under';return;}
      p.__m=1;[].forEach.call(p.querySelectorAll('[data-lgpanel-slot]'),function(s){s.__m=1;});
      b.scrollTop=250;st.top0=b.scrollTop;st.canScroll=b.scrollHeight>b.clientHeight+10;
      var before=panelNow(),textBefore=tx2(p),muts=[];
      var mo=new w.MutationObserver(function(rs){rs.forEach(function(r){
        if(r.type==='attributes'&&r.target===p)return;
        muts.push(r.type+':'+(r.target.nodeType===1?r.target.tagName.toLowerCase()+'.'+String(r.target.className).split(' ')[0]:'#text'));});});
      mo.observe(p,{childList:true,subtree:true,attributes:true,characterData:true});
      w.eval('renderApp();');await sleep(150);
      // a new snapshot from the box (its clock moved on) through the board's own throttled live redraw
      w.eval('window._qqqExec.updated_at=window._qqqExec.updated_at;window._qqqExecLastRenderAt=0;_qqqExecLiveRender();');await sleep(150);
      w.eval('renderApp();');await sleep(150);
      mo.takeRecords().forEach(function(r){muts.push(r.type);});mo.disconnect();
      var p2=q(PNQ),b2=p2?p2.querySelector('[data-lgpanel-body]'):null;
      st.same=p2===p;st.marked=!!(p2&&p2.__m);
      st.slotsKept=p2?[].every.call(p2.querySelectorAll('[data-lgpanel-slot]'),function(s){return s.__m===1;}):false;
      st.top1=b2?b2.scrollTop:null;st.muts=muts.slice(0,6);st.mutN=muts.length;
      st.before=before;st.after=panelNow();st.textSame=!!p2&&tx2(p2)===textBefore;
      st.drawn=!!q(PNQ+' .qb-sheet-candles-svg svg');
      await pShut();
    });
    // 7. paging, search, chip, LIST | TABLE: the open trade (an old one that a short page leaves out) stays open on its own trade
    if(T.heavy)await pStep(res,'survive',async function(st){
      var snap=function(){var o=panelNow();return o?{trade:o.trade,sym:o.sym,side:o.side,net:o.net}:null;};
      w.eval('window._qeTradesShown=50;renderApp();');await sleep(130);
      st.k2Row=!!pRowEl(T.k2);
      await pOpen(T.k2);
      await waitFor(function(){return !!q(PNQ+' .qb-sheet-candles-svg svg');},6000);
      st.open=snap();st.openDrawn=!!q(PNQ+' .qb-sheet-candles-svg svg');
      w.eval('window._qeTradesShown='+T.page+';renderApp();');await sleep(160);
      st.paged={onPage:!!pRowEl(T.k2),rows:tlKeys().length,snap:snap()};
      var sm=q('[data-qeshowmore]');st.moreBtn=!!sm;
      if(sm){sm.click();await sleep(160);}
      st.more={rows:tlKeys().length,snap:snap(),shown:w.eval('window._qeTradesShown')};
      await typeIn('zzzz');st.zzzz={rows:tlKeys().length,snap:snap()};
      await typeIn('');st.cleared={rows:tlKeys().length,snap:snap()};
      await typeIn('noise');st.noise={rows:tlKeys().length,snap:snap()};await typeIn('');
      var t1=await clickChip(T.hideChip);st.chip={rowOn:!!pRowEl(T.k2),snap:snap()};
      await clickChip('ALL');
      q('[data-lgview="table"]').click();await sleep(160);st.table={mode:(q('[data-lglist-frame="wb"]')||{getAttribute:function(){return null;}}).getAttribute('data-lgmode'),snap:snap()};
      q('[data-lgview="list"]').click();await sleep(160);st.list={snap:snap()};
      st.sheet=!!q('.qb-sheet');
      await pShut();
    });
    // 8. the caveats: each kind of trade opens a panel that carries its chips, its numbers and its words
    res.variety={};
    for(var vi=0;vi<(T.variety||[]).length;vi++){
      var vk=T.variety[vi];
      await pStep(res,'v'+vi,async function(st){
        st.key=vk;st.clicked=await pOpen(vk);
        await waitFor(function(){return !!q(PNQ+' .qb-sheet-candles-svg svg');},5000);
        st.read=pRead(mono&&vi<2);
        await pShut();
      });
      res.variety[vk]=res.steps['v'+vi];delete res.steps['v'+vi];
    }
    // 9. the trade leaves the board's rows (another range): the panel closes on its own; leaving the board closes it too
    if(T.heavy)await pStep(res,'gone',async function(st){
      await pOpen(T.k2);st.opened=!!q(PNQ);
      w.eval("homeRange='TODAY';renderApp();");await sleep(160);
      st.closed=!q('.lg-panel,.lg-panel-layer');st.key=w.eval('window._qbPanelKey');
      w.eval("homeRange='ALL';renderApp();");await sleep(140);
      st.back=!q('.lg-panel,.lg-panel-layer');
    });
    if(T.heavy)await pStep(res,'leave',async function(st){
      await pOpen(T.k1);st.opened=!!q(PNQ);
      w.eval("activeTab='home';renderApp();");await sleep(260);
      st.closed=!q('.lg-panel,.lg-panel-layer');st.key=w.eval('window._qbPanelKey');
      w.eval("activeTab='augur';augurSub='qqqpaper';renderApp();");await sleep(260);
      st.back=!q('.lg-panel,.lg-panel-layer');st.rows=tlKeys().length;
    });
    pStubOff();
    res.end=pgeo();
  };
  // the panel at every width the owner named, on the LIST and the TABLE: the page never scrolls sideways with it open or closed, a sheet at 600 px and under
  SCEN.pwidth=async function(T,res){
    res.w={};
    pStubOn();
    for(var mi=0;mi<2;mi++){
      var mode=mi?'table':'list';
      for(var i=0;i<T.widths.length;i++){
        var a=T.widths[i],r={};
        await setVpWH(a[0],a[1]);
        var vb=q('[data-lgview="'+mode+'"]');if(vb){vb.click();await sleep(120);}
        r.base=pgeo();r.mode=(q('[data-lglist-frame="wb"]')||{getAttribute:function(){return null;}}).getAttribute('data-lgmode');
        r.clicked=await pOpen(T.k1);
        var o=pRead(false);r.open=o?{mode:o.mode,rect:o.rect,vw:o.vw,vh:o.vh,g:o.g,inApp:o.inApp,sym:o.sym,trade:o.trade,bodyWide:o.bodyWide}:null;
        r.shut=await pShut();r.after=pgeo();
        res.w[a[0]+mode]=r;
      }
      var lb=q('[data-lgview="list"]');if(lb){lb.click();await sleep(100);}
    }
    pStubOff();
  };
  async function runTl(T){
    var res={};
    if(T.wh)await setVpWH(T.wh[0],T.wh[1]);else await setVp(T.vp);
    drain();
    try{res.seed=seed({vp:T.vp,theme:T.theme,fix:T.doc||FIX,range:T.range||null,todayNY:T.today||null});}catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    try{await SCEN[T.scen](T,res);}catch(e){res.threw=String(e&&e.stack?e.stack:e);}
    Object.assign(res,drain());
    return res;
  }
"""


S11_JS = r"""  // ── LEDGER step 11: the fixed page order and this board's own sections as closed folds. s11Read = what a viewer sees of the page order and of
  // every fold header (where it is, what it says, whether it is shut, what colour it is drawn in); s11Run = what a viewer does to the folds. ──
  var S11_KEYS=['orders','account','todayorders','feedsig','system','rails','events','model'];
  var S11_MARKS={orders:['[data-qbminipill]','[data-qbstop]'],account:['[data-qbasof]','[data-qbrecon]','[data-qbeqchg]'],
    todayorders:['[data-qbordersday]','tbody tr'],feedsig:[],system:['[data-qbordmode]','[data-qblasttick]','[data-qbsheet]'],
    rails:[],events:['.qe-evt-row'],model:[],list:['[data-lgrow]','[data-lggrp]']};
  function s11Hue(e,props){
    // r = g = b (or fully transparent): the one test MONO has for 'no colour'
    var w=W(),cs=w.getComputedStyle(e),bad=[];
    props.forEach(function(pr){
      var c=cs[pr]||'',p=c.replace(/[^0-9.,]/g,'').split(',').map(Number);
      if(p.length>=3&&!(p[0]===p[1]&&p[1]===p[2])&&!(p.length>3&&p[3]===0))bad.push(pr+' '+c);});
    return bad;
  }
  function s11Skel(){
    // the old page's markup shape: every element's tag, class and attribute NAMES in document order, no text and no values
    var root=q('.qb-shell');if(!root)return null;
    var s=[];
    (function walk(e){
      s.push(e.tagName+'.'+(typeof e.className==='string'?e.className:'')+'['+[].map.call(e.attributes,function(a){return a.name;}).sort().join(',')+']');
      [].forEach.call(e.children,walk);
    })(root);
    var str=s.join('|'),h=0x811c9dc5;
    for(var i=0;i<str.length;i++){h^=str.charCodeAt(i);h=(h*16777619)>>>0;}
    return {n:s.length,h:h};
  }
  function s11Read(){
    var d=D(),w=W(),sy=w.scrollY||0,o={};
    function bx(sel){
      // an empty range draws no chart svg: the chart's caption (in the chart foot, under the empty-range line) stands for it
      var e=q(sel)||(sel==='#qb-lg-chart'?q('.qbx-chart .qbx-chart-cap'):null);if(!e)return null;
      var r=e.getBoundingClientRect(),cs=w.getComputedStyle(e);
      return {t:Math.round(r.top+sy),b:Math.round(r.bottom+sy),l:Math.round(r.left),r:Math.round(r.right),w:Math.round(r.width),h:Math.round(r.height),
        shown:cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0};
    }
    var M={shell:'.qb-shell',hero:'#qb-hero-label',pills:'.qbx-range-row',chart:'#qb-lg-chart',status:'.qbx-statusline',stats:'.qbx-lgstats .lg-stats',
      more:'[data-lgmore="qb"]',cal:'[data-lgcalfold="qb"]',list:'[data-lglist="qb"]',listfold:'[data-qbfold="list"]',trades:'[data-lglist-frame="wb"]',own:'.qbx-own',
      ftop:'[data-lgframe-top="qb"]'};
    o.pos={};
    Object.keys(M).forEach(function(k){o.pos[k]=bx(M[k]);});
    o.strip={text:tx2(q('.qbx-statusline')),refresh:!!q('.qbx-statusline [data-qqqrefresh]'),inFold:!!q('[data-qbfoldbox] .qbx-statusline')};
    o.frame=frameRead();
    // every fold header, in page order: its key, title, summary, whether it is shut, where it is, its height (one line), the room its summary has
    o.folds=[].map.call(d.querySelectorAll('[data-qbfold]'),function(b){
      var k=b.getAttribute('data-qbfold'),p=d.getElementById('qbf-'+k),sm=b.querySelector('[data-qbfoldsum]'),t=b.querySelector('.qbx-fold-t');
      var br=b.getBoundingClientRect(),pr=p?p.getBoundingClientRect():null,pcs=p?w.getComputedStyle(p):null,bcs=w.getComputedStyle(b);
      var smr=sm?sm.getBoundingClientRect():null;
      return {key:k,title:tx2(t),sum:tx2(sm),sumHtml:sm?sm.innerHTML:null,exp:b.getAttribute('aria-expanded'),ctl:b.getAttribute('aria-controls'),
        btn:{t:Math.round(br.top+sy),b:Math.round(br.bottom+sy),l:Math.round(br.left),r:Math.round(br.right),h:Math.round(br.height),w:Math.round(br.width),
          shown:bcs.display!=='none'&&br.width>0&&br.height>0},
        sumH:smr?Math.round(smr.height):null,sumClip:sm?(sm.scrollWidth>sm.clientWidth+1):null,
        panel:p?{hiddenAttr:p.hasAttribute('hidden'),shown:pcs.display!=='none'&&pr.height>0,h:Math.round(pr.height),len:(p.textContent||'').replace(/\s+/g,' ').trim().length,
          inApp:!!p.closest('#app')}:null,
        hues:(function(){var bad=[];[b,t,sm,b.querySelector('.lg-chev')].concat(sm?[].slice.call(sm.querySelectorAll('*')):[]).forEach(function(e){
          if(e)s11Hue(e,['color','borderTopColor','backgroundColor']).forEach(function(x){if(bad.length<6)bad.push((e.className||e.tagName)+' '+x);});});
          if(p)s11Hue(p,['backgroundColor','borderTopColor']).forEach(function(x){bad.push('panel '+x);});return bad;})()};
    });
    // the page's shape: the fold layout, and a skeleton of its markup (the ?oldboards=1 page must draw the same one as the plain page)
    o.shape={lg6:!!q('.qbx-lg6'),ownBox:!!q('.qbx-own'),foldBtns:d.querySelectorAll('[data-qbfold]').length,foldBoxes:d.querySelectorAll('[data-qbfoldbox]').length,
      disc:[].map.call(d.querySelectorAll('[data-qbdisclosure]'),function(e){return e.getAttribute('data-qbdisclosure');}),
      modelToggle:!!q('[data-qqqmodeltoggle]'),statusInChart:!!q('.qbx-chart .qbx-status-strip'),skel:s11Skel()};
    return o;
  }
  // ── LEDGER step 12: the one page frame. frameRead = the frame, its three parts, and where the list, the status line, the chart foot and the
  // Filters row are; filtCycle = what a viewer does to the Filters row. ──
  function rectOf(e){
    if(!e)return null;
    var w=W(),sy=w.scrollY||0,r=e.getBoundingClientRect(),cs=w.getComputedStyle(e);
    return {t:Math.round(r.top+sy),b:Math.round(r.bottom+sy),l:Math.round(r.left),r:Math.round(r.right),w:Math.round(r.width),h:Math.round(r.height),
      shown:cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0};
  }
  function cssRuleFs(sel){
    // the font size the page's own css gives exactly this selector at the top level (the last such rule wins), or null: no such rule is in the page
    var fs=null;
    [].forEach.call(D().styleSheets,function(sh){var rs=null;try{rs=sh.cssRules;}catch(e){}
      if(rs)[].forEach.call(rs,function(r){if(r.selectorText===sel&&r.style&&r.style.fontSize)fs=r.style.fontSize;});});
    return fs;
  }
  function frameRead(){
    var d=D(),w=W(),o={};
    var all=d.querySelectorAll('[data-lgframe="qb"]'),f=all[0]||null;
    o.n=all.length;o.nAny=d.querySelectorAll('[data-lgframe]').length;
    if(!f)return o;
    var cs=w.getComputedStyle(f),p=f.parentElement,fbr=f.getBoundingClientRect();
    o.maxW=cs.maxWidth;o.disp=cs.display;o.cols=cs.gridTemplateColumns;o.w=Math.round(fbr.width*10)/10;
    if(p){var pr=p.getBoundingClientRect(),pcs=w.getComputedStyle(p);
      var pl=pr.left+(parseFloat(pcs.paddingLeft)||0)+(parseFloat(pcs.borderLeftWidth)||0),pe=pr.right-(parseFloat(pcs.paddingRight)||0)-(parseFloat(pcs.borderRightWidth)||0);
      o.gapL=Math.round((fbr.left-pl)*10)/10;o.gapR=Math.round((pe-fbr.right)*10)/10;o.parentW=Math.round((pe-pl)*10)/10;}
    o.parts={};
    ['top','side','rest'].forEach(function(k){o.parts[k]=[].filter.call(f.children,function(c){return c.getAttribute('data-lgframe-'+k)==='qb';}).length;});
    var ft=q('[data-lgframe-top="qb"]'),fs=q('[data-lgframe-side="qb"]'),fe=q('[data-lgframe-rest="qb"]'),fi=fs?fs.querySelector('.lg-frame-side-in'):null;
    o.top=rectOf(ft);o.side=rectOf(fs);o.rest=rectOf(fe);o.sideIn=rectOf(fi);
    o.sidePos=fs?w.getComputedStyle(fs).position:null;o.sideInOverflow=fi?w.getComputedStyle(fi).overflowY:null;
    var qs=q('.qbx-side');o.qbxSide=rectOf(qs);o.qbxSidePos=qs?w.getComputedStyle(qs).position:null;
    var where=function(e){if(!e)return null;return e.closest('[data-lgframe-top="qb"]')?'top':(e.closest('[data-lgframe-side="qb"]')?'side':(e.closest('[data-lgframe-rest="qb"]')?'rest':'none'));};
    var lst=q('[data-lglist="qb"]'),tl=q('[data-lglist-frame="wb"]'),own=q('.qbx-own'),cal=q('[data-lgcalfold="qb"]'),hero=q('.qbx-hero');
    o.list=rectOf(lst);o.listIn=where(lst);o.trades=rectOf(tl);o.tradesIn=where(tl);o.ownIn=where(own);o.cal=rectOf(cal);o.calIn=where(cal);
    o.hero=rectOf(hero);o.heroIn=where(hero);o.pills=rectOf(q('.qbx-range-row'));o.stats=rectOf(q('.qbx-lgstats .lg-stats'));
    // the status line: one, in the top block right after the hero, one or two lines, the Refresh button in it
    var sts=d.querySelectorAll('[data-lgstatus="qb"]'),st=sts[0]||null,sl=st?st.querySelector('.lg-status-line'):null,sw=st?st.closest('.qbx-statusline'):null;
    var swp=sw?sw.previousElementSibling:null;
    o.status={n:sts.length,box:rectOf(st),inTop:where(st)==='top',refresh:!!(st&&st.querySelector('[data-qqqrefresh]')),
      afterHero:!!(swp&&swp.classList.contains('qbx-hero')),lineH:sl?Math.round(sl.getBoundingClientRect().height*10)/10:null,
      lh:sl?parseFloat(w.getComputedStyle(sl).lineHeight):null,text:sl?tx2(sl):null};
    // the chart foot: one, in the chart section, right after the chart box, the caption (the only one on the page) and the key in it
    var fts=d.querySelectorAll('[data-lgchartfoot="qb"]'),fo=fts[0]||null,ch=q('#qb-lg-chart'),prev=fo?fo.previousElementSibling:null;
    var cap=d.querySelector('.qbx-chart-cap'),lcap=fo?fo.querySelector('.lg-chart-cap'):null;
    o.foot={n:fts.length,box:rectOf(fo),inChart:!!(fo&&fo.closest('.qbx-chart')),chart:rectOf(ch),prev:rectOf(prev),prevIsChart:!!(ch&&prev===ch),
      caps:d.querySelectorAll('.qbx-chart-cap').length,capsInFoot:fo?fo.querySelectorAll('.qbx-chart-cap').length:0,
      keys:d.querySelectorAll('.qbx-lg-key').length,keysInFoot:fo?fo.querySelectorAll('.qbx-lg-key').length:0,
      capFs:cap?w.getComputedStyle(cap).fontSize:null,sharedFs:lcap?w.getComputedStyle(lcap).fontSize:null,ruleFs:cssRuleFs('.lg-chart-cap')};
    // the list's Filters row: one, a child of the list right after its header, shut, its body hidden
    var fls=d.querySelectorAll('[data-lgfilters="qb"]'),fl=fls[0]||null,fb=fl?fl.querySelector('[data-lgfilt="qb"]'):null,fbd=fl?fl.querySelector('.lg-filters-body'):null;
    var fpv=fl?fl.previousElementSibling:null;
    o.filt={n:fls.length,inList:!!(fl&&fl.parentElement&&fl.parentElement.matches('[data-lglist="qb"]')),afterHd:!!(fpv&&fpv.classList.contains('lg-list-hd')),
      exp:fb?fb.getAttribute('aria-expanded'):null,ctl:fb?fb.getAttribute('aria-controls'):null,bodyId:fbd?fbd.id:null,
      hiddenAttr:fbd?fbd.hasAttribute('hidden'):null,bodyShown:fbd?(w.getComputedStyle(fbd).display!=='none'&&fbd.getBoundingClientRect().height>0):null,
      sum:fl?tx2(fl.querySelector('[data-lgfiltsum]')):null,none:fl?tx2(fl.querySelector('.lg-filters-none')):null};
    return o;
  }
  function filtState(){
    var w=W(),b=q('[data-lgfilt="qb"]'),bx=q('[data-lgfilters="qb"]'),p=bx?bx.querySelector('.lg-filters-body'):null,st=null;
    try{st=w.localStorage.getItem('el_lg_filters_qb');}catch(e){}
    if(!b||!p)return {missing:true,stored:st};
    var pr=p.getBoundingClientRect(),cs=w.getComputedStyle(p);
    return {exp:b.getAttribute('aria-expanded'),hiddenAttr:p.hasAttribute('hidden'),shown:cs.display!=='none'&&pr.height>0,h:Math.round(pr.height),
      text:tx2(p),stored:st,sum:tx2(bx.querySelector('[data-lgfiltsum]'))};
  }
  async function filtCycle(){
    // the Filters row: a tap opens it in place (the list node is the same), a redraw keeps it open (its choice lives in storage only, so a redraw
    // finds what a reload finds), a second tap closes it, a redraw keeps it closed
    var w=W(),rec={},b=q('[data-lgfilt="qb"]'),l0=q('[data-lglist="qb"]');
    rec.before=filtState();
    if(!b)return rec;
    b.click();await sleep(80);
    rec.open=filtState();rec.sameList=q('[data-lglist="qb"]')===l0;
    w.eval("renderApp();");await sleep(120);
    rec.reload=filtState();
    var b2=q('[data-lgfilt="qb"]');if(b2){b2.click();await sleep(80);}
    rec.closed=filtState();
    w.eval("renderApp();");await sleep(120);
    rec.closedReload=filtState();
    return rec;
  }
  function foldState(k){
    var d=D(),w=W(),b=q('[data-qbfold="'+k+'"]'),p=d.getElementById('qbf-'+k);
    if(!b||!p)return null;
    var pr=p.getBoundingClientRect(),cs=w.getComputedStyle(p),txt=(p.textContent||'').replace(/\s+/g,' ').trim(),st=null;
    try{st=w.localStorage.getItem('el_qb_fold_'+k);}catch(e){}
    var sel={};(S11_MARKS[k]||[]).forEach(function(s){sel[s]=p.querySelectorAll(s).length;});
    return {exp:b.getAttribute('aria-expanded'),hiddenAttr:p.hasAttribute('hidden'),shown:cs.display!=='none'&&pr.height>0,h:Math.round(pr.height),len:txt.length,
      text:txt.slice(0,700),stored:st,sel:sel,sum:tx2(b.querySelector('[data-qbfoldsum]'))};
  }
  async function s11Cycle(k){
    // a fold, tapped open: it shows its content; a reload (nothing in memory, the stored choice kept) finds it open; tapped shut it stays shut across a reload too
    var w=W(),rec={},b=q('[data-qbfold="'+k+'"]');
    if(!b)return null;
    rec.before=foldState(k);
    b.click();await sleep(110);
    rec.open=foldState(k);
    w.eval("window._qbFolds=null;renderApp();");await sleep(130);
    rec.reload=foldState(k);
    w.eval("renderApp();");await sleep(90);
    rec.redraw=foldState(k);
    var b2=q('[data-qbfold="'+k+'"]');if(b2){b2.click();await sleep(110);}
    rec.closed=foldState(k);
    w.eval("window._qbFolds=null;renderApp();");await sleep(130);
    rec.closedReload=foldState(k);
    return rec;
  }
  async function s11Run(){
    var w=W(),d=D(),res={laptop:{},phone:{},widths:{},blocked:null,errs:{}};
    // laptop 1366x768: every own fold
    await setVp('laptop');drain();
    try{res.seedL=seed({vp:'laptop',theme:'dark'});}catch(e){res.seedL='ERR '+e;}
    await sleep(220);
    res.order=[].map.call(d.querySelectorAll('[data-qbfold]'),function(b){return b.getAttribute('data-qbfold');});
    for(var i=0;i<S11_KEYS.length;i++){res.laptop[S11_KEYS[i]]=await s11Cycle(S11_KEYS[i]);}
    res.errs.laptop=drain();
    // phone 375x812: the strategy list's own fold, and two of the own folds, in the phone layout
    await setVp('phone');drain();
    try{res.seedP=seed({vp:'phone',theme:'dark'});}catch(e){res.seedP='ERR '+e;}
    await sleep(220);
    res.phone.list=await s11Cycle('list');
    if(res.phone.list){
      // its rows, when it is open: one line each
      var lk=q('[data-qbfold="list"]');if(lk){lk.click();await sleep(110);}
      res.phone.listRows=[].map.call(d.querySelectorAll('.qbx-side [data-lgrow]'),function(r){var rc=r.getBoundingClientRect();return {key:r.getAttribute('data-lgrow'),h:Math.round(rc.height),w:Math.round(rc.width)};});
      res.phone.listTopOpen=(function(){var t=q('[data-lglist-frame="wb"]'),s=q('.qb-shell');return t&&s?Math.round(t.getBoundingClientRect().top-s.getBoundingClientRect().top):null;})();
      lk=q('[data-qbfold="list"]');if(lk){lk.click();await sleep(110);}
    }
    res.phone.orders=await s11Cycle('orders');
    res.phone.account=await s11Cycle('account');
    res.errs.phone=drain();
    // storage that throws for the fold keys: the fold still opens (memory), nothing is thrown
    await setVp('laptop');drain();
    try{seed({vp:'laptop',theme:'dark'});}catch(e){}
    await sleep(200);drain();
    var Sp=w.Storage.prototype,g0=Sp.getItem,s0=Sp.setItem;
    Sp.getItem=function(k){if(/^el_qb_fold_/.test(k))throw new Error('blocked');return g0.apply(this,arguments);};
    Sp.setItem=function(k,v){if(/^el_qb_fold_/.test(k))throw new Error('blocked');return s0.apply(this,arguments);};
    try{
      var bb=q('[data-qbfold="rails"]');if(bb){bb.click();await sleep(130);}
      var b3=q('[data-qbfold="rails"]'),p3=d.getElementById('qbf-rails');
      res.blocked={exp:b3?b3.getAttribute('aria-expanded'):null,len:p3?(p3.textContent||'').replace(/\s+/g,' ').trim().length:null,errs:drain()};
    }finally{Sp.getItem=g0;Sp.setItem=s0;}
    // the page never scrolls sideways with EVERY fold open, at the widths a viewer has
    var S11W=[375,601,700,800,1000,1366];
    for(var j=0;j<S11W.length;j++){
      var wd=S11W[j];
      fr.style.width=wd+'px';fr.style.height='800px';
      await waitFor(function(){return W().innerWidth===wd;},2000);await sleep(70);
      drain();
      try{seed({vp:'laptop',theme:'dark',foldOpen:'all'});}catch(e){}
      await sleep(230);
      var r2={iw:w.innerWidth,sw:d.documentElement.scrollWidth,wide:[],open:[].map.call(d.querySelectorAll('[data-qbfold]'),function(b){return b.getAttribute('aria-expanded');}).join(',')};
      if(r2.sw>r2.iw+0)r2.wide=offenders(d);
      r2.errs=drain();
      res.widths[String(wd)]=r2;
    }
    // LEDGER step 12: a window wider than the frame: the frame stays 1320 px wide and centred, the list still the right-hand panel
    fr.style.width='1680px';fr.style.height='900px';
    await waitFor(function(){return W().innerWidth===1680;},2000);await sleep(70);
    drain();
    try{res.wideSeed=seed({vp:'laptop',theme:'dark'});}catch(e){res.wideSeed='ERR '+e;}
    await sleep(230);
    res.wide={iw:w.innerWidth,frame:frameRead(),errs:drain()};
    fr.style.width='1366px';fr.style.height='768px';
    return res;
  }
"""

# ── LEDGER step 11 (2026-10-06): one fixed page order; every own section a closed fold with a one-line summary; one set of breakpoints ──
S11_OWN_ORDER = ['orders', 'account', 'todayorders', 'feedsig', 'system', 'rails', 'events', 'model']   # the own folds, top to bottom
S11_OWN_REQUIRED = ['orders', 'account', 'system', 'rails', 'events', 'model']                          # always drawn; Today's orders / Feed & signals only when there is something
S11_PHONE_TOP_MAX = 760      # phone 375x812: the trade list starts at most this far under the board top. It was 784 before step 11 and 12; step 12's
                             # page puts it at 757 (the status line under the hero, the caption in the chart foot), and it must not grow (3 px slack)
S11_FOLD_ONE_LINE = 40       # a fold header is one line: the button is shorter than this (two lines of text would be 44 and over)
S11_HOUSE = (600, 740, 800, 920, 1100)   # the only widths this board's media / container queries may use (the shared parts' own: phone, compact, list cells, rail)
S11_WIDTHS = [375, 601, 700, 800, 1000, 1366]
# what the removed previous board drew: none of it may be in the page, in any case, with or without ?oldboards=1 (the page-side readout lists the ones it
# finds). The names are the ones tools/ledger_removed.py lints for in the source; this list catches them if a build ever composes them at run time.
OLD_MARKS = ['[data-qbtraderow]', '[data-qetraderow]', '[data-qbseg]', '[data-qelegend]', '[data-qblegrow]', '[data-qcalmo]', '[data-qcalday]',
             '[data-qechart]', '[data-qqqmodeltoggle]', '[data-qqqratiotoggle]', '.qe-drawer', '.qb-hero', '.qb-seg', '.qb-chart-svg',
             '.qbx-stat-strip', '.qbx-side-hd', '#qbCrossCapture']
S11_BAD_TOKEN = re.compile(r'NaN|undefined|\[object Object\]|null')


def _s11_expected(doc):
    """What each fold's header must say for this doc, worked out from the fixture: key -> list of substrings."""
    rails = doc.get('rails') or {}
    today = doc.get('today') or {}
    eq = doc.get('equity') or {}
    rd = doc.get('readiness') or {}
    ev = doc.get('events') or []
    orders = today.get('orders') or []
    out = {}
    lim = rails.get('daily_loss_limit_usd')
    bi = _fin(today.get('breaker_input'))
    if bi is None:     # a box that does not send the breaker's own figure: the page falls back to today's closed (of record) + open P&L
        rr = _fin(today.get('realized_pnl_record'))
        rr = rr if rr is not None else (_fin(today.get('realized_pnl')) or 0.0)
        bi = rr + (_fin(today.get('unrealized_pnl')) or 0.0)
    used = abs(min(0.0, bi))
    out['orders'] = [money(used) + ' of ' + money(abs(float(lim))) + ' daily stop used'] if lim is not None else ['no daily stop set']
    acc = []
    if eq.get('net_liq') is not None:
        acc.append(money(float(eq['net_liq'])))
        if eq.get('change_today') is not None:
            acc.append(signed(float(eq['change_today'])))
            acc.append('today')
    out['account'] = acc
    out['todayorders'] = ['%d order%s' % (len(orders), '' if len(orders) == 1 else 's')] if orders else None
    out['feedsig'] = ['feed up '] if doc.get('feed_days') else None
    out['system'] = (['NOT READY for real shares'] + (['(%d open)' % len(rd.get('missing') or [])] if rd.get('missing') else [])) if rd.get('ready') is False else ['ready for real shares']
    out['rails'] = ['daily stop ' + money(abs(float(lim)))] if lim is not None else ['no daily stop set']
    if rails.get('max_shares_per_leg') is not None:
        out['rails'].append('up to %d shares a leg' % int(rails['max_shares_per_leg']))
    out['events'] = ['%d events' % len(ev)] if ev else ['no events published yet']
    out['model'] = ['reference only']
    return out


def _s11_order_problems(tag, s11, iw, doc, fails):
    """The fixed order, top to bottom, by the page's own markers: hero, status line (step 12: directly under the hero), range pills, chart, stats strip,
    More stats fold, calendar fold, strategy list (a one-line fold up to 600 px; from 1100 px the frame's right-hand panel beside the top block), trade
    list, then the own folds in their order. (The chart caption's style is judged with the frame, _frame_problems.)"""
    pos = s11.get('pos') or {}
    two_col = iw >= 1100
    chain = ['hero', 'status', 'pills', 'chart', 'stats', 'more', 'cal'] + ([] if two_col else ['listfold' if iw <= 600 else 'list']) + ['trades']
    last, last_k = None, None
    for k in chain:
        p = pos.get(k)
        if not p or not p.get('shown'):
            fails.append('%s: the page has no drawn %s (the fixed order needs it)' % (tag, k))
            continue
        if last is not None and p['t'] < last['t'] + 1:
            fails.append('%s: the page order is wrong: %s (top %s) must come below %s (top %s)' % (tag, k, p['t'], last_k, last['t']))
        last, last_k = p, k
    if two_col:
        ls, ft = pos.get('list'), pos.get('ftop')
        if not ls or not ls.get('shown') or not ft or ls['l'] < ft['r'] + 1:
            fails.append("%s: on a laptop the strategy list is not in the right-hand panel beside the top block (%s, top block %s)" % (tag, ls, ft))
    st = s11.get('strip') or {}
    if (pos.get('status') or {}).get('shown') and (st.get('inFold') or not re.search(r'box updated|last update from the box|its last copy is from', st.get('text') or '') or not st.get('refresh')):
        fails.append('%s: the status line under the hero lost its box-updated line or its Refresh button, or sits in a fold (%s)' % (tag, st))
    folds = [f for f in s11.get('folds') or [] if f.get('key') != 'list']
    keys = [f['key'] for f in folds]
    miss = [k for k in S11_OWN_REQUIRED if k not in keys]
    if miss:
        fails.append('%s: own sections missing from the page (folded, never removed): %s' % (tag, miss))
    want = [k for k in S11_OWN_ORDER if k in keys]
    if keys != want:
        fails.append('%s: the own folds run %s, want %s' % (tag, keys, want))
    tr = pos.get('trades')
    for f in folds:
        if tr and f['btn']['t'] < tr['b'] - 1:
            fails.append('%s: the %s fold (top %s) is above the end of the trade list (bottom %s): own sections come last' % (tag, f['key'], f['btn']['t'], tr['b']))
    tops = [f['btn']['t'] for f in folds]
    if tops != sorted(tops):
        fails.append('%s: the own folds are not in page order by their tops: %s' % (tag, list(zip(keys, tops))))


def _s11_fold_problems(tag, s11, iw, theme, doc, fails):
    """Every own fold, shut as first drawn: a header of one line with a summary that is not empty and says the right number, the content not on the page,
    the chevron's state; the strategy list's phone fold; MONO draws no hue in a header."""
    exp = _s11_expected(doc)
    for f in s11.get('folds') or []:
        k = f['key']
        t = '%s: the %s fold' % (tag, k)
        if k == 'list':
            if iw <= 600:
                if not f['btn']['shown']:
                    fails.append('%s is not drawn on a phone (the list is a one-line fold up to 600 px)' % t)
                elif f['exp'] != 'false' or (f.get('panel') or {}).get('shown'):
                    fails.append('%s is open when first drawn on a phone (aria-expanded %s, panel shown %s): it starts shut' % (t, f['exp'], (f.get('panel') or {}).get('shown')))
            elif f['btn']['shown'] or not (f.get('panel') or {}).get('shown'):
                fails.append('%s is drawn above 600 px (button shown %s, list shown %s): the list is drawn as before there' % (t, f['btn']['shown'], (f.get('panel') or {}).get('shown')))
            if not (f.get('sum') or '').strip() or S11_BAD_TOKEN.search(f.get('sum') or ''):
                fails.append('%s has the summary %r' % (t, f.get('sum')))
            continue
        if not f['btn']['shown']:
            fails.append('%s header is not drawn' % t)
            continue
        if f['exp'] != 'false' or (f.get('panel') or {}).get('shown') or not (f.get('panel') or {}).get('hiddenAttr'):
            fails.append('%s is not shut when first drawn (aria-expanded %s, panel shown %s, hidden %s)'
                         % (t, f['exp'], (f.get('panel') or {}).get('shown'), (f.get('panel') or {}).get('hiddenAttr')))
        sm = (f.get('sum') or '').strip()
        if len(sm) < 3 or S11_BAD_TOKEN.search(sm):
            fails.append('%s has no usable one-line summary (%r)' % (t, f.get('sum')))
        if f['btn']['h'] > S11_FOLD_ONE_LINE or (f.get('sumH') or 0) > 22:
            fails.append('%s header is not one line (button %s px, summary %s px tall)' % (t, f['btn']['h'], f.get('sumH')))
        if not (f.get('title') or '').strip():
            fails.append('%s has no title' % t)
        for piece in (exp.get(k) or []):
            if piece not in sm:
                fails.append('%s says %r; the fixture needs %r in it' % (t, sm, piece))
        if theme == 'mono' and f.get('hues'):
            fails.append('%s draws a hue in MONO: %s' % (t, f['hues'][:3]))
    # the optional folds are there when the doc has something for them (this fixture has both)
    have = [f['key'] for f in s11.get('folds') or []]
    for k in ('todayorders', 'feedsig'):
        if exp.get(k) and k not in have:
            fails.append('%s: the %s fold is missing though the fixture has its content' % (tag, k))


S11_TEXT = {'orders': ['order'], 'account': ['Account equity', 'as of'], 'todayorders': ['Today'], 'feedsig': ['FEED UPTIME'],
            'system': ['Status', 'Integrity'], 'rails': ['DAILY LOSS LIMIT'], 'events': ['BOOT'], 'model': ['model'], 'list': ['ORB']}


def _s11_cycle_problems(tag, k, rec, doc, fails, phone=False):
    """One fold, tapped open then shut: it opens and shows its content, the choice is stored and a reload finds it, a redraw leaves it, shut again it stays shut."""
    t = '%s: the %s fold' % (tag, k)
    if not rec:
        fails.append('%s is not on the page to tap' % t)
        return
    b, o, rl, rd_, c, cr = (rec.get(x) or {} for x in ('before', 'open', 'reload', 'redraw', 'closed', 'closedReload'))
    if b.get('exp') != 'false' or b.get('shown'):
        fails.append('%s does not start shut (%s)' % (t, {x: b.get(x) for x in ('exp', 'shown')}))
    if o.get('exp') != 'true' or not o.get('shown') or o.get('h', 0) < 10:
        fails.append('%s did not open on a tap (aria-expanded %s, panel shown %s, %s px tall)' % (t, o.get('exp'), o.get('shown'), o.get('h')))
    if o.get('len', 0) < 12:
        fails.append('%s opened empty (%s characters)' % (t, o.get('len')))
    for w_ in S11_TEXT.get(k, []):
        if w_.lower() not in (o.get('text') or '').lower():
            fails.append('%s opened without %r in it (%r)' % (t, w_, (o.get('text') or '')[:120]))
    for sel, n in (o.get('sel') or {}).items():
        if not n:
            fails.append('%s opened without a %s in it' % (t, sel))
    if k == 'todayorders' and (o.get('sel') or {}).get('tbody tr') != len((doc.get('today') or {}).get('orders') or []):
        fails.append("%s lists %s order rows, the fixture has %d" % (t, (o.get('sel') or {}).get('tbody tr'), len((doc.get('today') or {}).get('orders') or [])))
    if o.get('stored') != '1':
        fails.append('%s did not store its open state for this viewer (el_qb_fold_%s = %r)' % (t, k, o.get('stored')))
    if o.get('sum') != b.get('sum'):
        fails.append('%s changed its summary on opening (%r -> %r)' % (t, b.get('sum'), o.get('sum')))
    if rl.get('exp') != 'true' or not rl.get('shown') or rl.get('len', 0) < 12:
        fails.append('%s is not remembered across a reload (aria-expanded %s, panel shown %s, %s characters)' % (t, rl.get('exp'), rl.get('shown'), rl.get('len')))
    if rd_.get('exp') != 'true' or not rd_.get('shown'):
        fails.append('%s was shut by a live redraw (aria-expanded %s)' % (t, rd_.get('exp')))
    if c.get('exp') != 'false' or c.get('shown') or c.get('stored') != '0':
        fails.append('%s did not shut on a second tap (aria-expanded %s, panel shown %s, stored %r)' % (t, c.get('exp'), c.get('shown'), c.get('stored')))
    if cr.get('exp') != 'false' or cr.get('shown'):
        fails.append('%s opens again by itself after a reload (aria-expanded %s)' % (t, cr.get('exp')))


def _judge_s11_run(res, fixture, fails):
    """The step 11 interaction run: every own fold on a laptop, the list fold on a phone, storage that throws, every fold open at six widths."""
    tag = 'LEDGER step 11 folds'
    if res is None:
        fails.append('%s: the run never happened' % tag)
        return
    if res.get('threw'):
        fails.append('%s: the probe itself threw -- %s' % (tag, _first(res['threw'])))
        return
    for nm in ('seedL', 'seedP'):
        if res.get(nm) != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get(nm))))
    order = [k for k in res.get('order') or [] if k != 'list']
    want = [k for k in S11_OWN_ORDER if (k in S11_OWN_REQUIRED or _s11_expected(fixture).get(k))]
    if order != want:
        fails.append('%s: the own folds on the page run %s, want %s' % (tag, order, want))
    for k in want:
        _s11_cycle_problems('%s (laptop 1366x768)' % tag, k, (res.get('laptop') or {}).get(k), fixture, fails)
    ph = res.get('phone') or {}
    _s11_cycle_problems('%s (phone 375x812)' % tag, 'list', ph.get('list'), fixture, fails, phone=True)
    for k in ('orders', 'account'):
        _s11_cycle_problems('%s (phone 375x812)' % tag, k, ph.get(k), fixture, fails, phone=True)
    rows = ph.get('listRows') or []
    if len(rows) < 2 or any(not (0 < x['h'] <= PHONE_ROW_MAX_H) for x in rows):
        fails.append('%s: with its fold open the phone list shows rows %s (want 2 or more, one line each: 1 to %d px)'
                     % (tag, [(x['key'], x['h']) for x in rows], PHONE_ROW_MAX_H))
    for nm in ('laptop', 'phone'):
        _errs('%s [%s]' % (tag, nm), (res.get('errs') or {}).get(nm) or {}, fails)
    bl = res.get('blocked') or {}
    if bl.get('exp') != 'true' or (bl.get('len') or 0) < 12:
        fails.append('%s: with storage that throws for its key a fold does not open (aria-expanded %s, %s characters): the memory copy must carry it'
                     % (tag, bl.get('exp'), bl.get('len')))
    _errs('%s [blocked storage]' % tag, bl.get('errs') or {}, fails)
    for wd in S11_WIDTHS:
        r = (res.get('widths') or {}).get(str(wd)) or {}
        t = '%s [every fold open, %d px]' % (tag, wd)
        if r.get('iw') != wd:
            fails.append('%s: not measured (window %s)' % (t, r.get('iw')))
            continue
        if (r.get('sw') or 0) > r['iw']:
            fails.append('%s: the page scrolls sideways (scrollWidth %s > window %s; sticking out: %s)' % (t, r.get('sw'), r['iw'], ', '.join(r.get('wide') or []) or '?'))
        if 'false' in (r.get('open') or ''):
            fails.append('%s: a fold is shut though every fold was opened (%s)' % (t, r.get('open')))
        _errs(t, r.get('errs') or {}, fails)
    # LEDGER step 12: a window wider than the frame
    t = 'LEDGER step 12 frame [%dx900 window]' % FRAME_WIDE
    wd = res.get('wide') or {}
    if res.get('wideSeed') != 'OK':
        fails.append('%s: renderApp threw -- %s' % (t, _first(res.get('wideSeed'))))
    elif wd.get('iw') != FRAME_WIDE:
        fails.append('%s: not measured (window %s)' % (t, wd.get('iw')))
    else:
        _frame_problems(t, wd.get('frame'), FRAME_WIDE, fails, wide=True)
        _errs(t, wd.get('errs') or {}, fails)


# ── LEDGER step 12 (2026-10-07): the one page frame (ledgerFrameHtml), the status line under the hero, the chart foot, the Filters row ──
FRAME_MAX_W = '1320px'      # the frame's computed max-width (the shared .lg-frame rule)
FRAME_W = 1320
FRAME_WIDE = 1680           # the window the step 11 run also draws the board in: wider than the frame, so the frame must be FRAME_W wide and centred
FRAME_TWO_COL = 1100        # from this width the list is the right-hand panel
STATUS_GAP_MAX = 24         # the status line starts at most this far under the hero box
STATUS_LINES_MAX = 2


def _frame_problems(tag, fr, iw, fails, wide=False):
    """The one page frame: exactly one [data-lgframe="qb"] with its top block, side panel and rest; its max width 1320 px, centred in its parent. From
    1100 px a grid: the list in the side panel to the right of the top block, level with it, never taller than it, not sticky, the trade list the full
    width under both; under 1100 px no grid and the list between the calendar and the trade list. The status line once, in the top block directly under
    the hero and above the pills, one or two lines, Refresh in it. The chart foot once, right after the chart box, holding the only caption (in the shared
    foot style) and the key. The list's Filters row once, right after the list header, closed, 'none' to filter."""
    if not fr:
        fails.append('%s: the page frame was not read' % tag)
        return
    if fr.get('n') != 1:
        fails.append('%s: want exactly one page frame [data-lgframe="qb"], the page has %s' % (tag, fr.get('n')))
        return
    parts = fr.get('parts') or {}
    if parts != {'top': 1, 'side': 1, 'rest': 1}:
        fails.append('%s: the frame holds %s, want one top block, one side panel and one rest as its children' % (tag, parts))
    if fr.get('maxW') != FRAME_MAX_W:
        fails.append("%s: the page frame's max-width is %r, want %s (the shared frame width)" % (tag, fr.get('maxW'), FRAME_MAX_W))
    gl, gr = fr.get('gapL'), fr.get('gapR')
    if gl is None or gr is None or abs(gl - gr) > 2 or min(gl, gr) < -1:
        fails.append('%s: the page frame is not centred in its parent (left gap %s px, right gap %s px, frame %s of %s px)'
                     % (tag, gl, gr, fr.get('w'), fr.get('parentW')))
    if wide and (fr.get('w') is None or abs(fr['w'] - FRAME_W) > 1):
        fails.append('%s: in a %d px window the page frame is %s px wide, want %d' % (tag, iw, fr.get('w'), FRAME_W))
    st = fr.get('status') or {}
    if fr.get('heroIn') != 'top' or fr.get('calIn') != 'top' or not st.get('inTop'):
        fails.append('%s: the hero (%s), the status line (in the top block %s) and the calendar (%s) must be in the top block'
                     % (tag, fr.get('heroIn'), st.get('inTop'), fr.get('calIn')))
    if fr.get('tradesIn') != 'rest' or fr.get('ownIn') != 'rest':
        fails.append('%s: the trade list (%s) and the own folds (%s) must be in the rest of the frame' % (tag, fr.get('tradesIn'), fr.get('ownIn')))
    top, side, rest, trd = fr.get('top') or {}, fr.get('side') or {}, fr.get('rest') or {}, fr.get('trades') or {}
    if iw >= FRAME_TWO_COL:
        if fr.get('disp') != 'grid':
            fails.append('%s: from %d px the page frame is a two-column grid, it is display %r' % (tag, FRAME_TWO_COL, fr.get('disp')))
        if fr.get('listIn') != 'side':
            fails.append("%s: from %d px the strategy list must be in the frame's right-hand panel [data-lgframe-side], it is in %r"
                         % (tag, FRAME_TWO_COL, fr.get('listIn')))
        if not (top.get('shown') and side.get('shown') and rest.get('shown')):
            fails.append('%s: a part of the frame is not drawn (top %s, side %s, rest %s)' % (tag, top, side, rest))
        else:
            if side['l'] < top['r'] + 1:
                fails.append('%s: the list panel (left %s) is not to the right of the top block (right %s)' % (tag, side['l'], top['r']))
            if abs(side['t'] - top['t']) > 2:
                fails.append('%s: the list panel (top %s) is not level with the top block (top %s)' % (tag, side['t'], top['t']))
            ls = fr.get('list') or {}
            if fr.get('listIn') == 'side' and (ls.get('t') is None or ls['t'] < side['t'] - 1 or ls['t'] > side['t'] + 24):
                fails.append('%s: the strategy list (top %s) does not start at the top of its panel (top %s)' % (tag, ls.get('t'), side['t']))
            if side['b'] > top['b'] + 2:
                fails.append('%s: the list panel (bottom %s) is taller than the top block (bottom %s): it must never make the page taller'
                             % (tag, side['b'], top['b']))
            if rest['t'] < max(top['b'], side['b']) - 1:
                fails.append('%s: the trade list part (top %s) does not start under both the top block (bottom %s) and the list panel (bottom %s)'
                             % (tag, rest['t'], top['b'], side['b']))
            if (abs(rest['l'] - top['l']) > 2 or abs(rest['r'] - side['r']) > 2 or not trd.get('shown')
                    or trd['l'] > top['l'] + 2 or trd['r'] < side['r'] - 2):
                fails.append('%s: the trade list does not span the full frame width under both (trade list %s to %s, rest %s to %s, top block from %s, '
                             'panel to %s)' % (tag, trd.get('l'), trd.get('r'), rest['l'], rest['r'], top['l'], side['r']))
            si = fr.get('sideIn') or {}
            if fr.get('sideInOverflow') not in ('auto', 'scroll') or si.get('b') is None or si['b'] > side['b'] + 1:
                fails.append('%s: the list does not scroll inside its panel (overflow %r, content bottom %s, panel bottom %s)'
                             % (tag, fr.get('sideInOverflow'), si.get('b'), side['b']))
        if fr.get('sidePos') == 'sticky' or fr.get('qbxSidePos') == 'sticky':
            fails.append('%s: the list panel is sticky (panel %r, list section %r): step 12 draws it beside the top block, never sticky'
                         % (tag, fr.get('sidePos'), fr.get('qbxSidePos')))
    else:
        if fr.get('disp') == 'grid':
            fails.append('%s: under %d px the page frame is one column, but it is a grid (%s)' % (tag, FRAME_TWO_COL, fr.get('cols')))
        cal, box = fr.get('cal') or {}, fr.get('qbxSide') or {}
        if fr.get('listIn') != 'side' or not cal or not box or not trd or box['t'] < cal['b'] - 1 or box['b'] > trd['t'] + 1:
            fails.append('%s: under %d px the strategy list (in %s, %s to %s) must sit between the calendar (bottom %s) and the trade list (top %s)'
                         % (tag, FRAME_TWO_COL, fr.get('listIn'), box.get('t'), box.get('b'), cal.get('b'), trd.get('t')))
    # the status line, directly under the hero
    hero, pills, sb = fr.get('hero') or {}, fr.get('pills') or {}, st.get('box') or {}
    if st.get('n') != 1:
        fails.append('%s: want one status line [data-lgstatus="qb"], the page has %s' % (tag, st.get('n')))
    else:
        if not st.get('refresh'):
            fails.append('%s: the status line has no Refresh button [data-qqqrefresh] in it' % tag)
        if (not st.get('afterHero') or not sb.get('shown') or not hero or sb['t'] < hero['b'] - 1 or sb['t'] - hero['b'] > STATUS_GAP_MAX
                or (pills and sb['b'] > pills['t'] + 1)):
            fails.append('%s: the status line (top %s, bottom %s, right after the hero %s) is not directly under the hero (bottom %s) and above the '
                         'range pills (top %s)' % (tag, sb.get('t'), sb.get('b'), st.get('afterHero'), hero.get('b'), pills.get('t')))
        lh, h = st.get('lh'), st.get('lineH')
        if not lh or h is None or h / lh > STATUS_LINES_MAX + 0.2 or h / lh < 0.8:
            fails.append('%s: the status line is %s px tall at %s px a line: want one or two lines (%r)' % (tag, h, lh, (st.get('text') or '')[:80]))
    # the chart foot, under the chart, holding the caption and the key
    fo = fr.get('foot') or {}
    fb, ch, stb = fo.get('box') or {}, fo.get('chart'), fr.get('stats')
    if fo.get('n') != 1 or not fo.get('inChart'):
        fails.append('%s: want one chart foot [data-lgchartfoot="qb"] in the chart section (%s on the page, in the chart section %s)'
                     % (tag, fo.get('n'), fo.get('inChart')))
    else:
        under = ch if ch else fo.get('prev')
        if (ch and not fo.get('prevIsChart')) or fb.get('t') is None or not under or fb['t'] < under['b'] - 1:
            fails.append('%s: the chart foot (top %s) does not come right after the chart box (bottom %s, right after it %s)'
                         % (tag, fb.get('t'), (under or {}).get('b'), fo.get('prevIsChart')))
        if stb and fb.get('b') is not None and fb['b'] > stb['t'] + 1:
            fails.append('%s: the chart foot (bottom %s) runs into the stats strip (top %s)' % (tag, fb['b'], stb['t']))
        if fo.get('caps') != 1 or fo.get('capsInFoot') != 1:
            fails.append('%s: the chart caption is not in the chart foot (%s captions on the page, %s in the foot)' % (tag, fo.get('caps'), fo.get('capsInFoot')))
        if fo.get('keys') != fo.get('keysInFoot'):
            fails.append("%s: the chart's key is not in the chart foot (%s keys on the page, %s in the foot)" % (tag, fo.get('keys'), fo.get('keysInFoot')))
    if not fo.get('ruleFs'):
        fails.append("%s: the shared chart foot rule (.lg-chart-cap) is not in the page's css (a rule in the shared css was swallowed)" % tag)
    elif fo.get('capFs') != fo.get('ruleFs') or fo.get('sharedFs') != fo.get('ruleFs'):
        fails.append('%s: the chart caption lost the shared foot style (.qbx-chart-cap reads %s, the foot caption %s, the shared .lg-chart-cap rule says %s)'
                     % (tag, fo.get('capFs'), fo.get('sharedFs'), fo.get('ruleFs')))
    # the Filters row, right after the list header, closed
    fl = fr.get('filt') or {}
    if fl.get('n') != 1 or not fl.get('inList') or not fl.get('afterHd'):
        fails.append("%s: the strategy list's Filters row [data-lgfilters=\"qb\"] is missing or not right after the list header (%s on the page, in the "
                     "list %s, after the header %s)" % (tag, fl.get('n'), fl.get('inList'), fl.get('afterHd')))
    else:
        if fl.get('exp') != 'false' or fl.get('hiddenAttr') is not True or fl.get('bodyShown'):
            fails.append('%s: the Filters row is not closed when first drawn (aria-expanded %s, body hidden %s, body shown %s)'
                         % (tag, fl.get('exp'), fl.get('hiddenAttr'), fl.get('bodyShown')))
        if fl.get('ctl') != 'qb-filters' or fl.get('bodyId') != 'qb-filters':
            fails.append('%s: the Filters button controls %r, its body is #%s (want qb-filters both)' % (tag, fl.get('ctl'), fl.get('bodyId')))
        if fl.get('sum') != 'none' or not fl.get('none'):
            fails.append("%s: the Filters row reads %r with the body line %r: this board has nothing to filter, so 'none' and the no-filters line"
                         % (tag, fl.get('sum'), fl.get('none')))


def _judge_filters_run(tag, rec, fails):
    """The interaction run's Filters row: closed with nothing stored, a tap opens it in place (stored '1'), a redraw keeps it open, a second tap closes it
    (stored '0'), a redraw keeps it closed."""
    t = '%s: the Filters row' % tag
    if not rec:
        fails.append('%s was not tapped (no record)' % t)
        return
    if rec.get('threw'):
        fails.append('%s: the probe threw -- %s' % (t, _first(rec['threw'])))
        return
    b, o, rl, c, cr = (rec.get(x) or {} for x in ('before', 'open', 'reload', 'closed', 'closedReload'))
    if b.get('missing') or not o:
        fails.append('%s is not on the page to tap (%s)' % (t, b))
        return
    if b.get('exp') != 'false' or b.get('shown') or b.get('stored') is not None:
        fails.append('%s does not start closed with nothing stored (%s)' % (t, b))
    if o.get('exp') != 'true' or not o.get('shown') or o.get('hiddenAttr') or o.get('stored') != '1':
        fails.append('%s did not open on a tap (aria-expanded %s, body shown %s, hidden %s, stored %r)'
                     % (t, o.get('exp'), o.get('shown'), o.get('hiddenAttr'), o.get('stored')))
    if not rec.get('sameList'):
        fails.append('%s: the tap redrew the strategy list (it opens in place)' % t)
    if 'no filters' not in (o.get('text') or ''):
        fails.append('%s opened without its no-filters line (%r)' % (t, (o.get('text') or '')[:120]))
    if rl.get('exp') != 'true' or not rl.get('shown'):
        fails.append('%s is not remembered: a redraw (all a reload has) finds it %s (aria-expanded %s)' % (t, 'shown' if rl.get('shown') else 'closed', rl.get('exp')))
    if c.get('exp') != 'false' or c.get('shown') or c.get('stored') != '0':
        fails.append('%s did not close on a second tap (aria-expanded %s, body shown %s, stored %r)' % (t, c.get('exp'), c.get('shown'), c.get('stored')))
    if cr.get('exp') != 'false' or cr.get('shown'):
        fails.append('%s opens again by itself after a redraw (aria-expanded %s)' % (t, cr.get('exp')))


def _flag_problems(tag, r, plain, fails):
    """?oldboards=1 draws the NEW page: the fold layout (qbx-lg6, the own box, the fold buttons and boxes), none of the removed previous board's markers
    or old disclosures, the same markup skeleton, page order, shared calendar / strategy list and trade list frame as the plain page for the same case,
    and LEDGER_OLDBOARDS is not a name in the page."""
    o = ((r.get('s11') or {}).get('shape')) or {}
    p = ((plain.get('s11') or {}).get('shape')) or {}
    if not o.get('lg6') or not o.get('ownBox') or not o.get('foldBtns') or not o.get('foldBoxes'):
        fails.append('%s: ?oldboards=1 does not draw the new page (qbx-lg6 %s, own box %s, %s fold buttons, %s fold boxes)'
                     % (tag, o.get('lg6'), o.get('ownBox'), o.get('foldBtns'), o.get('foldBoxes')))
    if o.get('modelToggle') or o.get('statusInChart'):
        fails.append('%s: ?oldboards=1 draws an old disclosure or the old status strip under the chart (model toggle %s, strip in chart %s)'
                     % (tag, o.get('modelToggle'), o.get('statusInChart')))
    sk, pk = o.get('skel') or {}, p.get('skel') or {}
    if not sk or [sk.get('n'), sk.get('h')] != [pk.get('n'), pk.get('h')]:
        fails.append('%s: the markup behind ?oldboards=1 is not the plain page (%s elements / hash %s, plain %s / %s)'
                     % (tag, sk.get('n'), sk.get('h'), pk.get('n'), pk.get('h')))
    old, pold = r.get('old') or {}, plain.get('old') or {}
    if old.get('oldMarks'):
        fails.append('%s: markers of the removed previous board are in the page: %s' % (tag, ', '.join(old['oldMarks'])))
    if old.get('flagConst') != 'undefined':
        fails.append('%s: LEDGER_OLDBOARDS is still a name in the page (typeof %s)' % (tag, old.get('flagConst')))
    if not old.get('sharedCalFold') or not old.get('sharedList'):
        fails.append('%s: ?oldboards=1 does not draw the shared calendar fold and strategy list (calendar fold %s, list %s)'
                     % (tag, old.get('sharedCalFold'), old.get('sharedList')))
    if not old.get('order') or old.get('order') != pold.get('order'):
        fails.append('%s: ?oldboards=1 changed the page order: %r (plain %r)' % (tag, old.get('order'), pold.get('order')))
    t0 = r.get('tl') or {}
    if t0.get('frames') != 1 or t0.get('oldSeg') or t0.get('oldRows'):
        fails.append('%s: ?oldboards=1 does not draw the one shared trade list frame (frames %s, old switch %s, old rows %s)'
                     % (tag, t0.get('frames'), t0.get('oldSeg'), t0.get('oldRows')))


def _static_breakpoints(path):
    """One set of breakpoints: every media / container query that styles this board uses only the house widths (600 phone, 740 compact, 800 / 920 list
    cells, 1100 rail). Read from the source text."""
    try:
        src = io.open(path, encoding='utf-8', newline='').read()
    except OSError as e:
        return ['the page source could not be read for the breakpoint check: %s' % e]
    bad = []
    for m in re.finditer(r'@(media|container)\b([^{;]*)\{', src):
        i, depth = m.end(), 1
        while i < len(src) and depth:
            c = src[i]
            depth += (c == '{') - (c == '}')
            i += 1
        body = src[m.start():i]
        if not re.search(r'\.(qb|qbx|qe)-|qqq|data-qb', body):
            continue
        for num in re.findall(r'(?:min|max)-(?:width|inline-size)\s*:\s*(\d+(?:\.\d+)?)\s*px', m.group(2)):
            if int(float(num)) not in S11_HOUSE:
                bad.append('@%s%s styles this board at %s px, which is no house width %s' % (m.group(1), m.group(2).rstrip(), num, S11_HOUSE))
    return bad


KEY_WORDS = ['book only = order never reached Webull', 'book price = no Webull fill price']


def _static_wording(path):
    """Wording the review fixed (L4, L6), read from the source: the chart key says BOOK ONLY and BOOK PRICE apart, and nothing says Webull has no
    paper API (the Orders mode sends to the Webull paper account)."""
    try:
        src = io.open(path, encoding='utf-8', newline='').read()
    except OSError as e:
        return ['the page source could not be read for the wording check: %s' % e]
    bad = ['the chart key no longer says %r' % k for k in KEY_WORDS if k not in src]
    if re.search(r'no paper API', src, re.I):
        bad.append("the page still says Webull has no paper API (the Rails fold): the Orders mode sends to the Webull paper account")
    return bad


def find_chrome():
    cands = [os.path.join('C:' + os.sep, 'Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
             os.path.join('C:' + os.sep, 'Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe')]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def make_handler(root, alt_index):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            if alt_index and (self.path == '/index.html' or self.path.startswith('/index.html?')):
                try:
                    with open(alt_index, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError as e:
                    self.send_error(500, str(e))
                return
            super().do_GET()

        def log_message(self, *a):
            pass
    return H


def qe_pnl_of(t):
    """The board's P&L of record for one trade (index.html qePnlOf): pnl_record, else the book
    pnl, else the re-priced real_pnl, else 0. A null or empty field is missing, never $0."""
    for k in ('pnl_record', 'pnl', 'real_pnl'):
        v = t.get(k)
        if v is None or v == '':
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v == v and v not in (float('inf'), float('-inf')):
            return v
    return 0.0


FAMILY = {'ORB': 'ORB', 'ENGUQ': 'ENGU-Q', 'NOISE': 'NOISE'}
CURRENT_RUN = {'ORB': '#314', 'ENGUQ': '#335', 'NOISE': '#382'}
NOISE_SWITCH = '2026-09-24'   # NOISE #304 -> #382 (index.html QE_LEG_VERSIONS)
TID_RE = re.compile(r'^([A-Za-z0-9_]+)-\d{8}T\d{6}Z-[LS]$')


def expected_leg_name(t):
    """The strategy name a trade row must show, worked out here and not read off the page: the
    run in the trade id when the id carries one (NOISE_304-... -> #304), else NOISE before the
    09-24 switch -> #304, else the leg's current run."""
    leg = str(t.get('leg') or '')
    fam = FAMILY.get(leg, leg)
    m = TID_RE.match(str(t.get('trade_id') or ''))
    dg = re.search(r'_(\d+)$', m.group(1)) if m else None
    if dg:
        return '%s #%s' % (fam, dg.group(1))
    day = str(t.get('entry_ts') or t.get('exit_ts') or '')[:10]
    if leg == 'NOISE' and re.match(r'^\d{4}-\d{2}-\d{2}$', day) and day < NOISE_SWITCH:
        return 'NOISE #304'
    return '%s %s' % (fam, CURRENT_RUN.get(leg, ''))


def money(v):
    return ('-' if v < 0 else '') + '${:,.2f}'.format(abs(v))


def _close_day(t):
    """index.html qeTradeDate: the New York day a trade closed (exit_ts), else its entry day."""
    d = str(t.get('exit_ts') or '')[:10] or str(t.get('entry_ts') or '')[:10]
    return d if re.match(r'^\d{4}-\d{2}-\d{2}$', d) else None


def _is_shadow(t):
    return t.get('shadow') is True or str(t.get('shadow') or '').lower() == 'true' or str(t.get('layer') or '').lower() == 'shadow'


def _js_round(x):
    return int(math.floor(x + 0.5))


def signed(v):
    """index.html ledgerSigned: '+$1.00' / '-$1.00' (a zero reads '+$0.00')."""
    return ('+' if v >= 0 else '-') + money(abs(v))


def short_money(v):
    """index.html ledgerShortMoney without its sign: $276, $1.2k, $12k."""
    a = abs(v)
    if a >= 10000:
        return '$%dk' % _js_round(a / 1000)
    if a >= 1000:
        s = '%.1f' % (a / 1000)
        return '$' + (s[:-2] if s.endswith('.0') else s) + 'k'
    return '$%d' % _js_round(a)


def _fin(v):
    """index.html qeFinRec: a finite number, else None (null / '' / text / NaN are missing)."""
    if v is None or v == '':
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if (v == v and v not in (float('inf'), float('-inf'))) else None


def _range_rows(trades, cutoff=None):
    """The trades the stats count: shadow rows left out, closed on or after `cutoff`, in exit order."""
    rows = [t for t in trades if not _is_shadow(t)]
    if cutoff:
        rows = [t for t in rows if (_close_day(t) or '') >= cutoff]
    return sorted(rows, key=lambda t: str(t.get('exit_ts') or t.get('entry_ts') or ''))


def expected_more(trades, cutoff=None):
    """More stats rows worked out here: {'Group|Label': value text}, or {} when the range is empty."""
    rows = _range_rows(trades, cutoff)
    if not rows:
        return {}
    vals = [qe_pnl_of(t) for t in rows]
    net = run = peak = dd = 0.0
    for v in vals:
        net += v
        run += v
        peak = max(peak, run)
        dd = max(dd, peak - run)
    broker = book = 0.0
    bo = wb = 0
    for t in rows:
        if t.get('book_only'):
            bo += 1
        else:
            broker += qe_pnl_of(t)
            a, r = _fin(t.get('pnl')), _fin(t.get('real_pnl'))
            book += a if a is not None else (r if r is not None else 0.0)
        if str(t.get('pnl_record_src') or '') == 'webull':
            wb += 1
    n = len(rows)
    # the current streak, walked back from the newest exit ($0 trades skipped), as ledgerStats counts it
    sn = sd = 0
    for v in reversed(vals):
        if not v:
            continue
        d = 1 if v > 0 else -1
        if not sn:
            sn, sd = 1, d
        elif d == sd:
            sn += 1
        else:
            break
    streak = '--' if not sn else '%d %s' % (sn, ('wins' if sn > 1 else 'win') if sd > 0 else ('losses' if sn > 1 else 'loss'))
    return {'Returns|Net P&L': signed(net), 'Risk|Max drawdown': money(dd), 'Risk|Current streak': streak,
            'Account|Broker made': signed(broker), 'Account|Book figure': signed(book),
            'Account|Book-only trades': '%d of %d' % (bo, n),
            'Account|Fill coverage': '%d of %d (%d%%)' % (wb, n, _js_round(wb / n * 100)),
            'Best and worst trade|Best trade': signed(max(vals)),
            'Best and worst trade|Worst trade': signed(min(vals))}


def expected_stats(trades, cutoff=None):
    """The four LEDGER tiles worked out here, not read off the page: the trades that closed on or after
    `cutoff` (None = all), shadow rows left out, walked in exit order at the P&L of record. A $0 trade is
    neither a win nor a loss. Returns {key: (value text, sub text)}."""
    rows = _range_rows(trades, cutoff)
    vals = [qe_pnl_of(t) for t in rows]
    n = len(vals)
    w = sum(1 for v in vals if v > 0)
    l = sum(1 for v in vals if v < 0)
    f = n - w - l
    gw = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    run = peak = dd = 0.0
    for v in vals:
        run += v
        peak = max(peak, run)
        dd = max(dd, peak - run)
    days = len(set(d for d in (_close_day(t) for t in rows) if d))
    if not n:
        return {'winrate': ('--', ''), 'pf': ('--', ''), 'maxdd': ('--', ''), 'trades': ('0', '')}
    wr = ('%d%%' % _js_round(w / (w + l) * 100)) if (w + l) else '--'
    pf = '--' if (not gw and not gl) else ('%.2f' % (gw / gl) if gl > 0 else 'no losses')
    return {'winrate': (wr, '%d W · %d L' % (w, l) + (' · %d even' % f if f else '')),
            'pf': (pf, ('%s won · %s lost' % (short_money(gw), short_money(gl))) if (gw or gl) else ''),
            'maxdd': (money(dd), 'worst drop from a high' if dd > 0 else ''),
            'trades': (str(n), 'over %d day%s' % (days, '' if days == 1 else 's'))}


def month_won(trades, month):
    """The calendar's '% won' for one month: wins / (wins + losses), a $0 trade is neither."""
    vals = [qe_pnl_of(t) for t in trades if (_close_day(t) or '').startswith(month)]
    w = sum(1 for v in vals if v > 0)
    l = sum(1 for v in vals if v < 0)
    return _js_round(w / (w + l) * 100) if (w + l) else None


def _zero_doc(fixture):
    """The fixture with its newest September loss turned into a $0 trade (P&L of record 0)."""
    doc = json.loads(json.dumps(fixture))
    for t in doc.get('trades_all') or []:
        if (_close_day(t) or '').startswith('2026-09') and qe_pnl_of(t) < 0:
            t['pnl_record'] = 0.0
            t['pnl'] = '0.0'
            break
    return doc


def _cutoff(range_key, today=STAT_TODAY):
    """index.html ledgerCutoff: the first New York day a range keeps (None = ALL)."""
    if range_key == 'TODAY':
        return today
    if range_key == 'YTD':
        return today[:4] + '-01-01'
    days = {'1W': 7, '1M': 30, '3M': 90}.get(range_key)
    if not days:
        return None
    y, m, d = map(int, today.split('-'))
    import datetime
    return (datetime.date(y, m, d) - datetime.timedelta(days=days)).isoformat()


SHADOW_PNL = 5000.0


def _shadow_doc(fixture):
    """The fixture plus one shadow row worth $5,000 that closed today: it must change no stat."""
    doc = json.loads(json.dumps(fixture))
    tr = doc.get('trades_all') or []
    last = max(tr, key=lambda t: str(t.get('exit_ts') or ''))
    s = json.loads(json.dumps(last))
    s.update({'shadow': True, 'pnl_record': SHADOW_PNL, 'pnl': str(SHADOW_PNL), 'real_pnl': str(SHADOW_PNL),
              'exit_ts': STAT_TODAY + ' 15:50:00', 'trade_id': 'NOISE-20261005T195000Z-L', 'book_only': False})
    tr.append(s)
    return doc


# LEDGER unify steps 7 + 10: the shared calendar and the shared strategy list, recomputed here from the fixture (never read off
# the page). The calendar takes the chosen range's trades at the P&L of record on their close day; the list's rows are the legs
# the board names (ORB #314, ENGU-Q #335, NOISE #382), the range's P&L of record, trades and win rate.
LIST_GROUPS = ['book', 'retired', 'shadow']
BOOK_NAMES = ['ORB #314', 'NOISE #382']       # the rows under BOOK, run numbers included (ENGU-Q #335 is retired in this doc)
RETIRED_NAME = 'ENGU-Q #335'
BOOK_NAMES_LIVE = ['ORB #314', 'ENGU-Q #335', 'NOISE #382']   # while ENGU-Q holds a position it is a BOOK leg again
LEG_KEYS = [('ORB', 'ORB #314'), ('ENGUQ', 'ENGU-Q #335'), ('NOISE', 'NOISE #382')]
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
          'December']
RANGE_WORD = {'TODAY': 'today', '1W': 'past week', '1M': 'past month', '3M': 'past 3 months', 'YTD': 'year to date',
              'ALL': 'all time'}
LIST_VH_MAX = 1.0   # phone: the trade list (the History section) starts within this many viewport heights of the board top
PHONE_ROW_MAX_H = 46  # phone: one line per strategy row (padding 9 + 9, one 12 px line)
SHADOW_NOTE = 'None are in the box'
NOTE_MARK = 'was #304'          # NOISE's note under its row: 'since Sep 24 · was #304 · KEEL v12 ...'
OTHER_NAME = 'Other legs'       # the list's row for trades of a strategy the board has no row for
OTHER_LEG = 'TTM'


def _grey(css):
    """'rgb(r, g, b)' / 'rgba(r, g, b, a)' with r = g = b (MONO has no hue); a clear colour passes."""
    p = [float(x) for x in re.findall(r'[\d.]+', css or '')]
    if len(p) >= 4 and p[3] == 0:
        return True
    return len(p) >= 3 and p[0] == p[1] == p[2]


def _money_val(txt):
    """'+$41.11' / '-$1,234.50' -> float, else None."""
    m = re.match(r'^([+-])\$([\d,]+\.\d\d)$', (txt or '').strip())
    return None if not m else (-1 if m.group(1) == '-' else 1) * float(m.group(2).replace(',', ''))


def expected_cal(trades, cutoff=None):
    """{day: {'v': money, 'n': trades, 'w': wins, 'l': losses}} -- what the calendar draws: the range's trades (shadow
    rows left out) at the P&L of record on the New York day each one closed. A $0 trade is neither a win nor a loss."""
    days = {}
    for t in _range_rows(trades, cutoff):
        d = _close_day(t)
        if not d:
            continue
        c = days.setdefault(d, {'v': 0.0, 'n': 0, 'w': 0, 'l': 0})
        v = qe_pnl_of(t)
        c['v'] += v
        c['n'] += 1
        if v > 0:
            c['w'] += 1
        elif v < 0:
            c['l'] += 1
    return days


def expected_caveats(trades, feed_days, cutoff=None):
    """{day: {reasons}} -- the days the calendar hatches: an exit priced from the 1-minute tape (no book pnl, a re-priced one),
    a failed parity check (the NinjaTrader one for a mirrored row, else engine against broker), a book-only trade, or a feed
    flagged invalid (that one needs no trade on the day)."""
    out = {}
    for t in _range_rows(trades, cutoff):
        d = _close_day(t)
        if not d:
            continue
        if _fin(t.get('pnl')) is None and _fin(t.get('real_pnl')) is not None:
            out.setdefault(d, set()).add('tape')
        nt = str(t.get('signal_source') or '').lower() == 'ninjatrader'
        if (t.get('parity_ok') is False) if nt else (t.get('broker_parity_ok') is False):
            out.setdefault(d, set()).add('parity')
        if t.get('book_only'):
            out.setdefault(d, set()).add('book')
    for f in feed_days or []:
        d = f.get('date')
        if d and f.get('valid') is False and (not cutoff or d >= cutoff):
            out.setdefault(d, set()).add('feed')
    return out


def cal_month_figs(days, month):
    """(money, trades, wins, losses) of one month of expected_cal()."""
    v = n = w = l = 0
    for d, c in days.items():
        if d.startswith(month):
            v += c['v']
            n += c['n']
            w += c['w']
            l += c['l']
    return v, n, w, l


def cal_sum_text(v, n, w, l):
    """The summary beside the month title: '-$53.65 · 3 trades · 0% won' (no win rate without a win or a loss)."""
    if not n:
        return 'no trades this month'
    s = '%s · %d trade%s' % (signed(round(v, 2)), n, '' if n == 1 else 's')
    if w + l:
        s += ' · %d%% won' % _js_round(w / (w + l) * 100)
    return s


def cal_weeks(days, month):
    """One entry per Sunday-first week of the month: {'v', 'n'} for a week with trades, None for an empty week."""
    import calendar
    import datetime
    y, m = int(month[:4]), int(month[5:7])
    first = (datetime.date(y, m, 1).weekday() + 1) % 7      # Sunday = 0
    nweeks = (first + calendar.monthrange(y, m)[1] + 6) // 7
    weeks = [None] * nweeks
    for d, c in days.items():
        if d.startswith(month):
            i = (int(d[8:10]) + first - 1) // 7
            w = weeks[i] or {'v': 0.0, 'n': 0}
            w['v'] += c['v']
            w['n'] += c['n']
            weeks[i] = w
    return weeks


def short_signed(v):
    """index.html ledgerShortMoney with its sign: '+$1.2k' / '-$47'."""
    return ('-' if v < 0 else '+') + short_money(v)


def _row_figs(vals):
    """One list row's figures from its trades' P&L of record: the signed total ('—' with no trade), 'N trades · X% won'
    (a $0 trade is neither a win nor a loss), the total and the trade count."""
    n = len(vals)
    net = round(sum(vals), 2)
    w = sum(1 for v in vals if v > 0)
    l = sum(1 for v in vals if v < 0)
    v2 = '%d trade%s' % (n, '' if n == 1 else 's') + ((' · %d%% won' % _js_round(w / (w + l) * 100)) if (w + l) else '')
    return {'value': signed(net) if n else '—', 'value2': v2, 'net': net, 'n': n}


def expected_leg_figs(trades, cutoff=None):
    """{row name: {'value', 'value2', 'net', 'n'}} -- each leg's range: its P&L of record (signed), its trades and win rate."""
    rows = _range_rows(trades, cutoff)
    return dict((nm, _row_figs([qe_pnl_of(t) for t in rows if t.get('leg') == key])) for key, nm in LEG_KEYS)


def expected_other_figs(trades, cutoff=None):
    """The 'Other legs' row: the range's trades of a strategy the board has no row for (not ORB, ENGU-Q or NOISE), else None."""
    keys = set(k for k, _ in LEG_KEYS)
    f = _row_figs([qe_pnl_of(t) for t in _range_rows(trades, cutoff) if t.get('leg') not in keys])
    return f if f['n'] else None


def expected_list_count(trades, cutoff, range_key):
    """The list's header figure: the range's P&L of record and its word, or the board's 'no trades' line."""
    rows = _range_rows(trades, cutoff)
    if not rows:
        return {'TODAY': 'no trades closed today', 'YTD': 'no trades closed this year'}.get(range_key) \
            or ('no trades closed in the ' + RANGE_WORD[range_key])
    return '%s · %s' % (signed(round(sum(qe_pnl_of(t) for t in rows), 2)), RANGE_WORD[range_key])


def expected_shadow_rows(trades, cutoff=None):
    """{row name: signed money} of the no-order shadow rows in the range (the list's Shadow group, never counted)."""
    out = {}
    for t in trades:
        if not _is_shadow(t):
            continue
        d = _close_day(t) or ''
        if cutoff and d < cutoff:
            continue
        nm = expected_leg_name(t)
        out[nm] = out.get(nm, 0.0) + qe_pnl_of(t)
    return dict((k, signed(round(v, 2))) for k, v in out.items())


def _positions(doc):
    """{leg: (Long or Short, shares, entry price)} of the doc's open positions (the status doc's own positions map)."""
    out = {}
    for k, v in (doc.get('positions') or {}).items():
        try:
            out[k] = ('Long' if v.get('side') == 'long' else 'Short', int(float(v.get('shares'))), float(v.get('entry_px')))
        except (TypeError, ValueError, AttributeError):
            pass
    return out


def _cal_open_want(vp, cal_open):
    """open on a laptop, closed on a phone until a viewer chooses; a stored choice wins."""
    if cal_open in ('0', '1'):
        return cal_open == '1'
    return vp == 'laptop'


def _judge_cal(tag, c, vp, theme, doc, cutoff, want_month, open_want, today, fails):
    """The shared calendar under Activity: fold and summary, the month, every day cell, the caveat hatching, the week cells and
    the arrows -- all against the fixture's own trades at the P&L of record on their close day."""
    c = c or {}
    if c.get('fold') is None:
        fails.append('%s: no shared calendar ([data-lgcalfold="qb"]) under Activity' % tag)
        return
    if c.get('oldDays') or c.get('oldNav'):
        fails.append('%s: the old month grid is still drawn beside the shared calendar' % tag)
    trades = doc.get('trades_all') or []
    days = expected_cal(trades, cutoff)
    months = sorted(set(d[:7] for d in days))
    mo = want_month if want_month in months else (months[-1] if months else today[:7])
    y, m = int(mo[:4]), int(mo[5:7])
    tot, n, w_, l_ = cal_month_figs(days, mo)
    if (c.get('fold') == 'true') != open_want or (c.get('panel') == 'shown') != open_want:
        fails.append('%s: the calendar fold reads aria-expanded %r with its panel %s, want %s (open on a laptop, closed on a phone '
                     'until chosen)' % (tag, c.get('fold'), c.get('panel'), 'open' if open_want else 'closed'))
    ft = c.get('foldText') or ''
    if '%s %d' % (MONTHS[m - 1], y) not in ft or (n and signed(round(tot, 2)) not in ft):
        fails.append("%s: the calendar fold reads %r, want the month %s %d and its total %s"
                     % (tag, ft, MONTHS[m - 1], y, signed(round(tot, 2)) if n else '(no trades)'))
    if not open_want:
        return
    if c.get('month') != mo or c.get('title') != '%s %d' % (MONTHS[m - 1], y):
        fails.append('%s: the calendar shows %r (%r), want %s' % (tag, c.get('month'), c.get('title'), mo))
        return
    want_sum = cal_sum_text(tot, n, w_, l_)
    if c.get('sum') != want_sum:
        fails.append('%s: the calendar month total reads %r, the fixture says %r (the sum of that month\'s trades at the P&L '
                     'of record)' % (tag, c.get('sum'), want_sum))
    nav = dict((k, dis) for k, dis in (c.get('nav') or []))
    want_nav = {'-1': (not months) or mo == months[0], '1': (not months) or mo == months[-1]}
    if nav != want_nav:
        fails.append('%s: the month arrows read disabled %r (earlier / later), want %r (disabled at the first and last month '
                     'with trades)' % (tag, nav, want_nav))
    got = dict((x['ds'], x) for x in (c.get('days') or []) if x.get('traded'))
    exp = dict((d, v) for d, v in days.items() if d.startswith(mo))
    if sorted(got) != sorted(exp):
        fails.append('%s: the calendar draws trades on %s, the fixture has them on %s'
                     % (tag, sorted(d[8:] for d in got), sorted(d[8:] for d in exp)))
    page_sum = 0.0
    for d, v in exp.items():
        x = got.get(d)
        if not x:
            continue
        if x.get('m') != short_signed(v['v']) or x.get('n') != '%d tr' % v['n']:
            fails.append('%s: calendar day %s reads %r / %r, the fixture says %s / %d tr'
                         % (tag, d, x.get('m'), x.get('n'), short_signed(v['v']), v['n']))
        tm = re.search(r': ([+-]\$[\d,]+\.\d\d),', x.get('title') or '')
        if not tm or tm.group(1) != signed(round(v['v'], 2)):
            fails.append('%s: calendar day %s says %r, the fixture says %s'
                         % (tag, d, x.get('title'), signed(round(v['v'], 2))))
        else:
            page_sum += _money_val(tm.group(1))
        if (x.get('up'), x.get('down')) != (v['v'] >= 0, v['v'] < 0):
            fails.append('%s: calendar day %s is drawn %s' % (tag, d, 'up' if x.get('up') else 'down' if x.get('down') else 'flat'))
    if exp and abs(page_sum - round(tot, 2)) > 0.011:
        fails.append("%s: the day cells print %s, the month total says %s" % (tag, signed(round(page_sum, 2)), signed(round(tot, 2))))
    cav = expected_caveats(trades, doc.get('feed_days'), cutoff)
    want_cav = sorted(int(d[8:10]) for d in cav if d.startswith(mo))
    got_cav = sorted(x['d'] for x in c.get('days') or [] if x.get('cav'))
    if got_cav != want_cav:
        fails.append('%s: the hatched caveat days are %s, the fixture says %s (tape-priced exit, failed parity, book only, '
                     'feed invalid)' % (tag, got_cav, want_cav))
    unhatched = [x['d'] for x in c.get('days') or [] if x.get('cav') and not (x.get('hatch') and x.get('dot'))]
    if unhatched:
        fails.append('%s: caveat days %s are marked but not hatched amber with the dot' % (tag, unhatched))
    ew, gw = cal_weeks(days, mo), c.get('weeks') or []
    if len(gw) != len(ew):
        fails.append('%s: the calendar has %d week cells, want %d' % (tag, len(gw), len(ew)))
    else:
        for i, (e, g) in enumerate(zip(ew, gw)):
            if e is None:
                if g.get('title') or g.get('m'):
                    fails.append('%s: calendar week %d has no trades but reads %r (an empty week is empty, never $0)'
                                 % (tag, i + 1, g.get('m')))
            else:
                want_t = 'week: %s, %d trade%s' % (signed(round(e['v'], 2)), e['n'], '' if e['n'] == 1 else 's')
                if g.get('title') != want_t or g.get('m') != short_signed(e['v']) or g.get('n') != '%d tr' % e['n']:
                    fails.append('%s: calendar week %d reads %r / %r, the fixture says %r' % (tag, i + 1, g.get('title'), g.get('m'), want_t))
    if theme == 'mono':
        bad = [x['mColor'] for x in c.get('days') or [] if x.get('mColor') and not _grey(x['mColor'])] \
            + [s for s in c.get('sumColors') or [] if not _grey(s)]
        if bad:
            fails.append('%s: the calendar draws colour under MONO (MONO has no hue): %s' % (tag, bad[:3]))
    if c.get('gridW') and c.get('box') and c['gridW'] > c['box']['w'] + 1:
        fails.append('%s: the calendar grid (%s px) is wider than its panel (%s px)' % (tag, c['gridW'], c['box']['w']))


def _judge_list(tag, lg, vp, theme, doc, cutoff, range_key, retired_open, shadow_open, fails, distance=True):
    """The strategy list on the shared list: its three groups in order, the BOOK rows named with run numbers and carrying the
    range's P&L of record, trades and win rate, the Retired and Shadow folds closed (their rows outside the account number),
    no switch, and where it sits: above the trade list on a phone (step 11), from 1100 px the frame's right-hand panel beside the top block (step 12)."""
    if not lg:
        fails.append('%s: no strategy list on the shared list ([data-lglist="qb"] in the side column)' % tag)
        return
    trades = doc.get('trades_all') or []
    groups = lg.get('groups') or []
    keys = [g['key'] for g in groups]
    pos = _positions(doc)
    live = 'ENGUQ' in pos     # a retired leg that holds a position is a BOOK leg again (owner decision 9): no Retired group then
    want_keys = [k for k in LIST_GROUPS if not (live and k == 'retired')]
    if keys != want_keys:
        fails.append('%s: the strategy list groups are %r, want %r (BOOK, Retired, Shadow - not counted; no Retired group while '
                     'ENGU-Q holds a position)' % (tag, keys, want_keys))
        return
    by = dict((g['key'], g) for g in groups)
    if lg.get('title') != 'Strategies' or lg.get('count') != expected_list_count(trades, cutoff, range_key):
        fails.append('%s: the list header reads %r / %r, want Strategies / %r'
                     % (tag, lg.get('title'), lg.get('count'), expected_list_count(trades, cutoff, range_key)))
    if lg.get('sw'):
        fails.append('%s: the list draws %d switches; this board has none (every leg counts)' % (tag, lg['sw']))
    figs = expected_leg_figs(trades, cutoff)
    other = expected_other_figs(trades, cutoff)
    want_names = (BOOK_NAMES_LIVE if live else BOOK_NAMES) + ([OTHER_NAME] if other else [])
    if other:
        figs[OTHER_NAME] = other
    bk = by['book']
    if bk.get('fold') or not (bk.get('head') or '').upper().startswith('BOOK') or ('· %d' % len(want_names)) not in (bk.get('head') or ''):
        fails.append('%s: the BOOK group reads %r (fold %s)' % (tag, bk.get('head'), bk.get('fold')))
    names = [x['name'] for x in bk.get('rows') or []]
    if names != want_names:
        fails.append('%s: the BOOK rows are %r, want %r (family + run number, from the leg definitions%s)'
                     % (tag, names, want_names, ', and an Other legs row for a strategy with no row' if other else ''))
    for x in bk.get('rows') or []:
        is_other = x.get('name') == OTHER_NAME
        if not is_other and not LEG_RE.match(x.get('name') or ''):
            fails.append('%s: list row %r has no family + run number' % (tag, x.get('name')))
        e = figs.get(x.get('name'))
        if e and (x.get('value') != e['value'] or x.get('value2') != e['value2']):
            fails.append('%s: list row %s reads %r / %r, the fixture says %r / %r (the range\'s P&L of record, trades, win rate)'
                         % (tag, x.get('name'), x.get('value'), x.get('value2'), e['value'], e['value2']))
        pz = pos.get(x.get('key'))
        want_side = ('LONG' if pz[0] == 'Long' else 'SHORT') if pz else 'FLAT'
        if not is_other and not (x.get('tag') or '').startswith(want_side):
            fails.append('%s: list row %s carries the side %r, want %s' % (tag, x.get('name'), x.get('tag'), want_side))
        if pz and not vp.startswith('phone') and ('%s %d @ %s' % (pz[0], pz[1], money(pz[2]))) not in (x.get('sub') or ''):
            fails.append('%s: list row %s shows %r under its name, want the live position %s %d @ %s'
                         % (tag, x.get('name'), x.get('sub'), pz[0], pz[1], money(pz[2])))
    rt = by.get('retired')
    if rt and (not rt.get('fold') or ('Retired' not in (rt.get('head') or '')) or ('flat since ' + RETIRED_SINCE) not in (rt.get('head') or '')):
        fails.append('%s: the Retired group reads %r (fold %s), want a fold saying "flat since %s"'
                     % (tag, rt.get('head'), rt.get('fold'), RETIRED_SINCE))
    sh = by['shadow']
    shadow = expected_shadow_rows(trades, cutoff)
    if not sh.get('fold') or (sh.get('head') or '').replace('▾', '').strip() != 'Shadow - not counted · %d' % len(shadow):
        fails.append('%s: the Shadow group reads %r (fold %s), want a fold reading "Shadow - not counted · %d"'
                     % (tag, sh.get('head'), sh.get('fold'), len(shadow)))
    for g, is_open in [z for z in ((rt, retired_open), (sh, shadow_open)) if z[0]]:
        want_open = 'true' if is_open else 'false'
        if g.get('expanded') != want_open:
            fails.append('%s: the %s group is aria-expanded=%r, want %r (closed until a viewer opens it)'
                         % (tag, g.get('key'), g.get('expanded'), want_open))
        if (not is_open) and g.get('rows'):
            fails.append('%s: the %s group draws %d rows while closed' % (tag, g.get('key'), len(g['rows'])))
    if (retired_open and rt) or live:
        if rt:
            rn = [x['name'] for x in rt.get('rows') or []]
            if rn != [RETIRED_NAME]:
                fails.append('%s: the Retired rows are %r, want %r' % (tag, rn, [RETIRED_NAME]))
            elif rt['rows'][0].get('value') != figs[RETIRED_NAME]['value'] or rt['rows'][0].get('value2') != figs[RETIRED_NAME]['value2']:
                fails.append('%s: the Retired row reads %r / %r, the fixture says %r / %r' % (
                    tag, rt['rows'][0].get('value'), rt['rows'][0].get('value2'), figs[RETIRED_NAME]['value'], figs[RETIRED_NAME]['value2']))
        # the rows add up to the account's range figure: BOOK + Retired are the legs that count, Shadow is never in it
        counted = [_money_val(x.get('value')) for g in (bk, rt) if g for x in g.get('rows') or []]
        want_tot = round(sum(qe_pnl_of(t) for t in _range_rows(trades, cutoff)), 2)
        if None not in counted and abs(sum(counted) - want_tot) > 0.011:
            fails.append('%s: BOOK + Retired add up to %s, the P&L of record of the range is %s (a shadow leg, or a leg with no row, '
                         'moved the list off the account number)' % (tag, signed(round(sum(counted), 2)), signed(want_tot)))
    if shadow_open:
        sn = dict((x['name'], x['value']) for x in sh.get('rows') or [])
        if sn != shadow:
            fails.append('%s: the Shadow rows are %r, the fixture says %r' % (tag, sn, shadow))
        if any(not x.get('off') for x in sh.get('rows') or []):
            fails.append('%s: a shadow row is not drawn faded (it is not counted)' % tag)
    rows = [x for g in groups for x in g.get('rows') or []]
    if vp.startswith('phone'):
        tall = [(x['name'], x['h']) for x in rows if x.get('h', 0) > PHONE_ROW_MAX_H]
        if tall:
            fails.append('%s: on a phone every list row is one line (<= %d px), but %s are taller' % (tag, PHONE_ROW_MAX_H, tall[:3]))
        if any(x.get('value2Shown') or x.get('subShown') for x in rows):
            fails.append('%s: on a phone a list row still shows its second line' % tag)
    else:
        if any(x.get('value2') and not x.get('value2Shown') for x in rows):
            fails.append('%s: on a laptop the trades / win rate line under the money is hidden' % tag)
    if theme == 'mono':
        bad = [x['valColor'] for x in rows if x.get('valColor') and not _grey(x['valColor'])]
        if bad:
            fails.append('%s: a list row draws its money in colour under MONO (MONO has no hue): %s' % (tag, bad[:3]))
    g = lg.get('geo') or {}
    if vp.startswith('phone'):
        # step 11: the list is ABOVE the trade list (a one-line fold up to 600 px) and Account is an own fold below it; _s11_order_problems judges both
        if distance and (g.get('histTop') is None or g.get('shellTop') is None or g['histTop'] - g['shellTop'] > LIST_VH_MAX * g['vh']):
            fails.append('%s: on a phone the trade list starts %s px under the top of the board (%.2f viewports of %s px); it must '
                         'start within %.1f (mistake #12)' % (tag, (g.get('histTop') or 0) - (g.get('shellTop') or 0),
                         ((g.get('histTop') or 0) - (g.get('shellTop') or 0)) / (g.get('vh') or 1), g.get('vh'), LIST_VH_MAX))
    else:
        # LEDGER step 12: the list is the frame's right-hand panel beside the top block (not sticky); the trade list runs the full width under both
        if not g.get('inSide'):
            fails.append("%s: on a laptop the strategy list is not inside the frame's right-hand panel [data-lgframe-side]" % tag)
        if g.get('listLeft') is None or g.get('topRight') is None or g['listLeft'] < g['topRight'] + 1:
            fails.append('%s: on a laptop the strategy list (left %s) is not to the right of the top block (right edge %s)'
                         % (tag, g.get('listLeft'), g.get('topRight')))
        if g.get('histTop') is None or g.get('panelBottom') is None or g['histTop'] < g['panelBottom'] - 1:
            fails.append('%s: on a laptop the trade list (top %s) does not start under the list panel (bottom %s)'
                         % (tag, g.get('histTop'), g.get('panelBottom')))
        if g.get('sticky') == 'sticky' or g.get('panelPos') == 'sticky':
            fails.append('%s: on a laptop the strategy list is sticky (list %r, panel %r): step 12 draws it beside the top block, never sticky'
                         % (tag, g.get('sticky'), g.get('panelPos')))


def _judge_inter_ledger(tag, res, fixture, fails):
    """The interaction run's LEDGER steps 7 + 10 part: the Retired fold open (the list adds up to the account's figure), the
    Shadow fold, a leg row's detail, the table view's run numbers, and the calendar -- day taps, month arrows, fold, and what a
    reload finds."""
    trades = fixture.get('trades_all') or []
    o = res.get('open') or {}
    _judge_list(tag + ' [Retired open]', o.get('list'), 'laptop', 'dark', fixture, None, 'ALL', True, False, fails)
    sd = res.get('shadow') or {}
    if not sd:
        fails.append('%s: no Shadow group to open ([data-lggrp="shadow"])' % tag)
    else:
        so, sc2 = sd.get('open') or {}, sd.get('closed') or {}
        if so.get('expanded') != 'true' or so.get('rows') or SHADOW_NOTE not in (so.get('note') or '') or sd.get('stored') != '1':
            fails.append('%s: the Shadow group did not open with its note and the choice kept (%s, stored %r)'
                         % (tag, {k: so.get(k) for k in ('expanded', 'rows', 'note')}, sd.get('stored')))
        if sc2.get('expanded') != 'false' or sc2.get('rows') or sd.get('stored2') != '0':
            fails.append('%s: the Shadow group did not close again (%s, stored %r)' % (tag, sc2.get('expanded'), sd.get('stored2')))
    lw = res.get('legrow') or {}
    fig = expected_leg_figs(trades)['NOISE #382']
    if lw.get('expanded') != 'true' or any(s not in (lw.get('detail') or '') for s in ('SINCE START', 'UNREALIZED', 'POSITION', fig['value'])):
        fails.append('%s: a tap on the NOISE row did not open its detail under it with since start %s (aria-expanded %r, text %r)'
                     % (tag, fig['value'], lw.get('expanded'), _first(lw.get('detail'), 160)))
    if lw.get('expandedAfter') != 'false' or lw.get('detailAfter'):
        fails.append('%s: a second tap on the NOISE row did not close its detail again (%r, detail still there: %s)'
                     % (tag, lw.get('expandedAfter'), lw.get('detailAfter')))
    inf = res.get('info') or {}
    if not inf:
        fails.append('%s: no note toggle on the NOISE row ([data-qbleginfo="NOISE"])' % tag)
    else:
        if inf.get('titleBefore') != 'show note' or NOTE_MARK in (inf.get('noteBefore') or ''):
            fails.append('%s: the NOISE note is open before any tap (toggle title %r)' % (tag, inf.get('titleBefore')))
        if NOTE_MARK not in (inf.get('note') or '') or inf.get('title') != 'hide note':
            fails.append('%s: a tap on the NOISE note toggle did not show its note under the row (toggle title %r, text %r)'
                         % (tag, inf.get('title'), _first(inf.get('note'), 120)))
        if inf.get('expanded') != 'false' or inf.get('detail'):
            fails.append("%s: a tap on the NOISE note toggle also opened the row's detail (aria-expanded %r, detail drawn: %s)"
                         % (tag, inf.get('expanded'), inf.get('detail')))
        if NOTE_MARK in (inf.get('noteAfter') or '') or inf.get('expandedAfter') != 'false':
            fails.append('%s: a second tap on the NOISE note toggle did not hide the note again (aria-expanded %r)'
                         % (tag, inf.get('expandedAfter')))
    tv = (res.get('table') or {}).get('legs')
    if tv is None:
        fails.append('%s: no Table view to read ([data-lgview="table"])' % tag)
    else:
        bad = [x for x in tv if not LEG_RE.match(x or '')]
        if bad or len(tv) != min(len(trades), 50):
            fails.append('%s: the Table view names strategies without family + run number: %s (%d rows for %d trades)'
                         % (tag, sorted(set(map(str, bad)))[:4], len(tv), len(trades)))
        elif len(trades) <= 50 and collections.Counter(tv) != collections.Counter(expected_leg_name(t) for t in trades):
            fails.append('%s: the Table view names the wrong run on a row' % tag)
    tdays = (res.get('table') or {}).get('days')
    if tdays is not None and len(trades) <= 50 and collections.Counter(tdays) != collections.Counter(_close_day(t) or '' for t in trades):
        fails.append('%s: the Table view rows carry the wrong close day (data-qbday), so a calendar tap cannot land on them' % tag)
    ca = res.get('cal') or {}
    if not ca:
        fails.append('%s: no calendar run to read' % tag)
        return

    def tapped(lst, day):
        return bool(lst) and lst[0].get('day') == day
    _judge_cal(tag + ' [calendar, October]', ca.get('start'), 'laptop', 'dark', fixture, None, None, True, STAT_TODAY, fails)
    if not tapped(ca.get('tapOct'), '2026-10-02') or not ca.get('flashOct'):
        fails.append("%s: a tap on Oct 2 did not scroll the trade list to that day's row and flash it (scrolled to %r, flash %s)"
                     % (tag, ca.get('tapOct'), ca.get('flashOct')))
    _judge_cal(tag + ' [calendar, after the earlier arrow]', ca.get('sept'), 'laptop', 'dark', fixture, None, '2026-09', True, STAT_TODAY, fails)
    if ca.get('storedMonth') != '2026-09' or ca.get('memMonth') != '2026-09':
        fails.append('%s: the earlier arrow did not keep the month for this viewer (stored %r, in memory %r)'
                     % (tag, ca.get('storedMonth'), ca.get('memMonth')))
    if not tapped(ca.get('tapSep'), '2026-09-23'):
        fails.append("%s: a tap on Sep 23 did not scroll the trade list to that day's row (scrolled to %r)" % (tag, ca.get('tapSep')))
    _judge_cal(tag + ' [calendar, folded]', ca.get('closed'), 'laptop', 'dark', fixture, None, '2026-09', False, STAT_TODAY, fails)
    if ca.get('storedOpen') != '0':
        fails.append('%s: closing the calendar did not keep the choice for this viewer (stored %r)' % (tag, ca.get('storedOpen')))
    _judge_cal(tag + ' [calendar, after a reload]', ca.get('reload'), 'laptop', 'dark', fixture, None, '2026-09', False, STAT_TODAY, fails)
    _judge_cal(tag + ' [calendar, reopened]', ca.get('reopen'), 'laptop', 'dark', fixture, None, '2026-09', True, STAT_TODAY, fails)
    if ca.get('storedOpen2') != '1':
        fails.append('%s: opening the calendar again did not keep the choice (stored %r)' % (tag, ca.get('storedOpen2')))
    _judge_cal(tag + ' [calendar, after the later arrow]', ca.get('oct'), 'laptop', 'dark', fixture, None, '2026-10', True, STAT_TODAY, fails)
    if not ca.get('moreDay') or ca.get('moreHadRow'):
        fails.append("%s: the probe's own SHOW MORE case is wrong (day %r, its row already on the page: %s)"
                     % (tag, ca.get('moreDay'), ca.get('moreHadRow')))
    elif not tapped(ca.get('moreSpy'), ca['moreDay']) or not ca.get('moreHasRow') or ca.get('moreRowsAfter') != len(trades):
        fails.append("%s: a tap on %s, whose rows were not on the page yet (%s rows shown), did not draw every row and scroll to that "
                     "day's newest trade (rows after %s of %d, scrolled to %r)"
                     % (tag, ca['moreDay'], ca.get('moreRowsBefore'), ca.get('moreRowsAfter'), len(trades), ca.get('moreSpy')))


def _other_doc(fixture):
    """The fixture with its last two ORB trades turned into a strategy the board has no row for (the box started publishing a
    leg before the page learned its name): the list must still add up to the account's figure, so it draws an Other legs row."""
    doc = json.loads(json.dumps(fixture))
    orb = [t for t in doc.get('trades_all') or [] if t.get('leg') == 'ORB']
    for t in sorted(orb, key=lambda t: str(t.get('exit_ts') or ''))[-2:]:
        t['leg'] = OTHER_LEG
    return doc


def _enguq_open_doc(fixture):
    """The fixture with ENGU-Q long 10 @ 600.10 (live 600.52): a retired leg that holds a position is a BOOK leg again (owner
    decision 9), so the list has no Retired group, ENGU-Q reads LONG with its live position line, and the rows still add up."""
    doc = json.loads(json.dumps(fixture))
    doc.setdefault('positions', {})['ENGUQ'] = {'side': 'long', 'shares': '10', 'entry_px': '600.10',
                                                'entry_ts': STAT_TODAY + ' 10:00:05', 'unrealized': '4.20'}
    doc.setdefault('positions_live', {}).update(
        {'broker_net_qty': 10, 'legs_net_qty': 10, 'total_open_pnl': 4.2,
         'legs': [{'leg': 'ENGUQ', 'side': 'long', 'shares': 10, 'entry_px': 600.1, 'live_px': 600.52, 'live_source': 'stream',
                   'live_age_s': 1.0, 'open_pnl': 4.2, 'time_in_trade_min': 3}]})
    return doc


def _stats_cases(fixture):
    """Each: name, range, doc, vp, theme, calendar month, today, more (More stats open as a reload finds
    it), empty (no trade closed in the range)."""
    z = _zero_doc(fixture)

    def c(name, rg, doc, vp='laptop', th='dark', cal=None, today=STAT_TODAY, more=False, empty=False, now=None,
          cal_open=None, folds=False):
        return {'name': name, 'range': rg, 'doc': doc, 'vp': vp, 'theme': th, 'cal': cal, 'today': today,
                'more': more, 'empty': empty, 'now': now or FRESH_NOW, 'cal_open': cal_open, 'folds': folds}
    return [c('ALL', 'ALL', fixture),
            c('1W', '1W', fixture),
            c('1W (MONO, 390x844, More stats open)', '1W', fixture, vp='phone390', th='mono', more=True, cal_open='1'),
            c('$0 trade', 'ALL', z, cal='2026-09'),
            c('TODAY', 'TODAY', fixture),
            c('1M (375x812, More stats open)', '1M', fixture, vp='phone', more=True, cal_open='1'),
            c('TODAY before the first exit (2026-10-06, More stats open)', 'TODAY', fixture, today='2026-10-06',
              more=True, empty=True, now='2026-10-06 08:00:00'),
            c('a shadow row closed today (ALL, More stats open)', 'ALL', _shadow_doc(fixture), th='mono', more=True, folds=True),
            c('an unlisted strategy leg (ALL, 375x812, both folds open)', 'ALL', _other_doc(fixture), vp='phone', folds=True),
            c('ENGU-Q holds a position (ALL, 1366x768)', 'ALL', _enguq_open_doc(fixture)),
            c('ENGU-Q holds a position (ALL, 375x812)', 'ALL', _enguq_open_doc(fixture), vp='phone')]


# ---------------------------------------------------------------------------------------------------------------------------------
# LEDGER unify step 8 (2026-10-06): this board's trade list is TRADING-LOG's shared frame (ledgerTradeListHtml / ledgerTradeListWire),
# as REAL's is. Everything below is worked out here from the fixture and never read off the page: which trades each chip, search and
# range leaves, their order (newest CLOSE first, under a header for each New York close day), each day's signed net and every cell.
# ---------------------------------------------------------------------------------------------------------------------------------
TL_CHIP_KEYS = ['ALL', 'LONG', 'SHORT', 'WINS', 'LOSSES', 'ORB', 'ENGUQ', 'NOISE', 'BOOKONLY']
TL_CHIP_LABELS = ['ALL', 'LONG', 'SHORT', 'WINS', 'LOSSES', 'ORB #314', 'ENGU-Q #335', 'NOISE #382', 'BOOK ONLY']
TL_COMMON_CELLS = ['time', 'sym', 'side', 'size', 'pnl', 'pts', 'strat', 'chart']
TL_PHONE_CELLS = ['time', 'sym', 'side', 'pnl', 'chart']
TL_PAGE = 18                 # the SHOW MORE case: the list shows this many rows first, and on to the end of that trade's day (the 18th trade shares 09-25 with the 19th)
TL_FRAME_TOP_MAX = 792       # phone: the frame starts at most this far under the board top (the History section started at 784 before the frame)
TL_TODAY = STAT_TODAY
TL_WIDTHS = [375, 390, 600, 601, 640, 700, 800, 900, 1000, 1099, 1100, 1280, 1366]
TL_CAV_BOX = 800             # the flagged-row mark under the time is drawn while the list's own box is this wide or narrower (a container query; the flags column is drawn above it)
CSV_FILE = 'qqq_shadow_book_closed_trades.csv'
# the CSV the button saves keeps the columns it always had (the original thirty-one, then the ledger ones)
CSV_COLS = [
    'entry_ts', 'exit_ts', 'leg', 'side', 'shares', 'entry_px',
    'exit_px', 'pnl', 'exit_reason', 'nt_entry_ts', 'nt_exit_ts', 'nt_qty',
    'nt_mult', 'nt_notional_usd', 'shadow_notional_usd', 'notional_ratio', 'latency_s', 'real_entry_px',
    'real_exit_px', 'real_pnl', 'slip_entry_ps', 'slip_exit_ps', 'repriced_at', 'nt_points',
    'expected_usd', 'track_err_usd', 'parity_ok', 'parity_note', 'note', 'size',
    'shares_wanted', 'trade_id', 'close_day_ny', 'pnl_record', 'pnl_record_source', 'pnl_record_note',
    'pnl_backtest', 'book_only', 'book_only_reason', 'fills_vs_backtest', 'fills_vs_backtest_note', 'entry_backtest_px',
    'entry_webull_px', 'entry_fill', 'exit_backtest_px', 'exit_webull_px', 'exit_fill', 'fill_gap_usd',
    'design_gap_usd', 'execution_gap_usd',
]
MON3 = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
DASH = '—'


def row_key(t):
    """index.html window._qeRowKey: the trade id, else leg|entry|exit (what a row, the sheet and the CSV go by)."""
    tid = t.get('trade_id')
    return 'QE:' + (str(tid) if tid else '%s|%s|%s' % (t.get('leg') or '', t.get('entry_ts') or '', t.get('exit_ts') or ''))


def _hm_secs(s):
    m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?', str(s or ''))
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0) if m else None


def _tl_close_key(t):
    """index.html ledgerCloseKey: the close day, then the exit time in seconds (the entry time when there is no exit time)."""
    ex, en = str(t.get('exit_ts') or ''), str(t.get('entry_ts') or '')
    x = _hm_secs(ex[11:19] or en[11:19])
    return '%s %05d' % (_close_day(t) or '', x if x is not None else 0)


def tl_order(trades):
    """Newest close first; two trades closed in the same second stay as the board leaves them (a stable sort, reversed)."""
    return list(reversed(sorted(trades, key=_tl_close_key)))


def js_fixed(x, d):
    """JavaScript's Number.prototype.toFixed: the exact value of the double, a tie rounded away from zero."""
    from decimal import Decimal, ROUND_HALF_UP
    return format(Decimal(float(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP), 'f')


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float('nan')


def _num(v):
    """A finite-or-not number, or None when the board's qeMoney / qeNum would draw a dash (null, undefined, NaN)."""
    if v is None:
        return None
    x = _to_float(v)
    return None if x != x else x


def loc2(x):
    """Number.prototype.toLocaleString('en-US', two fraction digits): the SHORTEST decimal form of the double (743.175), a tie rounded away from zero."""
    from decimal import Decimal, ROUND_HALF_UP
    return '{:,.2f}'.format(Decimal(repr(abs(float(x)))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def qe_money(v):
    """index.html qeMoney: $1,234.50 / -$1.00, a dash for null / NaN."""
    x = _num(v)
    return DASH if x is None else ('-$' if x < 0 else '$') + loc2(x)


def qe_num(v, d=0):
    x = _num(v)
    return DASH if x is None else js_fixed(x, d)


def fmt_et(iso):
    """index.html qeFmtET: 'Oct 02, 10:35'."""
    if not iso:
        return DASH
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})', str(iso))
    if not m:
        return str(iso)
    return '%s %s, %s:%s' % (MON3[int(m.group(2)) - 1], m.group(3), m.group(4), m.group(5))


CAV_ORDER = ['BOOK ONLY', 'CHECK FILL', 'FILL GAP', 'BOOK PRICE', 'PART BOOK PRICE', 'NOT COMPARED']


def _fill_word(t):
    """index.html parityChip on a failed fill check: CHECK FILL when a side has an unexplained part (a fill that does not fit the tape), else FILL GAP."""
    fp = t.get('fp') if isinstance(t.get('fp'), dict) else None
    for k in ('en', 'ex'):
        s = fp.get(k) if fp else None
        if isinstance(s, str):
            p = s.split('|')
            u = _to_float(p[6]) if len(p) > 6 and p[6] != '' else 0.0
        elif isinstance(s, dict):
            u = _to_float(s.get('unx')) if s.get('unx') is not None else 0.0
        else:
            continue
        if u == u and abs(u) >= 0.00005:
            return 'CHECK FILL'
    return 'FILL GAP'


def row_cav_word(t):
    """The one caveat word a row carries under its strategy name (index.html qbCavWord): the first of CAV_ORDER that the row's own flags hold."""
    words = [(_fill_word(t) if isinstance(w, tuple) else w) for w in tl_flags_want(t)[1:]]
    return next((k for k in CAV_ORDER if k in words), '')


def row_caveat(t):
    """The trades a caveat word sits on: book only, a book / part-book price, a failed fill check, no fill comparison (not an NT mirror)."""
    return bool(row_cav_word(t))


def tl_flags_want(t):
    """Words the EXIT / FLAGS cell must carry: the exit reason (a dash when none), then the chips the old rows drew. A tuple = any of."""
    r = t.get('exit_reason')
    want = [DASH if r in (None, '') else str(r)]
    for w in ('BREAKER', 'KILL', 'EOD'):
        if re.search(w, str(r or ''), re.I):
            want.append(w)
            break
    if t.get('book_only'):
        want.append('BOOK ONLY')
    nt = str(t.get('signal_source') or '').lower() == 'ninjatrader'
    src = str(t.get('pnl_record_src') or '')
    if not t.get('book_only') and not nt and src in ('book', 'part'):
        want.append('PART BOOK PRICE' if src == 'part' else 'BOOK PRICE')
    if not nt:
        ok = t.get('broker_parity_ok')
        if ok is False:
            want.append(('FILL GAP', 'CHECK FILL'))
        elif ok is None:
            want.append('NOT COMPARED')
    return want


def tl_hay(t):
    """What the search reads of a trade (index.html qbHay without the flag words): name, leg, side, QQQ, exit reason, id, entry day, close day."""
    return ' '.join([expected_leg_name(t).strip(), str(t.get('leg') or ''), str(t.get('side') or '').upper(), 'QQQ',
                     str(t.get('exit_reason') or ''), str(t.get('trade_id') or ''),
                     str(t.get('entry_ts') or '')[:10], str(t.get('exit_ts') or '')[:10]]).lower()


def tl_range_rows(doc, cutoff=None):
    """The trades the list's range holds, in the doc's order: shadow rows left out, closed on or after the cutoff."""
    rows = [t for t in (doc.get('trades_all') or []) if not _is_shadow(t)]
    if cutoff:
        rows = [t for t in rows if (_close_day(t) or '') >= cutoff]
    return rows


def tl_rows(doc, cutoff=None, chip='ALL', query=''):
    """The trades the list shows for this range, chip and search text, newest close first."""
    q = (query or '').strip().lower()
    keep = []
    for t in tl_range_rows(doc, cutoff):
        if q and q not in tl_hay(t):
            continue
        p = qe_pnl_of(t)
        s = str(t.get('side') or '').upper()
        s = 'LONG' if s in ('LONG', 'BUY', 'L') else ('SHORT' if s in ('SHORT', 'SELL', 'S') else '')
        if chip == 'LONG' and s != 'LONG':
            continue
        if chip == 'SHORT' and s != 'SHORT':
            continue
        if chip == 'WINS' and not p > 0:      # a $0 trade is neither a win nor a loss
            continue
        if chip == 'LOSSES' and not p < 0:
            continue
        if chip == 'BOOKONLY' and not t.get('book_only'):
            continue
        if chip in ('ORB', 'ENGUQ', 'NOISE') and t.get('leg') != chip:
            continue
        keep.append(t)
    return tl_order(keep)


def tl_page(rows, shown):
    """The rows one page of the list holds: the newest `shown`, then on to the end of that trade's close day (SHOW MORE never cuts a day in two)."""
    cut = min(len(rows), max(1, shown))
    while cut < len(rows) and _close_day(rows[cut]) == _close_day(rows[cut - 1]):
        cut += 1
    return rows[:cut]


def tl_day_label(ds, today):
    """index.html ledgerDayLabel: TODAY / YESTERDAY / 'WED . SEP 30' (the day after the day's short name)."""
    import datetime
    y, m, d = map(int, ds.split('-'))
    day, t = datetime.date(y, m, d), datetime.date(*map(int, today.split('-')))
    if day == t:
        return 'TODAY'
    if day == t - datetime.timedelta(days=1):
        return 'YESTERDAY'
    return '%s \u00b7 %s %d' % (['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'][(day.weekday() + 1) % 7],
                                ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'][m - 1], d)


def tl_days(rows):
    """[(close day, [trades])] in the order the rows come."""
    days, order = {}, []
    for t in rows:
        d = _close_day(t) or ''
        if d not in days:
            days[d] = []
            order.append(d)
        days[d].append(t)
    return [(d, days[d]) for d in order]


def tl_running(range_rows):
    """{row key: the range's running P&L of record in close order} (the table's RUNNING column)."""
    out, run = {}, 0.0
    for t in sorted(range_rows, key=_tl_close_key):
        run += qe_pnl_of(t)
        out[row_key(t)] = run
    return out


def tl_side_text(t):
    s = str(t.get('side') or '').upper()
    return 'LONG' if s in ('LONG', 'BUY', 'L') else ('SHORT' if s in ('SHORT', 'SELL', 'S') else '')


def tl_size_text(t):
    x = _num(t.get('shares'))
    return '--' if x is None or x in (float('inf'), float('-inf')) else '%g' % x


def tl_pts_text(t):
    x = _num(t.get('shares'))
    if x is None or not x > 0:
        return '--'
    pts = qe_pnl_of(t) / x
    return ('+' if pts >= 0 else '-') + js_fixed(abs(pts), 2) + '/sh'


def tl_time_text(t, mode):
    """The time cell: the entry time (with its date, in the list, when the trade closed on a later day), '-> exit' after it (the caveat word is the
    strategy cell's since 2026-10-08)."""
    en, ex = str(t.get('entry_ts') or ''), str(t.get('exit_ts') or '')
    ed, a, b, cd = en[:10], en[11:16], ex[11:16], _close_day(t)
    if mode == 'table':
        return ed + ed[5:] + ' ' + (a or '--')
    s = ((ed[5:] + ' ' if (ed and cd and ed != cd) else '') + a) if a else '--'
    if b:
        s += '→ ' + b
    return s


def tl_sheet_title(t):
    return '%s · %s → %s' % (expected_leg_name(t).strip(), fmt_et(t.get('entry_ts')), fmt_et(t.get('exit_ts')))


def tl_has_nt(trades):
    return any(t.get(k) is not None for t in trades for k in ('nt_points', 'expected_usd', 'track_err_usd'))


def tl_heads(has_nt):
    """The table's header row: the common columns (this board's labels), then its own."""
    return (['ENTRY (ET)', 'STRATEGY', 'SIDE', 'SHARES', 'P&L', 'PTS', 'EXIT / FLAGS', 'CHART', 'EXIT (ET)', 'ENTRY $', 'EXIT $', 'RUNNING']
            + (['NT POINTS', 'EXPECTED $', 'TRACK ERR'] if has_nt else []) + ['REAL P&L', 'SLIP/SH'])


def _avg_slip(t):
    a, b = t.get('slip_entry_ps'), t.get('slip_exit_ps')
    a = None if a is None else abs(_to_float(a))
    b = None if b is None else abs(_to_float(b))
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2


def tl_own_cells(t, run, has_nt):
    """The table's own columns: exit time, entry / exit price, running total, [NinjaTrader three], real P&L, slip a share."""
    out = {'out': fmt_et(t.get('exit_ts')), 'epx': qe_money(t.get('entry_px')), 'xpx': qe_money(t.get('exit_px')),
           'run': qe_money(run)}
    if has_nt:
        out['ntp'] = DASH if t.get('nt_points') is None else qe_num(t.get('nt_points'), 2)
        out['exp'] = DASH if t.get('expected_usd') is None else qe_money(t.get('expected_usd'))
        out['trk'] = DASH if t.get('track_err_usd') is None else qe_money(t.get('track_err_usd'))
    out['real'] = DASH if t.get('real_pnl') is None else qe_money(t.get('real_pnl'))
    sp = _avg_slip(t)
    out['slip'] = DASH if sp is None else qe_num(sp, 3)
    return out


def _tl_row_problems(r, t, ds, mode, run, has_nt):
    """What is wrong with one drawn row, as short phrases."""
    c = r.get('cells') or {}
    bad = []
    if r.get('qbday') != ds:
        bad.append('data-qbday %r, want %r' % (r.get('qbday'), ds))
    name = expected_leg_name(t).strip()
    if c.get('sym') != name or r.get('legSpans') != 1:
        bad.append('strategy %r (%s name span), want %r' % (c.get('sym'), r.get('legSpans'), name))
    for k, want in (('side', tl_side_text(t)), ('size', tl_size_text(t)), ('pnl', signed(qe_pnl_of(t))), ('pts', tl_pts_text(t)),
                    ('time', tl_time_text(t, mode))):
        if c.get(k) != want:
            bad.append('%s %r, want %r' % (k, c.get(k), want))
    flags = c.get('strat') or ''
    for w in tl_flags_want(t):
        alts = w if isinstance(w, tuple) else (w,)
        if not any(a in flags for a in alts):
            bad.append('flags %r lack %s' % (flags, ' / '.join(alts)))
    cv, want_cav = r.get('cav') or {}, row_cav_word(t)
    if (cv.get('w') or '') != want_cav or (want_cav and (cv.get('t') != want_cav or cv.get('cell') != 'sym' or cv.get('n') != 1)):
        bad.append('caveat word %r (text %r, in the %s cell, %s on the row), want %s' % (cv.get('w'), cv.get('t'), cv.get('cell'), cv.get('n'),
                                                                                     repr(want_cav) + ' under the strategy name' if want_cav else 'none'))
    if r.get('glyph') != row_key(t):
        bad.append('chart glyph %r, want %r' % (r.get('glyph'), row_key(t)))
    if mode == 'table':
        for k, want in tl_own_cells(t, run, has_nt).items():
            if c.get(k) != want:
                bad.append('%s %r, want %r' % (k, c.get(k), want))
    return bad


def _judge_tl_frame(tag, tl, doc, cutoff, fails, mode='list', chip='ALL', query='', shown=50, vp='laptop', theme='dark',
                    top_check=False, none_text=None, today=None):
    """One drawn frame against the fixture: the toolbar (count, LIST | TABLE, search, chips), a header for each close day with that day's
    signed net, the rows under it in order, every cell. Returns the rows the page should hold (None when there is no frame)."""
    if not tl or tl.get('frames') != 1 or not tl.get('mode'):
        fails.append('%s: the trade list is not drawn by the shared frame (frames on the page: %s, [data-lglist-frame="wb"] %s)'
                     % (tag, (tl or {}).get('frames'), 'there' if (tl or {}).get('mode') else 'missing'))
        return None
    if tl.get('mode') != mode:
        fails.append('%s: the frame is in %r mode, want %r' % (tag, tl.get('mode'), mode))
    if tl.get('oldSeg') or tl.get('oldRows'):
        fails.append('%s: the old trade list is still drawn beside the shared frame (%s old switch, %s old rows)'
                     % (tag, tl.get('oldSeg'), tl.get('oldRows')))
    rng = tl_range_rows(doc, cutoff)
    exp_all = tl_rows(doc, cutoff, chip, query)
    page = tl_page(exp_all, shown)
    closed_n = len(tl_range_rows(doc))
    want_count = '%d / %d trades' % (len(page), closed_n)
    if tl.get('count') != want_count:
        fails.append('%s: the count reads %r, want %r' % (tag, tl.get('count'), want_count))
    ch = tl.get('chips') or []
    if [c.get('k') for c in ch] != TL_CHIP_KEYS or [c.get('t') for c in ch] != TL_CHIP_LABELS:
        fails.append('%s: the chips read %r, want %r (the five shared ones, then ORB / ENGU-Q / NOISE with their run numbers and BOOK ONLY)'
                     % (tag, [c.get('t') for c in ch], TL_CHIP_LABELS))
    elif [c['k'] for c in ch if c.get('on')] != [chip] or any((c.get('p') == 'true') != bool(c.get('on')) for c in ch):
        fails.append('%s: the chip pressed is %r (aria-pressed %r), want only %s' % (
            tag, [c['k'] for c in ch if c.get('on')], [c.get('p') for c in ch], chip))
    vw = tl.get('views') or []
    if [v.get('k') for v in vw] != ['list', 'table'] or [v['k'] for v in vw if v.get('on')] != [mode] \
            or [v.get('p') for v in vw] != [('true' if v['k'] == mode else 'false') for v in vw]:
        fails.append('%s: the LIST | TABLE switch reads %r, want %s pressed' % (tag, vw, mode.upper()))
    sb = tl.get('search') or {}
    if sb.get('id') != 'wb-search' or sb.get('val') != query:
        fails.append('%s: the search box is %r, want #wb-search holding %r' % (tag, sb, query))
    if not tl.get('csv'):
        fails.append('%s: no CSV button beside the count ([data-qeexportcsv])' % tag)
    want_more = ('SHOW MORE (%d more)' % (len(exp_all) - len(page))) if len(exp_all) > len(page) else None
    if tl.get('more') != want_more:
        fails.append('%s: SHOW MORE reads %r, want %r' % (tag, tl.get('more'), want_more))
    days_want = tl_days(page)
    days = tl.get('days') or []
    if not page:
        if days:
            fails.append('%s: the frame draws %d day headers for a list with no trade in it' % (tag, len(days)))
        if none_text and none_text not in (tl.get('noRows') or '') and none_text not in (tl.get('empty') or ''):
            fails.append('%s: the empty list says %r, want it to say %r' % (tag, _first(tl.get('noRows') or tl.get('empty'), 160), none_text))
        return page
    if [d.get('day') for d in days] != [d for d, _ in days_want]:
        fails.append('%s: the day headers are %r, want %r (the New York day each trade CLOSED, newest first)'
                     % (tag, [d.get('day') for d in days][:8], [d for d, _ in days_want][:8]))
        return page
    has_nt = tl_has_nt(rng)
    run = tl_running(rng)
    problems = []
    for dr, (ds, ts) in zip(days, days_want):
        net = _js_round(sum(qe_pnl_of(t) for t in ts) * 100) / 100.0
        if dr.get('net') != signed(net):
            fails.append('%s: the %s header says %r, its %d rows make %s' % (tag, ds, dr.get('net'), len(ts), signed(net)))
        if today and dr.get('label') != tl_day_label(ds, today):
            fails.append('%s: the %s header is labelled %r, want %r' % (tag, ds, dr.get('label'), tl_day_label(ds, today)))
        cls = 'lg-up' if net > 0 else ('lg-down' if net < 0 else 'lg-flat')
        if cls not in (dr.get('netCls') or '').split():
            fails.append('%s: the %s net is drawn as %r, want %s (%s)' % (tag, ds, dr.get('netCls'), cls, signed(net)))
        if dr.get('meta') != '%d trade%s' % (len(ts), '' if len(ts) == 1 else 's'):
            fails.append('%s: the %s header counts %r, want %d trade(s)' % (tag, ds, dr.get('meta'), len(ts)))
        got_ids = [r.get('id') for r in dr.get('rows') or []]
        if got_ids != [row_key(t) for t in ts]:
            fails.append('%s: the rows under %s are %r, want %r' % (tag, ds, [g[3:] for g in got_ids][:6], [row_key(t)[3:] for t in ts][:6]))
            continue
        for r, t in zip(dr['rows'], ts):
            for p in _tl_row_problems(r, t, ds, mode, run.get(row_key(t)), has_nt):
                problems.append('%s %s' % (row_key(t)[3:], p))
    for p in problems[:4]:
        fails.append('%s: a row is wrong -- %s' % (tag, p))
    if len(problems) > 4:
        fails.append('%s: ... and %d more row problems' % (tag, len(problems) - 4))
    if mode == 'table' and tl.get('heads') != tl_heads(has_nt):
        fails.append('%s: the table header reads %r, want %r (the common columns, then this board\'s own)' % (tag, tl.get('heads'), tl_heads(has_nt)))
    g = tl.get('geo') or {}
    want_vis = TL_PHONE_CELLS if vp.startswith('phone') else (TL_COMMON_CELLS if mode == 'list' else None)
    if want_vis and (tl.get('vis') != want_vis or tl.get('visLast') != want_vis):
        fails.append('%s: a row draws the cells %r (last row %r), want %r%s' % (
            tag, tl.get('vis'), tl.get('visLast'), want_vis, ' (five on a phone)' if vp.startswith('phone') else ''))
    if tl.get('cavN') != sum(1 for t in page if row_caveat(t)):
        fails.append('%s: %s flagged-row marks drawn for %d flagged trades' % (tag, tl.get('cavN'), sum(1 for t in page if row_caveat(t))))
    elif vp.startswith('phone') and tl.get('cavShown') != tl.get('cavN'):
        fails.append('%s: the flagged-row marks are not drawn on a phone (%s of %s shown); the flags column is not one of its five cells'
                     % (tag, tl.get('cavShown'), tl.get('cavN')))
    elif vp == 'laptop' and tl.get('cavShown'):
        fails.append('%s: %s flagged-row marks drawn on a laptop beside the flags column' % (tag, tl.get('cavShown')))
    if theme == 'mono':
        col = tl.get('colors') or {}
        bad = [c for k in ('net', 'pnl', 'side') for c in col.get(k) or [] if not _grey(c)]
        if bad:
            fails.append('%s: the frame draws money or a side in colour under MONO (MONO has no hue): %s' % (tag, bad[:3]))
    if vp.startswith('phone'):
        if (g.get('docSW') or 0) > (g.get('iw') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (scrollWidth %s > window %s)' % (tag, g.get('docSW'), g.get('iw')))
        if top_check and mode == 'list':
            ft, hs = g.get('frameTop'), g.get('histTop')
            if ft is None or ft > TL_FRAME_TOP_MAX or ft > (g.get('vh') or 0):
                fails.append('%s: on a phone the trade list starts %s px under the top of the board, want %d or less (and inside the %s px '
                             'screen): the list top must not grow' % (tag, ft, TL_FRAME_TOP_MAX, g.get('vh')))
            elif hs is not None and ft - hs > 4:
                fails.append('%s: on a phone %d px of heading or padding sit between the top of the History section and the list'
                             % (tag, ft - hs))
    return page


def csv_name(scope=''):
    """The CSV's file name (review L5): the plain name for ALL with no chip and no search, else the range / chip / search after it."""
    return CSV_FILE if not scope else CSV_FILE[:-4] + '_' + scope + '.csv'


def csv_problems(tag, res, want_rows, scope=''):
    """The CSV the button saved against the trades it should hold: file name (with the list's scope), the columns it always had, one line a trade in
    list order."""
    out = []
    if not res:
        return ['%s: the CSV button saved nothing' % tag]
    if res.get('n') != csv_name(scope):
        out.append('%s: the file is %r, want %r (the file name says which trades it holds)' % (tag, res.get('n'), csv_name(scope)))
    import csv as _csv
    rows = list(_csv.reader(io.StringIO(res.get('t') or '', newline='')))
    if not rows or rows[0] != CSV_COLS:
        out.append('%s: the CSV columns are %r, want the %d it always had' % (tag, (rows[0] if rows else None), len(CSV_COLS)))
        return out
    body = [dict(zip(rows[0], r)) for r in rows[1:]]
    keys = ['QE:' + (r.get('trade_id') or '%s|%s|%s' % (r.get('leg'), r.get('entry_ts'), r.get('exit_ts'))) for r in body]
    if keys != [row_key(t) for t in want_rows]:
        if sorted(keys) == sorted(row_key(t) for t in want_rows):
            out.append("%s: the CSV holds the right %d trades in another order than the list shows them (it starts with %s, the list with %s)"
                       % (tag, len(keys), keys[0][3:], row_key(want_rows[0])[3:]))
        else:
            out.append('%s: the CSV holds %d trades (%s...), want %d (%s...)' % (
                tag, len(keys), ', '.join(k[3:] for k in keys[:2]), len(want_rows), ', '.join(row_key(t)[3:] for t in want_rows[:2])))
        return out
    for r, t in zip(body, want_rows):
        if r.get('pnl_record') != js_fixed(qe_pnl_of(t), 2) or r.get('close_day_ny') != (_close_day(t) or ''):
            out.append('%s: the CSV line for %s says P&L of record %r on %r, want %s on %s' % (
                tag, row_key(t)[3:], r.get('pnl_record'), r.get('close_day_ny'), js_fixed(qe_pnl_of(t), 2), _close_day(t)))
            break
    return out


# ---- LEDGER step 9 (2026-10-06): the shared trade panel a row opens on this board ----
PN_RUNS = [('laptop', 'glass'), ('laptop', 'paper'), ('laptop', 'mono'), ('phone', 'glass'), ('phone', 'paper'), ('phone', 'mono')]
PN_WIDTHS = [375, 600, 601, 700, 800, 1000, 1366]       # the widths named for the sideways-scroll check, and the 600 / 601 rule either side
PN_SLOTS = ['head', 'chart', 'numbers', 'notes', 'actions']
PN_DESTRUCTIVE = re.compile(r'DELETE|REMOVE|EDIT|SAVE|IGNORE|CLEAR', re.I)


def dur_str(secs):
    """index.html durStr on durationSecs: 49m 57s, 5m 9s, 1h 3m, 45s."""
    if secs is None or secs < 0:
        return DASH
    if secs < 60:
        return '%ds' % secs
    m, ss = divmod(secs, 60)
    if m < 60:
        return '%dm' % m + (' %ds' % ss if ss else '')
    h, mm = divmod(m, 60)
    return '%dh' % h + (' %dm' % mm if mm else '')


def _hold_secs(t):
    """Seconds between the entry and exit stamps (New York wall-clock strings, so a plain difference)."""
    import datetime as _dt
    try:
        a = _dt.datetime.strptime(str(t.get('entry_ts'))[:19], '%Y-%m-%d %H:%M:%S')
        b = _dt.datetime.strptime(str(t.get('exit_ts'))[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None
    return int(round((b - a).total_seconds()))


def _fp_side(s):
    """One side of a trade's fill parity packed as 'bt|wb|fs|edge|dsg|slp|unx|why' (index.html qeFpSide): the Webull fill and its status."""
    if not isinstance(s, str):
        return None
    p = s.split('|')

    def n(i):
        return None if i >= len(p) or p[i] == '' else _to_float(p[i])
    return {'wb': n(1), 'fs': {'o': 'ok', 's': 'suspect'}.get(p[2] if len(p) > 2 else '', 'none')}


def _cls(v):
    return 'lg-flat' if v is None or v != v else ('lg-up' if v > 0 else ('lg-down' if v < 0 else 'lg-flat'))


def panel_when(t):
    en, ex = str(t.get('entry_ts') or ''), str(t.get('exit_ts') or '')
    return '%s \u00b7 %s \u2192 %s ET' % (en[:10], en[11:16] or '--', (ex[5:10] + ' ' if (ex and ex[:10] != en[:10]) else '') + (ex[11:16] or '--'))


def panel_rows_want(t, doc):
    """[(label, text, colour class or None)] the numbers slot must carry, in order, worked out here from the fixture."""
    rng = tl_range_rows(doc)
    own = tl_own_cells(t, tl_running(rng).get(row_key(t)), True)
    pnl = qe_pnl_of(t)
    fp = t.get('fp') if isinstance(t.get('fp'), dict) else None
    nt_mirror = str(t.get('signal_source') or '').lower() == 'ninjatrader'

    def fill(k):
        s = _fp_side(fp.get(k)) if (fp and not nt_mirror) else None
        return DASH if not s or s['wb'] is None else qe_money(s['wb']) + (' (looks wrong)' if s['fs'] == 'suspect' else '')
    src = str(t.get('pnl_record_src') or '')
    cov = 'none (order never sent)' if t.get('book_only') else {'webull': 'Webull both sides', 'part': 'Webull one side, book other',
                                                                'book': 'none (book prices)'}.get(src, DASH)
    bt, bk, real = _fin(t.get('pnl_backtest')), _fin(t.get('pnl')), _num(t.get('real_pnl'))
    sh = _num(t.get('shares'))
    rvb = None if bt is None else _js_round((pnl - bt) * 100) / 100
    fpd = fp if (fp and not nt_mirror) else None

    def usd(label, k):
        v = _fin(fpd.get(k)) if fpd else None
        return (label, DASH if v is None else signed(v), _cls(v))
    rows = [('SHARES', DASH if sh is None else '{:,}'.format(_js_round(sh)), None),
            ('NOTIONAL', qe_money(t.get('shadow_notional_usd')), None),
            ('ENTRY $', own['epx'], None), ('ENTRY FILL', fill('en'), None), ('EXIT $', own['xpx'], None), ('EXIT FILL', fill('ex'), None),
            ('HOLD', dur_str(_hold_secs(t)), None),
            ('P&L OF RECORD', '%s \u00b7 %s' % (signed(pnl), {'webull': 'Webull', 'part': 'of record'}.get(src, 'book')), _cls(pnl)),
            ('BACKTEST P&L', '%s \u00b7 %s' % (DASH, bt_why(t, doc)) if bt is None else signed(bt), _cls(bt)),
            ('RECORD vs BACKTEST', DASH if rvb is None else signed(rvb), _cls(rvb)),
            ('BOOK P&L', DASH if bk is None else signed(bk), _cls(bk)),
            usd('FILL GAP $', 'gap_usd'), usd('DESIGN GAP $', 'dsg_usd'), usd('SLIPPAGE + UNEXPLAINED $', 'exec_usd'),
            ('RUNNING', own['run'], None), ('REAL P&L', own['real'], _cls(real)), ('SLIP/SH', own['slip'], None), ('FILL COVERAGE', cov, None)]
    if any(t.get(k) is not None for k in ('nt_points', 'expected_usd', 'track_err_usd')):
        rows += [('NT POINTS', own['ntp'], None), ('EXPECTED $', own['exp'], None), ('TRACK ERR', own['trk'], None)]
    if t.get('nt_entry_ts') or t.get('nt_exit_ts') or t.get('latency_s') is not None:
        rows += [('NT ENTRY', fmt_et(t.get('nt_entry_ts')) if t.get('nt_entry_ts') else DASH, None),
                 ('NT EXIT', fmt_et(t.get('nt_exit_ts')) if t.get('nt_exit_ts') else DASH, None),
                 ('LATENCY', (qe_num(t.get('latency_s'), 2) + 's') if t.get('latency_s') is not None else DASH, None)]
    return rows


def _fp_cause_side(s):
    """One side of a trade's fp (packed 'bt|wb|fs|edge|dsg|slp|unx|why' or a dict) -> {edge, slp, unx, why}, None when absent."""
    if isinstance(s, str):
        p = s.split('|')
        g = lambda i: (_to_float(p[i]) if len(p) > i and p[i] != '' else None)
        return {'edge': g(3), 'slp': g(5) or 0.0, 'unx': g(6) or 0.0, 'why': p[7] if len(p) > 7 else ''}
    if isinstance(s, dict):
        return {'edge': _num(s.get('edge')), 'slp': _num(s.get('slp')) or 0.0, 'unx': _num(s.get('unx')) or 0.0, 'why': s.get('why') or ''}
    return None


# the FILLS vs BACKTEST line's reason on a flagged trade, by cause (api/qqq_exec.py's note order: worse, round trip when
# broker_parity.round_trip_check is on, odd)
FP_CAUSE_WORDS = {'worse': 'a Webull fill came out more than 15 cents a share worse than the backtest',
                  'tape': 'a Webull fill does not fit the tape',
                  'diverged': 'the resting Webull order filled where the backtest did not exit',
                  'rt': 'the two Webull fills together came out more than 15 cents a share worse',
                  'other': 'the box flagged this trade'}


def fp_cause_want(t, doc=None):
    """Why the box flagged this trade's fills: worse / rt / tape / diverged / other; None when it is not flagged."""
    fp = t.get('fp') if isinstance(t.get('fp'), dict) else None
    if not fp or not fp.get('flag'):
        return None
    comp = [x for x in (_fp_cause_side(fp.get('en')), _fp_cause_side(fp.get('ex'))) if x and x['edge'] is not None]
    if any(x['slp'] + x['unx'] < -0.15 - 1e-9 for x in comp):
        return 'worse'
    rt_on = bool(((doc or {}).get('broker_parity') or {}).get('round_trip_check'))
    if rt_on and len(comp) == 2 and sum(x['slp'] + x['unx'] for x in comp) < -0.15 - 1e-9:
        return 'rt'
    odd = [x for x in comp if abs(x['unx']) >= 0.00005]
    if odd:
        return 'diverged' if all(x['why'] == 'diverged' for x in odd) else 'tape'
    return 'other'


def bt_why(t, doc):
    """Why a trade has no backtest P&L (index.html, the panel's BACKTEST P&L dash): its exit side's code in words, else 'not on record'."""
    fp = t.get('fp') if isinstance(t.get('fp'), dict) else None
    ex, code = (fp or {}).get('ex'), ''
    if isinstance(ex, str):
        p = ex.split('|')
        code = p[7] if len(p) > 7 else ''
    elif isinstance(ex, dict):
        code = ex.get('why') or ''
    if not code or code == 'nofill':
        return 'not on record'
    return str(((doc.get('broker_parity') or {}).get('why_text') or {}).get(code) or code)


# three caveat trades get a Webull exit try that came back with each of these (the stub feeds it; panel_layer_problems judges its mark)
PN_OUTCOMES = ['NETTED', 'REFUSED', 'UNKNOWN']


def panel_pick(doc):
    """The trades the panel runs open: k1 = the newest (flagged), k2 = an older one a short page leaves out, hideChip hides k2, variety = one of
    each kind of caveat (book only, a failed fill check, EOD, a part-book price, NinjaTrader figures, a KEEL size, a note, a plain one)."""
    rows = tl_rows(doc)
    page = set(row_key(t) for t in tl_page(rows, TL_PAGE))
    rest = [t for t in rows if row_key(t) not in page]
    k2 = next((t for t in rest if t.get('trade_id') and tl_side_text(t) == 'LONG'), rest[0])

    def first(pred):
        return next((t for t in rows if pred(t)), None)
    cand = [rows[0], first(lambda t: t.get('book_only')), first(lambda t: t.get('broker_parity_ok') is False and not t.get('book_only')),
            first(lambda t: re.search('EOD', str(t.get('exit_reason') or '')) and t.get('trade_id')),
            first(lambda t: t.get('pnl_record_src') == 'part'),
            first(lambda t: any(t.get(k) is not None for k in ('nt_points', 'expected_usd', 'track_err_usd'))),
            first(lambda t: _fin(t.get('size')) not in (None, 1.0) and t.get('trade_id')),
            first(lambda t: t.get('note')),
            first(lambda t: t.get('pnl_record_src') == 'webull' and t.get('broker_parity_ok') is True and not re.search('EOD|BREAKER|KILL', str(t.get('exit_reason') or ''))),
            # no backtest P&L, and the box says why (the backtest has not exited this trade): the panel's dash carries those words
            first(lambda t: _fin(t.get('pnl_backtest')) is None and bt_why(t, doc) != 'not on record'),
            # a flagged trade whose cause is a fill that does not fit the tape (CHECK FILL): the FILLS vs BACKTEST line must say so, not '15 cents worse'
            first(lambda t: t.get('broker_parity_ok') is False and not t.get('book_only') and _fill_word(t) == 'CHECK FILL')]
    seen, variety = set(), []
    for t in cand:
        if t is not None and row_key(t) not in seen:
            seen.add(row_key(t))
            variety.append(row_key(t))
    # three caveat trades (entry and exit on one day, so the stubbed day carries both) get an exit try that came back REFUSED / NETTED / UNKNOWN
    by_key = dict((row_key(t), t) for t in rows)
    same_day = [k for k in variety[1:] if str(by_key[k].get('entry_ts') or '')[:10] == str(by_key[k].get('exit_ts') or '')[:10]]
    outcomes = dict(zip(same_day, ['REFUSED', 'NETTED', 'UNKNOWN']))
    return {'k1': row_key(rows[0]), 'k2': row_key(k2), 'hideChip': 'SHORT' if tl_side_text(k2) == 'LONG' else 'LONG', 'variety': variety,
            'outcomes': outcomes}


def panel_problems(tag, o, t, doc):
    """What is wrong with one open panel read against its trade: header, caveat chips, numbers rows, notes, actions."""
    bad = []
    if o.get('trade') != row_key(t):
        bad.append('the panel is tied to %r, want %r' % (o.get('trade'), row_key(t)))
    if o.get('sym') != expected_leg_name(t).strip():
        bad.append('the header names %r, want %r (family + run number)' % (o.get('sym'), expected_leg_name(t).strip()))
    if o.get('side') != tl_side_text(t):
        bad.append('the side tag reads %r, want %s' % (o.get('side'), tl_side_text(t)))
    pnl = qe_pnl_of(t)
    if o.get('net') != signed(pnl):
        bad.append('the net reads %r, want %s (the P&L of record, signed)' % (o.get('net'), signed(pnl)))
    elif _cls(pnl) not in (o.get('netCls') or '').split():
        bad.append('the net is drawn with %r, want %s' % (o.get('netCls'), _cls(pnl)))
    if o.get('when') != panel_when(t):
        bad.append('the day and times read %r, want %r' % (o.get('when'), panel_when(t)))
    sh = _num(t.get('shares'))
    if sh is not None and ('%s sh' % '{:,}'.format(_js_round(sh))) not in (o.get('sub') or ''):
        bad.append('the header does not say %s sh (%r)' % ('{:,}'.format(_js_round(sh)), o.get('sub')))
    want = tl_flags_want(t)[1:]
    chips = o.get('chips') or []
    if len(chips) != len(want) or not all(any(a in chips for a in (w if isinstance(w, tuple) else (w,))) for w in want):
        bad.append('the caveat chips read %r, want %s' % (chips, ' + '.join('/'.join(w) if isinstance(w, tuple) else w for w in want) or 'none'))
    if o.get('slots') != PN_SLOTS:
        bad.append('the slots come in the order %r, want %r' % (o.get('slots'), PN_SLOTS))
    rows = panel_rows_want(t, doc)
    got = o.get('rows') or {}
    if list(got.keys()) != [r[0] for r in rows]:
        bad.append('the numbers rows are %r, want %r' % (list(got.keys()), [r[0] for r in rows]))
    else:
        for lab, txt, cls in rows:
            if got.get(lab) != txt:
                bad.append('%s reads %r, want %r' % (lab, got.get(lab), txt))
            elif cls and cls not in ((o.get('rowCls') or {}).get(lab) or '').split():
                bad.append('%s is drawn with %r, want %s' % (lab, (o.get('rowCls') or {}).get(lab), cls))
    fpx = t.get('fp') if isinstance(t.get('fp'), dict) else None
    if str(t.get('signal_source') or '').lower() == 'ninjatrader':
        fpx = None
    fh = o.get('fpHead')
    if fpx is None and fh is not None:
        bad.append('a FILLS vs BACKTEST line %r on a trade with no fill comparison' % (fh,))
    elif fpx is not None:
        flag = bool(fpx.get('flag'))
        if not fh or fh[0] != ('flagged' if flag else 'ok') or (('FLAGGED' in (fh[1] or '')) != flag):
            bad.append('the FILLS vs BACKTEST line reads %r, want it %s' % (fh, 'marked FLAGGED (the box flagged this trade)' if flag else 'without FLAGGED'))
        cause = fp_cause_want(t, doc)
        txt = (fh or ['', ''])[1] or ''
        if cause and FP_CAUSE_WORDS[cause] not in txt:
            bad.append('the FILLS vs BACKTEST line reads %r, want its reason %r (the cause the box flagged it for)' % (txt, FP_CAUSE_WORDS[cause]))
        if cause in ('tape', 'diverged', 'other') and '15 cents' in txt:
            bad.append("the FILLS vs BACKTEST line says the fills were over 15 cents a share worse on a trade flagged for another cause (%s): %r" % (cause, txt))
        if not flag and ' - ' in txt:
            bad.append('the FILLS vs BACKTEST line gives a flag reason on a trade the box did not flag: %r' % txt)
    n = o.get('notes') or ''
    if 'keeps no notes' not in n or 'read-only' not in n:
        bad.append('the notes slot does not say it is read-only and keeps no notes (%r)' % _first(n, 90))
    if o.get('editable'):
        bad.append('the panel holds %s editable control(s) (a box, a select): its notes are read-only' % o.get('editable'))
    r = str(t.get('exit_reason') or '')
    if 'EXIT REASON' not in n or (r and r not in n):
        bad.append('the notes lack the exit reason %r' % r)
    for w in want:
        if not any((a + ':') in n for a in (w if isinstance(w, tuple) else (w,))):
            bad.append('the notes do not spell out the flag %s in words' % ('/'.join(w) if isinstance(w, tuple) else w))
    if not want and 'FLAGS none' not in n:
        bad.append('the notes do not say there are no flags')
    keel = t.get('size') not in (None, '') and _fin(t.get('size')) not in (None, 1.0)
    if keel != ('SIZE (KEEL)' in n):
        bad.append('the KEEL size note is %s, want it %s' % ('there' if 'SIZE (KEEL)' in n else 'missing', 'there' if keel else 'absent'))
    if t.get('note') and (str(t['note'])[:30] not in n or 'NOTE' not in n):
        bad.append("the notes lack the trade's own note")
    pn = t.get('broker_parity_note') if str(t.get('signal_source') or '').lower() != 'ninjatrader' else t.get('parity_note')
    if pn and (str(pn)[:25] not in n or 'PARITY' not in n):
        bad.append('the notes lack the parity note %r' % _first(pn, 40))
    b = o.get('buttons') or []
    if len(b) != 1 or 'OPEN CANDLES' not in b[0] or o.get('delBtn') or PN_DESTRUCTIVE.search(o.get('actionsText') or ''):
        bad.append('the actions slot holds %r (want OPEN CANDLES alone, nothing that changes the trade)' % (b,))
    if not o.get('chartDrawn'):
        bad.append('the chart slot never drew the candles (%r)' % _first(o.get('chartText'), 80))
    if o.get('oldSheet'):
        bad.append('the board\'s old sheet is on the page beside the panel')
    return ['%s: %s' % (tag, x) for x in bad]


def panel_geo_problems(tag, o, sheet, base):
    """Where the open panel sits: a right-hand panel 440 wide and full height above 600 px, a bottom sheet at 600 and under; over the page, in <body>."""
    bad = []
    want_mode = 'sheet' if sheet else 'side'
    if o.get('mode') != want_mode:
        bad.append('the panel mode is %r, want %r (%s)' % (o.get('mode'), want_mode, 'a bottom sheet at 600 px and under, a right-hand panel above'))
    rc, vw, vh = o.get('rect') or {}, o.get('vw') or 0, o.get('vh') or 0
    if sheet:
        if not (rc.get('l') == 0 and rc.get('w') == vw and rc.get('b') == vh):
            bad.append('the sheet should be the full width on the bottom edge (left=%s width=%s bottom=%s, screen %sx%s)'
                       % (rc.get('l'), rc.get('w'), rc.get('b'), vw, vh))
        if (rc.get('h') or 0) > 0.9 * vh or (rc.get('t') or 0) < 0.1 * vh:
            bad.append('the sheet is %spx tall with its top at %spx on a %spx screen: it must leave a strip of page above it to tap (at most 90%%)'
                       % (rc.get('h'), rc.get('t'), vh))
    else:
        if not (abs((rc.get('r') or 0) - vw) <= 1 and abs((rc.get('h') or 0) - vh) <= 1 and rc.get('w') == 440):
            bad.append('the panel should be 440 px wide and the full height on the right (right=%s width=%s height=%s, screen %sx%s)'
                       % (rc.get('r'), rc.get('w'), rc.get('h'), vw, vh))
    if o.get('inApp'):
        bad.append('the panel is inside #app, which every redraw rebuilds: it must live in <body>')
    g = o.get('g') or {}
    if (g.get('sw') or 0) > (g.get('cw') or 0) + 1:
        bad.append('the page scrolls sideways while the panel is open (scrollWidth %s > %s)' % (g.get('sw'), g.get('cw')))
    if base and (abs((g.get('sw') or 0) - (base.get('sw') or 0)) > 1 or abs((g.get('sh') or 0) - (base.get('sh') or 0)) > 1):
        bad.append('opening the panel changed the page size from %sx%s to %sx%s (it must sit over the page)'
                   % (base.get('sw'), base.get('sh'), g.get('sw'), g.get('sh')))
    if o.get('bodyWide'):
        bad.append('the panel body scrolls sideways')
    return ['%s: %s' % (tag, x) for x in bad]


def _panel_room(tag, label, g, base, fails, size=True):
    """A page with no panel open: nothing of it left behind, the page exactly as big as before the first open (size=False: after the board was
    redrawn under another range and another tab, whose own height is not the panel's business), <body> holding the same elements."""
    g = g or {}
    if g.get('nodes'):
        fails.append('%s: %s - %s trade panel node(s) are still in the page (a closed panel must not be in it)' % (tag, label, g.get('nodes')))
    for k, nice in (('sw', 'width'), ('sh', 'height')):
        if size and (g.get(k) is None or base.get(k) is None or abs(g[k] - base[k]) > 1):
            fails.append('%s: %s - the page is %s px %s, it was %s before the panel opened (a closed panel takes room)' % (tag, label, g.get(k), nice, base.get(k)))
    if g.get('kids') != base.get('kids'):
        fails.append('%s: %s - <body> holds %r, it held %r before the panel opened' % (tag, label, g.get('kids'), base.get('kids')))


def _judge_tl_panel(tag, res, doc, cs, fails):
    """One trade panel run (a laptop or a phone, one theme): open from a row, Esc, outside, the button, the glyph, a redraw, paging / search / chip /
    LIST | TABLE, each kind of caveat, the trade leaving the rows and the viewer leaving the board."""
    vp, theme = cs['vp'], cs['theme']
    sheet = vp == 'phone'
    pn = cs['pn']
    st, base = res.get('steps') or {}, res.get('base') or {}
    by_key = dict((row_key(t), t) for t in doc.get('trades_all') or [])
    t1, t2 = by_key[pn['k1']], by_key[pn['k2']]
    for name, s in list(st.items()) + [('variety ' + k[3:30], v) for k, v in (res.get('variety') or {}).items()]:
        if (s or {}).get('threw'):
            fails.append('%s, %s: the probe step threw -- %s' % (tag, name, _first(s['threw'])))
    if base.get('nodes'):
        fails.append('%s: the panel is in the page before anything was opened (%s node(s))' % (tag, base.get('nodes')))
    # -- open
    o = st.get('open') or {}
    rd = o.get('read')
    if not o.get('clicked') or not rd:
        fails.append('%s: a tap on the row of %s did not open the trade panel (row found=%s)' % (tag, pn['k1'], o.get('clicked')))
        return
    fails.extend(panel_problems('%s, open' % tag, rd, t1, doc))
    fails.extend(panel_layer_problems('%s, open' % tag, rd))
    if not (rd.get('fed') or {}).get('entry'):
        fails.append("%s: the probe's own case is wrong: the stub's bars do not hold the newest trade's entry, so no candle layer can be judged" % tag)
    fails.extend(panel_geo_problems('%s, open' % tag, rd, sheet, base))
    if rd.get('role') != 'dialog' or rd.get('modal') != 'true':
        fails.append('%s: the panel is not marked role=dialog aria-modal=true (%r, %r)' % (tag, rd.get('role'), rd.get('modal')))
    if not rd.get('focusIn'):
        fails.append('%s: focus did not move into the panel when it opened' % tag)
    if not o.get('drew'):
        fails.append('%s: the chart in the panel never drew an <svg> (the candles were stubbed)' % tag)
    if not o.get('hasOpen'):
        fails.append('%s: the panel has no OPEN CANDLES button' % tag)
    if sheet:
        if o.get('hasExpand') or 'wider screen' not in (rd.get('chartText') or ''):
            fails.append('%s: the phone chart shows EXPAND or lacks the wider-screen hint (the full viewer is not for a phone): %r'
                         % (tag, _first(rd.get('chartText'), 120)))
    elif not o.get('hasExpand'):
        fails.append('%s: the laptop chart has no EXPAND button' % tag)
    for what, got in (('EXPAND', o.get('expandOpened')), ('OPEN CANDLES', o.get('openOpened'))):
        if what == 'EXPAND' and sheet:
            continue
        if len(got or []) != 1 or got[0].get('no') != pn['k1'] or not got[0].get('has'):
            fails.append('%s: %s did not open the full candle viewer for this trade, stepping through the list rows (%r)' % (tag, what, got))
    if not o.get('stillOpen'):
        fails.append('%s: the panel closed when the candle viewer was asked for' % tag)
    if theme == 'mono':
        hue = rd.get('hue') or {}
        if (hue.get('checked') or 0) < 60:
            fails.append('%s: the MONO hue scan read only %s colours - it did not run' % (tag, hue.get('checked')))
        if hue.get('bad'):
            fails.append('%s: the panel carries a hue in MONO: %s' % (tag, '; '.join(hue['bad'])))
    # -- Esc
    e = st.get('esc') or {}
    if not e.get('closed'):
        fails.append('%s: Escape did not close the trade panel' % tag)
    _panel_room(tag, 'after Escape', e.get('g'), base, fails)
    if e.get('key') is not None:
        fails.append('%s: the board still holds %r as the open trade after Escape' % (tag, e.get('key')))
    # -- a tap outside, a tap inside
    s = st.get('outside') or {}
    if not s.get('clicked') or not s.get('opened'):
        fails.append('%s: the panel did not open for the outside-tap test' % tag)
    elif s.get('hit') != 'layer':
        fails.append('%s: the point tapped outside the panel lands on %r, not on the dimmed page' % (tag, s.get('hit')))
    else:
        if not s.get('keptOnInside'):
            fails.append('%s: a tap inside the panel closed it' % tag)
        if s.get('open'):
            fails.append('%s: a tap on the dimmed page outside the panel did not close it' % tag)
        _panel_room(tag, 'after a tap outside', s.get('g'), base, fails)
    # -- the close button
    s = st.get('button') or {}
    if not s.get('btn'):
        fails.append('%s: the panel has no close button' % tag)
    elif s.get('open'):
        fails.append('%s: the close button did not close the panel' % tag)
    _panel_room(tag, 'after the close button', s.get('g'), base, fails)
    # -- a Webull attempt netted against another leg: its diamond and its legend rows (the stub feeds outcome NETTED)
    nt = st.get('netted') or {}
    if not nt.get('clicked') or not nt.get('read'):
        fails.append('%s: the panel did not open for the netted-attempt case (row found=%s)' % (tag, nt.get('clicked')))
    else:
        fails.extend(panel_layer_problems('%s, a netted Webull attempt' % tag, nt['read'], netted=True))
        if not (nt['read'].get('fed') or {}).get('entry'):
            fails.append("%s: the probe's own case is wrong: no entry on the netted case's bars, so no diamond can be judged" % tag)
    # -- the chart glyph opens the candles and not the panel
    gl = st.get('glyph') or {}
    gt = by_key.get(gl.get('key'))
    if gt is None or len(gl.get('opened') or []) != 1 or gl['opened'][0].get('no') != gl.get('key') or gl.get('panel') or gl.get('keyState') is not None:
        fails.append('%s: a tap on a row\'s chart glyph must open the candles for that trade and not the panel (%r)' % (tag, gl))
    if pn.get('heavy'):
        # -- a redraw every few seconds: the same panel, the same trade, nothing rewritten, the scroll kept
        rr = st.get('redraw') or {}
        if not rr.get('canScroll'):
            fails.append("%s: the probe's own redraw case is wrong: the panel body cannot scroll, so the scroll check proves nothing" % tag)
        if not rr.get('same') or not rr.get('marked') or not rr.get('slotsKept'):
            fails.append('%s: a redraw of the board replaced the open panel or one of its slots (same panel node %s, panel %s, slots %s): it must be '
                         'refreshed in place' % (tag, rr.get('same'), rr.get('marked'), rr.get('slotsKept')))
        if rr.get('mutN'):
            fails.append('%s: a redraw of the board rewrote %s thing(s) inside the open panel (%s): it flickers' % (tag, rr.get('mutN'), ', '.join(rr.get('muts') or [])))
        if rr.get('canScroll') and abs((rr.get('top1') or 0) - (rr.get('top0') or 0)) > 2:
            fails.append('%s: a redraw moved the panel scroll from %s to %s' % (tag, rr.get('top0'), rr.get('top1')))
        want1 = {'trade': pn['k1'], 'sym': expected_leg_name(t1).strip(), 'side': tl_side_text(t1), 'net': signed(qe_pnl_of(t1))}
        for what in ('before', 'after'):
            got = rr.get(what)
            if not got or any(got.get(k) != v for k, v in want1.items() if k in got) or not got.get('trade'):
                fails.append('%s: %s the redraws the panel reads %r, want %r' % (tag, what, got, want1))
        if not rr.get('textSame') or not rr.get('drawn'):
            fails.append('%s: the panel changed its content or lost its chart over a redraw that changed nothing about the trade (text same %s, chart %s)'
                         % (tag, rr.get('textSame'), rr.get('drawn')))
        # -- paging, search, chip, LIST | TABLE: the open trade (an old one a short page leaves out) stays
        sv = st.get('survive') or {}
        want2 = {'trade': pn['k2'], 'sym': expected_leg_name(t2).strip(), 'side': tl_side_text(t2), 'net': signed(qe_pnl_of(t2))}
        if not sv.get('k2Row') or (sv.get('paged') or {}).get('onPage') is not False or (sv.get('chip') or {}).get('rowOn') is not False:
            fails.append("%s: the probe's own paging case is wrong (row of %s on the full page %s, on the short page %s, behind the %s chip %s)"
                         % (tag, pn['k2'], sv.get('k2Row'), (sv.get('paged') or {}).get('onPage'), pn['hideChip'], (sv.get('chip') or {}).get('rowOn')))
        if not sv.get('openDrawn'):
            fails.append('%s: the chart of a trade the list does not show right now never drew in the panel' % tag)
        if (sv.get('zzzz') or {}).get('rows') != 0:
            fails.append("%s: the probe's own search case is wrong: 'zzzz' left %s rows" % (tag, (sv.get('zzzz') or {}).get('rows')))
        for what, key in (('opened', 'open'), ('SHOW MORE shortened the page', 'paged'), ('SHOW MORE was tapped', 'more'),
                          ('a search that matches nothing', 'zzzz'), ('the search was cleared', 'cleared'), ('a search for noise', 'noise'),
                          ('a chip that hides it', 'chip'), ('the LIST turned into the TABLE', 'table'), ('the TABLE went back to the LIST', 'list')):
            sn = sv.get(key)
            got = sn if key == 'open' else ((sn or {}).get('snap'))
            if not got:
                fails.append('%s: the open trade panel is gone after %s (it must stay on its trade)' % (tag, what))
            elif got != want2:
                fails.append('%s: after %s the panel shows %r, want %r' % (tag, what, got, want2))
        if sv.get('sheet'):
            fails.append("%s: the board's old sheet opened while the trade panel was used" % tag)
        if (sv.get('table') or {}).get('mode') != 'table':
            fails.append("%s: the probe's own LIST | TABLE case is wrong (mode %r)" % (tag, (sv.get('table') or {}).get('mode')))
    # -- each kind of caveat
    vs = res.get('variety') or {}
    if len(vs) < 6:
        fails.append("%s: the probe's own caveat cases are wrong: only %d kinds of trade found in the fixture" % (tag, len(vs)))
    if sorted((pn.get('outcomes') or {}).values()) != PN_OUTCOMES:
        fails.append("%s: the probe's own outcome cases are wrong: %r" % (tag, pn.get('outcomes')))
    for k, v in vs.items():
        t = by_key.get(k)
        if t is None or not (v or {}).get('read'):
            fails.append('%s: the panel did not open for %s (%s)' % (tag, k[3:], 'row found' if (v or {}).get('clicked') else 'no row'))
            continue
        fails.extend(panel_problems('%s, %s' % (tag, k[3:40]), v['read'], t, doc))
        fails.extend(panel_layer_problems('%s, %s' % (tag, k[3:40]), v['read']))
        oc = (pn.get('outcomes') or {}).get(k)
        if ((v['read'].get('fed') or {}).get('outcome') or None) != (oc or None):
            fails.append("%s, %s: the probe's own case is wrong: the stub fed the Webull exit outcome %r, the case wants %r"
                         % (tag, k[3:40], (v['read'].get('fed') or {}).get('outcome'), oc))
        if theme == 'mono' and v['read'].get('hue'):
            hue = v['read']['hue']
            if hue.get('bad'):
                fails.append('%s, %s: the panel carries a hue in MONO: %s' % (tag, k[3:40], '; '.join(hue['bad'])))
    bo = next((by_key[k] for k in vs if by_key.get(k) and by_key[k].get('book_only')), None)
    if bo is None or 'BOOK ONLY' not in ((vs.get(row_key(bo)) or {}).get('read') or {}).get('chips', []):
        fails.append('%s: the panel of a book-only trade does not carry the BOOK ONLY chip (%r)' % (tag, ((vs.get(row_key(bo)) or {}).get('read') or {}).get('chips') if bo else 'no such trade'))
    if not any(by_key[k].get('nt_points') is not None for k in vs if by_key.get(k)):
        fails.append("%s: the probe's own case is wrong: no trade with NinjaTrader figures was opened" % tag)
    # -- the trade leaves the rows; the viewer leaves the board
    if pn.get('heavy'):
        gn = st.get('gone') or {}
        if not gn.get('opened') or not gn.get('closed') or gn.get('key') is not None:
            fails.append('%s: the panel stayed open after its trade left the board rows (another range): opened %s, closed %s, state %r'
                         % (tag, gn.get('opened'), gn.get('closed'), gn.get('key')))
        if not gn.get('back'):
            fails.append('%s: a trade panel is on the page after the range went back to ALL' % tag)
        lv = st.get('leave') or {}
        if not lv.get('opened') or not lv.get('closed') or lv.get('key') is not None:
            fails.append('%s: the panel stayed on the page after the viewer left the board: opened %s, closed %s, state %r'
                         % (tag, lv.get('opened'), lv.get('closed'), lv.get('key')))
        if not lv.get('back') or not lv.get('rows'):
            fails.append('%s: coming back to the board did not draw it again clean (panel %s, rows %s)' % (tag, not lv.get('back'), lv.get('rows')))
    _panel_room(tag, 'at the end', res.get('end'), base, fails, size=not pn.get('heavy'))


def _judge_tl_pwidth(tag, res, cs, fails):
    """The panel open and closed at every width: the page never scrolls sideways, a sheet at 600 and under, a right-hand panel above."""
    for mode in ('list', 'table'):
        for w in PN_WIDTHS:
            r = (res.get('w') or {}).get('%d%s' % (w, mode)) or {}
            t = '%s [%s, %d px]' % (tag, mode.upper(), w)
            o = r.get('open')
            if not r.get('clicked') or not o:
                fails.append('%s: a tap on a row did not open the panel' % t)
                continue
            if o.get('vw') != w or r.get('mode') != mode:
                fails.append('%s: the page is not measured (window %s, %s mode)' % (t, o.get('vw'), r.get('mode')))
                continue
            base = r.get('base') or {}
            if (base.get('sw') or 0) > (base.get('cw') or 0) + 1:
                fails.append('%s: the page scrolls sideways with the panel closed (scrollWidth %s > %s)' % (t, base.get('sw'), base.get('cw')))
            fails.extend(panel_geo_problems(t, o, w <= 600, base))
            if not r.get('shut'):
                fails.append('%s: Escape did not close the panel' % t)
            _panel_room(t, 'closed again', r.get('after'), base, fails)


def _judge_tl_main(tag, res, doc, fails):
    """The laptop run: every chip, a typed search (focus and caret kept), the sheet for the tapped trade (after a chip, after a search then
    clear, after a redraw, from the table), the chart glyph, SHOW MORE, LIST | TABLE remembered, the CSV, a calendar tap past a chip."""
    def J(sub, tl, **kw):
        return _judge_tl_frame('%s [%s]' % (tag, sub), tl, doc, None, fails, today=TL_TODAY, **kw)
    allrows = tl_rows(doc)
    all_keys = [row_key(t) for t in allrows]
    J('first draw', res.get('start'))
    for k in TL_CHIP_KEYS:
        tl = (res.get('chips') or {}).get(k)
        n = len(tl_rows(doc, None, k))
        if tl is None:
            fails.append('%s: the %s chip is not on the page' % (tag, k))
            continue
        if k != 'ALL' and not 0 < n < len(allrows):
            fails.append("%s: the probe's own case is wrong: the %s chip leaves %d of %d trades" % (tag, k, n, len(allrows)))
        J('chip ' + k, tl, chip=k)
    for txt, got in zip(['o', 'or', 'orb'], res.get('typed') or []):
        if not got.get('focus') or got.get('val') != txt or got.get('sel') != [len(txt), len(txt)]:
            fails.append('%s: after typing %r the search box has focus %s, text %r, caret %s -- it must keep its focus and caret across the '
                         'redraw' % (tag, txt, got.get('focus'), got.get('val'), got.get('sel')))
    if len(res.get('typed') or []) != 3:
        fails.append('%s: the typing step did not run' % tag)
    dk = res.get('doneKept') or {}
    if dk.get('focus') is not False or dk.get('hold'):
        fails.append('%s: after the viewer left the search box (a blur outside any redraw: the phone keyboard\'s Done) the next redraw took the '
                     'focus back into it (%s)' % (tag, dk))
    rt = res.get('retyped') or {}
    if not rt.get('focus') or rt.get('val') != 'o':
        fails.append('%s: typing again after leaving the box did not keep its focus (%s)' % (tag, rt))
    for q in ('orb', 'noise'):
        n = len(tl_rows(doc, None, 'ALL', q))
        if not 0 < n < len(allrows):
            fails.append("%s: the probe's own case is wrong: searching %r leaves %d of %d trades" % (tag, q, n, len(allrows)))
    J('search orb', res.get('search'), query='orb')
    J('search noise', res.get('searchNoise'), query='noise')
    if (res.get('cleared') or {}).get('rows') != all_keys or (res.get('cleared') or {}).get('query'):
        fails.append('%s: clearing the search did not bring every trade back (%s rows, query %r)'
                     % (tag, len((res.get('cleared') or {}).get('rows') or []), (res.get('cleared') or {}).get('query')))
    by_key = dict((row_key(t), t) for t in doc.get('trades_all') or [])
    for what, sh in (('after the SHORT chip', res.get('sheet1')), ('after a search and clear', res.get('sheet2')), ('from the table', res.get('sheet3'))):
        t = by_key.get((sh or {}).get('key'))
        if t is None:
            fails.append('%s: the trade panel step %s tapped no trade of the fixture (%r)' % (tag, what, sh))
            continue
        now = sh.get('now') or {}
        want = {'trade': row_key(t), 'sym': expected_leg_name(t).strip(), 'side': tl_side_text(t), 'net': signed(qe_pnl_of(t)), 'when': panel_when(t)}
        if now != want:
            fails.append('%s: a tap on the row for %s %s opened the trade panel %r, want %r (the panel follows the trade, not the row number)'
                         % (tag, row_key(t)[3:], what, now, want))
        if sh.get('closed') is False:
            fails.append('%s: the trade panel %s did not close' % (tag, what))
    s2 = res.get('sheet2') or {}
    if not s2.get('now') or s2.get('afterRender') != s2.get('now'):
        fails.append('%s: a redraw while the trade panel was open moved it from %r to %r' % (tag, s2.get('now'), s2.get('afterRender')))
    if not s2.get('escClosed'):
        fails.append('%s: Escape did not close the trade panel' % tag)
    gl = res.get('glyph') or {}
    gt = by_key.get(gl.get('key'))
    if gt is None or (gl.get('opened') or {}).get('no') != gl.get('key') \
            or not str((gl.get('opened') or {}).get('label') or '').startswith(expected_leg_name(gt).strip()) or gl.get('sheet'):
        fails.append('%s: a tap on a row\'s chart glyph did not open the candles for that trade (and only them): %r' % (tag, gl))
    pg = tl_page(allrows, TL_PAGE)
    if not TL_PAGE < len(pg) < len(allrows):
        fails.append("%s: the probe's own SHOW MORE case is wrong (%d of %d rows on a first page of %d: the cut must land inside a day, "
                     "or the day-split check proves nothing)" % (tag, len(pg), len(allrows), TL_PAGE))
    J('SHOW MORE, first page', res.get('page'), shown=TL_PAGE)
    J('SHOW MORE, after a tap', res.get('afterMore'), shown=TL_PAGE + 50)
    if res.get('shownState') != TL_PAGE + 50:
        fails.append('%s: a tap on SHOW MORE moved the page from %d to %r, want %d' % (tag, TL_PAGE, res.get('shownState'), TL_PAGE + 50))
    J('TABLE', res.get('table'), mode='table')
    if res.get('tableStored') != 'table':
        fails.append('%s: choosing TABLE was not stored for this board (el_lg_view_wb is %r)' % (tag, res.get('tableStored')))
    if res.get('reloadMode') != 'table':
        fails.append('%s: a page that comes back finds the list in %r mode, want the TABLE the viewer chose' % (tag, res.get('reloadMode')))
    J('LIST again', res.get('listAgain'))
    if res.get('listStored') != 'list':
        fails.append('%s: choosing LIST again was not stored (el_lg_view_wb is %r)' % (tag, res.get('listStored')))
    fails.extend(csv_problems('%s [CSV, every trade]' % tag, res.get('csvAll'), allrows))
    fails.extend(csv_problems('%s [CSV, SHOW MORE page open: every trade the list matches]' % tag, res.get('csvPage'), allrows))
    longs = tl_rows(doc, None, 'LONG')
    fails.extend(csv_problems('%s [CSV, LONG chip]' % tag, res.get('csvLong'), longs, 'LONG'))
    if len(res.get('longRows') or []) != len(longs):
        fails.append('%s: the LONG chip shows %d rows, want %d' % (tag, len(res.get('longRows') or []), len(longs)))
    orbs = tl_rows(doc, None, 'ALL', 'orb')
    fails.extend(csv_problems('%s [CSV, search orb]' % tag, res.get('csvOrb'), orbs, 'search-orb'))
    w1l = tl_rows(doc, _cutoff('1W', TL_TODAY), 'LONG')
    fails.extend(csv_problems('%s [CSV, 1W range + LONG chip]' % tag, res.get('csv1wLong'), w1l, '1W_LONG'))
    if len(res.get('w1LongRows') or []) != len(w1l):
        fails.append('%s: 1W + LONG shows %d rows, want %d' % (tag, len(res.get('w1LongRows') or []), len(w1l)))
    if len(res.get('orbRows') or []) != len(orbs):
        fails.append('%s: the search "orb" shows %d rows, want %d' % (tag, len(res.get('orbRows') or []), len(orbs)))
    ct = res.get('calTap') or {}
    if not ct.get('had') or ct.get('rowBefore'):
        fails.append("%s: the probe's own calendar case is wrong (day cell %s, its row on the page behind the SHORT chip: %s)"
                     % (tag, ct.get('had'), ct.get('rowBefore')))
    elif ct.get('active') != ['ALL'] or ct.get('query') or not ct.get('rowAfter'):
        fails.append('%s: a calendar tap on a day the SHORT chip hid did not clear the chip and land on that day (chip %r, search %r, '
                     'row on the page: %s)' % (tag, ct.get('active'), ct.get('query'), ct.get('rowAfter')))
    nn = res.get('none') or {}
    if nn.get('rows') or 'No trades match' not in (nn.get('empty') or '') or nn.get('count') != '0 / %d trades' % len(allrows):
        fails.append('%s: a search that matches nothing reads %r / %r with %d rows, want "No trades match this search or chip" and 0 / %d'
                     % (tag, nn.get('empty'), nn.get('count'), len(nn.get('rows') or []), len(allrows)))
    nc = res.get('noneCleared') or {}
    if nc.get('rows') != all_keys or nc.get('query') or nc.get('active') != ['ALL']:
        fails.append('%s: the clear link did not bring every trade back (%s rows, search %r, chip %r)'
                     % (tag, len(nc.get('rows') or []), nc.get('query'), nc.get('active')))


def _judge_tl_zero(tag, res, doc, fails):
    """A $0 trade is neither a win nor a loss: WINS and LOSSES leave it out, ALL keeps it."""
    zero = [t for t in tl_range_rows(doc) if qe_pnl_of(t) == 0]
    if len(zero) != 1:
        fails.append("%s: the probe's own case is wrong: %d $0 trades" % (tag, len(zero)))
        return
    zk = row_key(zero[0])
    for sub, key, chip, want_in in (('first draw', 'start', 'ALL', True), ('WINS', 'wins', 'WINS', False), ('LOSSES', 'losses', 'LOSSES', False),
                                    ('ALL', 'all', 'ALL', True)):
        tl = res.get(key)
        _judge_tl_frame('%s [%s]' % (tag, sub), tl, doc, None, fails, chip=chip, today=TL_TODAY)
        ids = [r.get('id') for d in ((tl or {}).get('days') or []) for r in d.get('rows') or []]
        if (zk in ids) != want_in:
            fails.append('%s [%s]: the $0 trade %s the list (a $0 trade is neither a win nor a loss)'
                         % (tag, sub, 'is missing from' if want_in else 'is in'))


def _judge_tl_shadow(tag, res, fixture, doc, fails):
    """A shadow row closed today: it is in the list, the count, the day net and the CSV nowhere."""
    shadow = [t for t in doc.get('trades_all') or [] if _is_shadow(t)]
    if len(shadow) != 1:
        fails.append("%s: the probe's own case is wrong: %d shadow rows" % (tag, len(shadow)))
        return
    sk = row_key(shadow[0])
    plain = [row_key(t) for t in tl_rows(fixture)]
    for sub, key, mode in (('list', 'start', 'list'), ('table', 'table', 'table')):
        tl = res.get(key)
        _judge_tl_frame('%s [%s]' % (tag, sub), tl, doc, None, fails, mode=mode, today=TL_TODAY)
        ids = [r.get('id') for d in ((tl or {}).get('days') or []) for r in d.get('rows') or []]
        if sk in ids or ids != plain:
            fails.append('%s [%s]: the list holds %d trades%s, want the fixture\'s %d without the shadow row'
                         % (tag, sub, len(ids), ' (the shadow row among them)' if sk in ids else '', len(plain)))
    fails.extend(csv_problems('%s [CSV]' % tag, res.get('csv'), tl_rows(doc)))
    if sk[3:] in ((res.get('csv') or {}).get('t') or ''):
        fails.append('%s [CSV]: the shadow row is in the CSV' % tag)


def _judge_tl_overnight(tag, res, doc, fails):
    """A trade that entered on a Friday and closed on the Monday sits under the Monday header, with its entry date on the row."""
    ov = [t for t in tl_range_rows(doc) if (_close_day(t) or '') != str(t.get('entry_ts') or '')[:10]]
    if len(ov) != 1:
        fails.append("%s: the probe's own case is wrong: %d trades closed on a later day than they entered" % (tag, len(ov)))
        return
    ok = row_key(ov[0])
    for sub, key, mode in (('list', 'start', 'list'), ('table', 'table', 'table')):
        tl = res.get(key)
        _judge_tl_frame('%s [%s]' % (tag, sub), tl, doc, None, fails, mode=mode, today=TL_TODAY)
        under = [d.get('day') for d in ((tl or {}).get('days') or []) for r in d.get('rows') or [] if r.get('id') == ok]
        if under != [_close_day(ov[0])]:
            fails.append('%s [%s]: the weekend trade sits under %r, want its close day %s' % (tag, sub, under, _close_day(ov[0])))


def _judge_tl_phone(tag, res, doc, vp, theme, fails):
    """A phone: five cells a row in the LIST and the TABLE, the flagged-row mark, the list top, no sideways page."""
    for mode in ('list', 'table'):
        _judge_tl_frame('%s [%s]' % (tag, mode.upper()), res.get(mode), doc, None, fails, mode=mode, vp=vp, theme=theme, top_check=True,
                        today=TL_TODAY)


def _judge_tl_width(tag, res, fails):
    """At every width the page is never wider than the window, in the LIST and in the TABLE; in the LIST no row is wider than its box and no
    strategy name is cut."""
    for mode in ('list', 'table'):
        for w in TL_WIDTHS:
            r = (res.get(mode) or {}).get(str(w)) or {}
            t = '%s [%s, %d px]' % (tag, mode.upper(), w)
            if r.get('iw') != w or r.get('mode') != mode or not r.get('rows'):
                fails.append('%s: the frame is not measured (window %s, %s mode, %s rows)' % (t, r.get('iw'), r.get('mode'), r.get('rows')))
                continue
            if (r.get('docSW') or 0) > (r.get('iw') or 0):
                fails.append('%s: the page scrolls sideways (scrollWidth %s > window %s; sticking out: %s)'
                             % (t, r.get('docSW'), r.get('iw'), ', '.join(r.get('wide') or []) or '?'))
            if mode == 'list' and r.get('rowsOver'):
                fails.append('%s: %s rows are wider than their box (by up to %s px)' % (t, r.get('rowsOver'), r.get('worst')))
            if mode == 'list' and r.get('symClip'):
                fails.append('%s: %s strategy names are cut off' % (t, r.get('symClip')))
            n, shown = r.get('cav') or [0, 0]
            if n and (r.get('frameW') or 0) <= 0:
                fails.append('%s: the list box was not measured (%r)' % (t, r.get('frameW')))
            elif n and shown != (n if r['frameW'] <= TL_CAV_BOX else 0):
                fails.append('%s: %s of %s flagged-row marks are drawn in a list box %s px wide (they show up to %d px)' % (t, shown, n, r.get('frameW'), TL_CAV_BOX))


def _tl_cases(fixture):
    """The runs on the trade list: name, scenario, doc (None = the fixture), viewport, theme, today, [width, height]."""
    def c(name, scen, doc=None, vp='laptop', th='dark', wh=None):
        return {'name': name, 'scen': scen, 'doc': doc, 'vp': vp, 'theme': th, 'today': TL_TODAY, 'wh': wh}
    out = [c('laptop 1366x768', 'main'),
           c('a $0 trade', 'zero', _zero_doc(fixture)),
           c('a shadow row closed today', 'shadow', _shadow_doc(fixture)),
           c('a trade held over a weekend', 'overnight', _overnight_doc(fixture)),
           c('phone 375x812', 'phone', vp='phone'),
           c('phone 390x844 MONO', 'phone', vp='phone390', th='mono')]
    w0 = c('widths %d to %d' % (TL_WIDTHS[0], TL_WIDTHS[-1]), 'width', wh=[TL_WIDTHS[0], 812])
    w0['widths'] = [[w, 812 if w < 700 else 900] for w in TL_WIDTHS]
    # LEDGER step 9: the trade panel, a laptop and a phone in glass / paper / MONO, and at the widths named
    pick = panel_pick(fixture)
    for vp, th in PN_RUNS:
        p = c('panel %s %s' % ('laptop 1366x768' if vp == 'laptop' else 'phone 375x812', th), 'panel', vp=vp, th=th)
        p['pn'] = dict(pick, vp=vp, heavy=(th == 'glass'))     # the steps that redraw the board many times run on the glass laptop and phone
        out.append(p)
    pw = c('panel widths %d to %d' % (PN_WIDTHS[0], PN_WIDTHS[-1]), 'pwidth', wh=[PN_WIDTHS[0], 812])
    pw['widths'] = [[w, 812 if w < 700 else 900] for w in PN_WIDTHS]
    pw['pn'] = dict(pick, vp='laptop')
    return out + [w0, pw]


def _overnight_doc(fixture):
    """The fixture with one Friday trade held over the weekend: it entered Fri 09-25 12:15 and closes Mon 09-28 09:35."""
    doc = json.loads(json.dumps(fixture))
    for t in doc.get('trades_all') or []:
        if str(t.get('entry_ts') or '').startswith('2026-09-25 12:15'):
            t['exit_ts'] = '2026-09-28 09:35:00'
            return doc
    raise RuntimeError('probe fixture changed: no 2026-09-25 12:15 trade to hold over the weekend')


def _judge_tl(data, fixture, fails, unfinished, why):
    """The trade list runs (the shared frame): one verdict per run."""
    got = data.get('tl') or {}
    for cs in _tl_cases(fixture):
        tag = 'trade list [%s]' % cs['name']
        res = got.get(cs['name'])
        if res is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if res.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get('seed'))))
            continue
        if res.get('threw'):
            fails.append('%s: the probe step threw -- %s' % (tag, _first(res.get('threw'))))
        _errs(tag, res, fails)
        doc, sc = cs['doc'] or fixture, cs['scen']
        if sc == 'main':
            _judge_tl_main(tag, res, doc, fails)
        elif sc == 'zero':
            _judge_tl_zero(tag, res, doc, fails)
        elif sc == 'shadow':
            _judge_tl_shadow(tag, res, fixture, doc, fails)
        elif sc == 'overnight':
            _judge_tl_overnight(tag, res, doc, fails)
        elif sc == 'phone':
            _judge_tl_phone(tag, res, doc, cs['vp'], cs['theme'], fails)
        elif sc == 'width':
            _judge_tl_width(tag, res, fails)
        elif sc == 'panel':
            _judge_tl_panel(tag, res, doc, cs, fails)
        elif sc == 'pwidth':
            _judge_tl_pwidth(tag, res, cs, fails)


def _removed_lint(alt_index):
    """Static lint (tools/ledger_removed.py): nothing the LEDGER clean-up removed (LEDGER_OLDBOARDS, the previous chart / stats / legs / calendar / trade list /
    drawer builders and their classes and hooks) is back in the file being gated. [] when clean."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    try:
        import ledger_removed
    finally:
        sys.path.pop(0)
    return ledger_removed.lint_file(alt_index or os.path.join(ROOT, 'index.html'), ['shared', 'webull'])


def _attempt(chrome, alt_index, fixture):
    probs = _removed_lint(alt_index)
    if probs:
        return FAIL, probs, [], None, False
    pdir = tempfile.mkdtemp(prefix='_webullprobe_', dir=ROOT)
    variants = [{'name': nm, 'nowMs': now if isinstance(now, int) else et_ms(now), 'doc': doc,
                 'offline': bool(exp.get('offline')), 'missing': bool(exp.get('missing')), 'unloaded': bool(exp.get('unloaded')),
                 'pin': bool(exp.get('pin')), 'systemOpen': bool(exp.get('ordmode') or exp.get('system') or exp.get('host') or exp.get('ordmode_has')),
                 'liveErr': bool(exp.get('liveErr')), 'prev': exp.get('prev'), 'prevCache': bool(exp.get('prev_cache')),
                 'tab': exp.get('tab'), 'vp': exp.get('vp', 'laptop'),
                 'renderMs': et_ms(exp['render_at']) if exp.get('render_at') else None,
                 'checkedMs': et_ms(exp['checked_at']) if exp.get('checked_at') else None,
                 'tick': bool(exp.get('tick')), 'fetch': exp.get('fetch'), 'theme': exp.get('theme', 'dark'),
                 'visread': bool(exp.get('visread')), 'cachesnap': bool(exp.get('cachesnap'))}
                for nm, now, doc, exp in _variant_docs(fixture)]
    stats = [{'name': c['name'], 'range': c['range'], 'doc': c['doc'], 'vp': c['vp'], 'theme': c['theme'],
              'calMonth': c['cal'], 'today': c['today'], 'more': c['more'], 'calOpen': c['cal_open'], 'folds': c['folds'],
              'nowMs': et_ms(c['now'])}
             for c in _stats_cases(fixture)]
    tls = [dict({'name': c['name'], 'scen': c['scen'], 'doc': c['doc'], 'vp': c['vp'], 'theme': c['theme'], 'today': c['today'], 'wh': c['wh'],
                 'widths': c.get('widths'), 'page': TL_PAGE}, **(c.get('pn') or {})) for c in _tl_cases(fixture)]
    html = (PROBE_HTML.replace('__CASES__', json.dumps(CASES)).replace('__VP__', json.dumps(VIEWPORTS))
            .replace('__STATS__', json.dumps(stats)).replace('__TLS__', json.dumps(tls)).replace('__TLJS__', TL_JS).replace('__S11JS__', S11_JS)
            .replace('__NOW__', json.dumps(et_ms(FRESH_NOW))).replace('__VARS__', json.dumps(variants))
            .replace('__FIX__', json.dumps(fixture)).replace('__OLDMARKS__', json.dumps(OLD_MARKS)))
    io.open(os.path.join(pdir, 'probe.html'), 'w', encoding='utf-8').write(html)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='webullprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
             '--user-data-dir=' + prof, '--virtual-time-budget=210000', '--window-size=1500,1000',
             '--dump-dom', 'http://127.0.0.1:%d/%s/probe.html' % (port, os.path.basename(pdir))],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900).stdout
    except Exception as e:
        return INCONCLUSIVE, ['chrome failed: %s' % e], [], None, True
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'WEBULLPROBE: (\{.*?\})</pre>', out or '', re.S)
    if not m:
        return INCONCLUSIVE, ['probe produced no readout'], [], None, True
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
                          .replace('&amp;', '&'))
    except Exception as e:
        return INCONCLUSIVE, ['unreadable readout: %s' % e], [], None, True
    if os.environ.get('WEBULLPROBE_DUMP'):
        print(json.dumps(data, indent=1)[:20000])
    if os.environ.get('WEBULLPROBE_DUMP_FILE'):
        io.open(os.environ['WEBULLPROBE_DUMP_FILE'], 'w', encoding='utf-8').write(json.dumps(data))
    res = _judge(data, fixture)
    st = _static_breakpoints(alt_index or os.path.join(ROOT, 'index.html')) + _static_wording(alt_index or os.path.join(ROOT, 'index.html'))
    if st:
        return FAIL, list(res[1]) + st, res[2], res[3], True
    return res


def _first(s, n=300):
    s = str(s or '')
    return s if len(s) <= n else s[:n] + '...'


def _errs(tag, r, fails):
    for k in ('uncaught', 'errors', 'loadErr'):
        for e in (r.get(k) or [])[:3]:
            fails.append('%s: %s -- %s' % (tag, {'uncaught': 'uncaught error', 'errors': 'console.error',
                                                'loadErr': 'LOAD ERROR'}[k], _first(e)))
    if r.get('overlay'):
        fails.append('%s: a LOAD ERROR overlay was on the page' % tag)


def _topbox(tag, r, fails):
    """The top bar WEBULL chip must be drawn where the owner can see it."""
    b = r.get('topBox')
    if not b:
        fails.append('%s: the top bar WEBULL chip is not on the page' % tag)
        return
    why = []
    if b.get('disp') == 'none' or b.get('vis') == 'hidden' or (b.get('op') is not None and b['op'] < 0.5):
        why.append('hidden (display %s, visibility %s, opacity %s)' % (b.get('disp'), b.get('vis'), b.get('op')))
    if not b.get('w') or not b.get('h'):
        why.append('zero size')
    elif b['l'] < -1 or b['t'] < -1 or b['r'] > b['vw'] + 1 or b['b'] > b['vh'] + 1:
        why.append('outside the %sx%s viewport (%s,%s to %s,%s)' % (b['vw'], b['vh'], b['l'], b['t'], b['r'], b['b']))
    if b.get('covered'):
        why.append('covered by %s' % b.get('coveredBy'))
    if why:
        fails.append('%s: the top bar WEBULL chip is %s' % (tag, '; '.join(why)))


def _judge_tiles(tag, r, want, fails):
    """The four shared tiles: present, in order, the right kind of text, equal to `want`."""
    st = r.get('stats') or []
    keys = [x[0] for x in st]
    if keys != STAT_KEYS:
        fails.append('%s: the stat tiles under the chart are %r, want %r ([data-lgstat])' % (tag, keys, STAT_KEYS))
        return
    got = {x[0]: (x[1] or '', x[2] or '') for x in st}
    if not re.match(r'^(\d+%|--)$', got['winrate'][0]):
        fails.append('%s: WIN RATE reads %r, not a percent' % (tag, got['winrate'][0]))
    if not re.match(r'^(\d+\.\d\d|no losses|--)$', got['pf'][0]):
        fails.append('%s: PROFIT FACTOR reads %r' % (tag, got['pf'][0]))
    if not re.match(r'^(\$[\d,]+\.\d\d|--)$', got['maxdd'][0]) or (got['maxdd'][0] == '--') != (want['maxdd'][0] == '--'):
        fails.append('%s: MAX DRAWDOWN reads %r, not a positive dollar amount' % (tag, got['maxdd'][0]))
    if not re.match(r'^\d+$', got['trades'][0]):
        fails.append('%s: TRADES reads %r, not a count' % (tag, got['trades'][0]))
    for k in STAT_KEYS:
        wv, ws = want[k]
        if got[k][0] != wv:
            fails.append('%s: %s reads %r, the fixture says %r' % (tag, k, got[k][0], wv))
        if ws is not None and got[k][1] != ws:
            fails.append('%s: the %s tile line reads %r, the fixture says %r' % (tag, k, got[k][1], ws))


def _judge_strip(tag, r, vp, fails):
    """The shared stat strip is SEEN, right under the chart: shown, of real size, below the chart box, above the
    Account and History sections, and on a phone above the Strategies list (as on REAL)."""
    b = r.get('statBox')
    if not b:
        fails.append('%s: the shared stat strip (.qbx-lgstats) is not on the page' % tag)
        return
    if (b.get('disp') == 'none' or b.get('vis') == 'hidden' or (b.get('op') is not None and b['op'] < 0.5)
            or not b.get('w') or not b.get('h') or not b.get('tileH') or b.get('tileH') == 9999):
        fails.append('%s: the stat strip cannot be seen (display %s, visibility %s, opacity %s, %sx%s px, tiles %s px high)'
                     % (tag, b.get('disp'), b.get('vis'), b.get('op'), b.get('w'), b.get('h'), b.get('tileH')))
        return
    top = b.get('top')
    if b.get('chartBottom') is None or top < b['chartBottom'] - 1:
        fails.append('%s: the stat strip does not start under the chart (strip top %s, chart bottom %s)'
                     % (tag, top, b.get('chartBottom')))
    for k, what in (('acctTop', 'Account'), ('histTop', 'History')):
        if b.get(k) is not None and top >= b[k]:
            fails.append('%s: the stat strip is drawn under the %s section (strip top %s, %s top %s)'
                         % (tag, what, top, what, b[k]))
    if vp.startswith('phone') and b.get('sideTop') is not None and top >= b['sideTop']:
        fails.append('%s: on a phone the stat strip is drawn under the Strategies list (strip top %s, list top %s)'
                     % (tag, top, b['sideTop']))


def _hue_and_label(tag, r, sc_, fixture, fails):
    """An open fold: no hue under MONO, and the account's change named for the day it belongs to."""
    m = r.get('more') or {}
    if sc_['theme'] == 'mono' and m.get('hued'):
        fails.append('%s: More stats draws colour under MONO (MONO has no hue): %s' % (tag, '; '.join(m['hued'][:4])))
    eq = fixture.get('equity') or {}
    if eq.get('net_liq') is None or eq.get('change_today') is None:
        return
    import datetime
    as_day, clock_day = str(eq.get('as_of_et') or '')[:10], sc_['now'][:10]
    if as_day and as_day != clock_day:
        wd = datetime.date(*map(int, as_day.split('-'))).strftime('%a')
        want = 'Account change on %s %s' % (wd, as_day[5:])
    else:
        want = 'Account change today'
    acct = [k.split('|', 1)[1] for k in (m.get('vals') or {}) if k.startswith('Account|')]
    if want not in acct:
        got = [a for a in acct if a.startswith('Account change')]
        fails.append("%s: More stats names the account's change %r, want %r (the doc's balance was read on %s, "
                     "the page's clock reads %s)" % (tag, got, want, as_day, clock_day))


def _judge_more(tag, r, sc_, trades, cutoff, fixture, fails):
    """A stats case's More stats fold: closed unless the case stored it open (as a reload finds it), then
    shown with the right groups and values; with no trade in the range, still the Account rows."""
    m = r.get('more') or {}
    if not sc_['more']:
        if r.get('moreBtn') != 'false' or m.get('panel') != 'hidden':
            fails.append('%s: More stats is not closed (aria-expanded %r, panel %r)' % (tag, r.get('moreBtn'), m.get('panel')))
        return
    if r.get('moreBtn') != 'true' or m.get('panel') != 'shown':
        fails.append('%s: More stats was stored open for this viewer but draws %s (aria-expanded %r) -- an open fold '
                     'is not remembered on reload' % (tag, m.get('panel'), r.get('moreBtn')))
        return
    vals = m.get('vals') or {}
    acct = [k.split('|', 1)[1] for k in vals if k.startswith('Account|')]
    _hue_and_label(tag, r, sc_, fixture, fails)
    if sc_['empty']:
        if not m.get('empty'):
            fails.append("%s: More stats does not say 'No trades in this range.' (groups %r)" % (tag, m.get('groups')))
        elif m.get('gap') is None or m['gap'] < 8:
            fails.append("%s: 'No trades in this range.' runs into the Account heading (%s px between them)"
                         % (tag, m.get('gap')))
        miss = [a for a in ACCOUNT_ROWS_ANY_RANGE if not any(x.startswith(a) for x in acct)]
        if miss:
            fails.append('%s: with no trade closed in the range More stats loses the Account rows %s (has %r)'
                         % (tag, miss, acct))
        eq = fixture.get('equity') or {}
        rails = fixture.get('rails') or {}
        checks = [('Account|Daily loss limit', money(-abs(float(rails['daily_loss_limit_usd'])))
                   if rails.get('daily_loss_limit_usd') is not None else '--')]
        if eq.get('net_liq') is not None:
            checks.append(('Account|Account equity', money(float(eq['net_liq']))))
        for k, w in checks:
            if k in vals and vals[k] != w:
                fails.append('%s: More stats %s reads %r, the fixture says %r' % (tag, k.split('|')[1], vals[k], w))
        ox = vals.get('Account|Open exposure') or ''
        if 'Account|Open exposure' in vals and not re.match(r'^-?\$[\d,]+\.\d\d', ox):
            fails.append('%s: More stats Open exposure reads %r, not a dollar amount' % (tag, ox))
        return
    if (m.get('groups') or [])[:4] != ['Returns', 'Risk', 'Mix', 'Account'] or 'Best and worst trade' not in (m.get('groups') or []):
        fails.append('%s: More stats groups are %r, want Returns, Risk, Mix, Account, Best and worst trade' % (tag, m.get('groups')))
    miss = [a for a in ACCOUNT_ROWS if not any(x.startswith(a) for x in acct)]
    if miss:
        fails.append('%s: the Account group is missing %s (has %r)' % (tag, miss, acct))
    for k, w in expected_more(trades, cutoff).items():
        if vals.get(k) != w:
            fails.append('%s: More stats %s reads %r, the fixture says %r' % (tag, k.replace('|', ' > '), vals.get(k), w))
    timed = [t for t in _range_rows(trades, cutoff) if t.get('entry_ts') and t.get('exit_ts')
             and str(t['exit_ts']) > str(t['entry_ts'])]
    hold = vals.get('Mix|Average hold')
    if timed and (not hold or hold == '--' or not re.search(r'\d', hold)):
        fails.append('%s: More stats Average hold reads %r with %d trades timed in the doc' % (tag, hold, len(timed)))


# -- KEEPS CHECKLIST (2026-10-07): board features that were on the page and that no check would notice breaking ---------------------------------------
FILLS_CHIP = 'FILLS BEHIND BACKTEST'
PAR_CHIP_RE = re.compile(r'^\d+ PARITY MISMATCH(ES)?$')


def expected_par_chip(doc):
    """The hero's PARITY MISMATCH chip (checked minus ok of the NinjaTrader-mirror summary): its text, None when it is not drawn, False when the doc has no summary to judge by."""
    p = doc.get('parity')
    if not isinstance(p, dict):
        return False
    try:
        n = int(float(p.get('checked'))) - int(float(p.get('ok')))
    except (TypeError, ValueError):
        return False
    return ('%d PARITY MISMATCH%s' % (n, '' if n == 1 else 'ES')) if n > 0 else None


def expected_fills_chip(doc):
    """FILLS BEHIND BACKTEST is drawn while the broker parity's rolling flag (board_flag) is up."""
    return bool((doc.get('broker_parity') or {}).get('board_flag'))


def expected_recon(doc):
    """The Account fold's share check on a live box: (its data-qbrecon word, its text) from positions_live, None when the doc gives no share counts."""
    pl = doc.get('positions_live')
    if not isinstance(pl, dict):
        return None
    bq, lq = _num(pl.get('broker_net_qty')), _num(pl.get('legs_net_qty'))
    if bq is None or lq is None:
        return None

    def word(q):
        n = _js_round(abs(q))
        return 'flat' if n == 0 else ('long ' if q > 0 else 'short ') + str(n)
    bad = bool(pl.get('mismatch'))
    return ('mismatch' if bad else 'ok',
            '%s \u2014 Webull holds %s \u00b7 legs sum to %s' % ('MISMATCH' if bad else 'OK', word(bq), word(lq)))


def expected_lease_ok(doc):
    return (doc.get('broker') or {}).get('lease_ok_to_send') is not False


def expected_host_line(doc, stale=False):
    """The System fold's host line while the one-computer check passes on a fresh doc; None when it fails (its reason is then worded by the page) or
    the box is silent (then 'last known, as of <time>': the variant states it)."""
    host = str(((doc.get('lease') or {}).get('host_id')) or 'an unknown computer')
    return ('Running on %s \u00b7 one-computer check OK' % host) if (expected_lease_ok(doc) and not stale) else None


def _fixture_book_only_problems(fixture):
    """The probe's own fixture: the box's book_only_summary must agree with its trades (the count of book-only trades, the broker's net of the rest)."""
    sm = fixture.get('book_only_summary') or {}
    rows = [t for t in fixture.get('trades_all') or [] if not _is_shadow(t)]
    out = []
    if int(sm.get('book_only_count') or 0) != sum(1 for t in rows if t.get('book_only')):
        out.append("the probe's own fixture is inconsistent: book_only_summary counts %s book-only trades, the trades carry %d"
                   % (sm.get('book_only_count'), sum(1 for t in rows if t.get('book_only'))))
    broker = round(sum(qe_pnl_of(t) for t in rows if not t.get('book_only')), 2)
    if _fin(sm.get('broker_net')) is None or abs(_fin(sm['broker_net']) - broker) > 0.005:
        out.append("the probe's own fixture is inconsistent: book_only_summary says the broker made %s, the trades that reached it make %s" % (sm.get('broker_net'), broker))
    return out


def _hero_extras(tag, r, doc, fails, stale_like=False, colour=True, ex=None, sys_open=False):
    """KEEPS CHECKLIST: the hero's amber broker line, the PARITY MISMATCH / FILLS BEHIND BACKTEST chips, the Account fold's share check and, with System
    open, its host line - each against what the doc says. `ex` carries the literal values a variant states for itself, so a mirror that drifted cannot
    agree with a broken page."""
    ex = ex or {}
    # -- the amber line: 'broker made $X of that (N book-only trades excluded)'
    notes, titles = r.get('heroNote') or [], r.get('heroNoteTitles') or []
    idx = [i for i, x in enumerate(notes) if x.startswith('broker made')]
    got_line = [notes[i] for i in idx]
    want = broker_line_want(doc)
    if 'broker_line' in ex and (ex['broker_line'] or None) != want:
        fails.append("%s: the probe's own case is wrong: the doc implies the broker line %r, the variant says %r" % (tag, want, ex['broker_line']))
    if want is None:
        if got_line:
            fails.append('%s: the hero shows %r although no trade on the page is book-only' % (tag, got_line))
    elif got_line != [want]:
        fails.append("%s: the hero's amber broker line reads %r, want %r (the page's own sum over its trades, book-only ones left out - never the box's "
                     "book_only_summary, review L3)" % (tag, got_line, want))
    else:
        n = sum(1 for t in doc.get('trades_all') or [] if not _is_shadow(t) and t.get('book_only'))
        tw = '%d trade%s never reached the broker' % (n, '' if n == 1 else 's')
        tip = titles[idx[0]] if idx[0] < len(titles) else ''
        if tw not in tip:
            fails.append("%s: the broker line's tooltip reads %r, want it to say %r" % (tag, tip, tw))
    # -- the chips: each drawn when its condition holds, left out when it does not, grey on a silent box
    flags = r.get('flags') or {}
    pc = [k for k in flags if PAR_CHIP_RE.match(k)]
    wp = expected_par_chip(doc)
    if 'par_chip' in ex and ex['par_chip'] != wp:
        fails.append("%s: the probe's own case is wrong: the doc implies the parity chip %r, the variant says %r" % (tag, wp, ex['par_chip']))
    if wp is None and pc:
        fails.append('%s: the hero draws %r although the NinjaTrader-mirror check has no mismatch' % (tag, pc))
    elif wp and pc != [wp]:
        fails.append('%s: the hero chips are %r, want %r (the mirror check: %s checked, %s ok)'
                     % (tag, sorted(flags), wp, (doc.get('parity') or {}).get('checked'), (doc.get('parity') or {}).get('ok')))
    wf = expected_fills_chip(doc)
    if 'fills_chip' in ex and ex['fills_chip'] != wf:
        fails.append("%s: the probe's own case is wrong: the doc implies FILLS BEHIND BACKTEST %s, the variant says %s" % (tag, wf, ex['fills_chip']))
    if wf != (FILLS_CHIP in flags):
        fails.append('%s: the hero %s the %s chip (the broker parity rolling flag is %s); chips %r'
                     % (tag, 'lacks' if wf else 'shows', FILLS_CHIP, 'up' if wf else 'down', sorted(flags)))
    if colour:
        for k in pc + ([FILLS_CHIP] if FILLS_CHIP in flags else []):
            if (flags[k] == 'grey') != stale_like:
                fails.append('%s: the hero chip %s is drawn %s, want %s (a flag the box wrote is only as current as its doc)'
                             % (tag, k, flags[k], 'grey' if stale_like else 'in colour'))
    # -- the Account fold's share check (a live box; a silent box's grey line is judged with the Account flags)
    rw = expected_recon(doc)
    if 'recon' in ex and tuple(ex['recon']) != rw:
        fails.append("%s: the probe's own case is wrong: positions_live implies the share check %r, the variant says %r" % (tag, rw, ex['recon']))
    if rw is not None and not stale_like and (r.get('recon'), r.get('reconTxt')) != rw:
        fails.append("%s: the Account fold's share check reads %r (data-qbrecon=%r), want %r (%r) from positions_live"
                     % (tag, r.get('reconTxt'), r.get('recon'), rw[1], rw[0]))
    # -- the System fold's host line and its one-computer check
    if sys_open:
        hl = r.get('hostLine')
        wh = expected_host_line(doc, stale_like)
        if 'hostline' in ex and wh is not None and ex['hostline'] != wh:
            fails.append("%s: the probe's own case is wrong: the doc implies the host line %r, the variant says %r" % (tag, wh, ex['hostline']))
        want_h = ex.get('hostline') or wh
        if want_h is not None and hl != want_h:
            fails.append('%s: the System fold\'s host line reads %r, want %r' % (tag, hl, want_h))
        if not expected_lease_ok(doc) and (hl or '').endswith('one-computer check OK'):
            fails.append('%s: the System fold says the one-computer check is OK while another computer holds the lease (%r)' % (tag, hl))
        if hl is None:
            fails.append('%s: the System fold has no "Running on <host> . one-computer check" line' % tag)
        elif stale_like and 'last known' not in hl:
            fails.append("%s: the System fold's host line reads %r on a silent box, want it marked last known with its time (review L2)" % (tag, hl))


# the candle layers a trade's panel chart draws, by data-mk: (hover title, the shape element, the legend row's start, what it is)
PN_LAYERS = {
    'signal': (re.compile(r'^signal bar$'), 'rect', 'signal bar ', 'the signal bar'),
    'bt_in': (re.compile(r'^backtest fill \d+\.\d\d$'), 'circle', 'backtest in ', 'the backtest fill'),
    'book_in': (re.compile(r'^book fill \d+\.\d\d$'), 'line', 'book in ', 'the book fill'),
    'wb_in': (re.compile(r'^Webull fill \d+\.\d\d$'), 'path', 'Webull in ', 'the Webull entry attempt'),
    'book_out': (re.compile(r'^book exit \d+\.\d\d$'), 'rect', 'book out ', 'the book exit'),
    'wb_out': (re.compile(r'^Webull exit \d+\.\d\d$'), 'rect', 'Webull out ', 'the Webull exit attempt'),
    'wb_netted': (re.compile(r'^no Webull order - netted against another leg at \d+\.\d\d$'), 'path', 'no Webull order ', 'a netted Webull attempt'),
    'bt_out': (re.compile(r'^backtest exit \d+\.\d\d$'), 'rect', 'backtest out ', 'the backtest exit'),
    'wb_refused': (re.compile(r'^Webull refused: probe: refused by Webull$'), None, 'Webull refused ', 'a Webull exit try Webull refused'),
    'wb_unknown': (re.compile(r"^sent - Webull's answer unknown"), None, "Webull's answer unknown", 'a Webull exit try whose answer never came'),
}
# the Webull exit try's mark by the outcome the stub fed it (None = FILLED)
PN_EXIT_MARK = {None: 'wb_out', 'NETTED': 'wb_netted', 'REFUSED': 'wb_refused', 'UNKNOWN': 'wb_unknown'}


def panel_layer_problems(tag, o, netted=False):
    """KEEPS CHECKLIST: one open panel's chart draws each candle layer's own mark - signal bar, backtest fill, book in / out, the Webull attempts (or the diamond
    of a NETTED one) - exactly the marks the stub fed that fall on its bars, each with its hover title, its shape and its legend row."""
    if not o.get('chartDrawn'):
        return []             # panel_problems already says the chart never drew
    fed = o.get('fed') or {}
    wb = 'wb_netted' if netted else None
    xmk = wb or PN_EXIT_MARK.get(fed.get('outcome'), 'wb_out')
    want = (['signal', 'bt_in', 'book_in', wb or 'wb_in'] if fed.get('entry') else []) + (['book_out', 'bt_out', xmk] if fed.get('exit') else [])
    got = o.get('marks') or []
    bad = []
    if bool(fed.get('netted')) != bool(netted):
        bad.append("the probe's own case is wrong: the stub fed netted=%s, the case wants %s" % (fed.get('netted'), netted))
    if sorted(m.get('k') or '' for m in got) != sorted(want):
        bad.append('the chart draws the layers %r, want %r (signal bar, backtest fill, book in / out, Webull attempts%s)'
                   % (sorted(m.get('k') or '' for m in got), sorted(want), ' - the attempt netted' if netted else ''))
    for m in got:
        spec = PN_LAYERS.get(m.get('k'))
        if spec is None:
            continue
        if not spec[0].match(m.get('t') or ''):
            bad.append('%s is titled %r (want %s)' % (spec[3], m.get('t'), spec[0].pattern))
        if spec[1] and m.get('sh') != spec[1]:
            bad.append('%s is drawn as <%s>, want <%s>' % (spec[3], m.get('sh'), spec[1]))
    legend = o.get('legend') or ''
    for k in sorted(set(want)):
        spec = PN_LAYERS[k]
        if netted and k == 'wb_netted':
            rows = (['no Webull order in '] if fed.get('entry') else []) + (['no Webull order out '] if fed.get('exit') else [])
        elif k == 'wb_netted':
            rows = ['no Webull order out ']
        else:
            rows = [spec[2]]
        for rw in rows:
            if rw not in legend:
                bad.append('the legend under the chart has no row for %s (%r missing from %r)' % (spec[3], rw, _first(legend, 160)))
    if 'wb_netted' in want and 'netted against another leg' not in legend:
        bad.append('the legend does not say the attempt was netted against another leg (%r)' % _first(legend, 160))
    return ['%s: %s' % (tag, x) for x in bad]


def _judge(data, fixture):
    fails, notes, unfinished = [], [], []
    fails.extend(_fixture_book_only_problems(fixture))
    why = data.get('why')
    if data.get('renderApp') != 'function':
        return (INCONCLUSIVE, ['app did not boot (renderApp=%s); see preflight_boot' % data.get('renderApp')],
                notes, data, True)
    if not data.get('authSettled'):
        notes.append('the signed-out screen never appeared; cases ran anyway')
    closed = round(sum(qe_pnl_of(t) for t in fixture.get('trades_all') or []), 2)
    n_rows = min(len(fixture.get('trades_all') or []), 50)
    cases = data.get('cases') or {}
    for nm, cfg in CASES:
        r = cases.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (nm, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, _first(r.get('call'))))
            continue
        if r.get('sampleErr'):
            fails.append('%s: the probe could not read the page -- %s' % (nm, _first(r['sampleErr'])))
            continue
        _errs(nm, r, fails)
        if r.get('heroMissing'):
            fails.append('%s: hero ids missing: %s' % (nm, ', '.join(r['heroMissing'])))
        if not MONEY_RE.match(r.get('heroBig') or ''):
            fails.append('%s: the hero big number reads %r, not a dollar amount' % (nm, r.get('heroBig')))
        if not (r.get('heroToday') or '').endswith('today'):
            fails.append('%s: the hero has no "today" line (got %r)' % (nm, r.get('heroToday')))
        if r.get('pills') != ','.join(LEDGER_RANGES):
            fails.append('%s: the range pills read %r, not %s' % (nm, r.get('pills'), ' '.join(LEDGER_RANGES)))
        if not r.get('chart'):
            fails.append('%s: the shared equity chart was not drawn (#qb-lg-chart has no svg)' % nm)
        else:
            min_h = 150 if cfg['vp'] == 'phone' else 200
            if (r.get('chartH') or 0) < min_h:
                fails.append('%s: the equity chart is %spx tall (squashed; needs %s+)' % (nm, r.get('chartH'), min_h))
            if (r.get('chartDates') or 0) < 2 or (r.get('chartTicks') or 0) < 2:
                fails.append('%s: the chart has %s date labels and %s price labels (needs 2+ of each)'
                             % (nm, r.get('chartDates'), r.get('chartTicks')))
            if not r.get('chartBands'):
                fails.append('%s: no hatched data-caveat day on the chart ([data-lgband])' % nm)
            if not r.get('chartMarks'):
                fails.append('%s: no run-change marker on the chart ([data-lgmark])' % nm)
            elif 'NOISE' not in (r.get('markText') or '') or '#382' not in (r.get('markText') or ''):
                fails.append('%s: the run-change marker reads %r (needs family + run, e.g. NOISE #304 -> #382)'
                             % (nm, r.get('markText')))
            if r.get('lines') != WANT_LINES:
                fails.append('%s: the chart legend lines are %r, not %r' % (nm, r.get('lines'), WANT_LINES))
            elif (r.get('lineIconW') or 0) > 24:
                fails.append('%s: the legend line icons are %spx wide (the legend wraps; want 16px)'
                             % (nm, r.get('lineIconW')))
            key = r.get('key') or ''
            if 'hatched' not in key or 'book only' not in key or 'book price' not in key or not all(k in key for k in KEY_WORDS):
                fails.append('%s: the caveat / book-only key under the chart reads %r' % (nm, key))
        _judge_list(nm, r.get('lg'), cfg['vp'], cfg['theme'], fixture, None, 'ALL', False, False, fails)
        _judge_cal(nm, r.get('lgcal'), cfg['vp'], cfg['theme'], fixture, None, None, _cal_open_want(cfg['vp'], None), STAT_TODAY, fails)
        _judge_tl_frame(nm, r.get('tl'), fixture, None, fails, vp=cfg['vp'], theme=cfg['theme'], top_check=True)
        _s11_order_problems(nm, r.get('s11') or {}, r.get('innerW') or 0, fixture, fails)
        _frame_problems(nm, (r.get('s11') or {}).get('frame'), r.get('innerW') or 0, fails)
        _s11_fold_problems(nm, r.get('s11') or {}, r.get('innerW') or 0, cfg['theme'], fixture, fails)
        if cfg['vp'] == 'phone':
            pp = (r.get('s11') or {}).get('pos') or {}
            tp = (pp.get('trades') or {}).get('t', 0) - (pp.get('shell') or {}).get('t', 0) if pp.get('trades') and pp.get('shell') else None
            if tp is None or tp > S11_PHONE_TOP_MAX:
                fails.append('%s: on a phone the trade list starts %s px under the board top; the limit is %d (757 since step 12) and it must not grow' % (nm, tp, S11_PHONE_TOP_MAX))
        legs = r.get('tradeLegs') or []
        if r.get('tradeRows') != n_rows:
            fails.append('%s: the trade list shows %s rows for %s trades' % (nm, r.get('tradeRows'), n_rows))
        bad = [x for x in legs if not LEG_RE.match(x or '')]
        if bad:
            fails.append('%s: trade rows without family + run number: %s' % (nm, sorted(set(map(str, bad)))[:5]))
        elif len(fixture.get('trades_all') or []) <= 50:
            want = collections.Counter(expected_leg_name(t) for t in fixture.get('trades_all') or [])
            got = collections.Counter(legs)
            if got != want:
                fails.append('%s: trade rows name the wrong run: shown %s, want %s'
                             % (nm, dict(sorted(got.items())), dict(sorted(want.items()))))
        dashes = r.get('lineDashes') or []
        if r.get('lines') == WANT_LINES and len(set(dashes)) != len(WANT_LINES):
            fails.append('%s: the three faint lines do not carry three different dashes (%r); under MONO they '
                         'cannot be told apart' % (nm, dashes))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (scrollWidth %s > clientWidth %s; sticking out: %s)'
                         % (nm, r.get('scrollW'), r.get('clientW'), ', '.join(r.get('wide') or []) or '?'))
        if (r.get('appLen') or 0) < 3000:
            fails.append('%s: the board rendered almost nothing (%s chars)' % (nm, r.get('appLen')))
        if 'silent' in (r.get('fresh') or {}):
            fails.append('%s: the fresh doc (24 s old, in the session) shows %r' % (nm, r['fresh']['silent']))
        _judge_tiles(nm, r, expected_stats(fixture.get('trades_all') or []), fails)
        _judge_strip(nm, r, cfg['vp'], fails)
        if r.get('moreBtn') != 'false':
            fails.append('%s: the More stats fold is not there closed (aria-expanded=%r)' % (nm, r.get('moreBtn')))
        if r.get('oldStats'):
            fails.append('%s: the old stat tiles are still drawn beside the shared ones' % nm)
        if (r.get('old') or {}).get('oldMarks'):
            fails.append('%s: markers of the removed previous board are in the page: %s' % (nm, ', '.join(r['old']['oldMarks'])))
        if not r.get('top') or r['top'][0] != 'flat':
            fails.append('%s: the top bar WEBULL chip reads %r, want FLAT' % (nm, r.get('top')))
        _topbox(nm, r, fails)
        _hero_extras(nm, r, fixture, fails, colour=cfg['theme'] == 'dark')
    _judge_variants(data, fixture, fails, unfinished, why)
    _judge_tl(data, fixture, fails, unfinished, why)
    got_st = data.get('stats') or {}
    for sc_ in _stats_cases(fixture):
        nm, rg, doc, vp, cm = sc_['name'], sc_['range'], sc_['doc'], sc_['vp'], sc_['cal']
        tag = 'stats [%s]' % nm
        r = got_st.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('call'))))
            continue
        _errs(tag, r, fails)
        if r.get('badTok'):
            fails.append('%s: the page shows %r' % (tag, r['badTok']))
        tr = doc.get('trades_all') or []
        cut = _cutoff(rg, sc_['today'])
        want = expected_stats(tr, cut)
        n_plain = len([t for t in tr if not _is_shadow(t)])
        if (want['trades'][0] == '0') != sc_['empty'] or (rg != 'ALL' and want['trades'][0] == str(n_plain)):
            fails.append('%s: the probe\'s own case is wrong: %s of %s trades in the range' % (tag, want['trades'][0], len(tr)))
        if any(_is_shadow(t) for t in tr):
            # a shadow row must change nothing: the tiles equal the fixture's own
            if want != expected_stats(fixture.get('trades_all') or [], cut):
                fails.append("%s: the probe's own case is wrong: its shadow row moved the recomputation" % tag)
            # ... and the hero and the trade list count the same trades as the stats (no shadow row anywhere)
            plain = [t for t in tr if not _is_shadow(t)]
            hero = money(_js_round(sum(qe_pnl_of(t) for t in plain) * 100) / 100.0)
            if r.get('heroBig') != hero:
                fails.append('%s: the hero reads %r, the trades without the shadow row make %s' % (tag, r.get('heroBig'), hero))
            if r.get('tradeRows') != min(len(plain), 50):
                fails.append('%s: the trade list shows %s rows, want %s (the shadow row left out)'
                             % (tag, r.get('tradeRows'), min(len(plain), 50)))
        _judge_tiles(tag, r, want, fails)
        _judge_strip(tag, r, vp, fails)
        _judge_more(tag, r, sc_, tr, cut, fixture, fails)
        _judge_list(tag, r.get('lg'), vp, sc_['theme'], doc, cut, rg, sc_['folds'], sc_['folds'], fails, distance=not sc_['more'])
        _judge_cal(tag, r.get('lgcal'), vp, sc_['theme'], doc, cut, cm, _cal_open_want(vp, sc_['cal_open']), sc_['today'], fails)
        _s11_order_problems(tag, r.get('s11') or {}, r.get('innerW') or 0, doc, fails)
        _frame_problems(tag, (r.get('s11') or {}).get('frame'), r.get('innerW') or 0, fails)
        _judge_tl_frame(tag, r.get('tl'), doc, cut, fails, vp=vp, theme=sc_['theme'], top_check=not sc_['more'], today=sc_['today'],
                        none_text=('no trades closed today \u00b7 %d more outside this range' % len(tl_range_rows(doc))) if sc_['empty'] else None)
        if nm == '$0 trade':
            if '1 even' not in (want['winrate'][1] or ''):
                fails.append('%s: the probe\'s $0 fixture trade did not land (%r)' % (tag, want['winrate'][1]))
            cw = month_won(tr, cm)
            if r.get('calWon') != cw:
                fails.append("%s: the calendar's %s '%% won' reads %r, want %r (a $0 trade is neither a win nor a loss)"
                             % (tag, cm, r.get('calWon'), cw))
        if vp.startswith('phone') and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (sticking out: %s)' % (tag, ', '.join(r.get('wide') or []) or '?'))
    res = data.get('inter')
    if res is None:
        unfinished.append('interaction run: never ran (why=%s)' % why)
    elif res.get('threw') and not res.get('seed'):
        fails.append('interaction run: the probe itself threw -- %s' % _first(res['threw']))
    else:
        tag = 'interaction run'
        if res.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get('seed'))))
        if res.get('threw'):
            fails.append('%s: %s' % (tag, _first(res['threw'])))
        _errs(tag, res.get('errs') or {}, fails)
        o, c = res.get('open') or {}, res.get('closed') or {}
        if o.get('expanded') != 'true' or not o.get('engu') or o.get('stored') != '1':
            fails.append('%s: the Retired group did not open with ENGU-Q in it and the choice kept (%s)' % (tag, o))
        if c.get('expanded') != 'false' or c.get('rows'):
            fails.append('%s: the Retired group did not close again (%s)' % (tag, c))
        sc = res.get('scrub') or {}
        if not sc:
            fails.append('%s: no chart to scrub' % tag)
        else:
            if sc.get('bigStart') != '$0.00' or 'start of the range' not in (sc.get('todayStart') or ''):
                fails.append('%s: a scrub at the range start did not write $0.00 / start of the range into the hero '
                             '(got %r / %r)' % (tag, sc.get('bigStart'), sc.get('todayStart')))
            if sc.get('bigEnd') != money(closed):
                fails.append('%s: a scrub at the last day reads %r, want the closed P&L of record %s'
                             % (tag, sc.get('bigEnd'), money(closed)))
            if not sc.get('held') or sc.get('heldAfter'):
                fails.append('%s: the live redraw hold did not follow the scrub (held=%s, after=%s)'
                             % (tag, sc.get('held'), sc.get('heldAfter')))
            if not sc.get('sameSvg'):
                fails.append('%s: the scrub re-rendered the chart' % tag)
            if sc.get('bigAfter') != sc.get('big0') or sc.get('todayAfter') != sc.get('today0'):
                fails.append('%s: leaving the chart did not put the hero back (%r -> %r)'
                             % (tag, sc.get('big0'), sc.get('bigAfter')))
        lg = res.get('legend') or {}
        if not lg.get('off') or 'ORB' not in (lg.get('stored') or ''):
            fails.append('%s: switching the ORB line off was not remembered (%s)' % (tag, lg))
        fo = res.get('fold') or {}
        if not fo:
            fails.append('%s: no More stats fold ([data-lgmore="qb"])' % tag)
        else:
            if fo.get('before') != 'false' or fo.get('open') != 'true' or fo.get('panel') != 'shown' or fo.get('stored') != '1':
                fails.append('%s: More stats did not open on a tap (aria-expanded %s -> %s, panel %s, stored %r)'
                             % (tag, fo.get('before'), fo.get('open'), fo.get('panel'), fo.get('stored')))
            if (fo.get('groups') or [])[:4] != ['Returns', 'Risk', 'Mix', 'Account']:
                fails.append('%s: More stats groups are %r, want Returns, Risk, Mix, Account' % (tag, fo.get('groups')))
            miss = [a for a in ACCOUNT_ROWS if not any(x.startswith(a) for x in (fo.get('acct') or []))]
            if miss:
                fails.append('%s: the Account group is missing %s (has %r)' % (tag, miss, fo.get('acct')))
            if fo.get('bad'):
                fails.append('%s: More stats shows %r' % (tag, fo['bad']))
            # on ALL the Webull rows against the fixture (Book figure over the same trades as Broker made)
            fvals = fo.get('vals') or {}
            for k, w in expected_more(fixture.get('trades_all') or []).items():
                if fvals.get(k) != w:
                    fails.append('%s: More stats %s reads %r on ALL, the fixture says %r'
                                 % (tag, k.split('|')[1], fvals.get(k), w))
            if fo.get('closed') != 'false' or fo.get('panelAfter') != 'hidden' or fo.get('stored2') != '0':
                fails.append('%s: More stats did not close again (aria-expanded %s, panel %s, stored %r)'
                             % (tag, fo.get('closed'), fo.get('panelAfter'), fo.get('stored2')))
        _judge_inter_ledger(tag, res, fixture, fails)
        _judge_filters_run(tag, res.get('filt'), fails)
    _judge_s11_run(data.get('s11'), fixture, fails)
    # ?oldboards=1 no longer changes anything: the second page load draws the plain laptop / MONO board
    r = cases.get('flagpage')
    plain = cases.get('laptop/mono') or {}
    if r is None:
        unfinished.append('flagpage: never ran (why=%s)' % why)
    elif r.get('call') != 'OK':
        fails.append('flagpage: renderApp threw -- %s' % _first(r.get('call')))
    else:
        _errs('flagpage', r, fails)
        for k, what in (('statTilesAll', 'shared stat tiles'), ('stats', 'tile values'), ('moreBtn', 'More stats fold'), ('calWon', 'calendar'),
                        ('tradeRows', 'trade rows'), ('tradeLegs', 'trade strategies')):
            if r.get(k) != plain.get(k):
                fails.append('flagpage: ?oldboards=1 does not draw the plain page %s (%r, plain %r)' % (what, r.get(k), plain.get(k)))
        for k, what in (('chart', 'shared chart'), ('retired', 'Retired group')):
            if bool(r.get(k)) != bool(plain.get(k)):
                fails.append('flagpage: ?oldboards=1 does not draw the plain page %s (%r, plain %r)' % (what, bool(r.get(k)), bool(plain.get(k))))
        if not r.get('statTilesAll') or not r.get('chart') or r.get('oldStats') or r.get('oldChart'):
            fails.append('flagpage: ?oldboards=1 does not draw the shared tiles and chart alone (tiles %s, chart %s, old tiles %s, old chart %s)'
                         % (r.get('statTilesAll'), bool(r.get('chart')), r.get('oldStats'), r.get('oldChart')))
        _flag_problems('flagpage', r, plain, fails)
    if fails:
        return FAIL, fails, notes, data, True
    if unfinished:
        return INCONCLUSIVE, unfinished, notes, data, True
    return PASS, [], notes, data, False


def _keeps_problems(tag, r, ex, fails):
    """The post-landing keeps on one variant (review 2026-10-07 section 4): the host line, the broker line, the strategy TODAY figure, the hero alarm
    chips, the share check, the Orders card's sentence, the daily stop's own words."""
    if ex.get('host'):
        want_st, subs, green = ex['host']
        h = r.get('host')
        if not h:
            fails.append("%s: the System fold has no 'Running on <host> - one-computer check' line ([data-qbhost])" % tag)
        else:
            if h[0] != want_st:
                fails.append('%s: the host line is marked %r, want %r (%r)' % (tag, h[0], want_st, h[1]))
            for s in subs:
                if s not in (h[1] or ''):
                    fails.append('%s: the host line reads %r, want %r in it' % (tag, h[1], s))
            if bool(h[2]) != green:
                fails.append('%s: the host line %s green, want %s (%r)' % (tag, 'draws' if h[2] else 'has no', 'green OK' if green else
                                                                            'no green: the check is only as current as the doc', h[1]))
    if ex.get('legtodayval') and r.get('legTodayVal') != ex['legtodayval']:
        fails.append("%s: the NOISE row's TODAY figure reads %r, want %r (today.legs_record, else the page's own sum on the box's day)"
                     % (tag, r.get('legTodayVal'), ex['legtodayval']))
    flags = r.get('flags') or {}
    for k, want in (ex.get('flags_has') or {}).items():
        if flags.get(k) != want:
            fails.append('%s: the hero chip %s is %s, want it drawn %s (chips: %r)' % (tag, k, 'missing' if k not in flags else 'drawn ' + flags[k], want, flags))
    for k in ex.get('flags_lacks') or []:
        if any(k in f for f in flags):
            fails.append('%s: the hero shows a %s chip on a doc that has none (chips: %r)' % (tag, k, flags))
    if ex.get('recon_is'):
        st, start = ex['recon_is']
        if r.get('recon') != st or not (r.get('reconTxt') or '').startswith(start):
            fails.append('%s: the share check reads %r (%s), want %s starting %r' % (tag, r.get('reconTxt'), r.get('recon'), st, start))
    for s in ex.get('ordmode_has') or []:
        if s not in (r.get('ordMode') or ''):
            fails.append('%s: the Orders card (System) reads %r, want %r in it' % (tag, r.get('ordMode'), s))
    for s in ex.get('stop_has') or []:
        if s not in (r.get('stopTxt') or ''):
            fails.append('%s: the daily stop line reads %r, want %r in it' % (tag, r.get('stopTxt'), s))
    for s in ex.get('stop_lacks') or []:
        if s in (r.get('stopTxt') or ''):
            fails.append('%s: the daily stop line reads %r, it must not say %r' % (tag, r.get('stopTxt'), s))


def _judge_variants(data, fixture, fails, unfinished, why):
    """The freshness variants: each chip, label and the top bar chip, against what the variant's
    clock and doc say they must be."""
    got_all = data.get('vars')
    for nm, _now, _doc, ex in _variant_docs(fixture):
        tag = 'freshness [%s]' % nm
        r = (got_all or {}).get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('call'))))
            continue
        if r.get('sampleErr'):
            fails.append('%s: the probe could not read the page -- %s' % (tag, _first(r['sampleErr'])))
            continue
        _errs(tag, r, fails)
        if r.get('after') not in (None, 'OK'):
            fails.append('%s: the probe step after the render threw -- %s' % (tag, _first(r.get('after'))))
        if r.get('wantsLiveHome') is not False:
            fails.append('%s: the full-doc listener would run on HOME (%r) -- it must be the board\'s only: about 134 KB '
                         'per snapshot, 0.7 GB a day per visible device against the 10 GiB a month cap' % (tag, r.get('wantsLiveHome')))
        if r.get('wantsLiveBoard') is not True:
            fails.append('%s: the doc listener would not run on the WEBULL PAPER board (%r)' % (tag, r.get('wantsLiveBoard')))
        if r.get('timer') != 'number':
            fails.append('%s: the 30 s freshness timer is not running (_qbFreshTimer is %r) -- a page left open never '
                         'turns stale while the box is silent (finding 8)' % (tag, r.get('timer')))
        if r.get('badTok'):
            fails.append('%s: the page shows %r' % (tag, r['badTok']))
        if ex.get('vp', 'laptop') != 'laptop' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways at %s (sticking out: %s)'
                         % (tag, ex.get('vp'), ', '.join(r.get('wide') or []) or '?'))
        if ex.get('visread') and r.get('visRead') != ex['visread']:
            fails.append('%s: reads when the page is shown again [HOME 60 s after the last, HOME 400 s after, board 60 s after] '
                         'are %r, want %r -- away from the board at most one per 5 min (each is the whole doc)'
                         % (tag, r.get('visRead'), ex['visread']))
        if ex.get('cachesnap') and r.get('cantRead') is not True:
            fails.append("%s: after a cached listener snapshot qbCantRead() is %r, want true -- a copy from this browser's "
                         'cache is not a read, so the page must not start blaming the box' % (tag, r.get('cantRead')))
        if ex.get('top_hidden'):
            b = r.get('topBox')
            if r.get('top') is not None or (b and b.get('disp') != 'none'):
                fails.append('%s: the top bar shows a WEBULL chip %r for an account with no Webull box' % (tag, r.get('top')))
        else:
            _topbox(tag, r, fails)
        if ex.get('pin'):
            p = r.get('pin') or {}
            if not p.get('tbH1'):
                fails.append('%s: the probe could not measure the top bar and sub-tab strip (%r)' % (tag, p))
            else:
                if (p.get('tbH0') or 0) >= p['tbH1']:
                    fails.append('%s: the stale chip did not make the phone top bar taller (%r to %r px), so this check '
                                 'proves nothing -- give it a longer chip text' % (tag, p.get('tbH0'), p['tbH1']))
                if p.get('subStyleTop') != '%dpx' % p['tbH1'] or p.get('subTop', 0) < p.get('tbBottom', 0) - 1:
                    fails.append('%s: after the read the sticky sub-tab strip is pinned at %s (top %s) under a %s px top bar '
                                 '(bottom %s, scrolled %s) -- it slides under the bar' % (tag, p.get('subStyleTop'), p.get('subTop'),
                                 p['tbH1'], p.get('tbBottom'), p.get('scrollY')))
        if ex.get('calendar'):
            want_cal = [False, True, True, 780, True]
            try:
                got_cal = json.loads(r.get('cal') or 'null')
            except Exception:
                got_cal = r.get('cal')
            if got_cal != want_cal:
                fails.append('%s: the session calendar reads %r for [Thanksgiving 2026-11-26 open?, Fri 2027-12-31 open?, '
                             '2027-12-30 open?, close of 2026-11-27 in minutes, 2026-10-05 open?], want %r'
                             % (tag, got_cal, want_cal))
        if ex.get('tab'):
            # another tab: only the top bar chip is the board's business there
            if r.get('tab') != ex['tab']:
                fails.append('%s: the probe could not open %s (activeTab=%r)' % (tag, ex['tab'], r.get('tab')))
            if tuple(r.get('top') or ()) != tuple(ex['top'] or ()):
                fails.append('%s: the top bar WEBULL chip is %r away from the board, want %r' % (tag, r.get('top'), ex['top']))
            continue
        _keeps_problems(tag, r, ex, fails)
        fresh = r.get('fresh') or {}
        names = {'silent': 'BOX SILENT', 'keel': 'KEEL', 'publish': 'UPDATES FAILING', 'pubgap': 'UPDATES PAUSED',
                 'tickgap': 'BOX STALLED', 'noread': 'THIS PAGE CANNOT READ'}
        for k, label in names.items():
            want = ex.get(k)
            if want is None and k in fresh:
                fails.append('%s: the hero shows %r, want no %s chip' % (tag, fresh[k], label))
            elif want is not None and fresh.get(k) != want:
                fails.append('%s: the hero %s chip reads %r, want %r' % (tag, label, fresh.get(k), want))
        today = r.get('heroToday') or ''
        if ex.get('today') and not today.endswith(ex['today']):
            fails.append('%s: the hero today line reads %r, want it to end with %r' % (tag, today, ex['today']))
        if tuple(r.get('top') or ()) != tuple(ex['top']):
            fails.append('%s: the top bar WEBULL chip is %r, want %r' % (tag, r.get('top'), ex['top']))
        strip = r.get('strip') or ''
        for s in ex.get('strip_has') or []:
            if s not in strip:
                fails.append('%s: the status strip lacks %r (reads %r)' % (tag, s, strip))
        for s in ex.get('strip_lacks') or []:
            if s in strip:
                fails.append('%s: the status strip says %r (reads %r)' % (tag, s, strip))
        for key, what in (('stop', 'daily-stop caption'), ('orders', "orders header"), ('legtoday', "NOISE leg's today label")):
            if key in ex and r.get(key) != ex[key]:
                fails.append('%s: the %s is dated %r, want %r' % (tag, what, r.get(key), ex[key]))
        if ex.get('orders') and ex['orders'] != 'today' and ('Orders on ' + ex['orders']) not in (r.get('ordersTxt') or ''):
            fails.append('%s: the orders header reads %r' % (tag, r.get('ordersTxt')))
        if ex.get('stop') and ex['stop'] != 'today' and ('from ' + ex['stop']) not in (r.get('stopTxt') or ''):
            fails.append('%s: the daily-stop caption reads %r, want "from %s"' % (tag, r.get('stopTxt'), ex['stop']))
        if ex.get('asof_has') and ex['asof_has'] not in (r.get('asof') or ''):
            fails.append('%s: the Account line reads %r, want %r' % (tag, r.get('asof'), ex['asof_has']))
        if 'eq_stale' in ex and bool(r.get('eqStale')) != ex['eq_stale']:
            fails.append('%s: the Account STALE flag is %s, want %s' % (tag, bool(r.get('eqStale')), ex['eq_stale']))
        if ex.get('eq_why') and ex['eq_why'] not in (r.get('eqWhy') or ''):
            fails.append('%s: the Account STALE flag says why as %r, want it to contain %r' % (tag, r.get('eqWhy'), ex['eq_why']))
        if ex.get('keelwarn') and r.get('keelwarn') != ex['keelwarn']:
            fails.append('%s: the NOISE row KEEL warning reads %r, want %r' % (tag, r.get('keelwarn'), ex['keelwarn']))
        if ex.get('silent') and ex.get('mini_silent') and r.get('miniSilent') != ex['mini_silent']:
            fails.append('%s: the Orders summary reads %r, want %r' % (tag, r.get('miniSilent'), ex['mini_silent']))
        # LEDGER step 11: the Orders fold's own one-line header (the mode, the daily stop used out of its limit, its state)
        osm = r.get('ordSum') or ''
        if ex.get('ordsum_start') and not osm.startswith(ex['ordsum_start']):
            fails.append('%s: the Orders fold header reads %r, want it to start with %r' % (tag, osm, ex['ordsum_start']))
        for s in ex.get('ordsum_has') or []:
            if s not in osm:
                fails.append('%s: the Orders fold header reads %r, want %r in it' % (tag, osm, s))
        for s in ex.get('ordsum_lacks') or []:
            if s in osm:
                fails.append('%s: the Orders fold header reads %r, it must not say %r' % (tag, osm, s))
        # finding 8: neither Orders view may still claim the frozen mode while the box is silent
        stale_like = bool(ex.get('silent') or ex.get('noread'))
        if stale_like:
            want_pill = 'BOX SILENT' if ex.get('silent') else 'NO STATUS'
            if r.get('miniPill') != want_pill:
                fails.append('%s: the sidebar Orders pill reads %r on a stale copy, want %s' % (tag, r.get('miniPill'), want_pill))
            # a page that cannot read is not the box's fault: amber, never BOX SILENT's red
            want_col, bad_col = ('var(--attn-red)', 'var(--attn-amber)') if ex.get('silent') else ('var(--attn-amber)', 'var(--attn-red)')
            for what, h in (('sidebar Orders pill', r.get('miniPillHtml')), ('Orders card pill (System)', r.get('ordModeHtml'))):
                if h is not None and (want_col not in h.split('</span>')[0] or bad_col in h.split('</span>')[0]):
                    fails.append('%s: the %s is not drawn in %s (%r)' % (tag, what, want_col, _first(h, 160)))
            if 'Sending orders' in (r.get('miniTxt') or ''):
                fails.append('%s: the sidebar Orders summary still says it is sending orders (%r)' % (tag, r.get('miniTxt')))
        if ex.get('ordmode'):
            om = r.get('ordMode') or ''
            if not om.startswith(ex['ordmode']) or 'Sending orders' in om or om.startswith('PAPER'):
                fails.append('%s: the Orders card (System) reads %r, want it to start with %r and not say '
                             'PAPER / Sending orders' % (tag, om, ex['ordmode']))
        # finding 9: every figure from an earlier trading day is dimmed
        if ex.get('today') and ex['today'] != 'today':
            for key, what in (('opNotToday', "hero's day line"), ('opStop', 'daily-stop bar'), ('opLegToday', "NOISE leg's day figure")):
                if r.get(key) is None or r[key] >= 1:
                    fails.append('%s: the %s from %s is drawn at opacity %r, want it dimmed' % (tag, what, ex['today'], r.get(key)))
        # finding 24: the Account change carries its own date and is dimmed when it is not today's
        # (every variant's balance was read on the doc's own trading day, so the two dates agree)
        if ex.get('today'):
            want_chg = ex['today']
            if r.get('eqChg') != want_chg:
                fails.append('%s: the Account change is labelled %r, want %r' % (tag, r.get('eqChg'), want_chg))
            elif want_chg != 'today' and (r.get('eqChgOp') is None or r['eqChgOp'] >= 1):
                fails.append('%s: the Account change from %s is not dimmed (opacity %r)' % (tag, want_chg, r.get('eqChgOp')))
            elif want_chg == 'today' and r.get('eqChgOp') is not None and r['eqChgOp'] < 1:
                fails.append("%s: today's Account change is dimmed (opacity %r)" % (tag, r.get('eqChgOp')))
        if stale_like:
            if r.get('recon') != 'stale' or 'as of ' not in (r.get('reconTxt') or ''):
                fails.append('%s: the Account reconcile line reads %r (%s) on a silent box, want it grey with its time'
                             % (tag, r.get('reconTxt'), r.get('recon')))
        elif r.get('recon') == 'stale':
            fails.append('%s: the Account reconcile line is greyed although the box is not silent' % tag)
        if ex.get('keelline') and ex['keelline'] not in (r.get('keelLine') or ''):
            fails.append('%s: the NOISE KEEL line reads %r, want it to contain %r' % (tag, r.get('keelLine'), ex['keelline']))
        if ex.get('lasttick') and r.get('lastTick') != ex['lasttick']:
            fails.append('%s: System LAST TICK reads %r, want %r' % (tag, r.get('lastTick'), ex['lasttick']))
        # finding 8: a flag the box wrote is only as current as the doc -- grey while the box is silent
        nr = (r.get('flags') or {}).get('NOT READY')
        if nr is None:
            fails.append("%s: the box's NOT READY flag is missing from the hero (flags %r)" % (tag, r.get('flags')))
        elif stale_like != (nr == 'grey'):
            fails.append("%s: the box's NOT READY flag is drawn %s, want %s" % (tag, nr, 'grey' if stale_like else 'in colour'))
        if ex.get('legpill') and r.get('legPill') != ex['legpill']:
            fails.append("%s: the NOISE row's position pill (%r) is drawn %s, want %s"
                         % (tag, r.get('legPillTxt'), r.get('legPill'), ex['legpill']))
        if ex.get('live_has') and ex['live_has'] not in (r.get('liveLine') or ''):
            fails.append("%s: the NOISE row's position line reads %r, want it to contain %r" % (tag, r.get('liveLine'), ex['live_has']))
        if ex.get('live_lacks') and ex['live_lacks'] in (r.get('liveLine') or ''):
            fails.append("%s: the NOISE row's position line reads %r, it must not say %r" % (tag, r.get('liveLine'), ex['live_lacks']))
        for key, what in (('openpnl', 'Open figure'), ('unreal', 'UNREALIZED figure')):
            if ex.get(key) and r.get(key if key != 'openpnl' else 'openPnl') != ex[key]:
                fails.append("%s: the NOISE row's %s is drawn %s, want %s"
                             % (tag, what, r.get(key if key != 'openpnl' else 'openPnl'), ex[key]))
        # keeps checklist: the hero's broker line and chips, the Account share check, the System host line
        _hero_extras(tag, r, _doc, fails, stale_like=stale_like, colour=ex.get('theme', 'dark') == 'dark', ex=ex,
                     sys_open=bool(ex.get('system') or ex.get('ordmode')))


def _report(t0, attempt, may_retry, chrome, alt_index, fixture):
    verdict, msgs, notes, data, retry = attempt
    first = None
    if verdict != PASS and retry and may_retry:
        first = (verdict, msgs)
        print('WEBULLPROBE: attempt 1 did not pass, retrying once before blocking -- %s'
              % ('; '.join(msgs[:2]) or 'no detail'))
        verdict, msgs, notes, data, retry = _attempt(chrome, alt_index, fixture)
    elapsed = time.time() - t0
    data = data or {}
    if verdict == INCONCLUSIVE:
        print('WEBULLPROBE: INCONCLUSIVE -- %s' % ('; '.join(msgs[:3]) if msgs else 'no detail'))
        return INCONCLUSIVE
    if verdict == FAIL:
        print('WEBULLPROBE: FAIL (VERSION=%s, %.1fs%s, %d problem(s))'
              % (data.get('VERSION'), elapsed, ', both attempts' if first else '', len(msgs)))
        seen = set()
        for f in msgs:
            if f not in seen and len(seen) < 25:
                seen.add(f)
                print('  - ' + f)
        for n in notes[:6]:
            print('  note: ' + n)
        return FAIL
    lap = (data.get('cases') or {}).get('laptop/dark') or {}
    cal0, lg0 = lap.get('lgcal') or {}, lap.get('lg') or {}
    book = ' | '.join('%s %s' % (x.get('name'), x.get('value')) for g in lg0.get('groups') or [] if g.get('key') == 'book'
                      for x in g.get('rows') or [])
    pg = ((((data.get('cases') or {}).get('phone/dark') or {}).get('lg') or {}).get('geo')) or {}
    tlp = (((data.get('tl') or {}).get('phone 375x812') or {}).get('list') or {}).get('geo') or {}
    pnl_ = ((((data.get('tl') or {}).get('panel laptop 1366x768 glass') or {}).get('steps') or {}).get('open') or {}).get('read') or {}
    pnp_ = ((((data.get('tl') or {}).get('panel phone 375x812 glass') or {}).get('steps') or {}).get('open') or {}).get('read') or {}
    pnl_r, pnp_r = pnl_.get('rect') or {}, pnp_.get('rect') or {}
    print('WEBULLPROBE: PASS (VERSION=%s, %d cases + interaction + %d stats cases + %d trade list runs + %d freshness variants + the ?oldboards=1 page, %.1fs; '
          'laptop chart %spx, %s dates, %s price labels, %s caveat days, marker %r; tiles %s; calendar %s %s; list %s, %s; '
          'phone trade list %s px under the board top, its frame %s px (limit %d); '
          'trade panel %sx%s px on a laptop, a sheet %sx%s px on a phone, %d panel runs + %d widths)'
          % (data.get('VERSION'), len(CASES), len(data.get('stats') or {}), len(data.get('tl') or {}), len(data.get('vars') or {}), elapsed, lap.get('chartH'),
             lap.get('chartDates'), lap.get('chartTicks'), lap.get('chartBands'), lap.get('markText'),
             ' | '.join('%s %s' % (x[0], x[1]) for x in (lap.get('stats') or [])),
             cal0.get('title'), (cal0.get('sum') or '').split(' · ')[0], lg0.get('count'), book,
             (pg.get('histTop') or 0) - (pg.get('shellTop') or 0), tlp.get('frameTop'), TL_FRAME_TOP_MAX,
             pnl_r.get('w'), pnl_r.get('h'), pnp_r.get('w'), pnp_r.get('h'), len(PN_RUNS), 2 * len(PN_WIDTHS)))
    if first:
        print('  FLAKE: attempt 1 did not pass on this same file, the retry did. It said:')
        for f in first[1][:4]:
            print('    - ' + f)
    for n in notes[:6]:
        print('  note: ' + n)
    return PASS


def _selftest_one(path):
    """One broken copy in a process of its own (for --jobs): (exit code, the probe's own first lines)."""
    for _ in range(2):
        try:
            r = subprocess.run([sys.executable, os.path.abspath(__file__), '--file', path, '--no-retry'], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=1500)
        except Exception as e:
            return INCONCLUSIVE, ['probe process failed: %s' % e]
        if r.returncode != INCONCLUSIVE:     # a page that did not boot on a busy box gets one more try
            break
    return r.returncode, (r.stdout or '').strip().splitlines()[:4]


def selftest(jobs=1, only=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass
    src = io.open(os.path.join(ROOT, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='webullprobe-selftest-')
    bad = []
    try:
        built = []
        only_set = set(n.strip() for n in only.split(',') if n.strip()) if only else None
        if only_set is not None:
            unknown = sorted(only_set - set(m[0] for m in MUTANTS))
            if unknown:
                print('SELFTEST: ERROR -- --only names no such mutant: %s (the names are the first item of each MUTANTS entry in tools/webull_board_probe.py)'
                      % ', '.join(unknown))
                return FAIL
        for name, anchor, repl, why in MUTANTS:
            if only_set is not None and name not in only_set:
                continue
            n = src.count(anchor)
            if n != 1:
                print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in '
                      'index.html (expected once). Update MUTANTS in tools/webull_board_probe.py: %r'
                      % (name, n, anchor))
                return INCONCLUSIVE
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(anchor, repl))
            built.append((name, why, path))
        if jobs > 1:
            # the broken copies run side by side, each in its own process; the verdicts print in the order they finish
            import concurrent.futures as _cf
            retry = []
            with _cf.ThreadPoolExecutor(max_workers=jobs) as ex:
                futs = dict((ex.submit(_selftest_one, path), (name, why)) for name, why, path in built)
                for f in _cf.as_completed(futs):
                    name, why = futs[f]
                    code, head = f.result()
                    if only_set is not None:
                        print('-- mutant %s (%s): %s (exit %d): %s' % (name, why, 'caught' if code == FAIL else 'NOT caught', code,
                                                                       ' | '.join(h.strip()[:230] for h in head[:3] if h.strip())))
                    else:
                        print('-- mutant %s (%s): expect FAIL -> exit %d: %s' % (name, why, code, (head[0] if head else '')[:200]))
                    if code == INCONCLUSIVE:
                        retry.append((name, why, futs[f]))
                    elif code != FAIL:
                        bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s' % (name, code, why))
            # a page that did not boot with other copies running beside it (twice) is run once more alone before it counts as not caught
            paths = dict((nm, pth) for nm, _w, pth in built)
            for name, why, _ in retry:
                code, head = _selftest_one(paths[name])
                print('-- mutant %s (%s): INCONCLUSIVE under parallel load, alone: %s (exit %d): %s'
                      % (name, why, 'caught' if code == FAIL else 'NOT caught', code, (head[0] if head else '')[:200]))
                if code != FAIL:
                    bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s' % (name, code, why))
        else:
            for name, why, path in built:
                print('-- mutant %s (%s): expect FAIL' % (name, why))
                code = main(['--file', path, '--no-retry'])
                if code == INCONCLUSIVE:     # a page that did not boot on a busy box gets one more try
                    code = main(['--file', path, '--no-retry'])
                if only_set is not None:
                    print('   -> mutant %s: %s (exit %d)' % (name, 'caught' if code == FAIL else 'NOT caught', code))
                if code != FAIL:
                    bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s' % (name, code, why))
        if not only_set:
            print('-- current index.html: expect PASS')
            code = main([])
            if code != PASS:
                bad.append('current index.html did not PASS (exit %d)' % code)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL (%.1fs)' % (time.time() - t0))
        for b in bad:
            print('  - ' + b)
        return FAIL
    if only_set:
        print('SELFTEST (only %d mutants): PASS -- all caught (%.1fs)' % (len(built), time.time() - t0))
        return PASS
    print('SELFTEST: PASS -- gate caught %d/%d broken builds and passed the current one (%.1fs)'
          % (len(MUTANTS), len(MUTANTS), time.time() - t0))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--no-retry', action='store_true', help='do not re-render a failed attempt')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every MUTANT of index.html, then PASS on the real file')
    ap.add_argument('--only', default=None, help='with --selftest: only these mutants (comma separated names), and skip the final run on the current file')
    ap.add_argument('--jobs', type=int, default=0,
                    help='with --selftest: how many broken copies to run side by side (default: 4, or fewer on a small machine; 1 = one by one)')
    args = ap.parse_args(argv)
    if args.only is not None and not args.selftest:
        ap.error('--only needs --selftest')
    if args.selftest:
        return selftest(args.jobs if args.jobs > 0 else min(4, max(1, (os.cpu_count() or 2) // 3)), args.only)
    t0 = time.time()
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('WEBULLPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    if not os.path.isfile(FIXTURE):
        print('WEBULLPROBE: INCONCLUSIVE -- fixture missing: %s' % FIXTURE)
        return INCONCLUSIVE
    fixture = json.load(io.open(FIXTURE, encoding='utf-8'))
    chrome = find_chrome()
    if not chrome:
        print('WEBULLPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    return _report(t0, _attempt(chrome, alt_index, fixture), not args.no_retry, chrome, alt_index, fixture)


if __name__ == '__main__':
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
