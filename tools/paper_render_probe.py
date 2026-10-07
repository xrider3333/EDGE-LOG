#!/usr/bin/env python3
"""
tools/paper_render_probe.py -- render gate for the PAPER and PAPER * boards.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. tools/studies_render_probe.py proves
COMPARE > STUDIES renders. Neither enters the PAPER branch of renderApp, which is one
of the largest views in the file -- and on 2026-08-26 a change to it shipped a
mismatched paren that the boot gate happily reported as PASS right up until the app
white-screened. Same lesson as the studies probe, different view.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe, seeds the board with a
REAL captured fixture (tools/fixtures/paper_board.json -- 87 trades, 13 daily reports,
the NinjaTrader backtest-match doc and a bridge snapshot), then forces the PAPER view
and re-renders it once per control combination. No Firebase sign-in is needed: the
board reads window._paperTrades / _paperReports / _ntBtMatch, and the fixture supplies
all three.

WHAT IT ASSERTS
---------------
  * every case renders without throwing, on BOTH the PAPER and PAPER * layouts
  * every LEGS-table row carries exactly as many cells as the table has headings
    (the v73.190 nested-<td> lesson: a wrong cell count shifts every figure one
    column right under the wrong heading, and the ROW count stays correct)
  * COLUMNS: KEY genuinely shows fewer columns than ALL, and the rows follow the head
  * ARCHIVED LEGS DO NOT LEAK. With SHOW ARCHIVED off, no trade row may belong to a
    leg declared archived:true -- the defect the owner hit on 2026-08-26, where a
    retired leg had no row to switch off yet kept 13 trades in the table, the curve,
    the calendar and the board totals. With SHOW ARCHIVED on, they must come back.
  * NO RED NinjaTrader CROSS ON A LEG NinjaTrader DOES NOT RUN. A red cross means
    "NinjaTrader was running this and refused the trade"; on a leg with no `nt` field
    nothing was ever going to take it, so the claim is unmakeable.
  * the crown glyph appears on exactly the legs declared crown:true and nowhere else
  * sorting by every sortable column renders, and never changes the row count
  * the board never silently empties
  * LEDGER step 3 (owner 2026-10-03), PAPER * layout: the all-time trade count shown equals the stored
    trade count; the big NET equals the listed strategies total equals the end of the bold line; the
    Other / shadow group has its own subtotal and is NOT in the big number (also with its trades switched
    on in the table); alarms that live in closed cards also show as chips in the hero
  * LEDGER step 4 (owner 2026-10-05), PAPER * layout: the hero is the shared one (same parts as REAL: label, big
    number, today line, range line, chips), labelled BOOK #463 - NT8 futures paper, with the warning chips inside
    it (since step 12: in the status line directly under it, the chip row empty); ONE pill row TODAY 1W 1M 3M YTD
    ALL (counted back from today) replaces the old 1W / 1M / All tabs and the Today / All time switch, and every
    pill moves the big number, the bold line, the stats, the calendar, the trade list and the strategy rows
    together; ALL is the old all-time figure
  * LEDGER step 5 (owner 2026-10-05): the curve is the shared ledgerChartRender - drawn at least 200 px tall on the
    laptop, with dates and a price scale, one faint line per shown book leg and a legend for them; the LAST point is
    the big number; a mouse hover and a finger drag write the hero number and the range line, and leaving puts them back
  * LEDGER steps 6, 7 and 10 (owner plan 2026-10-05; MANAGER 2026-10-06), PAPER * layout, each checked against a
    recomputation from the FIXTURE (the counted trades: book legs at their weights, closed, in the range, walked in the
    order they closed) and never against a number read off the page:
      - STATS: the four shared tiles in order (win rate, profit factor, max drawdown, trades) replace the ten-cell grid;
        drawdown is a POSITIVE dollar amount equal to the recomputation; the More stats fold opens with Returns, Risk, Mix
        and "Strategy vs control", holds every value the old grid showed (average trade / win / loss, best / worst day,
        green days, drawdown) and is remembered per browser; a range with no counted trades reads -- (the shared strip)
      - CALENDAR: the shared month calendar - a month's total and trade count equal the fixture's, a WEEK column, amber
        caveat days (roll splice / ORB look-ahead), the month arrows and the fold remembered per browser, and a day tap
        selects the rows that CLOSED that day (a trade entered weeks earlier included)
      - STRATEGY LIST: the shared list in the order BOOK #463 / Forward tests & controls / Other / shadow / Retired (the
        last two folds, closed); the BOOK group total equals the big number; every row is named family + run number, has a
        live-state dot, a signed P&L with an arrow and a switch; flipping a BOOK switch moves the big number, the chart
        end, the tiles, the calendar, the list and the trade list together, a not-counted strategy's switch only lists its
        trades; a row tap does what its switch does
      - PHONE (375 x 812): the trade list starts within one screen of the board top, the strategy list sits BELOW it with
        one line per row, the folds are closed and the page never scrolls sideways
      - ?oldboards=1 (a flag that changes nothing any more) draws the SAME board as the plain page: the shared tiles, strategy list and
        trade list frame, the same markup tree and css digests, none of the removed previous board's markers
  * LEDGER step 8 (owner plan 2026-10-05; MANAGER 2026-10-06), NT8 PAPER: the trades list is the shared trade list frame
    (ledgerTradeListHtml), each check recomputed from the FIXTURE (the rows the board lists, the New York day a trade closed,
    the money a row shows, the hold in seconds) and never read off the page:
      - ONE frame [data-lglist-frame="nt8"]: the count (shown / total), the five shared chips then one chip per strategy family,
        LIST | TABLE (a phone opens on LIST; remembered per board), the search box (keeps its cursor); every chip lists what the
        fixture says, WINS and LOSSES leave out a $0 trade
      - day headers newest CLOSE day first, each day net signed, coloured and equal to the sum of its counted rows; a trade still
        open sits in its own OPEN NOW block, in no day and no total
      - one visible tick box on every row at every width, one tick for every row shown; OPEN N CHARTS counts the ticks and hands the
        gallery exactly the ticked trades in list order; ticks on rows a filter hides drop out; a calendar day tap ticks that
        day's rows and scrolls to its header, also for a day older than the 200-row limit (the list stops at the END of a day)
      - a row click records the trade id (the trade panel is step 9) and never touches a tick box or the CHART cell
      - a strategy without a listed row reads family + #run number (ORB #257), as in the strategy list; the hold time reads in
        minutes and hours (the runner writes epoch SECONDS)
      - the PAGE never scrolls sideways (scrollWidth <= innerWidth, no tolerance) at 375, 601, 700, 800, 1000 and 1366 px, in LIST
        and in TABLE; a phone row is five cells; the phone TABLE fits its own box; the phone list starts no lower than 797 px
        under the board top
      - the old trades table (#ptrades-wrap) is nowhere in the page; no console.error or throw in any case
  * LEDGER step 9 (owner plan 2026-10-05; decision 6: a row click opens the panel), NT8 PAPER: TRADING-LOG's shared TRADE PANEL
    (ledgerTradePanelOpen) opens from a row of the list, each expectation recomputed from the FIXTURE:
      - on a laptop (1366x768) and a phone (375x812), in glass / paper / MONO (plus the LIST and the TABLE, and 600 px, still a bottom
        sheet): a click on a row opens a right-hand panel (laptop) or a bottom sheet (phone) tied to THAT trade id - the strategy with its
        run number, the side tag, the signed net coloured by lg-up / lg-down, the date and entry -> exit time, the size; slots in the order
        head, chart, numbers, notes, actions; in <body>, never inside #app
      - the numbers slot: entry, exit, size, hold time (the shared durStr on epoch SECONDS), points, net, SLIP, delta $ (from an injected
        NinjaTrader match), CUM (the counted trades in close order), and what the record carries (engine size, source, gate); the notes slot
        is READ-ONLY (it says NT8 keeps no notes) and shows the record reason / exit reason lines and the look-ahead warning; the actions
        slot holds OPEN IN GALLERY (it ticks the trade first) and the EL / NT / TV chips, nothing destructive; the chart slot draws the
        bars with its TRADE / FULL / minus / plus / PNG chips and EXPAND opens the full viewer; with no PC it says it could not load them
      - a tick box, the label round it, the CHART pill or a button inside a row never opens the panel; the OPEN NOW row opens one marked
        OPEN with no net and its exit read as open
      - the open trade survives a search, a chip (even one that takes the trade out of the list), LIST | TABLE and a redraw of the whole
        board, and never shows another trade; it closes by itself when the trade leaves the board rows (strategy switched off, a narrower
        range) and when the board is left
      - Esc, a tap outside and the close button close it, a tap inside does not; CLOSED = no .lg-panel node, the page exactly as wide and
        tall as before and <body> holding the same elements
      - in MONO no colour in the panel carries a hue; the PAGE never scrolls sideways at 375, 601, 700, 800, 1000 and 1366 px with the
        panel open or closed; no console.error or throw
    The BARS KEY (step 9 follow-up, case 'chartkey' in its own frame): a trade's bars are cached under the trade's own id, never under its
    place in the list. A stubbed PC answers every get_bars with bars whose price level belongs to the trade asked for; the CHART pill viewer
    and the OPEN N CHARTS gallery are then opened after a chip, a search, a LIST | TABLE switch and a header re-sort, and the price axis of
    every chart the page DREW must sit on that trade's own level (the gallery must hold exactly the ticked trades)
  * LEDGER step 11 (owner plan 2026-10-05; MANAGER 2026-10-06), NT8 PAPER: ONE page order, the board own sections as closed folds, ONE set of breakpoints
    (contract section 5b), every expectation recomputed from the FIXTURE or read off the live DOM, never from a number kept here:
      - the section markers [data-p2sec] run in the fixed order hero, range pills, chart, tiles, More stats, calendar, strategy list, trades, then the own
        folds (10s capture, NinjaTrader detail, cross-engine, gate audit, daily reports): strictly top to bottom at every width below 1100 px (the list
        is a fold between the calendar and the trades); from 1100 px the list is the right-hand column (since step 12 the frame panel beside the top
        block, not sticky) and every other section is stacked in the same order; no section is missing, empty or outside the board
      - the STATUS fold (the hero chips row; since step 12 the status line under the hero, a section of its own) and every own fold: closed to
        start (the strategy list fold is open above 600 px, closed on a phone), ONE summary line (<= 20 px tall, not cut, no stray markup), opens
        on a click and shows its content, closes again, and the choice is stored in localStorage; the status summary keeps every warning count (a
        warning chip per token, the totals, Recon 9 / Fills 1 from the fixture), REFRESH stays on the line (never inside a closed fold) and a
        warning chip opens the card that explains it
      - REMEMBERED: a fresh page (a real reload of a frame) after every fold was opened shows them all open, and closed after they were all closed
      - ONE SET OF BREAKPOINTS: every media / container rule that names the board (.p2 / nt8) uses only 600 (601 is its other side), 740, 800, 920
        or 1100 px; a scan that saw no such rule fails; the calendar opens by default above 600 px, closed up to it
      - the phone list top (trades) is no lower than before the step (797 px under the board top); the page never scrolls sideways at 375 / 601 / 700 /
        800 / 1000 / 1366 px; in MONO the new chrome (fold rows, REFRESH, the pills row, the hero with the status chips) has no hue
      - ?oldboards=1 draws the same board as the plain page (the same markup tree and css digests, so the same page sections and folds)
      - static lint (tools/ledger_removed.py): none of the identifiers the clean-up removed is back in index.html
  * LEDGER step 12 (MANAGER 2026-10-07, ONE PAGE FRAME), NT8 PAPER: the board sits in TRADING-LOG's shared page frame (ledgerFrameHtml),
    every expectation read off the live DOM of each case or worked out from the case's own settings, never from a number kept here:
      - exactly one [data-lgframe="p2"], at most 1320 px wide (computed max-width) and centred in its parent (left gap = right gap within 2 px,
        judged in every case whose window is wider than the frame); the markup in ONE order at every width: the top block (hero, STATUS, pills,
        chart, tiles, More stats, calendar), the side panel (the strategy list), the rest (the trades, then the own folds)
      - from 1100 px a two-column grid: the list ([data-p2sec="list"] in [data-lgframe-side]) is the right-hand panel beside the top block, level
        with it, never taller than it and scrolling inside it (no longer sticky); the trades and own folds run the full width under both; the drag
        bar [data-p2side] is on the panel. Under 1100 px ONE column, the list between the calendar and the trades
      - ONE status line [data-lgstatus="p2"] directly under the hero (above the pills) holds the status fold - every step 11 check of it (closed
        to start, one summary line, REFRESH on the line, a warning chip opens its card, remembered) reads it there - and the hero chip row is EMPTY
      - ONE chart foot [data-lgchartfoot="p2"] under the chart: the caption (.p2rhkey) shown on a laptop, hidden up to 600 px, gone from the pills
      - ONE Filters row [data-lgfilters="p2"] right after the list header: closed to start, its summary names the case's choices (Both / Raw /
        ML, the family, the sort, Baselines only), every old control inside it ([data-pkind] x3, [data-pfam], [data-lsort] x3, [data-pbase]);
        a click opens it (el_lg_filters_p2 = 1, every control drawn, each tray one line), Baselines only works from the open row (the board
        redraws, the row stays open), a second click closes it (0), and open / closed is remembered across a real reload
      - in MONO the status line, the chart foot and the Filters row carry no hue
  * money colours FOLLOW THE THEME (owner decision 8, 2026-10-05): no fixed green / red hex on a money cell, and
    every headline money cell carries an arrow and a sign, every dense one a sign
  * BOOK (owner 2026-10-04): the big number is the BOOK #463 figure - exactly the legs of api/paper.py _BOOK at
    their weights (TTM x3), read from the source, never a list kept here - and equals the BOOK group total
    equals the end of the bold line; "Forward tests & controls" and "Other / shadow" carry labelled subtotals
    that are not in it, and their switches never move it; the hero says BOOK #463; with no report weights the
    board's fallback equals _BOOK

The declarations (archived / crown / nt) are read out of index.html's own leg
definitions, so the probe compares what the source DECLARES against what the page
DRAWS rather than against a list that could drift.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.

Usage:
  python tools/paper_render_probe.py                # gates this repo's index.html
  python tools/paper_render_probe.py --file X.html  # gates X as if it were index.html
  python tools/paper_render_probe.py --selftest     # renders deliberately broken copies of the current index.html (MUTANTS
                                                    # below) side by side, asserts FAIL on each - for the reason it names - and
                                                    # then PASS on the real file (a few minutes; wt.py ship runs the plain probe)
  python tools/paper_render_probe.py --selftest --only a,b  # just those mutants, no pass on the real file (quick work on a few checks)

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import concurrent.futures
import datetime
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
CASE_CFG = {}

# name -> {sub, prefs, win, ls, frame}
#   prefs -> written into localStorage augurPrefs
#   win   -> assigned onto the iframe window before renderApp (lens-style, unsaved state)
#   ls    -> extra localStorage items (the per-browser LEDGER fold / month choices) set before renderApp
#   frame -> which iframe renders it: 'f' (laptop, default), 'fp' (375 px phone), 'fo' (laptop with ?oldboards=1)
CASES = [
    ('base',            {'sub': 'paper',  'prefs': {}, 'win': {}}),
    ('cols-all',        {'sub': 'paper',  'prefs': {'paperCols': 'all'}, 'win': {}}),
    ('paper2',          {'sub': 'paper2', 'prefs': {}, 'win': {}}),
    ('paper2-cols-all', {'sub': 'paper2', 'prefs': {'paperCols': 'all'}, 'win': {}}),
    ('fam-NOISE',       {'sub': 'paper',  'prefs': {'paperFam': 'NOISE'}, 'win': {}}),
    ('fam-ENGUQ',       {'sub': 'paper',  'prefs': {'paperFam': 'ENGU-Q'}, 'win': {}}),
    ('kind-ML',         {'sub': 'paper',  'prefs': {'paperKind': 'ML'}, 'win': {}}),
    ('kind-RAW',        {'sub': 'paper',  'prefs': {'paperKind': 'RAW'}, 'win': {}}),
    ('baselines',       {'sub': 'paper',  'prefs': {'paperBaseOnly': True}, 'win': {}}),
    ('legs-off',        {'sub': 'paper',
                         'prefs': {'paperLegOff': ['ORB', 'ORB_H', 'ENGUQ_ER', 'ENGUQ_ER_H',
                                                   'ENGUQ_L50', 'NOISE_225']}, 'win': {}}),
    ('show-archived',   {'sub': 'paper',  'prefs': {'paperOtherOn': ['ENGUQ']}, 'win': {'_paperShowArchived': True}}),
    ('scope-today',     {'sub': 'paper',  'prefs': {}, 'win': {'_paperMatrixScope': 'TODAY'}}),
    ('reports-open',    {'sub': 'paper2', 'prefs': {}, 'win': {'_p2Open': {'reports': True}}}),
    ('detail-open',     {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_paperShowCfg': True}}),
    ('sort-net',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'net', '_legSortDir': 'desc'}}),
    ('sort-net-asc',    {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'net', '_legSortDir': 'asc'}}),
    ('sort-pf',         {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'pf', '_legSortDir': 'desc'}}),
    ('sort-pf-asc',     {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'pf', '_legSortDir': 'asc'}}),
    ('sort-ev',         {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'ev', '_legSortDir': 'desc'}}),
    ('sort-perday',     {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'perday', '_legSortDir': 'desc'}}),
    ('sort-perday-asc', {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'perday', '_legSortDir': 'asc'}}),
    ('sort-fwd',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'fwd', '_legSortDir': 'desc'}}),
    ('sort-bf',         {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'bf', '_legSortDir': 'desc'}}),
    ('sort-leg',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'leg', '_legSortDir': 'asc'}}),
    ('sort-win',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'win', '_legSortDir': 'desc'}}),
    ('sort-days',       {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'days', '_legSortDir': 'desc'}}),
    ('sort-last',       {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'last', '_legSortDir': 'desc'}}),
    ('sort-n',          {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'n', '_legSortDir': 'desc'}}),
    # NT GATE chip (top bar): a status snapshot older than 15 minutes must read '?', and a PARTIAL gate must still
    # show a stale model age. checked_at far in the past / far in the future stand for old / fresh.
    ('gate-old-snapshot', {'sub': 'paper',  'prefs': {},
                           'win': {'_ntBridge': {'checked_at': '2020-01-01 00:00:00',
                                                 'gate': {'up': True, 'legs': [{'leg': 'A', 'loaded': True}]}}}}),
    ('gate-partial-stale', {'sub': 'paper',  'prefs': {},
                            'win': {'_ntBridge': {'checked_at': '2099-01-01 00:00:00',
                                                  'gate': {'up': True, 'error': 'x', 'stale_days': 6,
                                                           'legs': [{'leg': 'A', 'loaded': True},
                                                                    {'leg': 'B', 'loaded': False}]}}}}),
    ('gate-fresh-green', {'sub': 'paper',  'prefs': {},
                          'win': {'_ntBridge': {'checked_at': '2099-01-01 00:00:00',
                                                'gate': {'up': True, 'stale_days': 0,
                                                         'legs': [{'leg': 'A', 'loaded': True}]}}}}),
    # LEDGER step 3: the Other / shadow group, its switches, the strategy-list total, and warnings in the hero
    ('other-open',      {'sub': 'paper2', 'prefs': {}, 'win': {'_paperOtherOpen': True}}),
    ('other-on',        {'sub': 'paper2', 'prefs': {'paperOtherOn': ['ORB_257', 'NOISE_H'], 'paperOtherOpen': True},
                         'win': {}}),
    ('fwd-closed',      {'sub': 'paper2', 'prefs': {'paperFwdOpen': False}, 'win': {}}),
    ('range-today',     {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': 'TODAY'}}),
    ('range-1w',        {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': '1W'}}),
    ('range-1m',        {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': '1M'}}),
    ('range-3m',        {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': '3M'}}),
    ('range-ytd',       {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': 'YTD'}}),
    ('range-saved',     {'sub': 'paper2', 'prefs': {'paperRange': '1M'}, 'win': {}}),
    ('book-fallback',   {'sub': 'paper2', 'prefs': {}, 'win': {'__nobook': True}}),
    ('legs-off-p2',     {'sub': 'paper2',
                         'prefs': {'paperLegOff': ['ORB', 'ORB_H', 'ENGUQ_ER', 'ENGUQ_ER_H', 'ENGUQ_L50']},
                         'win': {}}),
    ('warn-stale-bridge', {'sub': 'paper2', 'prefs': {},
                           'win': {'_ntBridge': {'checked_at': '2020-01-01 00:00:00', 'up': True,
                                                 'strategies': [{'name': 'EdgeLogORB230', 'state': 'Realtime'}],
                                                 'gate': {'up': True, 'legs': [{'leg': 'A', 'loaded': True}]}}}}),
    ('no-bundle',       {'sub': 'paper2', 'prefs': {}, 'win': {'__noinfo': True}}),
    # LEDGER steps 6, 7 and 10 (PAPER * layout): the Retired fold, the More stats / calendar folds and the calendar month
    # remembered per browser, a 375 px phone, and the ?oldboards=1 flag (it must draw the same board as the plain page)
    ('retired-open',    {'sub': 'paper2', 'prefs': {'paperOtherOn': ['ENGUQ']}, 'win': {'_paperShowArchived': True}}),
    ('stats-open',      {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_stats_nt8': '1'}}),
    ('cal-closed',      {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_cal_nt8': '0'}}),
    ('cal-aug',         {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_calmo_nt8': '2026-08'}}),
    ('phone375',        {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp'}),
    ('flag-paper2',     {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fo'}),
    # LEDGER step 8 (the shared trade list frame on NT8): TABLE on a phone, the LIST on a laptop, every width from a phone to the
    # widest stacked page and the first two-column one, and a board with no trades at all
    ('phone375-table', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp', 'ls': {'el_lg_view_nt8': 'table'}}),
    ('laptop-list',    {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_view_nt8': 'list'}}),
    ('w600',           {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fm'}),
    ('w760',           {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fs'}),
    ('w1099',          {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fx'}),
    ('w1100',          {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fw'}),
    # zero state: an empty board must render a clean "no trades yet", not throw.
    ('empty',           {'sub': 'paper',  'prefs': {}, 'win': {'__empty': True}}),
]

# LEDGER step 8 (coordinator addendum 2026-10-06): the PAGE must never scroll sideways, at any width, in either view. One resizable
# frame is sized per case and the check is absolute (scrollWidth <= innerWidth, no tolerance): a phone, just past the phone cut, the
# middle of the stacked page, the first laptop widths and a normal laptop.
WIDTHS = (375, 601, 700, 800, 1000, 1366)
WIDTH_VIEWS = ('list', 'table')
for _w in WIDTHS:
    for _v in WIDTH_VIEWS:
        CASES.append(('wid-%d-%s' % (_w, _v), {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fz', 'width': _w,
                                                 'ls': {'el_lg_view_nt8': _v}}))

# LEDGER step 9: the shared trade panel on NT8 PAPER. `tid` is a counted winner (NOISE #422, size 1.75, carries a reason, an exit reason and a
# gate in the record), `tid2` a counted loser with a matched NinjaTrader fill (ORB #234, SHORT; the fixture builder injects the match), `otid`
# the trade that is still open. 'fl' is the 1366x768 laptop frame, 'fp' the 375x812 phone, 'fm' the 600 px edge; a phone case without
# `chart` has no PC to ask for bars. The first panel case in a frame must not have its bars cached yet (the cache outlives a case).
PANEL_TID, PANEL_TID2, PANEL_OTID = 'pt_NOISE_422_probe', 'pt_ORB_1786548600', 'pt_ENGUQ_335_probe_open'
# two trades of a strategy outside the book (its switch is on, paperOtherOn): their chips read NT approx (blue hex in the list) and NT cross (amber hex)
PANEL_BLUE, PANEL_AMBER = 'pt_NOISE_SBS_V90_1786628400', 'pt_NOISE_SBS_V90_1786635600'
PANEL_PREFS = {'paperOtherOn': ['NOISE_SBS_V90']}
PANEL_CASES = []
for _vp, _fr in (('laptop', 'fl'), ('phone', 'fp')):
    for _th in ('glass', 'paper', 'mono'):
        PANEL_CASES.append(('panel-%s-%s' % (_vp, _th), {'sub': 'paper2', 'prefs': PANEL_PREFS, 'win': {}, 'frame': _fr, 'theme': _th, 'vp': _vp,
                                                         'panel': {'tid': PANEL_TID, 'tid2': PANEL_TID2, 'otid': PANEL_OTID,
                                                                   'blue': PANEL_BLUE, 'amber': PANEL_AMBER,
                                                                   'chart': not (_vp == 'phone' and _th == 'glass')}}))
PANEL_CASES.append(('panel-laptop-glass-list', {'sub': 'paper2', 'prefs': PANEL_PREFS, 'win': {}, 'frame': 'fl', 'theme': 'glass', 'vp': 'laptop',
                                                'ls': {'el_lg_view_nt8': 'list'},
                                                'panel': {'tid': PANEL_TID, 'tid2': PANEL_TID2, 'otid': PANEL_OTID,
                                                          'blue': PANEL_BLUE, 'amber': PANEL_AMBER, 'chart': True}}))
PANEL_CASES.append(('panel-phone-glass-table', {'sub': 'paper2', 'prefs': PANEL_PREFS, 'win': {}, 'frame': 'fp', 'theme': 'glass', 'vp': 'phone',
                                                'ls': {'el_lg_view_nt8': 'table'},
                                                'panel': {'tid': PANEL_TID, 'tid2': PANEL_TID2, 'otid': PANEL_OTID,
                                                          'blue': PANEL_BLUE, 'amber': PANEL_AMBER, 'chart': True}}))
PANEL_CASES.append(('panel-w600', {'sub': 'paper2', 'prefs': PANEL_PREFS, 'win': {}, 'frame': 'fm', 'theme': 'glass', 'vp': 'edge600',
                                   'panel': {'tid': PANEL_TID, 'tid2': PANEL_TID2, 'otid': PANEL_OTID,
                                             'blue': PANEL_BLUE, 'amber': PANEL_AMBER, 'chart': True}}))
CASES.extend(PANEL_CASES)

# LEDGER step 9 follow-up: a trade's bars are cached under the trade's own id, never under its place in the list. Its own frame 'fk' (1366x900): the
# bars cache outlives a case, and a frame no other case has drawn a chart in starts with an empty one.
CHARTKEY_CASE = ('chartkey', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fk', 'ckey': True, 'ls': {'el_lg_view_nt8': 'list'}})
CASES.append(CHARTKEY_CASE)

# LEDGER step 11: the fixed page order, the own folds, the breakpoints. [data-p2sec] markers in the order they must run (the strategy list sits between the
# calendar and the trades on a page narrower than the two-column one; from 1100 px it is the right-hand column).
# LEDGER step 12: the status line is a section of its own directly under the hero, and the markup runs in this ONE order at every width - the shared page
# frame's top block (hero to calendar), its side panel (the strategy list: the right-hand panel from 1100 px) and the rest (the trades, the own folds).
SECTION_ORDER = ['hero', 'status', 'pills', 'chart', 'stats', 'more', 'cal', 'list', 'trades', 'capture', 'nt', 'recon', 'gate', 'reports']
TOP_SECTIONS = ['hero', 'status', 'pills', 'chart', 'stats', 'more', 'cal']   # LEDGER step 12: the frame top block, in this order
FRAME_MAX_W = '1320px'                                             # LEDGER step 12: .lg-frame max-width (WEBULL's column), centred
OWN_FOLDS = ['capture', 'nt', 'recon', 'gate', 'reports']          # the board own folds after the trades (the status fold lives in the status line)
S11_KEYS = ['status', 'capture', 'nt', 'recon', 'gate', 'reports', 'list']   # every remembered fold: localStorage el_lg_<key>_nt8
HOUSE_WIDTHS = [600, 601, 740, 800, 920, 1100]                     # the one set of breakpoints (contract 5b); 601 is the other side of 600
S11_PHONE_LIST_TOP = 797                                           # px under the board top before the step (LEDGER mistake #12) - it must not grow
# what the removed previous board drew: none of it may be in the page, in any case (the page-side readout lists the ones it finds). #ptrades-wrap
# is deliberately not in tools/ledger_removed.py, so a mutant can put it back and prove that THIS check sees it.
OLD_MARKS = ['#ptrades-wrap', '#ptrades-body', '#pt-selbar', 'tr[data-ptrow]', 'tr[data-paperleg]', 'tr[data-paperother]', '.p2rhstat',
             '.p2sheet', '[data-p2num]', '.p2rhrow']
_ALL_OPEN = dict(('el_lg_%s_nt8' % k, '1') for k in S11_KEYS)
_ALL_OPEN['el_lg_filters_p2'] = '1'                                # LEDGER step 12: the Filters row of the strategy list opened too
S11_CASES = [
    ('s11-laptop', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fl', 's11': 'fold'}),
    ('s11-phone', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp', 's11': 'fold'}),
    ('s11-tablet', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fs', 's11': 'fold'}),
    ('s11-mono-laptop', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fl', 'theme': 'mono', 'ls': _ALL_OPEN, 's11': 'mono'}),
    ('s11-mono-phone', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp', 'theme': 'mono', 'ls': _ALL_OPEN, 's11': 'mono'}),
    ('phone375-list-open', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp', 'ls': {'el_lg_list_nt8': '1'}}),
    # the auto-recover switch (a chip of the status row) is kept: a bridge snapshot that carries the watchdog
    ('s11-watchdog', {'sub': 'paper2', 'prefs': {}, 'frame': 'fl',
                      'win': {'_ntBridge': {'checked_at': '2099-01-01 00:00:00', 'up': True, 'watchdog': {'enabled': True},
                                            'strategies': [{'name': 'EdgeLogORB230', 'state': 'Realtime'}],
                                            'gate': {'up': True, 'stale_days': 0, 'legs': [{'leg': 'A', 'loaded': True}]}}}}),
]
CASES.extend(S11_CASES)

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>paper probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<iframe id="fp" src="../index.html" style="width:375px;height:812px;border:0"></iframe>
<iframe id="fo" src="../index.html?oldboards=1" style="width:1500px;height:1000px;border:0"></iframe>
<iframe id="fm" src="../index.html" style="width:600px;height:900px;border:0"></iframe>
<iframe id="fs" src="../index.html" style="width:760px;height:900px;border:0"></iframe>
<iframe id="fx" src="../index.html" style="width:1099px;height:900px;border:0"></iframe>
<iframe id="fw" src="../index.html" style="width:1100px;height:900px;border:0"></iframe>
<iframe id="fz" src="../index.html" style="width:1500px;height:900px;border:0"></iframe>
<iframe id="fl" src="../index.html" style="width:1366px;height:768px;border:0"></iframe>
<iframe id="fk" src="../index.html" style="width:1366px;height:900px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__, FIX=__FIX__, HOUSE=__HOUSE__, S11K=__S11K__, OLDMARKS=__OLDMARKS__;
(function(){
  var reported=false;
  // ---- LEDGER step 8 on NT8 PAPER: the shared trade list frame - console / throw sink, readouts, interactions
  var SINK={};
  function hook(id){
    var fw=document.getElementById(id).contentWindow,s={errors:[],uncaught:[]};SINK[id]=s;
    try{fw.renderAuth=function(){};}catch(e){}   // a late sign-in screen must not replace the board while the panel cases run
    try{var ce=fw.console.error;fw.console.error=function(){
      s.errors.push([].map.call(arguments,function(a){return String(a&&a.stack?a.stack:a).slice(0,300);}).join(' '));
      try{ce.apply(fw.console,arguments);}catch(e){}};}catch(e){}
    try{fw.addEventListener('error',function(ev){s.uncaught.push(String(ev.message||ev.error).slice(0,300));});
      fw.addEventListener('unhandledrejection',function(ev){s.uncaught.push('unhandledrejection '+String(ev.reason&&ev.reason.stack?ev.reason.stack:ev.reason).slice(0,300));});}catch(e){}
  }
  function drain(id){var s=SINK[id];if(!s)return {errors:[],uncaught:[]};return {errors:s.errors.splice(0).slice(0,8),uncaught:s.uncaught.splice(0).slice(0,8)};}
  function _t1(e){return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;}
  function _dayOf(row){
    var g=row.closest('[data-lgday]');if(g)return g.getAttribute('data-lgday');
    var p=row.previousElementSibling;
    while(p){if(p.hasAttribute&&p.hasAttribute('data-lgday'))return p.getAttribute('data-lgday');p=p.previousElementSibling;}
    return null;
  }
  // what the frame draws right now: toolbar, rows (with their day, cells, ticks), day headers, the open block
  function tlRead(d,w){
    var fr=d.querySelector('[data-lglist-frame="nt8"]');
    var o={frames:d.querySelectorAll('[data-lglist-frame]').length,frame:!!fr};
    if(!fr)return o;
    o.mode=fr.getAttribute('data-lgmode');
    o.chips=[].map.call(fr.querySelectorAll('[data-lgchip]'),_t1);
    o.chipOn=[].map.call(fr.querySelectorAll('[data-lgchip].active'),_t1);
    o.views=[].map.call(fr.querySelectorAll('[data-lgview]'),function(b){return b.getAttribute('data-lgview')+(b.getAttribute('aria-pressed')==='true'?'*':'');});
    var sb=fr.querySelector('input[data-lgsearch]');o.search=sb?sb.id:null;
    o.count=_t1(fr.querySelector('[data-lgcount]'));
    o.countLine=_t1(fr.querySelector('.lg-tl-count'));
    o.rows=[].map.call(fr.querySelectorAll('[data-lgtrade]'),function(r){
      var vis=0;[].forEach.call(r.children,function(c){if(w.getComputedStyle(c).display!=='none')vis++;});
      var pn=r.querySelector('.lg-c-pnl'),tk=r.querySelector('input[data-pttick]'),lg=r.querySelector('[data-pc="leg"]'),ho=r.querySelector('.lg-c-hold'),sd=r.querySelector('.lg-side');
      return {id:r.getAttribute('data-lgtrade'),tag:r.tagName,day:_dayOf(r),pcd:r.getAttribute('data-pcd'),open:r.hasAttribute('data-ptopenrow'),unc:r.hasAttribute('data-ptunc'),
        sel:r.hasAttribute('data-ptsel'),vis:vis,pnl:_t1(pn),pnlOver:pn?(pn.scrollWidth>pn.clientWidth+1):null,leg:lg?lg.textContent.replace(/\\s+/g,' ').trim():null,hold:_t1(ho),side:_t1(sd),tick:tk?!!tk.checked:null};});
    o.days=[].map.call(fr.querySelectorAll('[data-lgday]'),function(g){var n=g.querySelector('.lg-tl-daynet');return {day:g.getAttribute('data-lgday'),net:_t1(n),cls:n?n.className:'',txt:_t1(g)};});
    o.openHd=_t1(fr.querySelector('.p2tl-opensec .lg-tl-dayhd'));
    o.note=_t1(fr.querySelector('.p2tl-note'));
    var ob=fr.querySelector('[data-ptopen]');o.open=ob?{txt:_t1(ob),n:ob.getAttribute('data-n'),dis:ob.disabled}:null;
    o.tickAll=fr.querySelectorAll('input[data-pttickall]').length;
    o.tickN=fr.querySelectorAll('input[data-pttick]').length;
    var _vis=function(c){var b=c.getBoundingClientRect();return b.width>0&&b.height>0;};
    o.tickVis=[].filter.call(fr.querySelectorAll('input[data-pttick]'),_vis).length;
    o.tickAllVis=[].filter.call(fr.querySelectorAll('input[data-pttickall]'),_vis).length;
    o.th=[].map.call(fr.querySelectorAll('thead th'),_t1);
    var wr=fr.querySelector('.lg-tl-wrap');o.wrap=wr?{sw:wr.scrollWidth,cw:wr.clientWidth}:null;
    o.empty=_t1(fr.querySelector('.lg-tl-empty'));
    return o;
  }
  // chips, search, LIST | TABLE, tick boxes + OPEN N CHARTS, a row click, the CHART cell and a header sort - then everything put back
  function tlInteract(d,w,nm){
    var I={},LS=w.localStorage;
    var F=function(){return d.querySelector('[data-lglist-frame="nt8"]');};
    var ids=function(){return [].map.call(F().querySelectorAll('[data-lgtrade]'),function(r){return r.getAttribute('data-lgtrade');});};
    var click=function(sel){var e=F().querySelector(sel);if(!e)return false;e.click();return true;};
    var tickIds=function(){return [].map.call(F().querySelectorAll('input[data-pttick]:checked'),function(c){return c.getAttribute('data-pttick');});};
    var openBtn=function(){var b=F().querySelector('[data-ptopen]');return b?{txt:_t1(b),n:b.getAttribute('data-n'),dis:b.disabled}:null;};
    var gal0=w.openChartGallery,cnd0=w._openTradeCandles;
    try{
      // the chips: each one lists its own rows
      var keys=[].map.call(F().querySelectorAll('[data-lgchip]'),function(b){return b.getAttribute('data-lgchip');});
      I.chipKeys=keys;I.chips={};
      keys.forEach(function(k){
        if(!click('[data-lgchip="'+k+'"]'))return;
        I.chips[k]={ids:ids(),on:[].map.call(F().querySelectorAll('[data-lgchip].active'),function(b){return b.getAttribute('data-lgchip');}),count:_t1(F().querySelector('[data-lgcount]'))};
      });
      click('[data-lgchip="ALL"]');
      I.allAgain=ids();
      // the search box filters and keeps the cursor
      var s=F().querySelector('input[data-lgsearch]');
      s.focus();s.value='noise';try{s.setSelectionRange(5,5);}catch(e){}
      s.dispatchEvent(new w.Event('input',{bubbles:true}));
      var s2=F().querySelector('input[data-lgsearch]');
      I.search={ids:ids(),focus:d.activeElement===s2,caret:s2.selectionStart,value:s2.value};
      s2.value='';s2.dispatchEvent(new w.Event('input',{bubbles:true}));
      I.search.cleared=ids();
      // LIST | TABLE: switches, is stored per board and survives a redraw
      var v0=F().getAttribute('data-lgmode');
      click('[data-lgview="list"]');
      I.view={start:v0,afterList:F().getAttribute('data-lgmode'),stored:LS.getItem('el_lg_view_nt8'),listRows:ids().length,
        pressed:[].map.call(F().querySelectorAll('[data-lgview][aria-pressed="true"]'),function(b){return b.getAttribute('data-lgview');})};
      w.renderApp();I.view.afterRenderList=F().getAttribute('data-lgmode');
      click('[data-lgview="table"]');
      I.view.afterTable=F().getAttribute('data-lgmode');I.view.storedT=LS.getItem('el_lg_view_nt8');
      w.renderApp();I.view.afterRenderTable=F().getAttribute('data-lgmode');
      // tick boxes and OPEN N CHARTS
      w.__gallery=[];
      w.openChartGallery=function(B,rows,v,lbl,o){w.__gallery.push({n:rows.length,pids:rows.map(function(x){return x._pid;}),lbl:lbl,keep:!!(o&&o.keepOrder)});};
      var T=[].slice.call(F().querySelectorAll('input[data-pttick]'));
      I.tick={n:T.length,start:{ticked:tickIds(),open:openBtn()},order:ids()};
      if(T.length>=4){
        T[1].click();
        I.tick.one={ticked:tickIds(),open:openBtn(),selAttr:[].map.call(F().querySelectorAll('[data-lgtrade][data-ptsel]'),function(r){return r.getAttribute('data-lgtrade');})};
        T[2].click();T[3].click();
        I.tick.many={ticked:tickIds(),open:openBtn()};
        click('[data-ptopen]');I.tick.gallery=w.__gallery.slice();
        T[2].click();
        I.tick.down={ticked:tickIds(),open:openBtn()};
        F().querySelector('input[data-pttickall]').click();
        I.tick.all={ticked:tickIds(),open:openBtn(),rows:ids().length,box:F().querySelector('input[data-pttickall]').checked};
        F().querySelector('input[data-pttickall]').click();
        I.tick.none={ticked:tickIds(),open:openBtn()};
        w.__gallery=[];click('[data-ptallcharts]');I.tick.allCharts=w.__gallery.slice();
        // ticks follow what is shown: tick everything, narrow the list to LONG, widen it again
        [].forEach.call(F().querySelectorAll('input[data-pttick]'),function(c){c.click();});
        I.tick.everything={ticked:tickIds().length};
        click('[data-lgchip="LONG"]');
        I.tick.afterChip={ticked:tickIds(),open:openBtn(),shown:ids().length};
        click('[data-lgchip="ALL"]');
        I.tick.afterAll={ticked:tickIds().length,open:openBtn()};
        click('[data-lgview="list"]');I.tick.inList={ticked:tickIds().length,open:openBtn()};
        click('[data-lgview="table"]');
        click('[data-ptclear]');I.tick.cleared={ticked:tickIds(),open:openBtn()};
      }
      // a row click records the trade id (the trade panel is step 9) and leaves the ticks and the CHART cell alone
      var row=F().querySelector('[data-lgtrade]:not([data-ptopenrow])'),rid=row.getAttribute('data-lgtrade');
      var tk0=tickIds().length;w._ptRowId=null;
      row.querySelector('.lg-c-sym').click();
      I.row={id:rid,got:w._ptRowId,ticksBefore:tk0,ticksAfter:tickIds().length};
      w._ptRowId=null;row.querySelector('input[data-pttick]').click();I.row.tickIsRow=w._ptRowId;
      row.querySelector('input[data-pttick]').click();
      w._ptRowId=null;w.__chart=null;
      w._openTradeCandles=function(x){w.__chart=x._pid;};
      var cp=row.querySelector('[data-ptchart]');if(cp)cp.click();
      I.row.chart={opened:w.__chart,rowClick:w._ptRowId};
      // a header sort: no day headers once sorted by money, rows in money order
      var sh=F().querySelector('th [data-psort="usd"]');
      if(sh){
        sh.click();
        var f2=F();
        I.sort={mode:f2.getAttribute('data-lgmode'),days:f2.querySelectorAll('[data-lgday]').length,
          pnls:[].map.call(f2.querySelectorAll('tr[data-lgtrade]:not([data-ptopenrow]) .lg-c-pnl'),_t1),chip:_t1(f2.querySelector('.p2tl-sort'))};
      }
    }catch(e){I.err=String(e&&e.stack?e.stack:e);}
    // everything back to how the case started
    w.openChartGallery=gal0;w._openTradeCandles=cnd0;
    try{w.ledgerTradePanelClose('nt8','api');}catch(e){}w._ntPanelId=null;   // the row click above opened the trade panel (step 9)
    w._ptChip=null;w._ptQuery=null;w._ptSel=null;w._ptReach=null;w._ptRowId=null;w._paperSortCol=null;w._paperSortDir=null;
    LS.removeItem('el_lg_view_nt8');
    w.renderApp();
    return I;
  }
  // ---- LEDGER step 9 on NT8 PAPER: the shared trade panel, opened by a click on a row of the list ----------------------------------
  // every colour the panel draws (text, background, borders, outline, svg fill and stroke) must be a grey: MONO has no hue
  function hueScan(root,w){
    var cv=document.createElement('canvas');cv.width=1;cv.height=1;var cx=cv.getContext('2d');
    function rgba(css){try{cx.clearRect(0,0,1,1);cx.fillStyle='#000';cx.fillStyle=css;cx.fillRect(0,0,1,1);var a=cx.getImageData(0,0,1,1).data;return [a[0],a[1],a[2],a[3]];}catch(e){return null;}}
    var els=[root].concat(Array.prototype.slice.call(root.querySelectorAll('*'))),n=0,bad=[];
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
  function pnSleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  // the page as the panel must leave it: a closed panel is not in it at all
  function pnGeo(d,w){var de=d.documentElement;
    return {sw:de.scrollWidth,cw:de.clientWidth,sh:de.scrollHeight,kids:d.body.children.length,nodes:d.querySelectorAll('.lg-panel,.lg-panel-layer').length,vw:w.innerWidth,vh:w.innerHeight};}
  // the open panel: where it is, what it says, which slots it has, what is in them
  function pnLook(d,w,st){
    var PN='.lg-panel[data-lgpanel="nt8"]',q=function(s){return d.querySelector(s);};
    // a headless page may never produce the frames a CSS animation needs: finish the slide-in so the panel is measured where it ends up
    try{d.getAnimations().forEach(function(a){try{a.finish();}catch(e1){}});}catch(e){}
    var p=q(PN);st.exists=!!p;st.g=pnGeo(d,w);
    if(!p)return st;
    var r=p.getBoundingClientRect(),cs=w.getComputedStyle(p),nel=q(PN+' [data-lgpanel-net]'),b=p.querySelector('[data-lgpanel-body]');
    st.rect={l:Math.round(r.left),t:Math.round(r.top),r:Math.round(r.right),b:Math.round(r.bottom),w:Math.round(r.width),h:Math.round(r.height)};
    st.vis=cs.display+','+cs.visibility+','+cs.opacity;
    st.mode=p.getAttribute('data-lgpanel-mode');st.trade=p.getAttribute('data-lgpanel-trade');
    st.role=p.getAttribute('role');st.modal=p.getAttribute('aria-modal');
    st.sym=_t1(q(PN+' [data-lgpanel-sym]'));st.net=nel?_t1(nel):null;st.netCls=nel?nel.className:'';
    st.side=_t1(q(PN+' [data-lgpanel-side]'));st.sub=_t1(q(PN+' [data-lgpanel-sub]'));st.tag=_t1(q(PN+' .lg-panel-tag'));st.when=_t1(q(PN+' [data-lgpanel-when]'));
    st.slots=[].map.call(p.querySelectorAll('[data-lgpanel-slot]'),function(e){return e.getAttribute('data-lgpanel-slot');});
    st.inApp=!!p.closest('#app');st.bodyWide=b?b.scrollWidth>b.clientWidth+1:null;st.focusIn=p.contains(d.activeElement);
    st.nrows=[].map.call(p.querySelectorAll('.lg-panel-row'),function(e){var dd=e.querySelector('.lg-panel-dd');return [_t1(e.querySelector('.lg-panel-dt')),_t1(dd),dd?dd.className:''];});
    var nt=p.querySelector('[data-lgpanel-slot="notes"]');
    st.notes=_t1(nt);st.notesInputs=nt?nt.querySelectorAll('textarea,input,select,[contenteditable]').length:-1;
    st.chips=[].map.call(p.querySelectorAll('[data-ntpchips] > span'),_t1);
    st.btns={gallery:!!p.querySelector('[data-ntpgallery]'),expand:!!p.querySelector('[data-ntpexpand]'),
      z:[].map.call(p.querySelectorAll('[data-ntpz]'),function(x){return x.getAttribute('data-ntpz');}),del:p.querySelectorAll('button.del').length};
    var cb=p.querySelector('[data-ntpbody]');
    st.chart={svg:!!(cb&&cb.querySelector('svg')),body:_t1(cb),info:_t1(p.querySelector('[data-ntpinfo]'))};
    st.id=w._ntPanelId==null?null:String(w._ntPanelId);
    return st;
  }
  // one panel case: every step is a click or a key on the real page, then a read of what the panel and the page did
  async function panelInteract(d,w,cfg){
    var P=cfg.panel,R={steps:{},pad:null},PN='.lg-panel[data-lgpanel="nt8"]',q=function(s){return d.querySelector(s);};
    var F=function(){return q('[data-lglist-frame="nt8"]');};
    var rowEl=function(id){var f=F();return f?f.querySelector('[data-lgtrade="'+id+'"]'):null;};
    var clickRow=function(id){var r=rowEl(id);if(!r)return false;(r.querySelector('.lg-c-sym')||r).click();return true;};
    var shut=function(){try{w.ledgerTradePanelClose('nt8','api');}catch(e){}};
    var calls=w.__pnCalls=[];
    var cn0=w._openTradeCandles,ga0=w.openChartGallery;
    w._openTradeCandles=function(x,g,ctx){calls.push(['expand',x._pid,x._no,ctx&&ctx.all?ctx.all().length:null]);};
    w.openChartGallery=function(B,rows,v,lbl,o){calls.push(['gallery',rows.map(function(x){return x._pid;}),lbl,o&&o.title]);};
    function step(nm,fn){var st={};R.steps[nm]=st;try{var v=fn(st);if(v&&v.then)return v.then(null,function(e){st.err=String(e&&e.stack?e.stack:e);});}catch(e){st.err=String(e&&e.stack?e.stack:e);}return null;}
    try{
      w.renderApp();   // the first draw of a case is a few px taller than every later one: measure the settled page
      R.base=pnGeo(d,w);
      // 0. a click on a tick box, the label round it, the CHART pill or a button is that control own click: it never opens the panel
      step('skip',function(st){
        var r=rowEl(P.tid);if(!r){st.found=false;return;}st.found=true;
        var cb=r.querySelector('input[data-pttick]'),lab=r.querySelector('label.p2tk'),ch=r.querySelector('[data-ptchart]'),all=F().querySelector('[data-pttickall]'),btn=F().querySelector('[data-ptallcharts]');
        st.have=[!!cb,!!lab,!!ch,!!all,!!btn];
        if(cb)cb.click();if(cb)cb.click();   // tick, then untick
        if(lab)lab.click();if(lab)lab.click();
        if(ch)ch.click();
        if(btn)btn.click();
        st.nodes=pnGeo(d,w).nodes;st.id=w._ntPanelId==null?null:String(w._ntPanelId);
        st.ticks=[].filter.call(F().querySelectorAll('input[data-pttick]'),function(c){return c.checked;}).length;
        if(st.nodes)shut();
        w._ntPanelId=null;
      });
      calls.length=0;
      // 1. a click on a row opens the panel with that trade: header, geometry, slots, numbers, notes, actions (the chart is drawn from the PC bars)
      await step('open',async function(st){
        if(P.chart){
          var bars=[],px=29700,i;
          for(i=0;i<120;i++){var hh=9+Math.floor((30+i)/60),mm=(30+i)%60;px+=((i*7)%11)-5;
            bars.push({t:'2026-08-12 '+('0'+hh).slice(-2)+':'+('0'+mm).slice(-2)+':00',o:px,h:px+6,l:px-6,c:px+((i%3)-1)*2});}
          w.__pnBars={ok:true,bars:bars,entry_idx:40,exit_idx:70,overlays:{vwap:bars.map(function(b){return b.c;})}};
          w.eval("cmdRef={doc:function(){return {set:function(){return Promise.resolve();},onSnapshot:function(cb){setTimeout(function(){cb({data:function(){return {status:'done',result:window.__pnBars};}});},0);return function(){};}};}}");
        }
        st.clicked=clickRow(P.tid);
        await pnSleep(80);
        pnLook(d,w,st);
        if(P.chart){
          var p=q(PN),zi=function(z){var b=p&&p.querySelector('[data-ntpz="'+z+'"]');if(b)b.click();return _t1(p&&p.querySelector('[data-ntpinfo]'));};
          st.z={start:st.chart.info,out:zi('out'),back:zi('in'),full:zi('full'),trade:zi('trade')};
          var ex=p&&p.querySelector('[data-ntpexpand]');if(ex)ex.click();
          st.afterExpand=calls.slice();calls.length=0;
          var tk0=[].filter.call(F().querySelectorAll('input[data-pttick]'),function(c){return c.checked;}).length;
          var gb=p&&p.querySelector('[data-ntpgallery]');if(gb)gb.click();
          st.gallery=calls.slice();calls.length=0;
          st.tickRow=!!(rowEl(P.tid)&&rowEl(P.tid).querySelector('input[data-pttick]:checked'));
          st.ticks={before:tk0,after:[].filter.call(F().querySelectorAll('input[data-pttick]'),function(c){return c.checked;}).length,btn:_t1(q('[data-ptopen]'))};
          w.eval('cmdRef=null');
          w._ptSel=null;if(w._ntTl)w._ntTl.draw();
        }
        if(cfg.theme==='mono'&&q(PN))st.hue=hueScan(q(PN),w);
      });
      // 2. the open trade survives a redraw of the list (a search, a chip, LIST | TABLE) and of the whole board, and never shows another trade
      await step('rerender',async function(st){
        var inp=F().querySelector('input[data-lgsearch]');st.searchBox=!!inp;
        st.rowsBefore=F().querySelectorAll('[data-lgtrade]').length;
        if(inp){inp.value='zzzz-no-such-trade';inp.dispatchEvent(new w.Event('input',{bubbles:true}));}
        st.search={rows:F().querySelectorAll('[data-lgtrade]').length,listed:!!rowEl(P.tid)};pnLook(d,w,st.search);
        inp=F().querySelector('input[data-lgsearch]');
        if(inp){inp.value='';inp.dispatchEvent(new w.Event('input',{bubbles:true}));}
        st.cleared={rows:F().querySelectorAll('[data-lgtrade]').length,listed:!!rowEl(P.tid)};pnLook(d,w,st.cleared);
        var lb=F().querySelector('[data-lgchip="LOSSES"]');st.chipBtn=!!lb;
        if(lb)lb.click();
        st.chip={rows:F().querySelectorAll('[data-lgtrade]').length,listed:!!rowEl(P.tid)};pnLook(d,w,st.chip);
        var ab=F().querySelector('[data-lgchip="ALL"]');if(ab)ab.click();
        var other=F().getAttribute('data-lgmode')==='list'?'table':'list',vb=F().querySelector('[data-lgview="'+other+'"]');st.viewBtn=!!vb;
        if(vb)vb.click();
        st.view={rows:F().querySelectorAll('[data-lgtrade]').length,mode:F().getAttribute('data-lgmode')};pnLook(d,w,st.view);
        var vb2=F().querySelector('[data-lgview="'+(other==='list'?'table':'list')+'"]');if(vb2)vb2.click();
        w.renderApp();
        st.board={rows:F().querySelectorAll('[data-lgtrade]').length};pnLook(d,w,st.board);
      });
      // 3. Esc closes it
      step('esc',function(st){
        d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
        st.open=!!q(PN);st.g=pnGeo(d,w);st.id=w._ntPanelId==null?null:String(w._ntPanelId);
        if(st.open)shut();
      });
      // 4. a tap or click outside closes it, a tap inside does not
      await step('outside',async function(st){
        st.clicked=clickRow(P.tid);st.opened=!!q(PN);
        var s=q(PN+' [data-lgpanel-sym]');
        if(s){s.click();}
        st.keptOnInside=!!q(PN);
        var pt=cfg.vp==='phone'?[Math.round(w.innerWidth/2),20]:[30,Math.round(w.innerHeight/2)];
        var el=d.elementFromPoint(pt[0],pt[1]);
        st.hit=(el&&el.classList&&el.classList.contains('lg-panel-layer'))?'layer':(el?el.tagName+'.'+el.className:null);
        if(el){el.dispatchEvent(new w.PointerEvent('pointerdown',{bubbles:true,pointerType:cfg.vp==='phone'?'touch':'mouse'}));el.click();}
        st.open=!!q(PN);st.g=pnGeo(d,w);st.id=w._ntPanelId==null?null:String(w._ntPanelId);
        if(st.open)shut();
      });
      // 5. the close button closes it
      step('button',function(st){
        st.clicked=clickRow(P.tid);
        var x=q(PN+' [data-lgpanel-close]');st.btn=!!x;
        if(x)x.click();
        st.open=!!q(PN);st.g=pnGeo(d,w);
        if(st.open)shut();
      });
      // 6. another trade opened in the open panel switches it (and the net, side and name follow); a tick box click in the meantime does not
      step('switch',function(st){
        st.clicked=clickRow(P.tid);
        st.first=pnLook(d,w,{});
        st.clicked2=clickRow(P.tid2);
        pnLook(d,w,st);
        var r2=rowEl(P.tid);var cb=r2?r2.querySelector('input[data-pttick]'):null;
        if(cb)cb.click();
        st.afterTick={trade:(q(PN)||{getAttribute:function(){return null;}}).getAttribute('data-lgpanel-trade')};
        if(cb)cb.click();
        shut();
        st.nodesNow=pnGeo(d,w).nodes;
      });
      // 7. the trade still open (OPEN NOW) opens a panel too: marked OPEN, no net, the exit reads open
      step('openrow',function(st){
        st.clicked=clickRow(P.otid);
        pnLook(d,w,st);
        shut();
      });
      // 7b. the chip variants (NT approx, NT cross) of a strategy outside the book: tagged NOT BOOK, the three chips, no hue in MONO
      step('chips',function(st){
        [['blue',P.blue],['amber',P.amber]].forEach(function(x){
          var s={};st[x[0]]=s;s.clicked=clickRow(x[1]);pnLook(d,w,s);
          if(cfg.theme==='mono'&&q(PN))s.hue=hueScan(q(PN),w);
          shut();
        });
      });
      // 8. closed again: nothing left in the page, the page exactly as big as before the first open
      step('room',function(st){
        shut();
        st.g=pnGeo(d,w);st.id=w._ntPanelId==null?null:String(w._ntPanelId);
      });
      // 9. the trade leaves the board rows (its strategy switched off, a narrower range): the panel closes by itself, and the board comes back
      step('gone',function(st){
        var sw=q('[data-lglist="p2"] [data-lgsw="ORB"]');st.sw=!!sw;
        st.clicked=clickRow(P.tid2);st.opened=!!q(PN);
        if(sw)sw.click();
        st.afterOff={open:!!q(PN),id:w._ntPanelId==null?null:String(w._ntPanelId),listed:!!rowEl(P.tid2),g:pnGeo(d,w)};
        var sw2=q('[data-lglist="p2"] [data-lgsw="ORB"]');if(sw2)sw2.click();
        st.back={listed:!!rowEl(P.tid2),open:!!q(PN)};
        st.clicked3=clickRow(P.tid);st.opened3=!!q(PN);
        var pill=q('[data-pcwin="1M"]');st.pill=!!pill;
        if(pill)pill.click();
        st.afterRange={open:!!q(PN),id:w._ntPanelId==null?null:String(w._ntPanelId),listed:!!rowEl(P.tid)};
        var all=q('[data-pcwin="ALL"]');if(all)all.click();
        w._paperCurveWin=null;
        shut();
      });
      // 10. leaving the board closes the panel
      step('leave',function(st){
        st.clicked=clickRow(P.tid);st.opened=!!q(PN);
        w.eval("activeTab='home'");w.renderApp();
        st.open=!!q(PN);st.id=w._ntPanelId==null?null:String(w._ntPanelId);
        w.eval("activeTab='augur';augurSub='paper2'");w.renderApp();
        st.back={frame:!!F(),open:!!q(PN)};
        shut();
      });
    }catch(e){R.err=String(e&&e.stack?e.stack:e);}
    shut();w._ntPanelId=null;w._openTradeCandles=cn0;w.openChartGallery=ga0;
    try{w.eval('cmdRef=null');}catch(e2){}
    try{w.renderApp();}catch(e3){}   // the first draw after the leave-the-board step is a few px taller: measure the settled page again
    R.end=pnGeo(d,w);
    return R;
  }
  // the panel at the width of this case (the width sweep): the page must not scroll sideways with it open or closed
  function panelAtWidth(d,w){
    var o={},F=d.querySelector('[data-lglist-frame="nt8"]'),row=F?F.querySelector('[data-lgtrade]:not([data-ptopenrow])'):null;
    o.g0=pnGeo(d,w);
    if(!row)return o;
    (row.querySelector('.lg-c-sym')||row).click();
    pnLook(d,w,o);
    try{w.ledgerTradePanelClose('nt8','api');}catch(e){}
    o.g1=pnGeo(d,w);
    return o;
  }
  // LEDGER step 9 follow-up: a trade's bars are cached under the trade's own id, never under its place in the list (which every sort, search and chip
  // changes). A stubbed PC answers every get_bars with bars whose price level belongs to the trade asked for (entry + exit time are unique per row of
  // the fixture board); the CHART pill viewer and the OPEN N CHARTS gallery are then opened after a chip, a search, a LIST | TABLE switch and a header
  // re-sort, and the price axis of what the page DREW must sit on that trade's own level
  async function chartKeyInteract(d,w,cfg){
    var C={steps:[],all:null,orb:null,nz:null,sorted:null,ttm:null,req:0,err:null};
    var F=function(){return d.querySelector('[data-lglist-frame="nt8"]');};
    var rows0=w._paperCandleRows||[],lv={},lvById={};
    rows0.forEach(function(x,k){lv[x._et+'|'+x._xt2]=20000+1500*(k+1);lvById[x._pid]=20000+1500*(k+1);});
    w.__ckReq=[];
    w.__ckMk=function(p){var L=lv[p.entry_time+'|'+p.exit_time]||5000,bars=[],i;
      for(i=0;i<60;i++){var hh=9+Math.floor((30+i)/60),mm=(30+i)%60,c=L+((i%5)-2)*3;
        bars.push({t:'2026-08-12 '+('0'+hh).slice(-2)+':'+('0'+mm).slice(-2)+':00',o:c-1,h:c+4,l:c-4,c:c});}
      return {ok:true,bars:bars,entry_idx:20,exit_idx:40,overlays:{}};};
    w.eval("cmdRef={doc:function(){var rec={};return {set:function(c){rec.c=c;window.__ckReq.push(c.payload.entry_time+'|'+c.payload.exit_time);return Promise.resolve();},onSnapshot:function(cb){setTimeout(function(){cb({data:function(){return {status:'done',result:window.__ckMk(rec.c.payload)};}});},0);return function(){};}};}}");
    var ids=function(){return [].map.call(F().querySelectorAll('[data-lgtrade]'),function(r){return r.getAttribute('data-lgtrade');});};
    var axis=function(sv){var n=[];[].forEach.call(sv.querySelectorAll('text'),function(e){var t=e.textContent;if(/^[0-9]{1,3}(,[0-9]{3})+$/.test(t))n.push(+t.replace(/,/g,''));});return n;};
    var judge=function(sv,id){var a=axis(sv),L=lvById[id];return {axis:a.length?[Math.min.apply(null,a),Math.max.apply(null,a)]:null,want:L,ok:a.length>0&&a.every(function(v){return Math.abs(v-L)<=60;})};};
    var shutAll=function(){var c=d.querySelector('#chart-close');if(c)c.click();var g=d.getElementById('gal-close');if(g)g.click();};
    var viewPill=async function(n,id){
      var r=F().querySelector('[data-lgtrade="'+id+'"]'),b=r&&r.querySelector('[data-ptchart]'),res={kind:'pill',n:n,id:id,pill:!!b,svg:false,ok:false};
      if(!b)return res;
      b.click();await pnSleep(150);
      var sv=d.querySelector('#chart-body svg');res.svg=!!sv;
      if(sv)Object.assign(res,judge(sv,id));
      shutAll();await pnSleep(30);
      return res;
    };
    var gallery=async function(n){
      var res={kind:'gallery',n:n,btn:false,ticked:[],cards:[]},btn=F().querySelector('[data-ptopen]');
      res.ticked=[].map.call(F().querySelectorAll('input[data-pttick]:checked'),function(c){var r=c.closest('[data-lgtrade]');return r?r.getAttribute('data-lgtrade'):null;});
      if(!btn)return res;
      res.btn=true;res.label=(btn.textContent||'').trim();
      btn.click();await pnSleep(250);
      // the gallery lists its trades in the order of the list (keepOrder), so card n is the n-th ticked trade
      [].forEach.call(d.querySelectorAll('#gal-body [data-gal]'),function(c,n){
        var k=c.getAttribute('data-gal'),id=res.ticked[n]||null,sv=c.querySelector('.galchart svg');
        var j=(sv&&id)?judge(sv,id):{ok:false,axis:null,want:null};
        res.cards.push(Object.assign({key:k,id:id,svg:!!sv},j));});
      shutAll();await pnSleep(30);
      return res;
    };
    var tickOnly=function(list){
      [].forEach.call(F().querySelectorAll('input[data-pttick]:checked'),function(c){c.click();});
      list.forEach(function(id){var r=F().querySelector('[data-lgtrade="'+id+'"]'),c=r&&r.querySelector('input[data-pttick]');if(c)c.click();});
    };
    var chip=function(c){var b=F().querySelector('[data-lgchip="'+c+'"]');if(b)b.click();return !!b;};
    var search=function(v){var i=F().querySelector('input[data-lgsearch]');if(i){i.value=v;i.dispatchEvent(new w.Event('input',{bubbles:true}));}return !!i;};
    var view=function(v){var b=F().querySelector('[data-lgview="'+v+'"]');if(b)b.click();return !!b;};
    try{
      var i,all=ids();C.all=all;
      // the CHART pill: the first two rows of the list, then the rows of a chip, of a search, of the table re-sorted and of a chip in the table
      for(i=0;i<2&&i<all.length;i++)C.steps.push(await viewPill('all-'+i,all[i]));
      chip('fam:ORB');C.orb=ids();
      for(i=0;i<C.orb.length;i++)C.steps.push(await viewPill('chip-orb-'+i,C.orb[i]));
      chip('ALL');search('NOISE');C.nz=ids();
      for(i=0;i<C.nz.length;i++)C.steps.push(await viewPill('search-'+i,C.nz[i]));
      search('');
      view('table');chip('ALL');
      var sb=F().querySelector('[data-psort="date"]');if(sb)sb.click();
      sb=F().querySelector('[data-psort="date"]');if(sb)sb.click();
      C.sorted=ids();
      for(i=0;i<2&&i<C.sorted.length;i++)C.steps.push(await viewPill('table-sorted-'+i,C.sorted[i]));
      chip('fam:TTM');C.ttm=ids();
      for(i=0;i<C.ttm.length;i++)C.steps.push(await viewPill('table-chip-ttm-'+i,C.ttm[i]));
      chip('ALL');view('list');
      // OPEN N CHARTS: two ticked rows, then the rows of a chip, the same ticks in the table, then a search
      var a2=ids();
      tickOnly([a2[0],a2[1]]);C.steps.push(await gallery('gallery-all'));
      chip('fam:ORB');tickOnly(ids());C.steps.push(await gallery('gallery-chip-orb'));
      view('table');C.steps.push(await gallery('gallery-chip-orb-table'));
      view('list');chip('ALL');search('TTM');tickOnly(ids());C.steps.push(await gallery('gallery-search-ttm'));
      search('');
    }catch(e){C.err=String(e&&e.stack?e.stack:e);}
    shutAll();
    C.req=w.__ckReq.length;
    try{w.eval('cmdRef=null');}catch(e2){}
    w._ptSel=null;w._ptChip=null;w._ptQuery=null;
    try{w.renderApp();}catch(e3){}
    return C;
  }
  // ---- LEDGER step 11 on NT8 PAPER: the fixed page order, the own folds, one set of breakpoints, the previous board unchanged ----------------------
  function s11digest(s){var h1=0xdeadbeef,h2=0x41c6ce57;
    for(var i=0;i<s.length;i++){var c=s.charCodeAt(i);h1=Math.imul(h1^c,2654435761);h2=Math.imul(h2^c,1597334677);}
    h1=Math.imul(h1^(h1>>>16),2246822507)^Math.imul(h2^(h2>>>13),3266489909);h2=Math.imul(h2^(h2>>>16),2246822507)^Math.imul(h1^(h1>>>13),3266489909);
    return (h2>>>0).toString(16)+(h1>>>0).toString(16);}
  // every media / container rule with a width in it and a selector of the board (.p2 / #p2 / data-p2 / nt8) that matches something on the page now;
  // each width must be a house number. n counts the live rules, so a scan that sees nothing can be told from a clean one.
  function s11bp(d){
    var res={n:0,bad:[],widths:[]};
    Array.prototype.forEach.call(d.styleSheets,function(ss){
      var rules;try{rules=ss.cssRules;}catch(e){return;}
      (function walk(list){
        Array.prototype.forEach.call(list,function(rule){
          var cond=null;
          if(rule.media&&rule.cssRules)cond=rule.media.mediaText||'';
          else if(rule.conditionText!==undefined&&rule.cssRules)cond=rule.conditionText||'';
          if(cond!==null){
            var ws=cond.match(/(?:min|max)-width:\\s*[\\d.]+px/g);
            if(ws){
              var live=[];
              Array.prototype.forEach.call(rule.cssRules,function(ir){
                if(!ir.selectorText)return;
                ir.selectorText.split(',').forEach(function(sel){
                  sel=sel.trim();
                  if(!/\\.p2|#p2|data-p2|nt8/.test(sel))return;
                  var el=null;try{el=d.querySelector(sel);}catch(e){return;}
                  if(el)live.push(sel);
                });
              });
              if(live.length){
                res.n++;
                ws.forEach(function(wx){var px=parseFloat(wx.split(':')[1]);if(res.widths.indexOf(px)<0)res.widths.push(px);
                  if(HOUSE.indexOf(px)<0)res.bad.push(cond+' on '+live[0]);});
              }
            }
            walk(rule.cssRules);
          }else if(rule.cssRules){walk(rule.cssRules);}
        });
      })(rules);
    });
    res.widths.sort(function(a,b){return a-b;});
    return res;
  }
  // the page as it is drawn now: the section markers (top / left / size under the board top), every fold (state, summary, header, body, stored choice),
  // REFRESH, the warning chips, the calendar and More stats folds, the breakpoint scan - and, for the plain page and the ?oldboards=1 page, the digests of the board
  function s11Read(d,w,nm){
    var bd=d.querySelector('.p2rh'),o={board:!!bd};
    if(!bd)return o;
    try{w.scrollTo(0,0);}catch(e){}   // measured from the top of the page (the strategy list panel is not sticky since LEDGER step 12)
    var b0=bd.getBoundingClientRect(),tx=function(e){return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;};
    o.vw=w.innerWidth;
    o.sec=[].map.call(d.querySelectorAll('[data-p2sec]'),function(e){var r=e.getBoundingClientRect();
      return {k:e.getAttribute('data-p2sec'),top:Math.round(r.top-b0.top),left:Math.round(r.left),h:Math.round(r.height),w:Math.round(r.width),inBoard:bd.contains(e)};});
    o.folds=[].map.call(d.querySelectorAll('[data-p2fold]'),function(f){
      var k=f.getAttribute('data-p2fold'),b=f.querySelector('.p2fold-hd'),s=f.querySelector('[data-p2sum]'),bb=f.querySelector('.p2fold-body');
      var hr=b?b.getBoundingClientRect():null,sr=s?s.getBoundingClientRect():null;
      var x={k:k,exp:b?b.getAttribute('aria-expanded'):null,hidden:bb?bb.hidden:null,sum:tx(s),sumH:sr?Math.round(sr.height):null,hdH:hr?Math.round(hr.height):null,
        clip:s?(s.scrollWidth>s.clientWidth+1):null,bodyLen:bb?tx(bb).length:0,inSec:!!f.closest('.p2rh'),
        ls:(function(){try{return w.localStorage.getItem('el_lg_'+k+'_nt8');}catch(e){return 'ERR';}})()};
      if(k==='status'&&s){var tk=[].slice.call(s.querySelectorAll('.p2st')),t0=tk.length?tk[0].offsetTop:0;
        x.tok=tk.map(function(e){return {t:tx(e),line:e.offsetTop>t0+4?2:1};});}
      return x;});
    var rf=d.querySelector('[data-paperrefresh]'),rr=rf?rf.getBoundingClientRect():null;
    o.refresh=rf?{n:d.querySelectorAll('[data-paperrefresh]').length,vis:rr.width>0&&rr.height>0,right:Math.round(rr.right),inFold:!!rf.closest('.p2fold-body'),txt:tx(rf)}:null;
    o.warnChips=[].map.call(d.querySelectorAll('[data-lgstatus="p2"] .p2warn'),tx);   // LEDGER step 12: in the status line under the hero
    o.bp=s11bp(d);
    var cf=d.querySelector('[data-lgcalfold="p2"]'),mf=d.querySelector('[data-lgmore="p2"]');
    o.calOpen=cf?cf.getAttribute('aria-expanded'):null;o.moreOpen=mf?mf.getAttribute('aria-expanded'):null;
    var rl=d.querySelector('[data-p2col="side"]');
    if(rl){var rc=rl.getBoundingClientRect(),rs=rl.closest('[data-lgframe-side]');o.rail={top:Math.round(rc.top-b0.top),left:Math.round(rc.left),pos:w.getComputedStyle(rl).position,sidePos:rs?w.getComputedStyle(rs).position:null};}
    // LEDGER step 12: the shared page frame, the status line under the hero, the chart foot, the Filters row of the strategy list
    var bx=function(e){if(!e)return null;var r=e.getBoundingClientRect(),cs=w.getComputedStyle(e);
      return {top:Math.round(r.top-b0.top),bottom:Math.round(r.bottom-b0.top),left:Math.round(r.left),right:Math.round(r.right),w:Math.round(r.width),h:Math.round(r.height),pos:cs.position,ov:cs.overflowY};};
    var secs=function(e){return e?[].map.call(e.querySelectorAll('[data-p2sec]'),function(x){return x.getAttribute('data-p2sec');}):null;};
    var FR=d.querySelectorAll('[data-lgframe="p2"]');o.frameN=FR.length;
    if(FR.length){var F0=FR[0],fcs=w.getComputedStyle(F0),fr0=F0.getBoundingClientRect(),par=F0.parentElement,pr=par.getBoundingClientRect(),pcs=w.getComputedStyle(par);
      var pl=pr.left+(parseFloat(pcs.paddingLeft)||0)+(parseFloat(pcs.borderLeftWidth)||0),prr=pr.right-(parseFloat(pcs.paddingRight)||0)-(parseFloat(pcs.borderRightWidth)||0);
      var T=F0.querySelector('[data-lgframe-top="p2"]'),S=F0.querySelector('[data-lgframe-side="p2"]'),R=F0.querySelector('[data-lgframe-rest="p2"]');
      o.frame={maxW:fcs.maxWidth,disp:fcs.display,w:Math.round(fr0.width*10)/10,parW:Math.round((prr-pl)*10)/10,gapL:Math.round((fr0.left-pl)*10)/10,gapR:Math.round((prr-fr0.right)*10)/10,inBoard:bd.contains(F0),
        top:bx(T),side:bx(S),sideIn:bx(S?S.querySelector('.lg-frame-side-in'):null),rest:bx(R),inTop:secs(T),inSide:secs(S),inRest:secs(R),
        topKids:T?[].map.call(T.children,function(x){return x.getAttribute('data-p2sec');}):null,
        handle:S?S.querySelectorAll('[data-p2side]').length:0,handleAll:d.querySelectorAll('[data-p2side]').length,handleBox:bx(d.querySelector('[data-p2side]'))};}
    var SL=d.querySelectorAll('[data-lgstatus="p2"]');o.statusN=SL.length;
    if(SL.length){var s0=SL[0],pv=s0.previousElementSibling,nx=s0.nextElementSibling;
      o.status={prev:pv?pv.getAttribute('data-p2sec'):null,next:nx?nx.getAttribute('data-p2sec'):null,inTop:!!(s0.parentElement&&s0.parentElement.hasAttribute('data-lgframe-top')),
        inHero:!!s0.closest('.lg-hero'),fold:!!s0.querySelector('[data-p2fold="status"]'),refresh:!!s0.querySelector('.p2fold-act [data-paperrefresh]'),warn:s0.querySelectorAll('.p2warn').length};}
    var hc=d.querySelector('.p2rh .lg-hero-chips');o.heroChips=hc?{kids:hc.children.length,txt:tx(hc)}:null;
    var CF=d.querySelectorAll('[data-lgchartfoot="p2"]'),cw=d.getElementById('p2-chart');o.chartFootN=CF.length;o.chartDrawn=!!cw;
    if(CF.length){var c0=CF[0],ky=c0.querySelector('.p2rhkey'),kb=ky?ky.getBoundingClientRect():null;
      o.chartFoot={inChart:!!c0.closest('[data-p2sec="chart"]'),top:bx(c0).top,chartBottom:cw?bx(cw).bottom:null,key:!!ky,keyVis:!!(kb&&kb.width>0&&kb.height>0),keyTxt:tx(ky)};}
    o.keyOnPills=d.querySelectorAll('[data-p2sec="pills"] .p2rhkey').length;
    var FLT=d.querySelectorAll('[data-lgfilters="p2"]');o.filtN=FLT.length;
    if(FLT.length){var f0=FLT[0],fb=f0.querySelector('[data-lgfilt="p2"]'),fy=f0.querySelector('.lg-filters-body'),ll=f0.closest('[data-lglist="p2"]'),lh=ll?ll.querySelector('.lg-list-hd'):null;
      var cnt=function(root,sel){return root?root.querySelectorAll(sel).length:0;},onTx=function(sel){var e=fy?fy.querySelector(sel):null;return e?tx(e):null;};
      var CT={kind:'[data-pkind]',fam:'[data-pfam]',sort:'[data-lsort]',base:'[data-pbase]'},ins={},outs={};
      for(var ck in CT){ins[ck]=cnt(fy,CT[ck]);outs[ck]=cnt(bd,CT[ck])-ins[ck];}
      var pbe=fy?fy.querySelector('[data-pbase]'):null;
      o.filt={exp:fb?fb.getAttribute('aria-expanded'):null,hidden:fy?fy.hidden:null,sum:tx(f0.querySelector('[data-lgfiltsum="p2"]')),afterHd:!!(lh&&lh.nextElementSibling===f0),inList:!!ll,ins:ins,out:outs,
        on:{kind:onTx('[data-pkind].on'),fam:onTx('[data-pfam].on'),sort:onTx('[data-lsort].on'),base:pbe?pbe.getAttribute('aria-checked'):null},
        ls:(function(){try{return w.localStorage.getItem('el_lg_filters_p2');}catch(e){return 'ERR';}})()};}
    // the keeps: tick boxes + OPEN N CHARTS, the per-strategy filters, the strategy switches, the calendar days, the auto-recover switch
    o.keeps={ticks:d.querySelectorAll('input[data-pttick]').length,openBtn:!!d.querySelector('[data-ptopen]'),allCharts:!!d.querySelector('[data-ptallcharts]'),
      kind:d.querySelectorAll('[data-pkind]').length,fam:d.querySelectorAll('[data-pfam]').length,sort:d.querySelectorAll('[data-lsort]').length,base:!!d.querySelector('[data-pbase]'),
      rows:d.querySelectorAll('[data-lglist-frame="nt8"] [data-lgtrade]').length,sw:d.querySelectorAll('[data-lglist="p2"] [data-lgsw]').length,calDays:d.querySelectorAll('[data-lgcalday]').length,wd:d.querySelectorAll('[data-wdtoggle]').length,
      wdInBody:!!d.querySelector('.p2fold-body [data-wdtoggle]'),frame:d.querySelectorAll('[data-lglist-frame="nt8"]').length};
    o.oldMarks=OLDMARKS.filter(function(s){return !!d.querySelector(s);});
    o.flagConst=(function(){try{return w.eval('typeof LEDGER_OLDBOARDS');}catch(e){return 'error';}})();
    if(nm==='paper2'||nm==='flag-paper2'){
      var css=[].map.call(bd.querySelectorAll('style'),function(s){return s.textContent;}).join('\\n');
      var tree=[].map.call(bd.querySelectorAll('*'),function(e){
        var cl=(typeof e.className==='string'?e.className:'').trim().split(/\\s+/).filter(Boolean).sort().join('.');
        var at=[].map.call(e.attributes,function(a){return a.name;}).filter(function(n){return n!=='class';}).sort().join(',');
        return e.tagName.toLowerCase()+'.'+cl+'|'+at;}).join('\\n');
      o.dig={css:s11digest(css),cssLen:css.length,tree:s11digest(tree),treeN:bd.querySelectorAll('*').length,
        folds:bd.querySelectorAll('[data-p2fold],[data-p2sec],.p2own,.p2fold-hd').length};
    }
    return o;
  }
  // every fold opens on a click and shows its content, then closes again (and each state is stored); a warning chip opens its card; then the two shared folds
  function s11Folds(d,w){
    var R={folds:{}},tx=function(e){return e?(e.textContent||'').replace(/\\s+/g,' ').trim():'';};
    var LSg=function(k){try{return w.localStorage.getItem('el_lg_'+k+'_nt8');}catch(e){return 'ERR';}};
    var btn=function(k){return d.querySelector('.p2fold-hd[data-p2card="'+k+'"]');};
    var body=function(k){return d.getElementById('p2fold-'+k);};
    var vis=function(e){var r=e.getBoundingClientRect();return r.width>0&&r.height>0;};
    var keys=[].map.call(d.querySelectorAll('[data-p2fold]'),function(f){return f.getAttribute('data-p2fold');});
    keys.forEach(function(k){
      var o={},b=btn(k);
      if(!b){R.folds[k]={btn:false};return;}
      o.btn=true;o.was=b.getAttribute('aria-expanded');
      if(o.was==='true')b.click();
      o.closed=btn(k).getAttribute('aria-expanded');o.closedHidden=body(k).hidden;o.lsClosed=LSg(k);
      btn(k).click();
      var bb=body(k);
      o.exp=btn(k).getAttribute('aria-expanded');o.hidden=bb.hidden;o.len=tx(bb).length;o.vis=vis(bb);o.ls=LSg(k);
      if(k==='status'){var chips=[].slice.call(bb.querySelectorAll('.lg-chip')),wc=[].slice.call(bb.querySelectorAll('.p2warn'));
        o.chips=chips.length;o.chipsVis=chips.filter(vis).length;o.warn=wc.length;o.warnVis=wc.filter(vis).length;}
      btn(k).click();
      o.back=btn(k).getAttribute('aria-expanded');o.backHidden=body(k).hidden;o.lsBack=LSg(k);
      if(o.was==='true')btn(k).click();
      R.folds[k]=o;
    });
    // a warning chip opens the card that explains it (and the choice is stored)
    var wcb=d.querySelector('[data-p2warn="recon"]'),rb=btn('recon');
    if(wcb&&rb){var rw=rb.getAttribute('aria-expanded');if(rw==='true')rb.click();
      wcb.click();R.warnOpens={exp:btn('recon').getAttribute('aria-expanded'),hidden:body('recon').hidden,ls:LSg('recon')};
      if(rw!=='true')btn('recon').click();}
    // the two shared folds (they redraw the board): More stats and the calendar
    [['more','[data-lgmore="p2"]','p2-more'],['cal','[data-lgcalfold="p2"]','p2-cal']].forEach(function(s){
      var b=d.querySelector(s[1]);if(!b){R[s[0]]={btn:false};return;}
      var o={btn:true,was:b.getAttribute('aria-expanded')};
      if(o.was==='true'){b.click();b=d.querySelector(s[1]);}
      b.click();var p=d.getElementById(s[2]);
      o.exp=d.querySelector(s[1]).getAttribute('aria-expanded');o.hidden=p?p.hidden:null;o.len=tx(p).length;o.vis=p?vis(p):false;
      d.querySelector(s[1]).click();o.back=d.querySelector(s[1]).getAttribute('aria-expanded');
      if(o.was==='true')d.querySelector(s[1]).click();
      R[s[0]]=o;
    });
    return R;
  }
  // MONO: nothing the step drew has a hue - the hero, the status line (LEDGER step 12, with the status chips), every fold row (title, summary, chevron), REFRESH,
  // the pills row, the chart foot and the Filters row of the strategy list (step 12)
  function s11Mono(d,w){
    var roots=[].slice.call(d.querySelectorAll('.lg-hero,[data-lgstatus="p2"],.p2fold-row,.p2ctl,[data-lgchartfoot="p2"],[data-lgfilters="p2"]')),n=0,bad=[];
    roots.forEach(function(r){var x=hueScan(r,w);n+=x.checked;bad=bad.concat(x.bad);});
    return {roots:roots.length,checked:n,bad:bad.slice(0,8),theme:d.documentElement.getAttribute('data-theme')};
  }
  // LEDGER step 12: the Filters row of the strategy list - closed to start, a click opens it and shows every control (their trays one line each), a control
  // works with it open (Baselines only redraws the board: the row stays open and its summary names the choice), a second click closes it; each state stored
  function s12Filters(d,w){
    var R={},tx=function(e){return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;};
    var LSf=function(){try{return w.localStorage.getItem('el_lg_filters_p2');}catch(e){return 'ERR';}};
    var B=function(){return d.querySelector('[data-lgfilt="p2"]');},BD=function(){return d.getElementById('p2-filters');};
    var SM=function(){return tx(d.querySelector('[data-lgfiltsum="p2"]'));};
    var vis=function(e){if(!e)return false;var r=e.getBoundingClientRect();return r.width>0&&r.height>0;};
    var CTL='[data-pkind],[data-pfam],[data-lsort],[data-pbase]';
    // on a page narrower than 1100 px the strategy list is a fold: it is opened first when it is closed, so the row can be seen, and closed again after
    var lf=d.querySelector('.p2fold-hd[data-p2card="list"]'),lfWas=lf?lf.getAttribute('aria-expanded'):null;
    if(lf&&lfWas!=='true')lf.click();
    if(!B()||!BD()){R.btn=false;return R;}
    R.btn=true;R.start={exp:B().getAttribute('aria-expanded'),hidden:BD().hidden,ls:LSf(),sum:SM()};
    B().click();
    var bd=BD();
    R.open={exp:B().getAttribute('aria-expanded'),hidden:bd.hidden,vis:vis(bd),ls:LSf(),ctlN:bd.querySelectorAll(CTL).length,ctlVis:[].filter.call(bd.querySelectorAll(CTL),vis).length,
      trayMax:Math.max.apply(null,[0].concat([].map.call(bd.querySelectorAll('[data-ptray]'),function(t){return t.clientHeight;})))};
    var pb=bd.querySelector('[data-pbase]');
    if(pb){
      pb.click();
      var pb2=BD()?BD().querySelector('[data-pbase]'):null;
      R.base={exp:B()?B().getAttribute('aria-expanded'):null,hidden:BD()?BD().hidden:null,sum:SM(),on:pb2?pb2.getAttribute('aria-checked'):null};
      if(pb2)pb2.click();
      var pb3=BD()?BD().querySelector('[data-pbase]'):null;
      R.baseBack={exp:B()?B().getAttribute('aria-expanded'):null,sum:SM(),on:pb3?pb3.getAttribute('aria-checked'):null};
    }
    if(B())B().click();
    R.closed={exp:B()?B().getAttribute('aria-expanded'):null,hidden:BD()?BD().hidden:null,ls:LSf()};
    if(lf&&lfWas!=='true'){var lf2=d.querySelector('.p2fold-hd[data-p2card="list"]');if(lf2&&lf2.getAttribute('aria-expanded')==='true')lf2.click();}
    try{w.localStorage.removeItem('el_lg_filters_p2');}catch(e){}
    return R;
  }
  // a REAL reload of a page under test (a fresh window: only localStorage survives) - every fold is opened, the page reloaded, it is read, every fold is
  // closed, the page reloaded again and read. The board is seeded the way a case is, but the fold choices are left alone.
  async function s11Reload(vpw,vph,tag){
    var res={vp:vpw,tag:tag,steps:{}},fr=document.createElement('iframe'),id='fr_'+tag;
    fr.id=id;fr.style.cssText='width:'+vpw+'px;height:'+vph+'px;border:0;display:block';fr.src='../index.html';
    document.body.appendChild(fr);
    var loaded=function(){return new Promise(function(r){var h=function(){fr.removeEventListener('load',h);r();};fr.addEventListener('load',h);});};
    var seed=async function(){
      for(var t=0;t<4;t++){
        var w=fr.contentWindow;try{w.renderAuth=function(){};}catch(e){}
        var ok=w.eval("(function(){try{localStorage.setItem('augurPrefs','{}');var F="+JSON.stringify(FIX)+";"
          +"window._paperTrades=F.trades;window._paperReports=F.reports;window._ntBtMatch=F.ntBt;window._ntBridge=F.ntBridge;window._paperLoaded=true;window._paperLoading=false;"
          +"window._paperTradeInfo=F.tradeInfo;window._p2Open={};window._paperOtherOn=null;window._paperLegOff=null;window._paperCurveWin=null;"
          +"activeTab='augur';augurSub='paper2';renderApp();return !!document.querySelector('.p2rh');}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        if(ok===true)return 'OK';
        await pnSleep(700);
      }
      return 'no board';
    };
    var states=function(){var d=fr.contentDocument,o={};[].forEach.call(d.querySelectorAll('.p2fold-hd'),function(b){o[b.getAttribute('data-p2card')]=b.getAttribute('aria-expanded');});return o;};
    var lsAll=function(){var o={};try{S11K.forEach(function(k){o[k]=fr.contentWindow.localStorage.getItem('el_lg_'+k+'_nt8');});}catch(e){}return o;};
    var clickAll=function(){[].forEach.call(fr.contentDocument.querySelectorAll('.p2fold-hd'),function(b){b.click();});};
    // LEDGER step 12: the Filters row of the strategy list (open / closed in el_lg_filters_p2)
    var filt=function(){var b=fr.contentDocument.querySelector('[data-lgfilt="p2"]');return b?b.getAttribute('aria-expanded'):null;};
    var lsFilt=function(){try{return fr.contentWindow.localStorage.getItem('el_lg_filters_p2');}catch(e){return 'ERR';}};
    var clickFilt=function(){var b=fr.contentDocument.querySelector('[data-lgfilt="p2"]');if(b)b.click();};
    var reload=async function(){var p=loaded();fr.contentWindow.location.reload();await p;await pnSleep(3500);hook(id);};
    try{
      await loaded();await pnSleep(3500);hook(id);
      try{S11K.forEach(function(k){fr.contentWindow.localStorage.removeItem('el_lg_'+k+'_nt8');});fr.contentWindow.localStorage.removeItem('el_lg_filters_p2');}catch(e){}
      res.seed1=await seed();drain(id);
      res.start=states();res.lsStart=lsAll();res.filtStart=filt();
      var startOpen=res.start;
      clickAll();res.opened=states();res.lsOpened=lsAll();
      clickFilt();res.filtOpened=filt();res.lsFiltOpened=lsFilt();
      await reload();res.seed2=await seed();
      res.afterReload=states();res.lsAfter=lsAll();res.err1=drain(id);res.filtAfter=filt();
      clickAll();res.closed=states();res.lsClosed=lsAll();
      clickFilt();res.filtClosed=filt();res.lsFiltClosed=lsFilt();
      await reload();res.seed3=await seed();
      res.afterReload2=states();res.err2=drain(id);res.filtAfter2=filt();
    }catch(e){res.err=String(e&&e.stack?e.stack:e);}
    try{S11K.forEach(function(k){fr.contentWindow.localStorage.removeItem('el_lg_'+k+'_nt8');});fr.contentWindow.localStorage.removeItem('el_lg_filters_p2');}catch(e){}
    try{fr.remove();}catch(e){}
    return res;
  }
  async function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{['f','fp','fo','fm','fs','fx','fw','fz','fl','fk'].forEach(hook);}catch(e){}
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], cfg=CASES[i][1], r={};
        fr=document.getElementById(cfg.frame||'f'); w=fr.contentWindow; d=fr.contentDocument;
        if(cfg.width){fr.style.width=cfg.width+'px';void fr.offsetWidth;void d.documentElement.offsetWidth;}   // the resizable frame: this case's viewport width
        var empty=!!(cfg.win&&cfg.win.__empty);
        var noinfo=!!(cfg.win&&cfg.win.__noinfo);
        var nobook=!!(cfg.win&&cfg.win.__nobook);
        var win=JSON.parse(JSON.stringify(cfg.win||{})); delete win.__empty; delete win.__noinfo; delete win.__nobook;
        drain(cfg.frame||'f');
        var th0=w.eval('prefs.theme');   // a panel case sets a theme of its own: every other case keeps what it had
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(cfg.prefs||{}))+");"
          +"var F="+JSON.stringify(FIX)+";"
          +"window._paperTrades="+(empty?"[]":(cfg.more?("F.trades.concat("+JSON.stringify(cfg.more)+")"):"F.trades"))+";"
          +"window._paperReports="+(empty?"[]":(nobook?"F.reports.map(function(r){var c=Object.assign({},r);delete c.book;return c;})":"F.reports"))+";"
          +"window._ntBtMatch=F.ntBt;window._ntBridge=F.ntBridge;"
          +"window._paperLoaded=true;window._paperLoading=false;"
          +"window._paperOtherOn=null;window._paperOtherOpen=null;window._paperFwdOpen=null;window._paperCurveWin=null;"
          +"window._paperTradeInfo="+(empty?"{bundle:true,n_total:0}":(noinfo?"{bundle:false,n_total:null}":"F.tradeInfo"))+";"
          // every lens-style bit of window state reset per case, so cases cannot bleed
          +"window._paperShowArchived=false;window._paperShowCfg=false;"
          +"window._paperMatrixScope='ALL';window._legSortCol=null;window._legSortDir=null;"
          +"window._paperFam=null;window._paperKind=null;window._paperBaseOnly=null;"
          +"window._paperLegOff=null;window._paperCalMonth=null;window._ptSel=null;window._p2Open={};"
          +"window._ptChip=null;window._ptQuery=null;window._ptReach=null;window._ptRowId=null;window._paperSortCol=null;window._paperSortDir=null;"
          +"localStorage.removeItem('el_lg_view_nt8');"
          // LEDGER step 11: the remembered fold choices start empty in every case too
          +JSON.stringify(S11K)+".forEach(function(k){localStorage.removeItem('el_lg_'+k+'_nt8');});"
          // the per-browser LEDGER choices (More stats fold, calendar fold, calendar month) start empty in every case
          +"localStorage.removeItem('el_lg_stats_nt8');localStorage.removeItem('el_lg_cal_nt8');localStorage.removeItem('el_lg_calmo_nt8');"
          // LEDGER step 12: the Filters row of the strategy list starts closed (no stored choice) in every case
          +"localStorage.removeItem('el_lg_filters_p2');"
          +"var LS="+JSON.stringify(cfg.ls||{})+";for(var lk in LS)localStorage.setItem(lk,LS[lk]);"
          +"var W="+JSON.stringify(win)+";for(var k in W)window[k]=W[k];"
          +(cfg.theme?("prefs.theme="+JSON.stringify(cfg.theme)+";applyTheme();"):"")
          +"activeTab='augur';augurSub="+JSON.stringify(cfg.sub)+";renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        var ap=d.getElementById('app');
        r.appLen=ap?ap.innerHTML.length:-1;
        // ---- the LEGS table: the one whose rows carry data-paperleg
        var legRows=d.querySelectorAll('tr[data-paperleg],tr[data-paperother]');
        var listRows=d.querySelectorAll('[data-lglist="p2"] [data-lgrow]');
        r.legRows=legRows.length+listRows.length;
        r.legHead=0; r.colBad=[];
        if(legRows.length){
          var tbl=legRows[0].closest('table');
          var th=tbl?tbl.querySelectorAll('thead th'):[];
          r.legHead=th.length;
          for(var k=0;k<legRows.length;k++){
            if(legRows[k].cells.length!==th.length){
              r.colBad.push(legRows[k].getAttribute('data-paperleg')+' has '+legRows[k].cells.length
                            +' cells against '+th.length+' headings');
              break;}}
        }
        // PAPER plus sidebar: the legacy LEGS panel lives in a sticky left column.
        // Counting it here so a future refactor cannot silently drop the panel while
        // the tab still renders - which is exactly how it was missing in the first
        // place, and no gate noticed.
        r.sideBar=d.querySelectorAll('[data-p2side]').length;
        r.legsInSide=0;
        try{var _lr=d.querySelector('tr[data-paperleg],[data-lglist="p2"] [data-lgrow]');
            var _sb=d.querySelector('[data-p2side]');
            // since 2026-09-14 the rail can sit on either side; it carries data-p2col="side"
            var _side=d.querySelector('[data-p2col="side"]')||(_sb&&_sb.parentElement?_sb.parentElement.firstElementChild:null);
            if(_lr&&_sb&&_side)
              r.legsInSide=_side.contains(_lr)?1:0;}catch(_e){}
        // GEOMETRY, not just existence: the owner rejected two sidebars whose controls
        // wrapped into multi-line blobs, and every structural gate passed on both. A
        // segmented tray is one line of chips - if any tray in the sidebar renders
        // taller than ~2 lines, the layout has collapsed into wrapping again.
        // (LEDGER step 12: the trays sit in the Filters row, closed to start, so they read 0 here; the Filters run, s12Filters, measures them open.)
        r.sideTrayMax=0;
        try{var _sb2=d.querySelector('[data-p2side]');
            var _col=d.querySelector('[data-p2col="side"]')||(_sb2&&_sb2.parentElement?_sb2.parentElement.firstElementChild:null);
            if(_col){var _trays=_col.querySelectorAll('[data-ptray]');
              for(var _ti=0;_ti<_trays.length;_ti++)
                r.sideTrayMax=Math.max(r.sideTrayMax,_trays[_ti].clientHeight);}}catch(_e2){}
        // NOISE #422 row + the 10s capture-health lines (both injected into the fixture by main())
        r.legKeys=[];for(var lk=0;lk<legRows.length;lk++)r.legKeys.push(legRows[lk].getAttribute('data-paperleg')||legRows[lk].getAttribute('data-paperother'));
        for(var lk2=0;lk2<listRows.length;lk2++)r.legKeys.push(listRows[lk2].getAttribute('data-lgrow'));
        var _gk=function(g){return [].map.call(d.querySelectorAll('[data-lglist="p2"] .lg-grp[data-lggroup="'+g+'"] [data-lgrow]'),function(x){return x.getAttribute('data-lgrow');});};
        r.bookRowKeys=[].map.call(d.querySelectorAll('tr[data-paperleg]'),function(x){return x.getAttribute('data-paperleg');}).concat(_gk('book'));
        r.otherRowKeys=[].map.call(d.querySelectorAll('tr[data-paperother]'),function(x){return x.getAttribute('data-paperother');}).concat(_gk('fwd'),_gk('other'),_gk('retired'));
        var _hid=[].slice.call(d.querySelectorAll('.p2fold-body[hidden]'));_hid.forEach(function(e){e.hidden=false;});
        var _bt=d.body?d.body.innerText:'';
        _hid.forEach(function(e){e.hidden=true;});
        r.capNQ=(_bt.match(/10s capture NQ: [^\\n]*/)||[''])[0];
        r.capES=(_bt.match(/10s capture ES: [^\\n]*/)||[''])[0];
        var _gc=d.querySelector('a[href="http://127.0.0.1:8392"]');
        r.gateChip=_gc?(_gc.textContent||'').trim():'';
        r.sortable=d.querySelectorAll('[data-lsort]').length;
        r.colsCtl=d.querySelectorAll('[data-papercols]').length;
        // ---- the TRADES table
        var body=d.getElementById('ptrades-body');
        var fr0=d.querySelector('[data-lglist-frame="nt8"]');
        var trows=body?body.querySelectorAll('tr[data-ptrow]'):(fr0?fr0.querySelectorAll('[data-lgtrade]'):[]);
        r.tradeRows=trows.length;
        r.tradeLegs={}; r.redNoNt=[]; r.crowned={};
        for(var j=0;j<trows.length;j++){
          var cells=trows[j].cells||[];
          var _lc=trows[j].querySelector('[data-pc="leg"]')||cells[2];var legTxt=_lc?_lc.innerText.trim():'';
          // the crown glyph rides inside the LEG cell, so strip it for the label compare
          legTxt=legTxt.replace(/\\u0001?\\uD83D\\uDC51\\uFE0F?/g,'').trim();
          r.tradeLegs[legTxt]=(r.tradeLegs[legTxt]||0)+1;
          var _ec=trows[j].querySelector('[data-pc="eng"]')||trows[j].querySelector('.lg-c-slot')||cells[0];var chips=_ec?_ec.querySelectorAll('span'):[];
          for(var c=0;c<chips.length;c++){
            var t=(chips[c].textContent||'').trim();
            if(t.indexOf('NT')!==0)continue;
            var col=(chips[c].getAttribute('style')||'');
            if((col.indexOf('e24b4a')>=0||col.indexOf('var(--red)')>=0)&&t.indexOf('\\u2717')>0)r.redNoNt.push(legTxt);
          }
        }
        // ---- crowns actually drawn, by leg key, in the LEGS table
        for(var q=0;q<legRows.length;q++){
          var key=legRows[q].getAttribute('data-paperleg')||legRows[q].getAttribute('data-paperother');
          r.crowned[key]=(legRows[q].innerHTML.indexOf('\\uD83D\\uDC51')>=0)?1:0;
        }
        for(var q2=0;q2<listRows.length;q2++){
          r.crowned[listRows[q2].getAttribute('data-lgrow')]=(listRows[q2].innerHTML.indexOf('\\uD83D\\uDC51')>=0)?1:0;
        }
        // EXIT-DAY money (owner GO 2026-10-02): day headers read CLOSED, a still-open trade sits under its own
        // header with an unrealised mark, and the DAILY REPORTS table names the close day and carries BOOK $.
        r.openMarks=body?(body.innerText.match(/unrealised/g)||[]).length:(fr0?(fr0.textContent.match(/unrealised/g)||[]).length:0);
        r.dayHdrs=[].map.call(d.querySelectorAll('#ptrades-body tr.p2day'),function(x){return x.innerText.replace(/\\s+/g,' ').trim();});
        r.heroBig=[].map.call(d.querySelectorAll('#p2-hero-value'),function(x){return x.innerText;}).join('|');
        r.closeDayTh=[].filter.call(d.querySelectorAll('th'),function(x){return x.textContent.indexOf('CLOSE DAY')>=0;}).length;
        r.bookTh=[].filter.call(d.querySelectorAll('th'),function(x){return x.textContent.indexOf('BOOK $')>=0;}).length;
        // LEDGER step 3 readout (PAPER * layout)
        function _num(t){var m=String(t||'').replace(/,/g,'').match(/(-?)\\$([0-9.]+)/);return m?(m[1]?-1:1)*parseFloat(m[2]):null;}
        var _hn=d.querySelector('#p2-hero-value');
        r.heroNum=_hn?_num(_hn.textContent):null;
        var _hh=d.querySelector('.lg-hero');
        r.hero=_hh?{label:(_hh.querySelector('.lg-hero-label')||{}).innerText||'',today:(_hh.querySelector('.lg-hero-today')||{}).innerText||'',
          range:(_hh.querySelector('.lg-hero-range')||{}).innerText||'',
          parts:['.lg-hero-main','.lg-hero-label','.lg-hero-big','.lg-hero-today','.lg-hero-range','.lg-hero-chips'].map(function(q){return _hh.querySelector(q)?1:0;}).join(''),
          warnInChips:_hh.querySelectorAll('.lg-hero-chips .p2warn').length,chips:_hh.querySelectorAll('.lg-hero-chips .lg-chip').length,
          warnInStatus:d.querySelectorAll('[data-lgstatus="p2"] .p2warn').length}:null;
        r.pills=[].map.call(d.querySelectorAll('.lg-pills button'),function(x){return x.textContent.trim();});
        r.pillActive=[].map.call(d.querySelectorAll('.lg-pills button.active'),function(x){return x.textContent.trim();});
        r.oldTabs=d.querySelectorAll('.p2rhtabs').length;
        r.mscopeCtl=d.querySelectorAll('.p2rail [data-mscope]').length;
        r.rowDays=[].map.call(d.querySelectorAll('#ptrades-body tr[data-ptrow],[data-lglist-frame="nt8"] [data-lgtrade]'),function(x){return x.getAttribute('data-pcd');});
        r.calDays=[].map.call(d.querySelectorAll('[data-pcalday],[data-lgcalday]'),function(x){return x.getAttribute('data-pcalday')||x.getAttribute('data-lgcalday');});
        var _sv=d.querySelector('.p2rhstat .p2rhsv')||d.querySelector('[data-lgstat="trades"] .lg-stat-val');r.statTrades=_sv?parseInt(_sv.textContent,10):null;
        r.moneyHex=[].filter.call(d.querySelectorAll('#ptrades-body span.p2num, #p2legs span.p2num, .p2rhstat .p2rhsv span, [data-pcalday] div, tr[data-p2bookhd] span, tr[data-p2fwdhd] span, tr[data-p2otherhd] span, [data-lglist="p2"] .lg-row-val, [data-lglist="p2"] .lg-row-val *, [data-lglist="p2"] [data-p2grp] *, .lg-stats .lg-stat-val, .lg-more-panel .v, .lg-more-panel .v *, .lg-cal-panel [data-lgcalday], .lg-cal-panel [data-lgcalday] *'),function(x){return /#1d9e75|#e24b4a/i.test(x.getAttribute('style')||'');}).length;
        r.moneyMarks=[].map.call(d.querySelectorAll('#ptrades-body span.p2num, #p2legs span.p2num'),function(x){return x.innerText.trim();})
          .concat([].map.call(d.querySelectorAll('[data-lglist="p2"] .lg-row-val'),function(x){return x.innerText.split(String.fromCharCode(10))[0].trim();}));
        r.calMarks=[].map.call(d.querySelectorAll('[data-pcalday] > div:last-child'),function(x){return x.innerText.trim();})
          .concat([].map.call(d.querySelectorAll('[data-lgcalday] .m'),function(x){return x.innerText.trim();}));
        r.grpMarks=[].map.call(d.querySelectorAll('tr[data-p2bookhd] span:last-child, tr[data-p2fwdhd] > td > div > span:last-child, tr[data-p2otherhd] > td > div > span:last-child'),function(x){return x.innerText.trim();})
          .concat([].map.call(d.querySelectorAll('[data-p2grp] .lg-up, [data-p2grp] .lg-down'),function(x){return x.innerText.trim();})).filter(function(x){return x.indexOf('$')>=0;});
        r.maxDD=(function(){var o=null;[].forEach.call(d.querySelectorAll('.p2rhstat'),function(x){var l=x.querySelector('.p2rhsl');if(l&&/max drawdown/i.test(l.textContent))o=(x.querySelector('.p2rhsv')||{}).innerText||'';});
          var n2=d.querySelector('[data-lgstat="maxdd"] .lg-stat-val');if(n2)o=n2.innerText;return o;})();
        var _cs=d.querySelector('#p2-chart svg'),_pc=w._p2Chart||null;
        r.chart=_cs?{h:+_cs.getAttribute('height'),dates:_cs.querySelectorAll('[data-lgdate]').length,ticks:_cs.querySelectorAll('[data-lgtick]').length,
          legend:d.querySelectorAll('#p2-chart .lg-legend [data-lgline]').length,n:_pc?_pc.pts.length:0,last:(_pc&&_pc.pts.length)?_pc.pts[_pc.pts.length-1].v:null,
          faint:_cs.querySelectorAll('path[stroke-dasharray]').length}:null;
        r.scrub=null;
        if(_cs&&nm==='paper2'){
          try{
            var big=d.getElementById('p2-hero-value'),rng=d.getElementById('p2-hero-range');
            var b0=big.textContent,g0=rng.innerHTML,rc=_cs.getBoundingClientRect();
            var mk=function(t,x,pt){return new w.PointerEvent(t,{clientX:rc.left+x,clientY:rc.top+40,pointerType:pt,bubbles:true,pointerId:7});};
            _cs.dispatchEvent(mk('pointermove',rc.width*0.5,'mouse'));var m1=big.textContent,m1r=rng.innerText;
            _cs.dispatchEvent(mk('pointerleave',0,'mouse'));var mBack=(big.textContent===b0&&rng.innerHTML===g0);
            _cs.dispatchEvent(mk('pointerdown',rc.width*0.02,'touch'));var t1=big.textContent;
            _cs.dispatchEvent(mk('pointermove',rc.width*0.6,'touch'));var t2=big.textContent;
            _cs.dispatchEvent(mk('pointerup',0,'touch'));var tBack=(big.textContent===b0&&rng.innerHTML===g0);
            r.scrub={b0:b0,m1:m1,m1r:m1r,mBack:mBack,t1:t1,t2:t2,tBack:tBack};
          }catch(e){r.scrub={err:String(e)};}
        }
        r.rowNets=[].map.call(d.querySelectorAll('tr[data-paperleg]'),function(x){return x.getAttribute('data-paperleg')+'|'+_num(x.innerText);});
        try{var _sc=w._p2Scrub;r.boldEnd=(_sc&&_sc.total&&_sc.total.length)?_sc.total[_sc.total.length-1]:null;}catch(_e3){r.boldEnd=null;}
        var _ls=d.querySelector('[data-p2listed]');
        r.listed=_ls?{net:parseFloat(_ls.getAttribute('data-net')),n:+_ls.getAttribute('data-n'),tie:_ls.getAttribute('data-tie')}:null;
        var _oh=d.querySelector('[data-p2otherhd],[data-p2grp="other"]');
        r.otherHd=_oh?{net:parseFloat(_oh.getAttribute('data-net')),n:+_oh.getAttribute('data-n'),legs:+_oh.getAttribute('data-legs'),txt:_oh.innerText.replace(/\\s+/g,' ')}:null;
        r.otherRows=d.querySelectorAll('tr[data-paperother]').length+_gk('fwd').length+_gk('other').length+_gk('retired').length;
        function _hd(sel){var e=d.querySelector(sel);return e?{net:parseFloat(e.getAttribute('data-net')),n:+e.getAttribute('data-n'),legs:+e.getAttribute('data-legs'),txt:e.innerText.replace(/\\s+/g,' ')}:null;}
        r.bookHd=_hd('[data-p2bookhd],[data-p2grp="book"]');r.fwdHd=_hd('[data-p2fwdhd],[data-p2grp="fwd"]');r.retHd=_hd('[data-p2grp="retired"]');
        r.cap=(function(){var e=d.querySelector('.lg-hero-label');return e?e.innerText:'';})();
        r.bookW=w._paperBookW||null;
        var _ld=d.querySelector('[data-p2loaded]');
        r.loaded=_ld?{loaded:+_ld.getAttribute('data-loaded'),stored:_ld.getAttribute('data-stored'),other:+_ld.getAttribute('data-other'),txt:_ld.innerText}:null;
        r.warns=[].map.call(d.querySelectorAll('[data-lgstatus="p2"] .p2warn'),function(x){return x.innerText.replace(/\\s+/g,' ').trim();});   // LEDGER step 12: the status line
        var _ntc=d.querySelector('[data-p2card="nt"]');
        r.ntCardOpen=_ntc?(_ntc.hasAttribute('aria-expanded')?_ntc.getAttribute('aria-expanded')==='true':(_ntc.textContent.indexOf('\\u25be')>=0)):null;
        r.tradesHead=(function(){var x=d.querySelector('#ptrades-wrap');var h=x&&x.parentElement?x.parentElement.querySelector('.p2sh'):null;if(h)return h.innerText.replace(/\\s+/g,' ');var c=d.querySelector('[data-lglist-frame="nt8"] .lg-tl-count');return c?c.textContent.replace(/\\s+/g,' '):'';})();
        // ---- LEDGER steps 6, 7 and 10 on the PAPER * layout: the shared stats strip + More stats, the shared calendar, the shared list
        function _t(e){return e?e.textContent.replace(/\\s+/g,' ').trim():null;}
        function _top(e){if(!e)return null;return Math.round(e.getBoundingClientRect().top+(w.pageYOffset||0));}
        r.statTiles=[].map.call(d.querySelectorAll('.lg-stats [data-lgstat]'),function(e){return {k:e.getAttribute('data-lgstat'),v:_t(e.querySelector('.lg-stat-val')),sub:_t(e.querySelector('.lg-stat-sub')),top:_top(e)};});
        r.oldStatCells=d.querySelectorAll('.p2rhstat').length;
        var _ls0=d.querySelector('[data-lglist="p2"]');
        r.groups=_ls0?[].map.call(_ls0.querySelectorAll('.lg-grp'),function(g){var f=g.querySelector('[data-lggrp]');
          return {key:g.getAttribute('data-lggroup'),rows:g.querySelectorAll('[data-lgrow]').length,fold:!!f,open:f?f.getAttribute('aria-expanded'):null,txt:_t(g.querySelector('.lg-grp-hd'))};}):[];
        r.listRowInfo=_ls0?[].map.call(_ls0.querySelectorAll('[data-lgrow]'),function(x){var sw=x.querySelector('[data-lgsw]'),gp=x.closest('.lg-grp');
          return {key:x.getAttribute('data-lgrow'),name:_t(x.querySelector('.lg-row-name')),group:gp?gp.getAttribute('data-lggroup'):null,sw:sw?sw.getAttribute('aria-checked'):null,off:x.classList.contains('off'),
            val:(x.querySelector('.lg-row-val')||{innerText:''}).innerText.split(String.fromCharCode(10))[0].trim(),h:Math.round(x.getBoundingClientRect().height),dot:!!x.querySelector('.lg-row-name i'),sub:_t(x.querySelector('.lg-row-sub'))};}):[];
        var _tw=d.querySelector('#ptrades-wrap'),_tcard=(_tw&&_tw.closest)?_tw.closest('.p2sheet'):null;
        r.geo={vw:w.innerWidth,vh:w.innerHeight,scrollW:d.documentElement.scrollWidth,clientW:d.documentElement.clientWidth,boardTop:_top(d.querySelector('.p2rh')),
          tradesTop:_top(d.querySelector('[data-lglist-frame="nt8"]')||_tcard),listTop:_top(d.querySelector('[data-p2fold="list"]')||_ls0),moreTop:_top(d.querySelector('[data-lgmore="p2"]')),calTop:_top(d.querySelector('[data-lgcalfold="p2"]')),
          stripTop:_top(d.querySelector('.lg-stats')),chartTop:_top(d.querySelector('#p2-chart'))};
        // LEDGER step 12: the position of the strategy list column and of the frame panel round it (neither may be sticky any more)
        r.sideSticky=(function(){var c=d.querySelector('[data-p2col="side"]'),s=c?c.closest('[data-lgframe-side]'):null;return c?(w.getComputedStyle(c).position+'/'+(s?w.getComputedStyle(s).position:'none')):null;})();
        r.calFold=(function(){var b=d.querySelector('[data-lgcalfold="p2"]');return b?b.getAttribute('aria-expanded'):null;})();
        r.moreFold=(function(){var b=d.querySelector('[data-lgmore="p2"]');return b?b.getAttribute('aria-expanded'):null;})();
        function _calState(){var g=d.querySelector('.lg-cal[data-lgcal="p2"]');if(!g)return null;
          var days=g.querySelectorAll('[data-lgcalday]');
          return {month:g.getAttribute('data-lgcalmonth'),title:_t(g.querySelector('.lg-cal-title')),sum:_t(g.querySelector('.lg-cal-sum')),
            days:[].map.call(days,function(b){return b.getAttribute('data-lgcalday');}),
            dayN:[].map.call(days,function(b){return parseInt((b.querySelector('.n')||{textContent:'0'}).textContent,10)||0;}),
            cells:g.querySelectorAll('.lg-cal-grid > *').length,cav:g.querySelectorAll('.lg-cal-day.cav').length,
            prevDis:(g.querySelector('[data-lgcalmo="-1"]')||{}).disabled,nextDis:(g.querySelector('[data-lgcalmo="1"]')||{}).disabled};}
        r.cal=_calState();
        r.calPanelHidden=(function(){var p=d.getElementById('p2-cal');return p?!!p.hidden:null;})();
        r.s11=null;try{r.s11=s11Read(d,w,nm);}catch(e){r.s11={err:String(e&&e.stack?e.stack:e)};}   // before any interaction below moves the page
        r.tl=tlRead(d,w);
        r.tlGeo=(function(){var f0=d.querySelector('[data-lglist-frame="nt8"]'),b0=d.querySelector('.p2rh');
          return {vw:w.innerWidth,vh:w.innerHeight,scrollW:d.documentElement.scrollWidth,clientW:d.documentElement.clientWidth,frameTop:f0?_top(f0):null,boardTop:b0?_top(b0):null};})();
        // LEDGER step 9: behind ?oldboards=1 the shared trade panel is not in the page either until a row is clicked
        r.flagPanel=(nm==='flag-paper2')?{nodes:d.querySelectorAll('.lg-panel,.lg-panel-layer').length,id:w._ntPanelId==null?null:String(w._ntPanelId),frames:d.querySelectorAll('[data-lglist-frame]').length}:null;
        r.tlint=null;
        if(nm==='paper2'||nm==='other-on'){try{r.tlint=tlInteract(d,w,nm);}catch(e){r.tlint={err:String(e&&e.stack?e.stack:e)};}}
        // LEDGER step 9: the panel at this width (the width sweep), then the panel cases
        r.pw=null;
        if(cfg.width){try{r.pw=panelAtWidth(d,w);}catch(e){r.pw={err:String(e&&e.stack?e.stack:e)};}}
        r.panel=null;
        if(cfg.panel){try{r.panel=await panelInteract(d,w,cfg);}catch(e){r.panel={err:String(e&&e.stack?e.stack:e)};}}
        r.ckey=null;
        if(cfg.ckey){try{r.ckey=await chartKeyInteract(d,w,cfg);}catch(e){r.ckey={err:String(e&&e.stack?e.stack:e)};}}
        r.s11f=null;r.s11m=null;
        if(cfg.s11==='fold'){try{r.s11f=s11Folds(d,w);}catch(e){r.s11f={err:String(e&&e.stack?e.stack:e)};}}
        r.s12f=null;
        if(cfg.s11==='fold'){try{r.s12f=s12Filters(d,w);}catch(e){r.s12f={err:String(e&&e.stack?e.stack:e)};}}
        if(cfg.s11==='mono'){try{r.s11m=s11Mono(d,w);}catch(e){r.s11m={err:String(e&&e.stack?e.stack:e)};}}
        if(cfg.theme){try{w.eval("prefs.theme="+(th0===undefined?"undefined":JSON.stringify(th0))+";applyTheme();");}catch(e){}}
        // the capped list: a calendar tap on a day older than the list reaches (it extends the list to that day, ticks its rows, scrolls to it)
        r.capint=null;
        if(nm==='cap'){try{
          var Cx={},F0=function(){return d.querySelector('[data-lglist-frame="nt8"]');};
          w.__scrolled=[];w.Element.prototype.scrollIntoView=function(){(w.__scrolled=w.__scrolled||[]).push(this.getAttribute?this.getAttribute('data-lgday'):null);};
          var gd=0;
          while(gd++<14){var pb=d.querySelector('[data-lgcal="p2"][data-lgcalmo="-1"]');if(!pb||pb.disabled)break;pb.click();}
          var cm=d.querySelector('.lg-cal[data-lgcal="p2"]');
          Cx.month=cm?cm.getAttribute('data-lgcalmonth'):null;
          var cd0=d.querySelectorAll('.lg-cal[data-lgcal="p2"] [data-lgcalday]'),b0=cd0[0];
          Cx.day=b0.getAttribute('data-lgcalday');Cx.cellN=parseInt((b0.querySelector('.n')||{textContent:'0'}).textContent,10)||0;
          Cx.hadDay=!!F0().querySelector('[data-lgday="'+Cx.day+'"]');
          w.__scrolled=[];b0.click();
          var f3=F0(),tk3=[].slice.call(f3.querySelectorAll('input[data-pttick]:checked'));
          Cx.sel=tk3.length;Cx.selDays=tk3.map(function(c){return c.closest('[data-lgtrade]').getAttribute('data-pcd');});
          Cx.scrolled=(w.__scrolled||[]).slice();Cx.hasDay=!!f3.querySelector('[data-lgday="'+Cx.day+'"]');
          Cx.openTxt=(f3.querySelector('[data-ptopen]')||{}).textContent||null;
          Cx.tl=tlRead(d,w);
          w._ptSel=null;w._ptReach=null;
          r.capint=Cx;
        }catch(e){r.capint={err:String(e&&e.stack?e.stack:e)};}}
        r.int=null;
        if(nm==='paper2'){
          try{
            var I={};
            w.__scrolled=[];w.Element.prototype.scrollIntoView=function(){(w.__scrolled=w.__scrolled||[]).push(this.getAttribute?this.getAttribute('data-lgday'):null);};
            var _click=function(sel){var e=d.querySelector(sel);if(!e)return false;e.click();return true;};
            var _heroN=function(){var e=d.getElementById('p2-hero-value');return e?_num(e.textContent):null;};
            var _snap=function(){
              var pc=w._p2Chart||null,tl={},bk=d.querySelector('[data-p2grp="book"]');
              [].forEach.call(d.querySelectorAll('.lg-stats [data-lgstat]'),function(e){tl[e.getAttribute('data-lgstat')]=_t(e.querySelector('.lg-stat-val'));});
              return {hero:_heroN(),chartLast:(pc&&pc.pts.length)?pc.pts[pc.pts.length-1].v:null,tiles:tl,bookNet:bk?parseFloat(bk.getAttribute('data-net')):null,
                bookN:bk?+bk.getAttribute('data-n'):null,tradeRows:d.querySelectorAll('#ptrades-body tr[data-ptrow],[data-lglist-frame="nt8"] [data-lgtrade]').length,cal:_calState(),
                sw:[].map.call(d.querySelectorAll('[data-lglist="p2"] [data-lgsw]'),function(s){return s.getAttribute('data-lgsw')+'='+s.getAttribute('aria-checked');}).join(',')};};
            // More stats: opens with Returns / Risk / Mix + this board's own group, remembered per browser, closes again
            I.more={start:r.moreFold};
            if(_click('[data-lgmore="p2"]')){
              I.more.open=d.querySelector('[data-lgmore="p2"]').getAttribute('aria-expanded');
              I.more.groups=[].map.call(d.querySelectorAll('#p2-more [data-lgmsgroup]'),function(g){return g.getAttribute('data-lgmsgroup');});
              I.more.rows=[].map.call(d.querySelectorAll('#p2-more .lg-ms-row'),function(x){return [_t(x.querySelector('.l')),_t(x.querySelector('.v'))];});
              var _vs=d.querySelector('#p2-more [data-lgmsgroup="Strategy vs control"]');
              I.more.vsRows=_vs?_vs.querySelectorAll('.lg-ms-row').length:0;
              I.more.vsSubs=_vs?[].map.call(_vs.querySelectorAll('.p2vs-sub'),function(x){return _t(x);}):[];
              I.more.vsCrown=_vs?(_vs.innerHTML.indexOf('\\uD83D\\uDC51')>=0):false;
              I.more.vsTxt=_vs?_t(_vs):'';
              I.more.stored=localStorage.getItem('el_lg_stats_nt8');
              _click('[data-lgmore="p2"]');
              I.more.closed=d.querySelector('[data-lgmore="p2"]').getAttribute('aria-expanded');
              I.more.storedClosed=localStorage.getItem('el_lg_stats_nt8');
            }
            // calendar: the newest month, a day tap (the rows that CLOSED that day), then the month arrow back
            var _tap=function(){
              var dd=d.querySelectorAll('.lg-cal[data-lgcal="p2"] [data-lgcalday]');if(!dd.length)return null;
              var b=dd[dd.length-1],day=b.getAttribute('data-lgcalday'),cellN=parseInt((b.querySelector('.n')||{textContent:'0'}).textContent,10)||0;
              w.__scrolled=[];
              b.click();
              var fr1=d.querySelector('[data-lglist-frame="nt8"]');
              var sel=fr1?[].map.call(fr1.querySelectorAll('input[data-pttick]:checked'),function(c){return c.closest('[data-lgtrade]');}):d.querySelectorAll('#ptrades-body tr.ptsel');
              var o={day:day,cellN:cellN,sel:sel.length,selDays:[].map.call(sel,function(x){return x.getAttribute('data-pcd');}),
                forDay:d.querySelectorAll('#ptrades-body tr[data-ptrow][data-pcd="'+day+'"],[data-lglist-frame="nt8"] [data-lgtrade][data-pcd="'+day+'"]').length,
                scrolled:(w.__scrolled||[]).slice(),openTxt:fr1?((fr1.querySelector('[data-ptopen]')||{}).textContent||null):null};
              w._ptSel=null;return o;};
            I.cal0=_calState();
            I.tap0=_tap();
            if(_click('[data-lgcal="p2"][data-lgcalmo="-1"]')){
              I.calPrev=_calState();
              I.calStored=localStorage.getItem('el_lg_calmo_nt8');
              I.tap1=_tap();
            }
            // the switches: from here the calendar shows the earlier month, where the ORB trades closed
            I.flip0=_snap();
            if(_click('[data-lgsw="ORB"]')){I.flip1=_snap();_click('[data-lgsw="ORB"]');I.flip2=_snap();}
            // a strategy outside the book: its switch lists its trades and never moves a counted figure
            if(_click('[data-lgsw="NOISE_H"]')){I.oth1=_snap();_click('[data-lgsw="NOISE_H"]');I.oth2=_snap();}
            // tapping the row does what its switch does
            if(_click('[data-lglist="p2"] [data-lgrow="ORB"]')){I.rowTap=_snap();_click('[data-lglist="p2"] [data-lgrow="ORB"]');}
            _click('[data-lgcal="p2"][data-lgcalmo="1"]');
            I.calBack=_calState();
            // the calendar fold: closed means the panel is hidden and the choice is stored; open again
            if(_click('[data-lgcalfold="p2"]')){
              I.calFold={closed:d.querySelector('[data-lgcalfold="p2"]').getAttribute('aria-expanded'),hidden:(d.getElementById('p2-cal')||{}).hidden,stored:localStorage.getItem('el_lg_cal_nt8')};
              _click('[data-lgcalfold="p2"]');I.calFold.reopen=d.querySelector('[data-lgcalfold="p2"]').getAttribute('aria-expanded');
            }
            r.int=I;
          }catch(e){r.int={err:String(e&&e.stack?e.stack:e)};}
        }
        var _dr=drain(cfg.frame||'f');r.errors=_dr.errors;r.uncaught=_dr.uncaught;
        out.cases[nm]=r;
      }
      // LEDGER step 11: open / closed is remembered - a real reload of a fresh page, on a laptop and on a phone
      out.s11reload={};
      try{out.s11reload.lap=await s11Reload(1366,900,'lap');}catch(e){out.s11reload.lap={err:String(e&&e.stack?e.stack:e)};}
      try{out.s11reload.pho=await s11Reload(375,812,'pho');}catch(e){out.s11reload.pho={err:String(e&&e.stack?e.stack:e)};}
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='PAPERPROBE: '+JSON.stringify(out);
  }
  var _nLoaded=0;
  var FRAMES=['f','fp','fo','fm','fs','fx','fw','fz','fl','fk'];
  FRAMES.forEach(function(id){document.getElementById(id).addEventListener('load',function(){
    _nLoaded++; if(_nLoaded===FRAMES.length)setTimeout(function(){report('load');},3500);});});
  setTimeout(function(){report('backstop');},85000);
})();
</script>
</body></html>
"""


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def make_handler(root, alt_index=None):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            # --file: serve another build (a deliberately broken copy in the self-test) as /index.html
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


def read_leg_defs(index_path):
    """Pull the leg declarations straight out of index.html so the probe checks the render
    against what the source SAYS, not against a hand-kept list that could drift."""
    src = io.open(index_path, encoding='utf-8', newline='').read()
    i = src.find('const PAPER_LEG_DEFS=[')
    j = src.find('\n      ];', i)
    block = src[i:j] if i >= 0 and j > i else ''
    defs = {}
    for m in re.finditer(r"\{k:'([A-Z0-9_]+)'\s*,\s*label:'([^']*)'(.*?)(?=\n\s*(?:\{k:'|//|\])|$)",
                         block, re.S):
        k, label, rest = m.group(1), m.group(2), m.group(3)
        defs[k] = {'label': label,
                   'archived': "archived:true" in rest,
                   'crown': "crown:true" in rest,
                   'nt': bool(re.search(r"\bnt:'", rest))}
    return defs


def build_fixture(root, fix_path):
    """The real captured fixture plus everything it predates (injected trades, book weights, capture health).
    Shared by the probe and by any scratch harness that wants the same board."""
    fixture = json.load(io.open(fix_path, encoding='utf-8'))
    # Inject what the real fixture predates: a NOISE_422 tilted-size trade (2026-09-28 leg) and the nightly
    # capture_health block, one good instrument and one low-delta instrument.
    _src = next((t for t in fixture['trades'] if t.get('leg') == 'NOISE_SBS_V90'), None)
    if _src is not None:
        _t = dict(_src, id='pt_NOISE_422_probe', leg='NOISE_422', size=1.75,
                  pnl_usd=round(_src.get('pnl_usd', 0) * 1.75, 2),
                  # LEDGER step 9: lines the engine record may carry - the panel shows them read-only
                  reason='probe: break of the opening range', exit_reason='probe: trailing stop', gate='probe gate keep')
        fixture['trades'].append(_t)
    # EXIT-DAY: an OPEN ENGU-Q trade carrying a huge mark (must reach no total, curve or day) and a trade that
    # closed on a Sunday evening (counts on the Monday).
    _e = next((t for t in fixture['trades'] if str(t.get('leg', '')).startswith('ENGUQ')), None)
    if _e is not None:
        fixture['trades'].append(dict(_e, id='pt_ENGUQ_335_probe_open', leg='ENGUQ_335', open=True,
                                      close_day=None, exit_date='2026-09-30', pnl_usd=987654.0,
                                      exitIso='2026-09-30T16:09:00-04:00', exitTime=1790798940))
        fixture['trades'].append(dict(_e, id='pt_ENGUQ_335_probe_sun', leg='ENGUQ_335', open=False,
                                      exit_date='2026-09-20', close_day='2026-09-21', pnl_usd=123.0,
                                      exitIso='2026-09-20T19:30:00-04:00', exitTime=1790033400))
    # LEDGER step 3: trades of strategies that have NO listed row (the Other / shadow group). They must reach
    # the Other group subtotal and never the big number.
    _o = next((t for t in fixture['trades'] if t.get('leg') == 'NOISE_SBS_V90'), None)
    if _o is not None:
        for _i, (_lg, _usd) in enumerate((('TTM_299_SSOF2', 500.0), ('TTM_299_SSOF2', -120.0), ('ORB_257', 310.0))):
            fixture['trades'].append(dict(_o, id='pt_%s_probe_%d' % (_lg, _i), leg=_lg, pnl_usd=_usd,
                                          entryTime=_o['entryTime'] + 60 * (_i + 1), close_day=None, open=False))
    # LEDGER step 8: a $0 trade (a flat exit) on a strategy outside the book - the WINS and LOSSES chips must leave it out
    _z = next((t for t in fixture['trades'] if t.get('leg') == 'NOISE_H' and t.get('open') is not True), None)
    if _z is not None:
        fixture['trades'].append(dict(_z, id='pt_NOISE_H_probe_flat', pnl_usd=0.0, pnl_pts=0.0,
                                      entryTime=_z['entryTime'] + 90, exitTime=_z['exitTime'] + 90))
    # LEDGER step 9: a matched NinjaTrader fill for the ORB trade of 2026-08-12 (SLIP +0.75 pts against us, delta -$12.50), so the panel has
    # numbers for its SLIP and delta $ rows. `matched` is what the nightly reconcile writes; it changes no total and no alarm.
    _orb = next((t for t in fixture['trades'] if t.get('id') == 'pt_ORB_1786548600'), None)
    if _orb is not None and fixture['reports']:
        _lg = fixture['reports'][0].setdefault('reconcile', {}).setdefault('legs', {}).setdefault('ORB', {'live_only': [], 'matched': [], 'shadow_only': []})
        _lg.setdefault('matched', []).append({'shadow_entry': _orb['entryIso'], 'entry_slip_pts': 0.75, 'pnl_diff_usd': -12.5})
    # the newest report carries the book weights the way the nightly run writes them (read from api/paper.py)
    try:
        _bm = re.search(r"^    _BOOK = (\{[^}]*\})", io.open(os.path.join(root, 'api', 'paper.py'), encoding='utf-8').read(), re.M)
        fixture['reports'][0]['book'] = {'weights': __import__('ast').literal_eval(_bm.group(1)), 'source_run': 463,
                                          'pnl_usd': 0.0, 'missing': [], 'failed': []}
    except Exception:
        pass
    fixture['tradeInfo'] = {'bundle': True, 'n_total': len(fixture['trades']), 'parts': 1,
                            'loaded': len(fixture['trades'])}
    fixture['reports'][0]['capture_health'] = {
        'NQ': {'rth': {'bars': 2331, 'expected': 2340, 'bars_pct': 99.6, 'delta_pct': 98.3, 'rt_bars': 2000,
                       'longest_gap_min': 1.5, 'gap_start_et': '10:12'},
               'eth': {'bars': 8100, 'expected': 8280, 'delta_pct': 60.0, 'delta_from_et': '08:20'}},
        'ES': {'rth': {'bars': 2340, 'expected': 2340, 'bars_pct': 100.0, 'delta_pct': 38.0, 'rt_bars': 2340,
                       'longest_gap_min': 0.0, 'gap_start_et': None},
               'eth': {'bars': 8100, 'expected': 8280, 'delta_pct': 11.0}},
        'warning': '10-second capture problem - ES: buy/sell delta is filled in on only 38% of session bars.'}
    return fixture


def run(alt_index=None, timeout=300):
    """One full pass of the probe over this repo's index.html (or over alt_index, served as /index.html).
    Returns (exit code, the lines to print) so a self-test can run several passes side by side."""
    out_lines = []

    def say(msg):
        out_lines.append(msg)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(root, 'index.html')
    fix_path = os.path.join(root, 'tools', 'fixtures', 'paper_board.json')
    if not os.path.isfile(fix_path):
        say('PAPERPROBE: INCONCLUSIVE -- fixture missing: %s' % fix_path)
        return INCONCLUSIVE, out_lines
    # static lint (tools/ledger_removed.py): nothing the LEDGER clean-up removed is back in the file being gated
    sys.path.insert(0, os.path.join(root, 'tools'))
    try:
        import ledger_removed
    finally:
        sys.path.pop(0)
    probs = ledger_removed.lint_file(alt_index or index_path, ['shared', 'nt8'])
    if probs:
        say('PAPERPROBE: FAIL')
        for p_ in probs:
            say('  - ' + p_)
        return FAIL, out_lines
    chrome = find_chrome()
    if not chrome:
        say('PAPERPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE, out_lines

    defs = read_leg_defs(alt_index or index_path)
    if not defs:
        say('PAPERPROBE: INCONCLUSIVE -- could not read PAPER_LEG_DEFS out of index.html')
        return INCONCLUSIVE, out_lines
    arch_labels = {d['label'] for d in defs.values() if d['archived']}
    crown_keys = {k for k, d in defs.items() if d['crown']}
    nt_labels = {d['label'] for d in defs.values() if d['nt']}

    fixture = build_fixture(root, fix_path)
    ALL_CASES = list(CASES) + extra_cases(fixture)
    global CASE_CFG
    CASE_CFG = dict((n, c) for n, c in ALL_CASES)

    pdir = tempfile.mkdtemp(prefix='_paperprobe_', dir=root)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__CASES__', json.dumps([[n, c] for n, c in ALL_CASES]))
            .replace('__FIX__', json.dumps(fixture))
            .replace('__HOUSE__', json.dumps(HOUSE_WIDTHS))
            .replace('__S11K__', json.dumps(S11_KEYS))
            .replace('__OLDMARKS__', json.dumps(OLD_MARKS)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='paperprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=95000',
             '--dump-dom', 'http://127.0.0.1:%d/%s/probe.html' % (port, os.path.basename(pdir))],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=timeout).stdout
    except Exception as e:
        say('PAPERPROBE: INCONCLUSIVE -- chrome failed: %s' % e)
        return INCONCLUSIVE, out_lines
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'PAPERPROBE: (\{.*?\})</pre>', out, re.S)
    if not m:
        say('PAPERPROBE: INCONCLUSIVE -- probe produced no readout')
        return INCONCLUSIVE, out_lines
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        say('PAPERPROBE: INCONCLUSIVE -- unreadable readout: %s' % e)
        return INCONCLUSIVE, out_lines

    if data.get('err'):
        say('PAPERPROBE: FAIL -- probe threw: %s' % data['err'])
        return FAIL, out_lines

    if os.environ.get('PAPERPROBE_DUMP'):
        io.open(os.path.join(root, '_paperprobe_dump.json'), 'w', encoding='utf-8').write(
            json.dumps(data, indent=1, ensure_ascii=False))
    fails, cases = [], data.get('cases') or {}
    if len(cases) != len(ALL_CASES):
        fails.append('only %d of %d cases reported' % (len(cases), len(ALL_CASES)))

    for nm, r in cases.items():
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, r.get('call')))
            continue
        if (r.get('appLen') or 0) < 5000:
            fails.append('%s: board rendered almost nothing (appLen=%s)' % (nm, r.get('appLen')))
        if r.get('colBad'):
            fails.append('%s: %s' % (nm, '; '.join(r['colBad'])))
        if nm == 'empty':
            continue
        if not r.get('legRows'):
            fails.append('%s: LEGS table drew no rows' % nm)
        if not r.get('sortable'):
            fails.append('%s: no sortable LEGS headers rendered' % nm)
        # COLUMNS control removed by design in v73.396 - the sidebar table is locked
        # to KEY because thirteen columns cannot fit a sidebar. No assertion on it.
        if nm.startswith('paper2'):
            if not r.get('sideBar'):
                fails.append('%s: PAPER plus lost its strategy sidebar' % nm)
            elif not r.get('legsInSide'):
                fails.append('%s: the LEGS panel is no longer inside the sidebar '
                             'column' % nm)
            elif (r.get('sideTrayMax') or 0) > 40:
                fails.append('%s: a sidebar control tray is %spx tall - its chips are '
                             'wrapping into a blob again' % (nm, r.get('sideTrayMax')))
        # ARCHIVED LEGS MUST NOT LEAK unless SHOW ARCHIVED asked for them
        def _is(lbl, pool):
            return any(lbl.startswith(x) for x in pool)
        leaked = [l for l in (r.get('tradeLegs') or {}) if _is(l, arch_labels)]
        if nm in ('show-archived', 'retired-open'):
            if arch_labels and not leaked:
                fails.append('%s: archived legs did not come back into the trades table' % nm)
        elif leaked:
            fails.append('%s: archived leg(s) %s still in the trades table with SHOW ARCHIVED off'
                         % (nm, ', '.join(sorted(leaked))))
        # A RED CROSS CLAIMS NinjaTrader REFUSED THE TRADE -- unmakeable for a leg it never runs
        bad_red = sorted({l for l in (r.get('redNoNt') or []) if l and not _is(l, nt_labels)})
        if bad_red:
            fails.append('%s: red NT cross on leg(s) NinjaTrader does not run: %s'
                         % (nm, ', '.join(bad_red)))
        # CROWNS: exactly the declared ones, and only those
        drawn = {k for k, v in (r.get('crowned') or {}).items() if v}
        shown = set((r.get('crowned') or {}).keys())
        want = crown_keys & shown
        if drawn != want:
            fails.append('%s: crown drawn on %s, declared %s'
                         % (nm, sorted(drawn) or '(none)', sorted(want) or '(none)'))

    # NOISE #422 must be a LEGS row, labelled with the family name, and its trade must reach the trades table
    for nm in ('base', 'paper2'):
        r = cases.get(nm) or {}
        if 'NOISE_422' not in (r.get('legKeys') or []):
            fails.append('%s: no NOISE_422 row on the board' % nm)
        if not any(l.startswith('NOISE #422') for l in (r.get('tradeLegs') or {})):
            fails.append('%s: the NOISE #422 trade did not reach the trades table' % nm)
    # the capture-health line: one per instrument, low-delta day flagged in words (not colour alone)
    for nm in ('base', 'paper2'):
        r = cases.get(nm) or {}
        if ('2,331/2,340 bars, delta on 98%' not in (r.get('capNQ') or '')
                or 'split starts 08:20 ET' not in (r.get('capNQ') or '')):
            fails.append('%s: NQ capture line missing or wrong: %r' % (nm, r.get('capNQ')))
        if 'delta on 38%' not in (r.get('capES') or '') or 'LOW' not in (r.get('capES') or ''):
            fails.append('%s: ES capture line not flagged LOW: %r' % (nm, r.get('capES')))

    # EXIT-DAY board: the shared frame's day headers, OPEN NOW block and unrealised label are asserted from the fixture further down (LEDGER step 8).
    r = cases.get('reports-open') or {}
    if not r.get('closeDayTh') or not r.get('bookTh'):
        fails.append('reports-open: DAILY REPORTS lost its CLOSE DAY / BOOK $ columns')
    if '987,654' in ((cases.get('paper2') or {}).get('heroBig') or ''):
        fails.append('paper2: an open trade mark leaked into the hero net')

    # LEDGER step 3 + BOOK -- the numbers must tie out on the PAPER * layout. The book is READ from api/paper.py
    # (_BOOK), never kept here, so a changed book fails this probe until the board follows.
    book_w = {}
    try:
        _m = re.search(r"^    _BOOK = (\{[^}]*\})", io.open(os.path.join(root, 'api', 'paper.py'), encoding='utf-8').read(), re.M)
        book_w = {k: float(v) for k, v in __import__('ast').literal_eval(_m.group(1)).items()}
    except Exception as e:
        fails.append('could not read _BOOK out of api/paper.py: %s' % e)
    closed = [t for t in fixture['trades'] if t.get('open') is not True]
    def _w(t):
        return book_w.get(str(t.get('leg') or '').upper(), 0.0)
    exp_book = round(sum((t.get('pnl_usd') or 0) * _w(t) for t in closed))
    exp_fwd = sum(t.get('pnl_usd') or 0 for t in closed
                  if t.get('leg') in defs and not _w(t) and not defs[t['leg']]['archived'])
    exp_other = sum(t.get('pnl_usd') or 0 for t in closed if t.get('leg') not in defs and not _w(t))
    n_all = len(fixture['trades'])
    TIE = ('paper2', 'other-open', 'other-on', 'legs-off-p2', 'warn-stale-bridge', 'fwd-closed', 'book-fallback',
           'retired-open', 'stats-open', 'cal-closed', 'cal-aug', 'phone375')
    for nm in TIE:
        r = cases.get(nm) or {}
        ld, hn, be, li = r.get('loaded') or {}, r.get('heroNum'), r.get('boldEnd'), r.get('listed') or {}
        if ld.get('loaded') != n_all or str(ld.get('stored')) != str(n_all):
            fails.append('%s: all-time trade count shown %s of stored %s, fixture holds %d'
                         % (nm, ld.get('loaded'), ld.get('stored'), n_all))
        if hn is None or be is None or li.get('net') is None:
            fails.append('%s: hero number / bold line end / BOOK group total missing (%s, %s, %s)'
                         % (nm, hn, be, li.get('net')))
            continue
        if abs(hn - be) > 1.0 or abs(hn - li['net']) > 1.0 or li.get('tie') != '1':
            fails.append('%s: big NET %s, end of the bold line %s, BOOK group total %s (tie=%s) do not agree'
                         % (nm, hn, be, li['net'], li.get('tie')))
        if 'book #463 \u00b7 nt8 futures paper' not in (r.get('cap') or '').lower():
            fails.append('%s: the hero label is not BOOK #463 - NT8 futures paper: %r' % (nm, r.get('cap')))
    for nm in ('paper2', 'other-open', 'other-on', 'warn-stale-bridge', 'fwd-closed', 'book-fallback'):
        r = cases.get(nm) or {}
        if r.get('heroNum') is not None and abs(r['heroNum'] - exp_book) > 1.0:
            fails.append('%s: big NET %s is not the BOOK figure %s (a leg outside _BOOK leaked in, a book leg dropped, '
                         'or the TTM weight is not applied)' % (nm, r['heroNum'], exp_book))
        bh, fh, oh = r.get('bookHd') or {}, r.get('fwdHd') or {}, r.get('otherHd') or {}
        if not bh or abs(bh.get('net', 0) - exp_book) > 1.0 or bh.get('legs') != len(book_w):
            fails.append('%s: BOOK group total %s over %s legs, expected %s over %d' % (nm, bh.get('net'), bh.get('legs'), exp_book, len(book_w)))
        if not fh or abs(fh.get('net', 0) - exp_fwd) > 0.5:
            fails.append('%s: Forward tests & controls subtotal %s, expected %s' % (nm, fh.get('net'), exp_fwd))
        if 'not counted' not in (fh.get('txt') or '').lower():
            fails.append('%s: Forward tests & controls is not labelled as not counted: %r' % (nm, fh.get('txt')))
        if not oh or abs(oh.get('net', 0) - exp_other) > 0.5 or not oh.get('legs'):
            fails.append('%s: Other / shadow group subtotal %s, expected %s' % (nm, oh.get('net'), exp_other))
        if 'not counted' not in (oh.get('txt') or '').lower():
            fails.append('%s: the Other group is not labelled as not counted: %r' % (nm, oh.get('txt')))
        keys = list(r.get('bookRowKeys') or [])
        if sorted(keys) != sorted(book_w) or len(keys) != len(book_w):
            fails.append('%s: BOOK rows %s are not exactly the _BOOK legs %s' % (nm, keys, sorted(book_w)))
        if (r.get('bookW') or {}) != book_w:
            fails.append('%s: the board used book weights %s, api/paper.py _BOOK says %s' % (nm, r.get('bookW'), book_w))
    # the book rows come first and are the only switches that move the big number; the group rows are closed/open as set
    r = cases.get('paper2') or {}
    unl = [k for k in (r.get('otherRowKeys') or []) if k not in defs]
    lst = [k for k in (r.get('otherRowKeys') or []) if k in defs]
    if unl:
        fails.append('paper2: the Other / shadow group should be closed by default but drew %s' % unl)
    if not lst:
        fails.append('paper2: the Forward tests & controls group drew no rows by default')
    if any(k in book_w for k in lst):
        fails.append('paper2: a book leg is also listed under Forward tests & controls')
    r = cases.get('fwd-closed') or {}
    if r.get('otherRows'):
        fails.append('fwd-closed: the folded Forward tests & controls group still drew rows')
    r = cases.get('other-open') or {}
    if 'ORB_257' not in (r.get('otherRowKeys') or []):
        fails.append('other-open: the open Other group drew no unlisted strategy rows with switches')
    r = cases.get('other-on') or {}
    tl = list((r.get('tradeLegs') or {}).keys())
    if not any(l.startswith('ORB #257') for l in tl) or not any(l.startswith('NOISE #225') for l in tl):
        fails.append('other-on: switched-on not-counted strategies did not reach the trades table: %s' % tl)
    if 'other, not counted' not in (r.get('tradesHead') or '').lower():
        fails.append('other-on: the trades heading does not say the other rows are not counted: %r'
                     % r.get('tradesHead'))
    # LEDGER step 4 -- the shared hero and the ONE pill row. Expected figures come from the fixture, with the
    # range counted back from today in New York, a trade counted on the day it CLOSED.
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        today_ny = _dt.datetime.now(ZoneInfo('America/New_York')).date()
    except Exception:
        today_ny = (_dt.datetime.utcnow() - _dt.timedelta(hours=4)).date()

    def _close(t):
        if t.get('open') is True:
            return ''
        if t.get('close_day'):
            return t['close_day']
        x = str(t.get('exitIso') or '')[:10]
        d = _dt.date.fromisoformat(x)
        while d.weekday() >= 5:
            d += _dt.timedelta(days=1)
        return d.isoformat()

    def _cut(rng):
        if rng == 'TODAY':
            return today_ny.isoformat()
        if rng == 'YTD':
            return '%d-01-01' % today_ny.year
        n = {'1W': 7, '1M': 30, '3M': 90}.get(rng)
        return (today_ny - _dt.timedelta(days=n)).isoformat() if n else ''

    def _exp_range(rng):
        c = _cut(rng)
        rows = [t for t in closed if _w(t) and (not c or _close(t) >= c)]
        return round(sum((t.get('pnl_usd') or 0) * _w(t) for t in rows)), len(rows), c
    PILLS = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']
    for nm, rng in (('range-today', 'TODAY'), ('range-1w', '1W'), ('range-1m', '1M'), ('range-3m', '3M'),
                    ('range-ytd', 'YTD'), ('range-saved', '1M'), ('paper2', 'ALL')):
        r = cases.get(nm) or {}
        exp, n_exp, cut = _exp_range(rng)
        hn, be, li = r.get('heroNum'), r.get('boldEnd'), r.get('listed') or {}
        if hn is None or abs(hn - exp) > 1.0:
            fails.append('%s: big NET %s, expected the BOOK figure %s for %s (cutoff %r)' % (nm, hn, exp, rng, cut))
        if be is not None and hn is not None and abs(be - hn) > 1.0 and not (be is None):
            fails.append('%s: end of the bold line %s differs from the big NET %s' % (nm, be, hn))
        if li.get('net') is None or abs(li['net'] - exp) > 1.0 or li.get('tie') != '1':
            fails.append('%s: BOOK group total %s (tie %s), expected %s - the rows do not follow the range'
                         % (nm, li.get('net'), li.get('tie'), exp))
        if r.get('statTrades') != n_exp:
            fails.append('%s: the Trades stat reads %s, expected %d closed book trades in the range'
                         % (nm, r.get('statTrades'), n_exp))
        if cut:
            early = [x for x in (r.get('rowDays') or []) if x and x < cut]
            if early:
                fails.append('%s: the trade list shows trades closed before %s: %s' % (nm, cut, early[:3]))
            early = [x for x in (r.get('calDays') or []) if x < cut]
            if early:
                fails.append('%s: the calendar shows days before %s: %s' % (nm, cut, early[:3]))
        if r.get('pills') != PILLS or r.get('pillActive') != [rng]:
            fails.append('%s: the pill row reads %s with %s active, expected %s with %s'
                         % (nm, r.get('pills'), r.get('pillActive'), PILLS, rng))
        if r.get('oldTabs') or r.get('mscopeCtl'):
            fails.append('%s: an old range control is still on the board (tabs %s, Today/All switch %s)'
                         % (nm, r.get('oldTabs'), r.get('mscopeCtl')))
        h = r.get('hero') or {}
        if h.get('parts') != '111111':
            fails.append('%s: the hero is missing a shared part (main/label/big/today/range/chips = %s)' % (nm, h.get('parts')))
        if rng.lower() not in ('all',) and False:
            pass
    # the pills really change the number: a narrower range cannot be the all-time figure unless nothing differs
    allv = (cases.get('paper2') or {}).get('heroNum')
    if allv is not None and (cases.get('range-today') or {}).get('heroNum') == allv and exp_book:
        fails.append('range-today: TODAY shows the all-time figure - the pill is not driving the number')
    # the warning chips live in the status line directly under the hero numbers (LEDGER step 12; the hero chip row before it)
    r = cases.get('paper2') or {}
    if not (r.get('hero') or {}).get('warnInStatus'):
        fails.append('paper2: the warning chips are not inside the status line under the hero')

    # money colours follow the theme and carry a marker that needs no colour
    import re as _re
    for nm in ('paper2', 'other-open', 'other-on', 'range-1m'):
        r = cases.get(nm) or {}
        if r.get('moneyHex'):
            fails.append('%s: %d money cell(s) still use a fixed green / red hex instead of the theme colours' % (nm, r['moneyHex']))
        bad = [x for x in (r.get('moneyMarks') or []) if x and not _re.match(r'^[\u25b2\u25bc] [+-]\$', x) and x != '\u2014']
        if bad:
            fails.append('%s: money cells without an arrow and a sign: %s' % (nm, bad[:3]))
        bad = [x for x in (r.get('calMarks') or []) if not _re.match(r'^[+-]\$', x)]
        if bad:
            fails.append('%s: calendar money without a sign: %s' % (nm, bad[:3]))
        bad = [x for x in (r.get('grpMarks') or []) if not _re.search(r'[\u25b2\u25bc] [+-]\$', x)]
        if bad:
            fails.append('%s: group totals without an arrow and a sign: %s' % (nm, bad[:3]))
    # Max drawdown prints POSITIVE, the way REAL prints it ($1,234.56, no minus sign)
    for nm in ('paper2', 'range-1m', 'range-1w', 'other-on'):
        v = (cases.get(nm) or {}).get('maxDD')
        if v is not None and v.strip() == '--' and not (cases.get(nm) or {}).get('statTrades'):
            continue   # the shared strip prints -- when the range holds no counted trade (there is no drawdown to read)
        if v is None or not _re.match(r'^\$[0-9,]+(\.[0-9]{2})?$', v.strip()):
            fails.append('%s: Max drawdown reads %r, expected a positive dollar figure like REAL' % (nm, v))
    if not ((cases.get('paper2') or {}).get('moneyMarks')):
        fails.append('paper2: the colour check found no money cells to read')

    # LEDGER step 5 -- the shared chart: drawn, the last point is the big number, scrub writes the hero and restores it
    for nm in ('paper2', 'other-open', 'other-on', 'legs-off-p2', 'range-3m', 'range-ytd', 'range-1m', 'range-saved'):
        r = cases.get(nm) or {}
        c, hn = r.get('chart'), r.get('heroNum')
        if not c:
            if nm in ('range-1m', 'range-saved') and not (r.get('statTrades') or 0):
                continue
            fails.append('%s: the shared equity chart did not draw' % nm)
            continue
        if c.get('last') is None or hn is None or abs(c['last'] - hn) > 1.0:
            fails.append('%s: the last chart point %s is not the big number %s' % (nm, c.get('last'), hn))
        if (c.get('h') or 0) < 200:
            fails.append('%s: the chart is %spx tall, expected at least 200 on a laptop' % (nm, c.get('h')))
    r = cases.get('paper2') or {}
    c = r.get('chart') or {}
    if (c.get('dates') or 0) < 2 or (c.get('ticks') or 0) < 2:
        fails.append('paper2: the chart shows %s dates and %s price labels, expected at least 2 of each'
                     % (c.get('dates'), c.get('ticks')))
    if c.get('legend') != len(book_w) or (c.get('faint') or 0) < 1:
        fails.append('paper2: the chart legend has %s switches and %s faint lines, expected one per shown book leg (%d)'
                     % (c.get('legend'), c.get('faint'), len(book_w)))
    sc = r.get('scrub') or {}
    if sc.get('err') or not sc:
        fails.append('paper2: the scrub probe failed: %s' % sc.get('err'))
    else:
        if not sc.get('mBack') or not sc.get('tBack'):
            fails.append('paper2: the hero was not restored after a scrub (mouse %s, finger %s)' % (sc.get('mBack'), sc.get('tBack')))
        if sc.get('m1') == sc.get('b0') or 'that day' not in (sc.get('m1r') or ''):
            fails.append('paper2: a mouse hover did not write the hero (%r, line %r)' % (sc.get('m1'), sc.get('m1r')))
        if sc.get('t1') != '$0.00' or sc.get('t2') == sc.get('b0'):
            fails.append('paper2: a finger drag did not write the hero (start %r, later %r, big number %r)'
                         % (sc.get('t1'), sc.get('t2'), sc.get('b0')))

    # ------------------------------------------------------------------------------------------------------------
    # LEDGER steps 6, 7 and 10 -- recomputed from the fixture: the counted trades are the book legs at their weights,
    # closed, with a close day in the range, walked in the order they closed (close day, then exit time)
    import math as _math

    def _rows_for(rng, exclude=()):
        c = _cut(rng)
        rows = [t for t in closed if _w(t) and t.get('leg') not in exclude and (not c or _close(t) >= c)]
        rows.sort(key=lambda t: (_close(t), t.get('exitTime') or t.get('entryTime') or 0))
        return rows

    def _stats_of(rows):
        if not rows:
            return None
        net = peak = cur = dd = gw = gl = 0.0
        wins = losses = 0
        by_day = {}
        for t in rows:
            v = (t.get('pnl_usd') or 0) * _w(t)
            net += v
            cur += v
            peak = max(peak, cur)
            dd = max(dd, peak - cur)
            if v > 0:
                wins += 1
                gw += v
            elif v < 0:
                losses += 1
                gl -= v
            by_day[_close(t)] = by_day.get(_close(t), 0.0) + v
        dv = list(by_day.values())
        return {'n': len(rows), 'wins': wins, 'losses': losses, 'net': net, 'gw': gw, 'gl': gl, 'dd': dd,
                'wr': (wins / float(wins + losses)) if (wins + losses) else None,
                'pf': None if (not gw and not gl) else (gw / gl if gl > 0 else float('inf')),
                'avg': net / len(rows), 'avgw': (gw / wins) if wins else None, 'avgl': (gl / losses) if losses else None,
                'best': max(dv), 'worst': min(dv), 'green': sum(1 for v in dv if v > 0), 'days': len(dv)}

    def _tiles_of(e):
        if e is None:
            return {'winrate': '--', 'pf': '--', 'maxdd': '--', 'trades': '0'}
        pf = '--' if e['pf'] is None else ('no losses' if e['pf'] == float('inf') else '%.2f' % e['pf'])
        wr = '--' if e['wr'] is None else '%d%%' % int(_math.floor(e['wr'] * 100 + 0.5))
        return {'winrate': wr, 'pf': pf, 'maxdd': '${:,.2f}'.format(e['dd']), 'trades': str(e['n'])}

    def _money_in(txt):
        m = _re.search(r'(-?)\$([0-9,]+(?:\.[0-9]+)?)', (txt or '').replace('+', ''))
        return None if not m else (-1 if m.group(1) else 1) * float(m.group(2).replace(',', ''))

    def _sum_net(rows):
        return sum((t.get('pnl_usd') or 0) * _w(t) for t in rows)

    # -- STEP 6: the four shared tiles, equal to the recomputation, drawdown positive; the old ten-cell grid is gone
    STAT_CASES = {'paper2': ('ALL', ()), 'other-open': ('ALL', ()), 'other-on': ('ALL', ()), 'fwd-closed': ('ALL', ()),
                  'warn-stale-bridge': ('ALL', ()), 'book-fallback': ('ALL', ()), 'stats-open': ('ALL', ()),
                  'cal-closed': ('ALL', ()), 'cal-aug': ('ALL', ()), 'retired-open': ('ALL', ()), 'phone375': ('ALL', ()),
                  'legs-off-p2': ('ALL', ('ORB',)), 'range-today': ('TODAY', ()), 'range-1w': ('1W', ()),
                  'range-1m': ('1M', ()), 'range-3m': ('3M', ()), 'range-ytd': ('YTD', ()), 'range-saved': ('1M', ())}
    for nm, (rng, excl) in STAT_CASES.items():
        r = cases.get(nm) or {}
        exp = _stats_of(_rows_for(rng, excl))
        want = _tiles_of(exp)
        tiles = r.get('statTiles') or []
        if [x.get('k') for x in tiles] != ['winrate', 'pf', 'maxdd', 'trades']:
            fails.append('%s: the stats strip reads %s, expected the four tiles win rate, profit factor, max drawdown, '
                         'trades in that order' % (nm, [x.get('k') for x in tiles]))
            continue
        got = dict((x['k'], x['v']) for x in tiles)
        for k in ('winrate', 'pf', 'trades'):
            if got[k] != want[k]:
                fails.append('%s: the %s tile reads %r, the fixture says %r' % (nm, k, got[k], want[k]))
        dd = got['maxdd'] or ''
        if exp is None:
            if dd != '--':
                fails.append('%s: max drawdown reads %r for a range with no counted trade (expected --)' % (nm, dd))
        elif not _re.match(r'^\$[0-9,]+\.[0-9]{2}$', dd) or abs(_money_in(dd) - exp['dd']) > 0.006:
            fails.append('%s: max drawdown reads %r, expected the POSITIVE amount %s from the fixture' % (nm, dd, want['maxdd']))
        if r.get('oldStatCells'):
            fails.append('%s: the old ten-cell stats grid is still on the board' % nm)
        if exp is not None:
            sub = dict((x['k'], x.get('sub') or '') for x in tiles)
            if '%d W' % exp['wins'] not in sub['winrate'] or '%d L' % exp['losses'] not in sub['winrate']:
                fails.append('%s: the win rate tile says %r, expected %d W and %d L' % (nm, sub['winrate'], exp['wins'], exp['losses']))
            if sub['trades'] != 'over %d day%s' % (exp['days'], '' if exp['days'] == 1 else 's'):
                fails.append('%s: the trades tile says %r, expected %d trading day(s)' % (nm, sub['trades'], exp['days']))

    I = (cases.get('paper2') or {}).get('int') or {}
    if I.get('err') or not I:
        fails.append('paper2: the in-page interaction probe did not run: %s' % (I.get('err') or 'no readout'))
        I = {}
    exp_all = _stats_of(_rows_for('ALL'))
    mo = I.get('more') or {}
    if mo.get('start') != 'false' or mo.get('open') != 'true':
        fails.append('paper2: More stats should start closed and open on a tap (start %r, after the tap %r)' % (mo.get('start'), mo.get('open')))
    if mo.get('groups') != ['Returns', 'Risk', 'Mix', 'Strategy vs control']:
        fails.append('paper2: More stats opened with groups %r, not Returns, Risk, Mix, Strategy vs control' % mo.get('groups'))
    if mo.get('stored') != '1' or mo.get('closed') != 'false' or mo.get('storedClosed') != '0':
        fails.append('paper2: the More stats choice is not remembered per browser (stored %r / %r, aria %r)'
                     % (mo.get('stored'), mo.get('storedClosed'), mo.get('closed')))
    rowsd = dict((a, b) for a, b in (mo.get('rows') or []))
    if exp_all:
        # every value the old ten-cell grid showed lives in the fold now
        for label, want_v in (('Net P&L', exp_all['net']), ('Average trade', exp_all['avg']), ('Average win', exp_all['avgw']),
                              ('Average loss', exp_all['avgl']), ('Best day', exp_all['best']), ('Worst day', exp_all['worst']),
                              ('Max drawdown', exp_all['dd'])):
            got_v = _money_in(rowsd.get(label))
            if got_v is None or abs(got_v - want_v) > 0.006:
                fails.append('paper2: More stats %r reads %r, the fixture says %.2f' % (label, rowsd.get(label), want_v))
        if rowsd.get('Green days') != '%d of %d' % (exp_all['green'], exp_all['days']):
            fails.append('paper2: More stats Green days reads %r, expected %d of %d' % (rowsd.get('Green days'), exp_all['green'], exp_all['days']))
    vs_txt = mo.get('vsTxt') or ''
    if (mo.get('vsRows') or 0) < 3 or ' vs ' not in vs_txt or 'backfilled' not in vs_txt or not mo.get('vsCrown'):
        fails.append('paper2: "Strategy vs control" should list each traded strategy with its matched control, the dollar gap, the '
                     'crowns and the forward / backfilled split (rows %s, crown %s)' % (mo.get('vsRows'), mo.get('vsCrown')))
    if not mo.get('vsSubs') or not any('gate ' in s and 'refused' in s for s in mo.get('vsSubs')):
        fails.append('paper2: "Strategy vs control" lost the gate line of the gated strategies (%r)' % (mo.get('vsSubs') or [])[:2])
    if (cases.get('stats-open') or {}).get('moreFold') != 'true':
        fails.append('stats-open: a stored open More stats fold did not open on load')

    # -- STEP 7: the calendar. Month totals and counts equal the fixture; a day tap selects the rows that CLOSED that day
    allrows = _rows_for('ALL')
    months = sorted(set(_close(t)[:7] for t in allrows))

    def _month_info(mo_, rows=None):
        rows = [t for t in (allrows if rows is None else rows) if _close(t)[:7] == mo_]
        cav = set(_close(t) for t in rows if t.get('leg') == 'ORB' or t.get('roll_artifact')
                  or 'lookahead-engine' in (t.get('flags') or []))
        return {'n': len(rows), 'net': _sum_net(rows), 'days': sorted(set(_close(t) for t in rows)), 'cav': len(cav)}

    def _cal_sum(txt):
        m = _re.search(r'(\d+) trades?', txt or '')
        return _money_in(txt), (int(m.group(1)) if m else 0)

    def _cal_ok(tag, cal, mo_, rows=None):
        if not cal:
            fails.append('%s: the calendar is missing' % tag)
            return
        e = _month_info(mo_, rows)
        if cal.get('month') != mo_:
            fails.append('%s: the calendar shows %r, expected %s' % (tag, cal.get('month'), mo_))
            return
        net_g, n_g = _cal_sum(cal.get('sum'))
        if net_g is None or abs(net_g - e['net']) > 0.006 or n_g != e['n']:
            fails.append('%s: the month header reads %r, the fixture says %+.2f over %d trade(s)' % (tag, cal.get('sum'), e['net'], e['n']))
        if sorted(cal.get('days') or []) != e['days'] or sum(cal.get('dayN') or []) != e['n']:
            fails.append('%s: the calendar days %s (%s trades) are not the fixture days %s (%d trades)'
                         % (tag, cal.get('days'), sum(cal.get('dayN') or []), e['days'], e['n']))
        if (cal.get('cells') or 0) % 8 or not cal.get('cells'):
            fails.append('%s: the calendar grid has %s cells (rows of 7 days + a WEEK cell expected)' % (tag, cal.get('cells')))
        if cal.get('cav') != e['cav']:
            fails.append('%s: %s caveat day(s) hatched, expected %d (days with a roll-splice or ORB look-ahead trade)' % (tag, cal.get('cav'), e['cav']))

    def _tap_ok(tag, tap):
        if not tap or not tap.get('sel') or tap.get('sel') != tap.get('forDay') or tap.get('sel') != tap.get('cellN') \
                or set(tap.get('selDays') or []) != set([tap.get('day')]):
            fails.append('%s: tapping a calendar day selected %r - expected exactly the %s row(s) that closed on %s' % (tag, tap, (tap or {}).get('cellN'), (tap or {}).get('day')))

    if len(months) < 2:
        fails.append('the fixture should span two months for the calendar probe (got %s)' % months)
    else:
        _cal_ok('paper2 calendar', I.get('cal0'), months[-1])
        _tap_ok('paper2 calendar (newest month)', I.get('tap0'))
        _cal_ok('paper2 calendar (earlier month)', I.get('calPrev'), months[-2])
        _tap_ok('paper2 calendar (earlier month)', I.get('tap1'))
        _cal_ok('paper2 calendar (back to the newest month)', I.get('calBack'), months[-1])
        cp = I.get('calPrev') or {}
        if not cp.get('prevDis') or cp.get('nextDis'):
            fails.append('paper2: the month arrows should stop at the first month with trades (earlier disabled %r, later disabled %r)'
                         % (cp.get('prevDis'), cp.get('nextDis')))
        if I.get('calStored') != months[-2]:
            fails.append('paper2: the calendar month is not remembered per browser (stored %r, expected %s)' % (I.get('calStored'), months[-2]))
        _cal_ok('cal-aug (a remembered month)', (cases.get('cal-aug') or {}).get('cal'), months[-2])
    cf = I.get('calFold') or {}
    if (cases.get('paper2') or {}).get('calFold') != 'true' or cf.get('closed') != 'false' or not cf.get('hidden') \
            or cf.get('stored') != '0' or cf.get('reopen') != 'true':
        fails.append('paper2: the calendar fold should start open on a laptop, close (panel hidden, choice stored) and reopen: %r' % cf)
    r = cases.get('cal-closed') or {}
    if r.get('calFold') != 'false' or r.get('calPanelHidden') is not True:
        fails.append('cal-closed: a stored closed calendar fold opened anyway (aria %r, panel hidden %r)' % (r.get('calFold'), r.get('calPanelHidden')))
    # the caveat hatch exists on a day with an ORB look-ahead trade (the same mark the trade rows carry)
    if not (I.get('calPrev') or {}).get('cav'):
        fails.append('paper2: no calendar day is hatched amber although ORB look-ahead engine trades closed in the range')

    # -- STEP 10: the shared strategy list - groups in order, the BOOK total is the big number, one switch moves everything
    r = cases.get('paper2') or {}
    gs = r.get('groups') or []
    if [g.get('key') for g in gs] != ['book', 'fwd', 'other', 'retired']:
        fails.append('paper2: the strategy list groups read %s, expected BOOK, Forward tests & controls, Other / shadow, Retired'
                     % [g.get('key') for g in gs])
    else:
        byk = dict((g['key'], g) for g in gs)
        want_titles = {'book': 'BOOK #463', 'fwd': 'Forward tests & controls', 'other': 'Other / shadow - not counted', 'retired': 'Retired'}
        for k, ttl in want_titles.items():
            if not (byk[k].get('txt') or '').startswith(ttl):
                fails.append('paper2: the %s group is titled %r, expected %r' % (k, byk[k].get('txt'), ttl))
        if byk['book'].get('fold') or byk['book'].get('rows') != len(book_w):
            fails.append('paper2: the BOOK group should be open with one row per book leg (%d), got %s' % (len(book_w), byk['book']))
        if not byk['fwd'].get('fold') or byk['fwd'].get('open') != 'true' or not byk['fwd'].get('rows'):
            fails.append('paper2: the Forward tests & controls group should be a fold, open by default: %s' % byk['fwd'])
        for k in ('other', 'retired'):
            if not byk[k].get('fold') or byk[k].get('open') != 'false' or byk[k].get('rows'):
                fails.append('paper2: the %s group should be a fold, closed by default, drawing no rows: %s' % (k, byk[k]))
        retired_defs = sorted(k for k, d in defs.items() if d['archived'])
        ret_legs = ((cases.get('paper2') or {}).get('retHd') or {}).get('legs')
        if not retired_defs or ret_legs != len(retired_defs):
            fails.append('paper2: the Retired group counts %s strategies, the source declares %d archived' % (ret_legs, len(retired_defs)))
    rr = cases.get('retired-open') or {}
    rk = [x['key'] for x in (rr.get('listRowInfo') or []) if x.get('group') == 'retired']
    if sorted(rk) != sorted(k for k, d in defs.items() if d['archived']):
        fails.append('retired-open: the open Retired group lists %s, expected the archived strategies %s'
                     % (rk, sorted(k for k, d in defs.items() if d['archived'])))
    for nm in ('paper2', 'other-open', 'retired-open', 'legs-off-p2', 'phone375'):
        for row in (cases.get(nm) or {}).get('listRowInfo') or []:
            nm_txt = (row.get('name') or '').replace('\U0001F451', '').strip()
            if not _re.search(r'^[A-Z][A-Za-z-]*( [A-Z][A-Za-z-]*)* #\d+', nm_txt):
                fails.append('%s: the row %r is not named family + run number (%r)' % (nm, row.get('key'), nm_txt))
            if not row.get('dot'):
                fails.append('%s: the row %r has no live-state dot' % (nm, row.get('key')))
            if row.get('sw') not in ('true', 'false'):
                fails.append('%s: the row %r has no switch' % (nm, row.get('key')))
            if row.get('group') == 'book' and (row.get('sw') == 'false') != bool(row.get('off')):
                fails.append('%s: the BOOK row %r is faded %r with its switch %r' % (nm, row.get('key'), row.get('off'), row.get('sw')))
    r = cases.get('other-open') or {}
    if not any(x.get('name', '').startswith('ORB #257') for x in (r.get('listRowInfo') or [])):
        fails.append('other-open: the unlisted ORB 257 strategy is not named the family-name way (ORB #257): %s'
                     % [x.get('name') for x in (r.get('listRowInfo') or []) if x.get('group') == 'other'])
    r = cases.get('legs-off-p2') or {}
    offs = sorted(x['key'] for x in (r.get('listRowInfo') or []) if x.get('group') == 'book' and x.get('sw') == 'false')
    if offs != ['ORB']:
        fails.append('legs-off-p2: the switched-off BOOK legs read %s, expected [ORB]' % offs)
    # LEDGER step 12: the strategy list is the frame's right-hand panel, level with the top block and scrolling inside it - no longer sticky
    _ss = (cases.get('paper2') or {}).get('sideSticky')
    if not _ss or 'sticky' in _ss or 'fixed' in _ss:
        fails.append('paper2: the strategy list panel is sticky or missing on a laptop (%r) - since LEDGER step 12 it sits level with the top block' % _ss)
    # one flip, everything moves: hero, chart end, tiles, BOOK total, calendar, list and trade list (recomputed, then restored)
    f0, f1, f2 = I.get('flip0') or {}, I.get('flip1') or {}, I.get('flip2') or {}
    orb = [t for t in allrows if t.get('leg') == 'ORB']
    orb_net = _sum_net(orb)
    if not f0 or not f1 or not f2 or not orb or abs(orb_net) < 0.01:
        fails.append('paper2: the switch probe did not run (the fixture needs ORB trades with money in the range)')
    else:
        e1 = _stats_of(_rows_for('ALL', ('ORB',)))
        if abs(f1['hero'] - (f0['hero'] - orb_net)) > 0.01:
            fails.append('paper2: switching ORB off moved the big number %.2f to %.2f, expected %.2f' % (f0['hero'], f1['hero'], f0['hero'] - orb_net))
        if abs((f1.get('chartLast') or 0) - f1['hero']) > 0.01 or abs((f1.get('bookNet') or 0) - f1['hero']) > 0.01:
            fails.append('paper2: after the flip the chart end %s / BOOK group total %s are not the big number %s' % (f1.get('chartLast'), f1.get('bookNet'), f1['hero']))
        if f1.get('tiles') != _tiles_of(e1):
            fails.append('paper2: after the flip the tiles read %s, the fixture says %s' % (f1.get('tiles'), _tiles_of(e1)))
        if f1.get('bookN') != f0.get('bookN') - len(orb) or f1.get('tradeRows') != f0.get('tradeRows') - len(orb):
            fails.append('paper2: after the flip the list counts %s trades and the trade list %s rows, expected %d and %d fewer by %d'
                         % (f1.get('bookN'), f1.get('tradeRows'), f0.get('bookN') - len(orb), f0.get('tradeRows') - len(orb), len(orb)))
        mo_ = months[-2] if len(months) > 1 else None
        if mo_ and f0.get('cal', {}).get('month') == mo_:
            _cal_ok('paper2 calendar before the flip', f0.get('cal'), mo_)
            _cal_ok('paper2 calendar after the flip', f1.get('cal'), mo_, _rows_for('ALL', ('ORB',)))
        if 'ORB=true' not in (f0.get('sw') or '') or 'ORB=false' not in (f1.get('sw') or ''):
            fails.append('paper2: the ORB switch did not change state (%r then %r)' % ('ORB=true' in (f0.get('sw') or ''), 'ORB=false' in (f1.get('sw') or '')))
        for k in ('hero', 'chartLast', 'tiles', 'tradeRows', 'sw', 'bookN'):
            if f2.get(k) != f0.get(k) and not (isinstance(f0.get(k), float) and abs(f2.get(k) - f0.get(k)) < 0.01):
                fails.append('paper2: flipping ORB back did not restore %s (%r then %r)' % (k, f0.get(k), f2.get(k)))
        rt = I.get('rowTap') or {}
        if abs((rt.get('hero') or 0) - f1['hero']) > 0.01 or 'ORB=false' not in (rt.get('sw') or ''):
            fails.append('paper2: tapping the ORB row did not do what its switch does (big number %s, expected %s)' % (rt.get('hero'), f1['hero']))
        # a strategy outside the book: its switch lists its trades and never moves a counted figure
        o1, o2 = I.get('oth1') or {}, I.get('oth2') or {}
        nh = [t for t in fixture['trades'] if t.get('leg') == 'NOISE_H' and t.get('open') is not True]
        if not o1 or not nh:
            fails.append('paper2: the not-counted switch probe did not run')
        else:
            same = ('hero', 'chartLast', 'tiles', 'bookNet', 'bookN')
            if any(o1.get(k) != f0.get(k) for k in same):
                fails.append('paper2: a not-counted strategy switch moved a counted figure: %s' % [(k, f0.get(k), o1.get(k)) for k in same if o1.get(k) != f0.get(k)])
            if o1.get('tradeRows') != f0.get('tradeRows') + len(nh) or 'NOISE_H=true' not in (o1.get('sw') or ''):
                fails.append('paper2: switching NOISE #225 tree HYBRID on listed %s trade rows, expected %d more than %s'
                             % (o1.get('tradeRows'), len(nh), f0.get('tradeRows')))
            if o2.get('tradeRows') != f0.get('tradeRows') or 'NOISE_H=false' not in (o2.get('sw') or ''):
                fails.append('paper2: switching the not-counted strategy off again did not restore the trade list')

    # -- PHONE 375 x 812: trade list within one screen, the list below it, one line a row, folds closed, no sideways scroll
    r = cases.get('phone375') or {}
    g = r.get('geo') or {}
    if g.get('vw') != 375:
        fails.append('phone375: the phone frame is %s px wide, not 375' % g.get('vw'))
    if (g.get('scrollW') or 0) > (g.get('clientW') or 0) + 1:
        fails.append('phone375: the page scrolls sideways (scrollWidth %s > clientWidth %s)' % (g.get('scrollW'), g.get('clientW')))
    if not g.get('tradesTop') or g.get('boardTop') is None:
        fails.append('phone375: could not locate the trade list or the board top (%s)' % g)
    else:
        dist = g['tradesTop'] - g['boardTop']
        if dist > (g.get('vh') or 0):
            fails.append('phone375: the trade list starts %d px below the board top, more than one screen (%s px) - LEDGER mistake #12'
                         % (dist, g.get('vh')))
        # LEDGER step 11 turned the phone order round: the More stats and calendar folds and the strategy list fold (one line) now come BEFORE the trade list,
        # in the fixed page order (the full order is judged for every case further down); the strategy rows are measured with the list fold open
        if not g.get('listTop') or g['listTop'] >= g['tradesTop']:
            fails.append('phone375: the strategy list fold (top %s) is not above the trade list (top %s) - the fixed page order' % (g.get('listTop'), g['tradesTop']))
        for key in ('moreTop', 'calTop'):
            if not g.get(key) or g[key] >= g['tradesTop']:
                fails.append('phone375: the %s fold sits below the trade list on a phone (%s >= %s) - the fixed page order' % (key[:-3], g.get(key), g['tradesTop']))
    rh = [x.get('h') or 0 for x in ((cases.get('phone375-list-open') or {}).get('listRowInfo') or [])]
    if not rh or max(rh) > 48:
        fails.append('phone375: strategy rows are up to %s px tall - one line per row expected (48 or less)' % (max(rh) if rh else None))
    tt = [x.get('top') for x in (r.get('statTiles') or [])]
    if len(tt) != 4 or not (tt[0] == tt[1] and tt[2] == tt[3] and tt[2] > tt[0]):
        fails.append('phone375: the four stat tiles should sit two by two (tops %s)' % tt)
    if r.get('calFold') != 'false' or r.get('moreFold') != 'false':
        fails.append('phone375: the calendar / More stats folds should start closed on a phone (%r / %r)' % (r.get('calFold'), r.get('moreFold')))
    c = r.get('chart') or {}
    if (c.get('h') or 0) < 150:
        fails.append('phone375: the chart is %s px tall on a phone, expected at least 150' % c.get('h'))
    if r.get('pills') != ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']:
        fails.append('phone375: the pill row reads %s' % r.get('pills'))

    # -- ?oldboards=1 no longer changes anything: the flag page draws the NEW board - the shared tiles, the shared strategy list with the same
    #    book rows as the plain page, the one shared trade list frame and no trade panel until a row is clicked
    r = cases.get('flag-paper2') or {}
    if len(r.get('statTiles') or []) != 4 or not r.get('groups') or r.get('oldStatCells'):
        fails.append('flag-paper2: ?oldboards=1 must draw the shared stat tiles and the shared strategy list (tiles %s, groups %s, old cells %s)'
                     % (len(r.get('statTiles') or []), len(r.get('groups') or []), r.get('oldStatCells')))
    if not r.get('bookRowKeys') or sorted(r.get('bookRowKeys') or []) != sorted((cases.get('paper2') or {}).get('bookRowKeys') or []):
        fails.append('flag-paper2: the strategy list behind ?oldboards=1 lists %s, the plain page lists %s'
                     % (r.get('bookRowKeys'), (cases.get('paper2') or {}).get('bookRowKeys')))
    fp_ = r.get('flagPanel') or {}
    if fp_.get('nodes') or fp_.get('id') is not None or fp_.get('frames') != 1:
        fails.append('flag-paper2: ?oldboards=1 must draw the one shared trade list frame and no trade panel until a row is clicked (%s)' % fp_)

    # warnings reach the status line under the hero while their card is closed
    r = cases.get('warn-stale-bridge') or {}
    if not any('heartbeat stale' in w for w in (r.get('warns') or [])) or r.get('ntCardOpen'):
        fails.append('warn-stale-bridge: a stale NinjaTrader heartbeat is not a chip on the status line '
                     '(warns %r, card open %r)' % (r.get('warns'), r.get('ntCardOpen')))
    r = cases.get('paper2') or {}
    if not any('10s capture low' in w for w in (r.get('warns') or [])):
        fails.append('paper2: the low 10s capture is not a chip on the status line (warns %r)' % r.get('warns'))
    # before the first nightly bundle exists the board says so, and still renders
    r = cases.get('no-bundle') or {}
    if not any('newest 500 only' in w for w in (r.get('warns') or [])):
        fails.append('no-bundle: the missing history bundle is not a chip on the status line (warns %r)' % r.get('warns'))

    # the top-bar NT GATE chip: snapshot age first, PARTIAL shows a stale age too
    g = (cases.get('gate-old-snapshot') or {}).get('gateChip') or ''
    if 'NT GATE ? (status' not in g or 'old)' not in g:
        fails.append('gate-old-snapshot: stale snapshot not flagged on the chip: %r' % g)
    g = (cases.get('gate-partial-stale') or {}).get('gateChip') or ''
    if 'PARTIAL + STALE 6d' not in g:
        fails.append('gate-partial-stale: PARTIAL chip hides the stale model age: %r' % g)
    g = (cases.get('gate-fresh-green') or {}).get('gateChip') or ''
    if not g.endswith('NT GATE') or '?' in g:
        fails.append('gate-fresh-green: a fresh healthy snapshot should read plain NT GATE: %r' % g)

    # ------------------------------------------------------------------------------------------------------------
    # LEDGER step 8 (owner plan 2026-10-05; MANAGER 2026-10-06): the NT8 trades list is the SHARED FRAME (ledgerTradeListHtml).
    # Every expectation below is recomputed from the FIXTURE - the rows the board lists, the New York day a trade closed, the money
    # a row shows, the hold in seconds - and never read off the page. (The cases named 'paper*' all draw the merged PAPER tab: the
    # app routes 'paper' to 'paper2'.)
    def _disp(t):
        # the money a row shows: a book leg at its weight, any other strategy as it is
        return (t.get('pnl_usd') or 0) * (_w(t) or 1)

    def _capped(rows, limit=200):
        # the list stops after about 200 rows, at the END of a day (a day net is the whole day): every row that closed on or
        # after the close day of the 200th newest one
        if len(rows) <= limit:
            return rows
        stop = sorted((_close(t) for t in rows), reverse=True)[limit - 1]
        return [t for t in rows if _close(t) >= stop]

    def _listed(rng='ALL', off=(), other_on=(), trades=None):
        c = _cut(rng)
        rows = []
        for t in (fixture['trades'] if trades is None else trades):
            leg = t.get('leg')
            if not ((_w(t) and leg not in off) or leg in other_on):
                continue
            if t.get('open') is True or not c or _close(t) >= c:
                rows.append(t)
        return rows

    def _side_of(t):
        return {1: 'LONG', -1: 'SHORT'}.get(t.get('side'), '')

    def _fam_of(leg):
        up = str(leg or '').upper()
        for pre, fam in (('ORB', 'ORB'), ('ENGUQ', 'ENGU-Q'), ('NOISE', 'NOISE'), ('TTM', 'TTM'), ('ETFBOOK', 'DIP'), ('DIP_', 'DIP')):
            if up.startswith(pre):
                return fam
        return up

    def _dur_text(secs):
        # the shared durStr: seconds under a minute, then minutes (and seconds), then hours (and minutes)
        if secs < 60:
            return '%ds' % round(secs)
        mm = int(secs // 60)
        ss = int(round(secs % 60))
        if mm < 60:
            return '%dm' % mm + (' %ds' % ss if ss else '')
        return '%dh' % (mm // 60) + (' %dm' % (mm % 60) if mm % 60 else '')

    def _num_of(txt):
        m = _re.search(r'([+-])\$([0-9,]+\.[0-9]{2})', txt or '')
        return None if not m else (1 if m.group(1) == '+' else -1) * float(m.group(2).replace(',', ''))

    FRAME_CASES = {
        'base': {}, 'cols-all': {}, 'paper2': {}, 'paper2-cols-all': {}, 'other-open': {}, 'fwd-closed': {}, 'book-fallback': {},
        'warn-stale-bridge': {}, 'stats-open': {}, 'cal-closed': {}, 'cal-aug': {}, 'phone375': {}, 'phone375-table': {},
        'laptop-list': {}, 'w600': {}, 'w760': {}, 'w1099': {}, 'w1100': {},
        'other-on': {'other_on': ('ORB_257', 'NOISE_H')}, 'retired-open': {'other_on': ('ENGUQ',)}, 'legs-off-p2': {'off': ('ORB',)},
        'range-today': {'rng': 'TODAY'}, 'range-1w': {'rng': '1W'}, 'range-1m': {'rng': '1M'}, 'range-3m': {'rng': '3M'},
        'range-ytd': {'rng': 'YTD'}, 'range-saved': {'rng': '1M'},
    }
    LIST_CASES = ('laptop-list', 'phone375', 'w600')       # the cases that open on the LIST (a phone opens on LIST until a view is chosen)

    def _check_frame(nm, tl, spec):
        if not tl.get('frame'):
            fails.append('%s: the NT8 trades list is not drawn by the shared frame (no [data-lglist-frame="nt8"])' % nm)
            return
        if tl.get('frames') != 1:
            fails.append('%s: %s shared trade list frames on the NT8 board, expected exactly one' % (nm, tl.get('frames')))
        rows = _listed(spec.get('rng', 'ALL'), spec.get('off', ()), spec.get('other_on', ()), spec.get('trades'))
        closed_all = [t for t in rows if t.get('open') is not True]
        exp_closed = _capped(closed_all) if spec.get('cap') else closed_all
        if spec.get('floor'):
            exp_closed = [t for t in closed_all if _close(t) >= spec['floor']]
        exp_open = [t for t in rows if t.get('open') is True]
        # the toolbar: the five shared chips first (ALL on), then one chip per strategy family; LIST | TABLE with one half pressed; the search box
        chips = tl.get('chips') or []
        if chips[:5] != ['ALL', 'LONG', 'SHORT', 'WINS', 'LOSSES']:
            fails.append('%s: the chips read %s, expected ALL LONG SHORT WINS LOSSES first' % (nm, chips))
        fams = sorted(set(_fam_of(t.get('leg')) for t in rows))
        if sorted(chips[5:]) != fams:
            fails.append('%s: the strategy-family chips read %s, the listed rows hold the families %s' % (nm, chips[5:], fams))
        if tl.get('chipOn') != ['ALL']:
            fails.append('%s: the active chip reads %s, expected ALL' % (nm, tl.get('chipOn')))
        views = tl.get('views') or []
        if sorted(v.rstrip('*') for v in views) != ['list', 'table'] or sum(1 for v in views if v.endswith('*')) != 1:
            fails.append('%s: the LIST | TABLE toggle reads %s' % (nm, views))
        # the money of a row (an open trade's unrealised mark included) fits its own cell: it never runs into the next column
        over = [x['id'] for x in (tl.get('rows') or []) if x.get('pnlOver')]
        if over:
            fails.append('%s: the money overflows its cell on %d row(s) and runs into the next column: %s' % (nm, len(over), over[:3]))
        # one tick box on every row, visible at every width (a phone included), and one tick for every row shown
        n_dom = len(tl.get('rows') or [])
        if tl.get('tickN') != n_dom or tl.get('tickVis') != n_dom:
            fails.append('%s: %s tick boxes and %s visible for %d rows - every row needs a visible one' % (nm, tl.get('tickN'), tl.get('tickVis'), n_dom))
        if tl.get('tickAll') != 1 or tl.get('tickAllVis') != 1:
            fails.append('%s: the tick for every row shown is missing or hidden (%s drawn, %s visible)' % (nm, tl.get('tickAll'), tl.get('tickAllVis')))
        want_mode = spec.get('mode') or ('list' if nm in LIST_CASES else 'table')
        if tl.get('mode') != want_mode or (want_mode + '*') not in views:
            fails.append('%s: the list opened in %r, expected %r (a phone opens on LIST, a laptop on TABLE)' % (nm, tl.get('mode'), want_mode))
        if tl.get('search') != 'nt8-search':
            fails.append('%s: the search box is %r, expected nt8-search' % (nm, tl.get('search')))
        m = _re.match(r'^(\d+) / (\d+) trades', tl.get('count') or '')
        if not m or int(m.group(1)) != len(exp_closed) or int(m.group(2)) != len(closed_all):
            fails.append('%s: the count reads %r, expected %d / %d trades' % (nm, tl.get('count'), len(exp_closed), len(closed_all)))
        if len(exp_closed) < len(closed_all) and ('showing the newest %d of %d' % (len(exp_closed), len(closed_all))) not in (tl.get('countLine') or ''):
            fails.append('%s: the count line does not say the list stops at the newest %d of %d: %r' % (nm, len(exp_closed), len(closed_all), tl.get('countLine')))
        # the days: newest CLOSE day first; each day net signed and equal to the sum of its rows (counted trades only)
        e_days = {}
        for t in exp_closed:
            e = e_days.setdefault(_close(t), {'net': 0.0, 'ids': set()})
            e['ids'].add(t['id'])
            if _w(t):
                e['net'] += _disp(t)
        days = tl.get('days') or []
        got = [x.get('day') for x in days]
        if got != sorted(e_days, reverse=True):
            fails.append('%s: the day headers read %s, expected the close days %s newest first' % (nm, got, sorted(e_days, reverse=True)))
        dom = tl.get('rows') or []
        by_day = {}
        for x in dom:
            if not x.get('open'):
                by_day.setdefault(x.get('day'), []).append(x)
        for x in days:
            e = e_days.get(x.get('day'))
            if not e:
                continue
            txt = (x.get('net') or '').strip()
            n = _num_of(txt)
            if n is None or not _re.match(r'^[+-]\$', txt):
                fails.append('%s: the day %s net reads %r - it needs a sign' % (nm, x.get('day'), txt))
                continue
            if abs(n - e['net']) > 0.006:
                fails.append('%s: the day %s net reads %r, the fixture says %+.2f' % (nm, x.get('day'), txt, e['net']))
            cls = 'lg-up' if n > 0 else ('lg-down' if n < 0 else 'lg-flat')
            if cls not in (x.get('cls') or ''):
                fails.append('%s: the day %s net %r is not coloured %s (%r)' % (nm, x.get('day'), txt, cls, x.get('cls')))
            shown = by_day.get(x.get('day'), [])
            s = sum(_num_of(y.get('pnl')) or 0 for y in shown if not y.get('unc'))
            if abs(s - n) > 0.006:
                fails.append('%s: the day %s net %s is not the sum %.2f of its counted rows' % (nm, x.get('day'), txt, s))
        for day, e in e_days.items():
            ids = set(y['id'] for y in by_day.get(day, []))
            if ids != e['ids']:
                fails.append('%s: the day %s lists %s, the fixture closes %s that day' % (nm, day, sorted(ids), sorted(e['ids'])))
        for t in exp_closed:
            y = next((z for z in dom if z['id'] == t['id']), None)
            if y is None:
                continue
            if y.get('unc') != (not _w(t)):
                fails.append('%s: the row %s is marked not-counted=%s, the strategy %s is %s' % (nm, t['id'], y.get('unc'), t.get('leg'), 'outside' if not _w(t) else 'in the book'))
            pn = _num_of(y.get('pnl'))
            if pn is None or abs(pn - round(_disp(t), 2)) > 0.006:
                fails.append('%s: the row %s shows %r, the fixture says %+.2f' % (nm, t['id'], y.get('pnl'), _disp(t)))
            if y.get('side') != (_side_of(t) or None):
                fails.append('%s: the row %s side reads %r, expected %r' % (nm, t['id'], y.get('side'), _side_of(t)))
        # a trade still open is in no day and no total (its mark is unrealised) and sits in its own block
        open_dom = [x for x in dom if x.get('open')]
        if sorted(x['id'] for x in open_dom) != sorted(t['id'] for t in exp_open):
            fails.append('%s: the open rows are %s, expected %s' % (nm, sorted(x['id'] for x in open_dom), sorted(t['id'] for t in exp_open)))
        for x in open_dom:
            if x.get('day'):
                fails.append('%s: the open trade %s sits under the day %s' % (nm, x['id'], x.get('day')))
        if exp_open:
            hd = (tl.get('openHd') or '').lower()
            if 'open now' not in hd or 'not counted' not in hd:
                fails.append('%s: the open trades block does not say OPEN NOW / not counted: %r' % (nm, tl.get('openHd')))
            if not any('unrealised' in (x.get('pnl') or '') for x in open_dom):
                fails.append('%s: the open trade money is not labelled unrealised' % nm)
        if '987' in ' '.join(x.get('net') or '' for x in days):
            fails.append('%s: the open trade mark leaked into a day net' % nm)
        if 'close day' not in (tl.get('note') or '').lower():
            fails.append('%s: the list does not say the day is the CLOSE day: %r' % (nm, tl.get('note')))
        # a newer / older row in the fixture than the list shows: rows come out newest close first inside a day
        if exp_closed:
            order = [x['id'] for x in dom if not x.get('open')]
            if len(order) != len(exp_closed):
                fails.append('%s: %d rows drawn, expected %d closed rows' % (nm, len(order), len(exp_closed)))
        # the hold time reads in minutes and hours (the runner writes epoch SECONDS), TABLE only
        if tl.get('mode') == 'table':
            for t in exp_closed:
                y = next((z for z in dom if z['id'] == t['id']), None)
                if y is None:
                    continue
                want = _dur_text((t.get('exitTime') or 0) - (t.get('entryTime') or 0))
                if y.get('hold') != want:
                    fails.append('%s: the row %s hold reads %r, expected %r from the fixture times' % (nm, t['id'], y.get('hold'), want))
        return rows

    cap_trades = _cap_trades(fixture)
    FRAME_CASES['cap'] = {'cap': True, 'trades': fixture['trades'] + cap_trades}
    for nm, spec in FRAME_CASES.items():
        r = cases.get(nm) or {}
        if r:
            _check_frame(nm, r.get('tl') or {}, spec)
    # the capped list: a board with 216 closed trades stops at the end of the day that holds its 200th row (never in the middle
    # of a day, so a day net stays the whole day); a calendar tap on an older day extends the list down to it, ticks that day's
    # rows and scrolls to its header
    ci = (cases.get('cap') or {}).get('capint') or {}
    cap_closed = [t for t in _listed('ALL', trades=fixture['trades'] + cap_trades) if t.get('open') is not True]
    if ci.get('err') or not ci or not cap_trades:
        fails.append('cap: the capped list probe did not run: %s' % (ci.get('err') or 'no readout'))
    else:
        day = ci.get('day')
        n_day = sum(1 for t in cap_closed if _close(t) == day)
        if ci.get('month') != min(_close(t)[:7] for t in cap_closed) or not n_day or ci.get('hadDay'):
            fails.append('cap: the calendar did not reach a day below the list (month %s, day %s, already listed %s)'
                         % (ci.get('month'), day, ci.get('hadDay')))
        if ci.get('cellN') != n_day or ci.get('sel') != n_day or set(ci.get('selDays') or []) != set([day]):
            fails.append('cap: tapping the older day %s should tick its %d row(s), got %s on %s' % (day, n_day, ci.get('sel'), ci.get('selDays')))
        if not ci.get('hasDay') or ci.get('scrolled') != [day]:
            fails.append('cap: tapping the older day %s should extend the list to it and scroll to its header (header %s, scrolled %s)'
                         % (day, ci.get('hasDay'), ci.get('scrolled')))
        if ('OPEN %d CHART' % n_day) not in (ci.get('openTxt') or ''):
            fails.append('cap: OPEN N CHARTS reads %r after a tap on a day of %d trades' % (ci.get('openTxt'), n_day))
        _check_frame('cap (after a tap on the older day %s)' % day, ci.get('tl') or {}, {'trades': fixture['trades'] + cap_trades, 'floor': day})

    # the strategy label of a strategy without a listed row: family + #run number, the same as the strategy list (never ORB 257)
    r = cases.get('other-on') or {}
    labs = [(x.get('leg') or '').replace('\U0001F451', '') for x in ((r.get('tl') or {}).get('rows') or [])]
    if not any(l.startswith('ORB #257') for l in labs) or any(l.startswith('ORB 257') for l in labs):
        fails.append('other-on: a strategy without a listed row must read ORB #257 in the trades list (family, a hash sign, the run number): %s' % sorted(set(labs)))
    if any(_re.match(r'^[A-Z][A-Za-z-]* \d{2,}\b', l) for l in labs):
        fails.append('other-on: a strategy label reads family + number without the hash sign: %s' % sorted(set(labs)))


    # the phone: five cells a row (LIST and TABLE), the list top within one screen of the board top, no sideways page
    for nm in ('phone375', 'phone375-table', 'w600'):
        r = cases.get(nm) or {}
        bad = [(x['id'], x.get('vis')) for x in ((r.get('tl') or {}).get('rows') or []) if x.get('vis') != 5]
        if bad or not (r.get('tl') or {}).get('rows'):
            fails.append('%s: a phone row must be five cells (time, strategy, side, net, chart); got %s' % (nm, bad[:3] or 'no rows'))
    r = cases.get('phone375') or {}
    g = r.get('tlGeo') or {}
    if g.get('frameTop') is None or g.get('boardTop') is None:
        fails.append('phone375: could not locate the trade list frame or the board top (%s)' % g)
    else:
        dist = g['frameTop'] - g['boardTop']
        if dist > g.get('vh', 0):
            fails.append('phone375: the trade list starts %d px under the board top, more than one screen (%s px)' % (dist, g.get('vh')))
        if dist > 797:
            fails.append('phone375: the trade list starts %d px under the board top; it was 797 before the shared frame - it must not grow' % dist)
    for nm in ('phone375', 'phone375-table', 'w600', 'w760', 'w1099', 'w1100', 'paper2', 'laptop-list'):
        g = (cases.get(nm) or {}).get('tlGeo') or {}
        if not g or (g.get('scrollW') or 0) > (g.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways (scrollWidth %s > clientWidth %s)' % (nm, g.get('scrollW'), g.get('clientW')))
    _ss = (cases.get('w1100') or {}).get('sideSticky')
    if not _ss or 'sticky' in _ss or 'fixed' in _ss:
        fails.append('w1100: the strategy list panel is sticky or missing at 1100 px (%r)' % _ss)
    # the PAGE never scrolls sideways, at any width, in either view: absolute (scrollWidth <= innerWidth, no tolerance) at a phone, just
    # past the phone cut, the middle of the stacked page, the first laptop widths and a normal laptop
    for w_px in WIDTHS:
        for view in WIDTH_VIEWS:
            nm = 'wid-%d-%s' % (w_px, view)
            r = cases.get(nm) or {}
            g = r.get('tlGeo') or {}
            if g.get('vw') != w_px:
                fails.append('%s: the probe frame is %s px wide, not %d' % (nm, g.get('vw'), w_px))
                continue
            if (g.get('scrollW') or 0) > w_px or (g.get('scrollW') or 0) > (g.get('clientW') or 0) + 1:
                fails.append('%s: the page scrolls sideways at %d px in the %s view (scrollWidth %s, clientWidth %s, innerWidth %s)'
                             % (nm, w_px, view, g.get('scrollW'), g.get('clientW'), g.get('vw')))
            _check_frame(nm, r.get('tl') or {}, {'mode': view})
            wr_ = (r.get('tl') or {}).get('wrap') or {}
            if w_px <= 600 and view == 'table' and (wr_.get('sw') or 0) > (wr_.get('cw') or 0) + 1:
                fails.append('%s: the phone TABLE scrolls sideways inside its own box (%s px of table in %s px) - five columns must fit'
                             % (nm, wr_.get('sw'), wr_.get('cw')))
            if w_px <= 600:
                bad = [(x['id'], x.get('vis')) for x in ((r.get('tl') or {}).get('rows') or []) if x.get('vis') != 5]
                if bad or not (r.get('tl') or {}).get('rows'):
                    fails.append('%s: a phone row must be five cells (time, strategy, side, net, chart); got %s' % (nm, bad[:3] or 'no rows'))

    # a board with no trades draws the frame with its empty message
    tl = (cases.get('empty') or {}).get('tl') or {}
    if not tl.get('frame') or 'NO PAPER TRADES YET' not in (tl.get('empty') or '') or tl.get('rows'):
        fails.append('empty: a board with no trades should draw the shared frame with the empty message (%s)' % {k: tl.get(k) for k in ('frame', 'empty')})

    # nothing may log a console.error or throw while any case draws and is driven
    for nm, r in cases.items():
        if r.get('errors') or r.get('uncaught'):
            fails.append('%s: the page logged console.error / threw: %s' % (nm, (r.get('errors') or r.get('uncaught'))[:2]))

    # the interactions, on the plain board and on the board with strategies outside the book switched on (one is a $0 trade)
    def _ids_of(rows):
        return [t['id'] for t in rows]

    for nm in ('paper2', 'other-on'):
        r = cases.get(nm) or {}
        I2 = r.get('tlint') or {}
        if I2.get('err') or not I2:
            fails.append('%s: the trade list interaction probe did not run: %s' % (nm, I2.get('err') or 'no readout'))
            continue
        spec = FRAME_CASES[nm]
        rows = _listed(spec.get('rng', 'ALL'), spec.get('off', ()), spec.get('other_on', ()))
        order = I2.get('allAgain') or []
        if sorted(order) != sorted(_ids_of(rows)):
            fails.append('%s: ALL chip lists %s, expected %s' % (nm, sorted(order), sorted(_ids_of(rows))))
        byid = dict((t['id'], t) for t in fixture['trades'])

        def _exp_chip(k):
            if k == 'ALL':
                return [t for t in rows]
            if k == 'LONG':
                return [t for t in rows if _side_of(t) == 'LONG']
            if k == 'SHORT':
                return [t for t in rows if _side_of(t) == 'SHORT']
            if k == 'WINS':
                return [t for t in rows if t.get('open') is not True and _disp(t) > 0]
            if k == 'LOSSES':
                return [t for t in rows if t.get('open') is not True and _disp(t) < 0]
            if k.startswith('fam:'):
                return [t for t in rows if _fam_of(t.get('leg')) == k[4:]]
            return None
        for k, info in (I2.get('chips') or {}).items():
            want = _exp_chip(k)
            if want is None:
                fails.append('%s: an unknown chip %r' % (nm, k))
                continue
            if sorted(info.get('ids') or []) != sorted(_ids_of(want)):
                fails.append('%s: the %s chip lists %s, the fixture says %s' % (nm, k, sorted(info.get('ids') or []), sorted(_ids_of(want))))
            if info.get('on') != [k]:
                fails.append('%s: after a tap on %s the active chip reads %s' % (nm, k, info.get('on')))
        # a $0 trade is neither a win nor a loss: it is in ALL and in neither WINS nor LOSSES
        zero = [t for t in rows if t.get('open') is not True and abs(_disp(t)) < 1e-9]
        if nm == 'other-on':
            if not zero:
                fails.append('other-on: the fixture should hold a $0 trade on a strategy outside the book')
            for t in zero:
                if t['id'] in ((I2.get('chips') or {}).get('WINS') or {}).get('ids', []) or t['id'] in ((I2.get('chips') or {}).get('LOSSES') or {}).get('ids', []):
                    fails.append('other-on: the $0 trade %s is listed under WINS or LOSSES' % t['id'])
                if t['id'] not in ((I2.get('chips') or {}).get('ALL') or {}).get('ids', []):
                    fails.append('other-on: the $0 trade %s is missing from ALL' % t['id'])
        # the search box: filters, keeps the cursor
        sr = I2.get('search') or {}
        want = [t for t in rows if str(t.get('leg') or '').upper().startswith('NOISE')]
        if sorted(sr.get('ids') or []) != sorted(_ids_of(want)):
            fails.append('%s: searching "noise" lists %s, the fixture says %s' % (nm, sorted(sr.get('ids') or []), sorted(_ids_of(want))))
        if not sr.get('focus') or sr.get('caret') != 5 or sr.get('value') != 'noise':
            fails.append('%s: the search box lost its focus or cursor while filtering (%s)' % (nm, sr))
        if sorted(sr.get('cleared') or []) != sorted(_ids_of(rows)):
            fails.append('%s: clearing the search did not bring every row back' % nm)
        # LIST | TABLE: switches, is remembered (stored per board and kept across a redraw)
        vw = I2.get('view') or {}
        if vw.get('start') != 'table' or vw.get('afterList') != 'list' or vw.get('stored') != 'list' or vw.get('pressed') != ['list'] \
                or vw.get('afterRenderList') != 'list' or vw.get('afterTable') != 'table' or vw.get('storedT') != 'table' or vw.get('afterRenderTable') != 'table' \
                or vw.get('listRows') != len(rows):
            fails.append('%s: LIST | TABLE does not switch and stay (%s)' % (nm, vw))
        # tick boxes: one per row, the count on OPEN N CHARTS follows, the gallery gets exactly the ticked trades in list order
        tk = I2.get('tick') or {}
        n_rows = len(rows)
        if tk.get('n') != n_rows or tk.get('n', 0) < 4:
            fails.append('%s: %s tick boxes for %d rows' % (nm, tk.get('n'), n_rows))
            continue
        ordr = tk.get('order') or []

        def _btn(x, n):
            b = (x or {}).get('open') or {}
            return b.get('n') == str(n) and b.get('txt') == 'OPEN %d CHART%s' % (n, '' if n == 1 else 'S') and b.get('dis') == (n == 0)
        if (tk.get('start') or {}).get('ticked') or not _btn(tk.get('start'), 0):
            fails.append('%s: nothing is ticked at first and OPEN 0 CHARTS is disabled (%s)' % (nm, tk.get('start')))
        one = tk.get('one') or {}
        if one.get('ticked') != [ordr[1]] or one.get('selAttr') != [ordr[1]] or not _btn(one, 1):
            fails.append('%s: one tick should tick row %s and read OPEN 1 CHART (%s)' % (nm, ordr[1], one))
        many = tk.get('many') or {}
        if many.get('ticked') != [ordr[1], ordr[2], ordr[3]] or not _btn(many, 3):
            fails.append('%s: three ticks should read OPEN 3 CHARTS with %s (%s)' % (nm, ordr[1:4], many))
        gal = tk.get('gallery') or []
        if len(gal) != 1 or gal[0].get('pids') != [ordr[1], ordr[2], ordr[3]] or not gal[0].get('keep'):
            fails.append('%s: OPEN N CHARTS must hand the three ticked trades to the gallery in list order (%s)' % (nm, gal))
        down = tk.get('down') or {}
        if down.get('ticked') != [ordr[1], ordr[3]] or not _btn(down, 2):
            fails.append('%s: untick one and the count follows down (%s)' % (nm, down))
        al = tk.get('all') or {}
        if sorted(al.get('ticked') or []) != sorted(ordr) or not _btn(al, n_rows) or not al.get('box'):
            fails.append('%s: the tick for every row shown ticks all %d rows and reads OPEN %d CHARTS (%s)' % (nm, n_rows, n_rows, al))
        if (tk.get('none') or {}).get('ticked') or not _btn(tk.get('none'), 0):
            fails.append('%s: the second tap on the header tick clears every tick (%s)' % (nm, tk.get('none')))
        ac = tk.get('allCharts') or []
        if len(ac) != 1 or ac[0].get('pids') != ordr or not ac[0].get('keep'):
            fails.append('%s: ALL CHARTS must hand every trade shown to the gallery in list order (%s)' % (nm, ac))
        n_long = len([t for t in rows if _side_of(t) == 'LONG'])
        ach = tk.get('afterChip') or {}
        if tk.get('everything', {}).get('ticked') != n_rows or len(ach.get('ticked') or []) != n_long or ach.get('shown') != n_long or not _btn(ach, n_long):
            fails.append('%s: with every row ticked the LONG chip should leave %d ticked rows and OPEN %d CHARTS (%s)' % (nm, n_long, n_long, ach))
        aa = tk.get('afterAll') or {}
        if aa.get('ticked') != n_long or not _btn(aa, n_long) or (tk.get('inList') or {}).get('ticked') != n_long:
            fails.append('%s: the ticks follow what is shown (back to ALL: %s, in LIST: %s)' % (nm, aa, tk.get('inList')))
        if (tk.get('cleared') or {}).get('ticked') or not _btn(tk.get('cleared'), 0):
            fails.append('%s: clear ticks leaves ticks behind (%s)' % (nm, tk.get('cleared')))
        # a row click records the trade id (the panel is step 9), leaves the ticks alone, and neither the tick nor the CHART cell is a row click
        rw = I2.get('row') or {}
        if rw.get('got') != rw.get('id') or rw.get('ticksBefore') != rw.get('ticksAfter') or rw.get('tickIsRow') is not None \
                or (rw.get('chart') or {}).get('opened') != rw.get('id') or (rw.get('chart') or {}).get('rowClick') is not None:
            fails.append('%s: a row click must record its trade id and leave the tick box and the CHART cell alone (%s)' % (nm, rw))
        # a header sort: no day headers once sorted by money, rows in money order, the day-order chip says so
        so = I2.get('sort') or {}
        pn = [_num_of(x) for x in (so.get('pnls') or [])]
        if not pn or so.get('days') or pn != sorted(pn, reverse=True) or 'sorted by $' not in (so.get('chip') or ''):
            fails.append('%s: sorting by $ should drop the day headers and put the rows in money order (%s)' % (nm, so))

    # the calendar day tap ticks the rows that CLOSED that day and scrolls the list to that day header
    I = (cases.get('paper2') or {}).get('int') or {}
    for tag, key in (('newest month', 'tap0'), ('earlier month', 'tap1')):
        tp = I.get(key) or {}
        if not tp.get('sel') or tp.get('sel') != tp.get('forDay') or tp.get('sel') != tp.get('cellN') \
                or set(tp.get('selDays') or []) != set([tp.get('day')]):
            fails.append('paper2 calendar (%s): a day tap ticked %s row(s) of the days %s - expected exactly the %s row(s) that closed on %s'
                         % (tag, tp.get('sel'), tp.get('selDays'), tp.get('cellN'), tp.get('day')))
        elif tp.get('scrolled') != [tp.get('day')]:
            fails.append('paper2 calendar (%s): a day tap should scroll the list to the day header %s (scrolled to %s)' % (tag, tp.get('day'), tp.get('scrolled')))
        elif ('OPEN %d CHART' % tp.get('sel')) not in (tp.get('openTxt') or ''):
            fails.append('paper2 calendar (%s): OPEN N CHARTS reads %r after a day tap on %d rows' % (tag, tp.get('openTxt'), tp.get('sel')))

    # COLUMNS: retired in v73.396 - the sidebar table is locked to KEY (thirteen
    # columns cannot fit a sidebar; everything else is on the row hovers), so KEY and
    # ALL now render identically and comparing them asserts a control that no longer
    # exists. What still matters is covered above: the table renders, its rows match
    # its headings, and the sidebar holds it.
    # sorting must never lose or gain a row
    base_rows = (cases.get('cols-all') or {}).get('legRows')
    for nm, r in cases.items():
        if nm.startswith('sort-') and base_rows and r.get('legRows') != base_rows:
            fails.append('%s: %s leg rows against %s unsorted' % (nm, r.get('legRows'), base_rows))

    # ------------------------------------------------------------------------------------------------------------
    # LEDGER step 9 (owner plan 2026-10-05; decision 6: a row click opens the panel): the shared TRADE PANEL on NT8 PAPER. A click on a row
    # opens ledgerTradePanelOpen for that trade id; every expectation is recomputed from the FIXTURE (the strategy name, the side, the net, the
    # entry and exit, the hold in seconds, SLIP / delta $ from the injected NinjaTrader match, CUM from the counted trades in close order).
    FT = {t['id']: t for t in fixture['trades']}
    BSL = chr(92)

    def _lab(t):
        d = defs.get(t.get('leg')) or {}
        return _re.sub(_re.escape(BSL + 'u') + '([0-9a-fA-F]{4})', lambda m_: chr(int(m_.group(1), 16)), d.get('label') or str(t.get('leg')))

    def _sgn(v):
        return ('+' if v >= 0 else '-') + '$' + format(abs(round(v, 2)), ',.2f')

    def _sg2(v):
        return ('+' if v >= 0 else '-') + '%.2f' % abs(v)

    def _px(v):
        return '—' if v is None else '%.2f' % v

    def _cls_of(v):
        return 'lg-up' if v > 0 else ('lg-down' if v < 0 else 'lg-flat')

    def _cum_to(tid):
        # every counted closed trade of the board in the order it closed (close day, then the time of the exit), to and including this one
        rows_ = sorted([t for t in fixture['trades'] if t.get('open') is not True and _w(t)], key=lambda t: (_close(t), (t.get('exitIso') or '')[11:19]))
        run_, got_ = 0.0, None
        for t in rows_:
            run_ += _disp(t)
            if t['id'] == tid:
                got_ = run_
        return got_

    def _rowmap(st):
        return dict((x[0], (x[1], x[2])) for x in (st.get('nrows') or []) if x and len(x) >= 3)

    def _numbers_ok(tag, st, tid, label):
        t = FT[tid]
        rm_ = _rowmap(st)
        op_ = t.get('open') is True
        en, ex = t.get('entryIso') or '', t.get('exitIso') or ''
        sz = (t.get('size') or 1) * (1 if True else 1) * (_w(t) if (_w(t) and _w(t) > 1) else 1)
        szt = ('%g' % round(sz, 2))
        want = {
            'Entry': '%s %s ET · %s' % (en[5:10], en[11:16], _px(t.get('entry_px'))),
            'Exit': 'open' if op_ else '%s %s ET · %s' % (ex[5:10], ex[11:16], _px(t.get('exit_px'))),
            'Size': szt + (' contract' if szt == '1' else ' contracts'),
            'Hold': _dur_text((t.get('exitTime') or 0) - (t.get('entryTime') or 0)) + (' so far' if op_ else ''),
            'Points': _sg2(t.get('pnl_pts') or 0),
        }
        net = _disp(t)
        want['Unrealised' if op_ else 'Net'] = _sgn(net)
        for k, v in want.items():
            got = (rm_.get(k) or (None,))[0]
            if got != v:
                fails.append('%s: %s - the numbers row %s reads %r, the fixture says %r' % (tag, label, k, got, v))
        if 'Net' in want and _cls_of(net) not in (rm_.get('Net') or ('', ''))[1].split():
            fails.append('%s: %s - the Net row is not coloured %s (%r)' % (tag, label, _cls_of(net), rm_.get('Net')))
        for k in ('Slip pts', 'Delta $', 'Cum $'):
            if k not in rm_:
                fails.append('%s: %s - the numbers slot has no %s row' % (tag, label, k))
        return rm_

    for nm, cfg in PANEL_CASES:
        r = cases.get(nm) or {}
        tag = 'trade panel %s' % nm
        pn = r.get('panel') or {}
        if r.get('call') != 'OK':
            continue          # the render failure is already listed above
        if pn.get('err') or not pn:
            fails.append('%s: the panel run did not finish: %s' % (tag, pn.get('err') or 'no readout'))
            continue
        P = cfg['panel']
        st = pn.get('steps') or {}
        base = pn.get('base') or {}
        for sname, s_ in st.items():
            if s_.get('err'):
                fails.append('%s, step %s: the probe step threw -- %s' % (tag, sname, str(s_['err'])[:240]))
        sheet = cfg['vp'] in ('phone', 'edge600')      # 600 px and under: a bottom sheet; above: a right-hand panel
        T1, T2, OT = FT[P['tid']], FT[P['tid2']], FT[P['otid']]
        want_sym = dict((k, _lab(FT[k])) for k in (P['tid'], P['tid2'], P['otid'], P.get('blue'), P.get('amber')) if k)

        def says(label, s, tid, tag=tag, want_sym=want_sym):
            t = FT[tid]
            net = _disp(t)
            if s.get('trade') != tid:
                fails.append('%s: %s - the panel is tied to trade %r, expected %r' % (tag, label, s.get('trade'), tid))
            if s.get('sym') != want_sym[tid]:
                fails.append('%s: %s - the panel shows %r, expected the strategy %s' % (tag, label, s.get('sym'), want_sym[tid]))
            if t.get('open') is True:
                if s.get('net') is not None:
                    fails.append('%s: %s - an OPEN trade must show no net in the panel header, it shows %r' % (tag, label, s.get('net')))
            elif s.get('net') != _sgn(net):
                fails.append('%s: %s - the panel net reads %r, expected %s' % (tag, label, s.get('net'), _sgn(net)))
            elif _cls_of(net) not in (s.get('netCls') or '').split():
                fails.append('%s: %s - the panel net is not coloured with %s (class %r)' % (tag, label, _cls_of(net), s.get('netCls')))
            if s.get('side') != _side_of(t):
                fails.append('%s: %s - the panel side tag reads %r, expected %s' % (tag, label, s.get('side'), _side_of(t)))

        def room(label, g, tag=tag, base=base):
            g = g or {}
            if g.get('nodes'):
                fails.append('%s: %s - %s trade panel node(s) are still in the page (a closed trade panel must not be in it)' % (tag, label, g.get('nodes')))
            for k, nice in (('sw', 'width'), ('sh', 'height')):
                if g.get(k) is None or base.get(k) is None or abs(g[k] - base[k]) > 1:
                    fails.append('%s: %s - the page is %s px %s, it was %s before the panel opened (a closed trade panel takes room)'
                                 % (tag, label, g.get(k), nice, base.get(k)))
            if g.get('kids') != base.get('kids'):
                fails.append('%s: %s - <body> holds %s elements, it held %s before the panel opened' % (tag, label, g.get('kids'), base.get('kids')))

        if base.get('nodes'):
            fails.append('%s: the panel is in the page before anything was opened (%s node(s))' % (tag, base.get('nodes')))
        # -- a click on a tick box, the label round it, the CHART pill or a button inside a row never opens the panel
        sk = st.get('skip') or {}
        if not sk.get('found') or sk.get('have') != [True, True, True, True, True]:
            fails.append('%s: the row of %s has no tick box / label / CHART pill / tick-all / ALL CHARTS to click (%r)' % (tag, P['tid'], sk.get('have')))
        elif sk.get('nodes') or sk.get('id') is not None:
            fails.append('%s: a click on a tick box (or another control in a row) opened the NT8 trade panel' % tag)
        elif sk.get('ticks'):
            fails.append('%s: two clicks on a tick box and on its label left %s tick(s) on (they must toggle back to none)' % (tag, sk.get('ticks')))
        # -- open: the header
        o = st.get('open') or {}
        if not o.get('clicked') or not o.get('exists'):
            fails.append('%s: a click on the row of %s did not open the NT8 trade panel (row found=%s)' % (tag, P['tid'], o.get('clicked')))
            continue
        says('open', o, P['tid'])
        sym_t = want_sym[P['tid']]
        if o.get('tag'):
            fails.append('%s: a counted trade carries the chip %r in its panel header (only OPEN and NOT BOOK are chips)' % (tag, o.get('tag')))
        en_, ex_ = T1['entryIso'], T1['exitIso']
        if ('%s' % en_[:10]) not in (o.get('when') or '') or ('%s → %s ET' % (en_[11:16], ex_[11:16])) not in (o.get('when') or ''):
            fails.append('%s: the panel date and times read %r, expected %s and %s → %s ET' % (tag, o.get('when'), en_[:10], en_[11:16], ex_[11:16]))
        szt = '%g' % round(T1.get('size') or 1, 2)
        if (szt + ' ct') not in (o.get('sub') or ''):
            fails.append('%s: the panel header does not carry the size %s ct (%r)' % (tag, szt, o.get('sub')))
        want_mode = 'sheet' if sheet else 'side'
        if o.get('mode') != want_mode:
            fails.append('%s: the panel mode is %r, expected %r (phone = bottom sheet, laptop = right-hand panel)' % (tag, o.get('mode'), want_mode))
        vis = (o.get('vis') or ',,0').split(',')
        if vis[0] not in ('block', 'flex') or vis[1] != 'visible' or float(vis[2] or 0) < 0.5:
            fails.append('%s: the open panel is not visible (display,visibility,opacity = %s)' % (tag, o.get('vis')))
        if o.get('role') != 'dialog' or o.get('modal') != 'true':
            fails.append('%s: the panel is not marked role=dialog aria-modal=true (%r, %r)' % (tag, o.get('role'), o.get('modal')))
        rc, g_ = o.get('rect') or {}, o.get('g') or {}
        vw, vh = g_.get('cw') or 0, g_.get('vh') or 0      # the layer is fixed inside the page, so it ends where a scrollbar starts
        if sheet:
            if not (rc.get('l') == 0 and rc.get('w') == vw and rc.get('b') == vh):
                fails.append('%s: on a phone the panel should be a bottom sheet the full width and sitting on the bottom edge '
                             '(left=%s width=%s bottom=%s, screen %sx%s)' % (tag, rc.get('l'), rc.get('w'), rc.get('b'), vw, vh))
            if (rc.get('h') or 0) > 0.9 * vh or (rc.get('t') or 0) < 0.1 * vh:
                fails.append('%s: the phone sheet is %spx tall with its top at %spx on a %spx screen: it must leave a strip of page above it to tap'
                             % (tag, rc.get('h'), rc.get('t'), vh))
        else:
            if not (abs((rc.get('r') or 0) - vw) <= 1 and abs((rc.get('h') or 0) - vh) <= 1 and 380 <= (rc.get('w') or 0) <= 460):
                fails.append('%s: on a laptop the panel should be a right-hand panel 380-460px wide and the full height '
                             '(right=%s width=%s height=%s, screen %sx%s)' % (tag, rc.get('r'), rc.get('w'), rc.get('h'), vw, vh))
        if o.get('inApp'):
            fails.append('%s: the panel is inside #app, which every redraw rebuilds - it must live in <body>' % tag)
        if o.get('slots') != ['head', 'chart', 'numbers', 'notes', 'actions']:
            fails.append('%s: the panel slots come in the order %r, expected head, chart, numbers, notes, actions' % (tag, o.get('slots')))
        if o.get('bodyWide'):
            fails.append('%s: the panel body scrolls sideways' % tag)
        if (g_.get('sw') or 0) > (g_.get('cw') or 0) + 1 or abs((g_.get('sw') or 0) - (base.get('sw') or 0)) > 1 or abs((g_.get('sh') or 0) - (base.get('sh') or 0)) > 1:
            fails.append('%s: opening the panel changed the page size from %sx%s to %sx%s (it must sit over the page; no sideways scroll)'
                         % (tag, base.get('sw'), base.get('sh'), g_.get('sw'), g_.get('sh')))
        if not o.get('focusIn'):
            fails.append('%s: focus did not move into the panel when it opened' % tag)
        # the numbers slot: entry, exit, size, hold, points, net, SLIP, delta $, CUM - each from the fixture
        rm_ = _numbers_ok(tag, o, P['tid'], 'open')
        if T1.get('size') not in (None, 1, 1.0) and (rm_.get('Engine size') or (None,))[0] != 'x%.2f' % T1['size']:
            fails.append('%s: open - the numbers slot should carry the engine size x%.2f (%r)' % (tag, T1['size'], rm_.get('Engine size')))
        if T1.get('backfill') is not None:
            wsrc = 'backfilled' if T1['backfill'] else ('forward' + (', live since %s' % T1['live_from'] if T1.get('live_from') else ''))
            if (rm_.get('Source') or (None,))[0] != wsrc:
                fails.append('%s: open - the Source row reads %r, the record says %r' % (tag, (rm_.get('Source') or (None,))[0], wsrc))
        if (rm_.get('Gate') or (None,))[0] != T1.get('gate') or not T1.get('gate'):
            fails.append('%s: open - the numbers slot should carry what the record holds under gate (%r), got %r' % (tag, T1.get('gate'), (rm_.get('Gate') or (None,))[0]))
        # the notes slot: read-only (NT8 keeps no notes), the record reason and exit reason lines
        nt_ = o.get('notes') or ''
        if o.get('notesInputs'):
            fails.append('%s: the notes slot holds %s editable control(s): NT8 keeps no editable notes' % (tag, o.get('notesInputs')))
        if 'keeps no notes' not in nt_ or 'read-only' not in nt_:
            fails.append('%s: the notes slot does not say that NT8 keeps no notes and that these lines are read-only (%r)' % (tag, nt_[:140]))
        for lbl_, key_ in (('Reason', 'reason'), ('Exit reason', 'exit_reason')):
            if T1.get(key_) and (lbl_ not in nt_ or T1[key_] not in nt_):
                fails.append('%s: the notes slot should show the record %s line %r (%r)' % (tag, key_, T1[key_], nt_[:200]))
        # the actions slot: OPEN IN GALLERY and the EL / NT / TV chips, nothing destructive; the chart slot: its chips and EXPAND
        bt = o.get('btns') or {}
        if not bt.get('gallery') or bt.get('del'):
            fails.append('%s: the actions slot should hold OPEN IN GALLERY and nothing destructive (%r)' % (tag, bt))
        if len(o.get('chips') or []) != 3 or [c.split(' ')[0] for c in o['chips']] != ['EL', 'NT', 'TV']:
            fails.append('%s: the actions slot should carry the three chips EL, NT and TV (%r)' % (tag, o.get('chips')))
        if not bt.get('expand') or bt.get('z') != ['trade', 'full', 'out', 'in', 'png']:
            fails.append('%s: the chart slot should have TRADE, FULL, minus, plus, PNG and EXPAND (%r)' % (tag, bt))
        if P.get('chart'):
            ch_ = o.get('chart') or {}
            if not ch_.get('svg'):
                fails.append('%s: the chart in the panel never drew an <svg> from the bars (%r)' % (tag, (ch_.get('body') or '')[:80]))
            else:
                z = o.get('z') or {}
                nb = lambda s_: int(_re.match(r'.*? (\d+) of (\d+) bars', s_ or '').group(1)) if _re.match(r'.*? (\d+) of (\d+) bars', s_ or '') else None
                n0, nout, nback, nfull, ntr = nb(z.get('start')), nb(z.get('out')), nb(z.get('back')), nb(z.get('full')), nb(z.get('trade'))
                if None in (n0, nout, nback, nfull, ntr) or not (nout > n0 and nback < nout and nfull == 120 and ntr == n0):
                    fails.append('%s: the chart chips do not zoom (bars shown: start %s, minus %s, plus %s, FULL %s, TRADE %s)' % (tag, n0, nout, nback, nfull, ntr))
            ae = o.get('afterExpand') or []
            if len(ae) != 1 or ae[0][:2] != ['expand', P['tid']]:
                fails.append('%s: EXPAND should open the full viewer on trade %s (%r)' % (tag, P['tid'], ae))
            ga = o.get('gallery') or []
            if len(ga) != 1 or P['tid'] not in (ga[0][1] or []) or ga[0][2] != 'SELECTED TRADES':
                fails.append('%s: OPEN IN GALLERY should open the gallery with this trade (%r)' % (tag, ga))
            tk_ = o.get('ticks') or {}
            if not o.get('tickRow') or (tk_.get('after') or 0) < 1 or 'OPEN' not in (tk_.get('btn') or ''):
                fails.append('%s: OPEN IN GALLERY should tick this trade on the list first (ticks %r, row ticked %s)' % (tag, tk_, o.get('tickRow')))
        else:
            if 'could not load these bars' not in ((o.get('chart') or {}).get('body') or ''):
                fails.append('%s: with no PC to ask the chart slot should say it could not load the bars (%r)' % (tag, ((o.get('chart') or {}).get('body') or '')[:100]))
        if cfg['theme'] == 'mono':
            hue = o.get('hue') or {}
            if (hue.get('checked') or 0) < 40:
                fails.append('%s: the MONO hue scan read only %s colours - it did not run' % (tag, hue.get('checked')))
            if hue.get('bad'):
                fails.append('%s: in MONO the panel carries a colour with a hue: %s' % (tag, '; '.join(hue['bad'])))
        # -- a redraw of the list (a search, a chip, LIST | TABLE) and of the board: the same trade, never another
        rr = st.get('rerender') or {}
        if not rr.get('searchBox') or not rr.get('chipBtn') or not rr.get('viewBtn'):
            fails.append('%s: the redraw test could not find the search box / LOSSES chip / LIST | TABLE switch (%r)' % (tag, [rr.get('searchBox'), rr.get('chipBtn'), rr.get('viewBtn')]))
        else:
            for key, nice in (('search', 'a search that lists nothing'), ('cleared', 'the cleared search'), ('chip', 'the LOSSES chip (this trade is a winner)'),
                              ('view', 'the LIST | TABLE switch'), ('board', 'a redraw of the whole board')):
                s_ = rr.get(key) or {}
                if not s_.get('exists'):
                    fails.append('%s: the trade panel closed after %s (it must stay open on its trade)' % (tag, nice))
                    continue
                if s_.get('trade') != P['tid'] or s_.get('sym') != want_sym[P['tid']] or s_.get('net') != _sgn(_disp(T1)):
                    fails.append('%s: after the list was redrawn (%s) the panel shows %r %r under trade %r, not the trade that was opened (%s)'
                                 % (tag, nice, s_.get('sym'), s_.get('net'), s_.get('trade'), P['tid']))
            if (rr.get('search') or {}).get('rows') != 0 or (rr.get('chip') or {}).get('listed'):
                fails.append('%s: the search / LOSSES chip should have taken the trade out of the list (search rows %s, listed under LOSSES %s)'
                             % (tag, (rr.get('search') or {}).get('rows'), (rr.get('chip') or {}).get('listed')))
        # -- Esc, a click outside (and not inside), the close button
        e = st.get('esc') or {}
        if e.get('open'):
            fails.append('%s: Esc did not close the NT8 trade panel' % tag)
        if e.get('id') is not None:
            fails.append('%s: after Esc the board still says trade %r is open' % (tag, e.get('id')))
        room('after Esc', e.get('g'))
        ou = st.get('outside') or {}
        if not ou.get('opened'):
            fails.append('%s: the panel did not open a second time' % tag)
        else:
            if ou.get('hit') != 'layer':
                fails.append('%s: the point outside the panel is %r, not the dim layer' % (tag, ou.get('hit')))
            if not ou.get('keptOnInside'):
                fails.append('%s: a click inside the panel closed it' % tag)
            if ou.get('open'):
                fails.append('%s: a click or tap outside the NT8 trade panel did not close it' % tag)
            room('after a tap outside', ou.get('g'))
        bn = st.get('button') or {}
        if not bn.get('btn'):
            fails.append('%s: the panel has no close button' % tag)
        elif bn.get('open'):
            fails.append('%s: the close button did not close the NT8 trade panel' % tag)
        else:
            room('after the close button', bn.get('g'))
        # -- another trade opened in the open panel switches it; a tick box click in the meantime does not
        sw = st.get('switch') or {}
        if not sw.get('exists'):
            fails.append('%s: the panel closed when another trade was opened in it' % tag)
        else:
            says('after switching to another trade', sw, P['tid2'])
            if (sw.get('first') or {}).get('trade') != P['tid']:
                fails.append('%s: the panel the switch started from was tied to %r, expected %s' % (tag, (sw.get('first') or {}).get('trade'), P['tid']))
            if (sw.get('afterTick') or {}).get('trade') != P['tid2']:
                fails.append('%s: a click on a tick box while the panel is open changed the trade it shows (%r)' % (tag, sw.get('afterTick')))
            if sw.get('nodesNow'):
                fails.append('%s: %s panel node(s) left after the switched panel was closed' % (tag, sw.get('nodesNow')))
            # the second trade: SLIP and delta $ from the matched NinjaTrader fill, CUM, the look-ahead warning, the NT chip
            rm2 = _numbers_ok(tag, sw, P['tid2'], 'second trade')
            if (rm2.get('Slip pts') or (None,))[0] != '+0.75' or 'lg-down' not in (rm2.get('Slip pts') or ('', ''))[1].split():
                fails.append('%s: second trade - SLIP reads %r, the injected NinjaTrader match says +0.75 (against us)' % (tag, rm2.get('Slip pts')))
            if (rm2.get('Delta $') or (None,))[0] != '-$12.50' or 'lg-down' not in (rm2.get('Delta $') or ('', ''))[1].split():
                fails.append('%s: second trade - delta $ reads %r, the injected match says -$12.50' % (tag, rm2.get('Delta $')))
            cum2 = _cum_to(P['tid2'])
            if cum2 is None or (rm2.get('Cum $') or (None,))[0] != _sgn(cum2) or _cls_of(cum2) not in (rm2.get('Cum $') or ('', ''))[1].split():
                fails.append('%s: second trade - CUM reads %r, the counted trades in close order add up to %s' % (tag, rm2.get('Cum $'), None if cum2 is None else _sgn(cum2)))
            if 'Look-ahead' not in (sw.get('notes') or ''):
                fails.append('%s: second trade (an ORB engine row) - the notes slot lost the look-ahead warning (%r)' % (tag, (sw.get('notes') or '')[:120]))
            if not (sw.get('chips') or [''])[0].startswith('EL') or 'NT ✓' not in ' '.join(sw.get('chips') or []):
                fails.append('%s: second trade - the chips should read EL ✓, NT ✓ (matched) and TV (%r)' % (tag, sw.get('chips')))
        # -- the OPEN NOW row opens a panel too: marked OPEN, no net, the exit reads open
        orow = st.get('openrow') or {}
        if not orow.get('clicked') or not orow.get('exists'):
            fails.append('%s: a click on the OPEN NOW row of %s did not open a panel (row found=%s)' % (tag, P['otid'], orow.get('clicked')))
        else:
            says('the OPEN NOW row', orow, P['otid'])
            if orow.get('tag') != 'OPEN':
                fails.append('%s: the panel of the open trade is marked %r, expected OPEN' % (tag, orow.get('tag')))
            if not (orow.get('when') or '').endswith('ET ' + chr(0x2192) + ' open'):
                fails.append('%s: the panel of the open trade should read its times as entry ET -> open (%r)' % (tag, orow.get('when')))
            rmo = _numbers_ok(tag, orow, P['otid'], 'the OPEN NOW row')
            if (rmo.get('Cum $') or (None,))[0] != '—':
                fails.append('%s: the open trade has a CUM (%r): it is in no total yet' % (tag, rmo.get('Cum $')))
        # -- a strategy outside the book (NOT BOOK) with the chip variants NT approx and NT cross: the same three chips, no hue in MONO
        cp = st.get('chips') or {}
        for key, glyph in (('blue', chr(0x2248)), ('amber', chr(0x2717))):
            s_ = cp.get(key) or {}
            if not s_.get('clicked') or not s_.get('exists'):
                fails.append('%s: a click on the row of %s (a strategy outside the book) did not open the NT8 trade panel' % (tag, P[key]))
                continue
            says('a strategy outside the book (%s chip)' % key, s_, P[key])
            if s_.get('tag') != 'NOT BOOK':
                fails.append('%s: the panel of a trade outside the book is tagged %r, expected NOT BOOK' % (tag, s_.get('tag')))
            if len(s_.get('chips') or []) != 3 or glyph not in (s_['chips'][1] if len(s_.get('chips') or []) > 1 else ''):
                fails.append('%s: the %s chip variant should read NT %s in the panel (%r)' % (tag, key, glyph, s_.get('chips')))
            if (_rowmap(s_).get('Cum $') or (None,))[0] != chr(0x2014):
                fails.append('%s: a trade outside the book has a CUM (%r): it is in no total' % (tag, _rowmap(s_).get('Cum $')))
            if cfg['theme'] == 'mono':
                hue = s_.get('hue') or {}
                if (hue.get('checked') or 0) < 40 or hue.get('bad'):
                    fails.append('%s: in MONO the panel of the %s chip variant carries a colour with a hue (%s colours read): %s'
                                 % (tag, key, hue.get('checked'), '; '.join(hue.get('bad') or [])))
        # -- closed again: nothing left in the page, the page exactly as big as before
        rmm = st.get('room') or {}
        room('at the end', rmm.get('g'))
        if rmm.get('id') is not None:
            fails.append('%s: the board still says trade %r is open after the panel was closed' % (tag, rmm.get('id')))
        # -- the trade leaves the board rows: the panel closes by itself; leaving the board closes it too
        gn = st.get('gone') or {}
        if not gn.get('sw') or not gn.get('opened') or not gn.get('opened3') or not gn.get('pill'):
            fails.append('%s: the leave-the-list test could not run (switch %s, opened %s / %s, range pill %s)' % (tag, gn.get('sw'), gn.get('opened'), gn.get('opened3'), gn.get('pill')))
        else:
            ao = gn.get('afterOff') or {}
            if ao.get('listed') or ao.get('open') or ao.get('id') is not None or (ao.get('g') or {}).get('nodes'):
                fails.append('%s: the panel did not close when its trade left the list (strategy switched off: listed %s, open %s, id %r)'
                             % (tag, ao.get('listed'), ao.get('open'), ao.get('id')))
            if not (gn.get('back') or {}).get('listed') or (gn.get('back') or {}).get('open'):
                fails.append('%s: switching the strategy back on should list its trades again and leave no panel (%r)' % (tag, gn.get('back')))
            ar = gn.get('afterRange') or {}
            if ar.get('listed') or ar.get('open') or ar.get('id') is not None:
                fails.append('%s: the panel did not close when its trade left the range (TODAY: listed %s, open %s, id %r)' % (tag, ar.get('listed'), ar.get('open'), ar.get('id')))
        lv = st.get('leave') or {}
        if not lv.get('opened'):
            fails.append('%s: the leave-the-board test could not open a panel' % tag)
        elif lv.get('open') or lv.get('id') is not None:
            fails.append('%s: leaving the NT8 board did not close its trade panel (open %s, id %r)' % (tag, lv.get('open'), lv.get('id')))
        elif not (lv.get('back') or {}).get('frame'):
            fails.append('%s: the NT8 board did not come back after the leave test' % tag)
        room('after the whole run', pn.get('end'))
    # the panel at every width of the sweep, with the page itself never scrolling sideways, open or closed
    for w_px in WIDTHS:
        for view in WIDTH_VIEWS:
            nm = 'wid-%d-%s' % (w_px, view)
            pw = (cases.get(nm) or {}).get('pw') or {}
            if not pw or pw.get('err') or not pw.get('exists'):
                fails.append('%s: the trade panel did not open from a row at this width (%s)' % (nm, pw.get('err') or 'no panel'))
                continue
            wmode = 'sheet' if w_px <= 600 else 'side'
            if pw.get('mode') != wmode:
                fails.append('%s: the panel mode is %r at %d px, expected %r' % (nm, pw.get('mode'), w_px, wmode))
            g1, g2 = pw.get('g') or {}, pw.get('g1') or {}
            if (g1.get('sw') or 0) > (g1.get('vw') or 0):
                fails.append('%s: the page scrolls sideways at %d px with the trade panel open (scrollWidth %s > %s)' % (nm, w_px, g1.get('sw'), g1.get('vw')))
            if (g2.get('sw') or 0) > (g2.get('vw') or 0) or g2.get('nodes'):
                fails.append('%s: after the panel closed the page scrolls sideways (%s > %s) or %s node(s) are left' % (nm, g2.get('sw'), g2.get('vw'), g2.get('nodes')))
            rc = pw.get('rect') or {}
            if (rc.get('l') or 0) < 0 or (rc.get('r') or 0) > (g1.get('vw') or 0) + 1 or pw.get('bodyWide'):
                fails.append('%s: the panel does not fit the window at %d px (left %s, right %s, window %s)' % (nm, w_px, rc.get('l'), rc.get('r'), g1.get('vw')))
    # LEDGER step 9 follow-up: the bars of a trade are cached under the trade's own id. Every chart the page DREW (the CHART pill viewer, the
    # OPEN N CHARTS gallery) after a chip, a search, a LIST | TABLE switch and a header re-sort must have its price axis on that trade's own level
    ckr = cases.get('chartkey') or {}
    ck = ckr.get('ckey') or {}
    if ckr.get('call') == 'OK':
        steps = ck.get('steps') or []
        pills = [s for s in steps if s.get('kind') == 'pill']
        gals = [s for s in steps if s.get('kind') == 'gallery']
        if ck.get('err') or not steps:
            fails.append('chartkey: the bars-key run did not finish: %s' % (ck.get('err') or 'no readout'))
        else:
            if len(pills) < 9 or len(gals) != 4 or not ck.get('req'):
                fails.append('chartkey: the run is too small to say anything (%d CHART pills, %d galleries, %s get_bars requests)'
                             % (len(pills), len(gals), ck.get('req')))
            if ck.get('sorted') == ck.get('all') or (ck.get('orb') or [None])[0] == (ck.get('all') or [None])[0]:
                fails.append('chartkey: the fixture no longer moves a trade to another place in the list on a header sort or a chip (%s / %s / %s)'
                             % (ck.get('all'), ck.get('sorted'), ck.get('orb')))
            for s in pills:
                if not s.get('pill'):
                    fails.append('chartkey: %s - the row of %s has no CHART pill' % (s.get('n'), s.get('id')))
                elif not s.get('svg'):
                    fails.append('chartkey: %s - the CHART pill of %s opened no chart' % (s.get('n'), s.get('id')))
                elif not s.get('ok'):
                    fails.append('chartkey: %s - the CHART pill drew the bars of another trade: the chart of %s has a price axis of %s, its own bars sit at %s '
                                 '(the bars cache must be keyed by the trade id, never by its place in the list)'
                                 % (s.get('n'), s.get('id'), s.get('axis'), s.get('want')))
            for s in gals:
                tk = s.get('ticked') or []
                nc = len(s.get('cards') or [])
                if not s.get('btn') or len(tk) < 2:
                    fails.append('chartkey: %s - OPEN N CHARTS is missing or fewer than two trades are ticked (%s)' % (s.get('n'), tk))
                elif nc != len(tk):
                    fails.append('chartkey: %s - the OPEN N CHARTS gallery opened %d chart(s), exactly the %d ticked trades are expected (%s)' % (s.get('n'), nc, len(tk), tk))
                for c in (s.get('cards') or []):
                    if not c.get('svg'):
                        fails.append('chartkey: %s - the gallery card of %s drew no chart' % (s.get('n'), c.get('id')))
                    elif not c.get('ok'):
                        fails.append('chartkey: %s - the OPEN N CHARTS gallery drew the bars of another trade: the card of %s has a price axis of %s, its own bars '
                                     'sit at %s (the bars cache must be keyed by the trade id, never by its place in the list)'
                                     % (s.get('n'), c.get('id'), c.get('axis'), c.get('want')))
        for e in (ckr.get('errors') or []) + (ckr.get('uncaught') or []):
            fails.append('chartkey: a console error or an uncaught throw: %s' % e)

    s11_info = _judge_s11(cases, fixture, data, fails)
    s12_info = _judge_s12(cases, data, fails)

    if fails:
        say('PAPERPROBE: FAIL')
        for f in fails:
            say('  - ' + f)
        return FAIL, out_lines

    # the board has a strategy list (shared ledgerListHtml rows); ?oldboards=1 draws the same board (case flag-paper2)
    say('PAPERPROBE: PASS (VERSION=%s, %d cases, strategy list %s rows, %s trade rows, %d trade panel cases, '
          '%d chart bars-key steps)'
          % (data.get('VERSION'), len(cases), len((cases.get('base') or {}).get('listRowInfo') or []),
             (cases.get('base') or {}).get('tradeRows'), len(PANEL_CASES), len(((cases.get('chartkey') or {}).get('ckey') or {}).get('steps') or [])))
    say('PAPERPROBE step 11: %s' % s11_info)
    say('PAPERPROBE step 12: %s' % s12_info)
    return PASS, out_lines


def _judge_s11(cases, fixture, data, fails):
    """LEDGER step 11 on NT8 PAPER (see the docstring): the fixed page order, the own folds, remembered open / closed, one set of breakpoints, the phone
    list top, MONO, ?oldboards=1 = the plain board. Returns the one line the PASS output prints."""
    import re as _re
    # what the fixture says the warning counts are (the newest report that carries a reconcile block, the newest report's fills log)
    rec_n = fills_n = None
    reps = fixture.get('reports') or []
    for r_ in reps:
        rc = r_.get('reconcile') if isinstance(r_, dict) else None
        if rc and (rc.get('legs') or rc.get('error')):
            rec_n = len(((rc.get('verdict') or {}).get('problems')) or [])
            break
    if reps and isinstance(reps[0].get('live'), dict):
        fills_n = len(reps[0]['live'].get('warnings') or [])
    n_orders = n_cases = n_fold_reads = 0
    p2_cases = [(nm, r) for nm, r in cases.items() if (r.get('s11') or {}).get('board')]
    if not p2_cases:
        fails.append('step 11: no case drew the NT8 board - the page order cannot be judged')
    for nm, r in p2_cases:
        s = r['s11']
        if s.get('err'):
            fails.append('%s: the step 11 readout threw -- %s' % (nm, str(s['err'])[:200]))
            continue
        if s.get('oldMarks'):
            fails.append('%s: markers of the removed previous board are in the page: %s' % (nm, ', '.join(s['oldMarks'])))
        if s.get('flagConst') not in (None, 'undefined'):
            fails.append('%s: LEDGER_OLDBOARDS is still a name in the page (typeof %s)' % (nm, s.get('flagConst')))
        n_cases += 1
        vw = s.get('vw') or 0
        sec = s.get('sec') or []
        ks = [x['k'] for x in sec]
        two = vw >= 1100
        order = [k for k in SECTION_ORDER if not (nm == 'empty' and k == 'capture')]     # no report, no capture health block, no capture fold
        # LEDGER step 12: ONE markup order at every width (the frame's top block, its side panel, the rest); from 1100 px the list is the right-hand panel
        if ks != order:
            fails.append('%s: the page sections run %r, expected the fixed order %r at %d px' % (nm, ks, order, vw))
        else:
            byk = dict((x['k'], x) for x in sec)
            lst = byk['list']
            if two:
                # every section but the list panel is stacked in the fixed order: the top block, then the trades and the own folds under it
                main = [x for x in sec if x['k'] != 'list']
                tp = [x['top'] for x in main]
                if any(b <= a for a, b in zip(tp, tp[1:])):
                    fails.append('%s: the page sections are not stacked top to bottom in the fixed order at %d px (tops %r)' % (nm, vw, tp))
                right = max(x['left'] + x['w'] for x in sec if x['k'] in TOP_SECTIONS)
                if lst['left'] < right or abs(lst['top'] - byk['hero']['top']) > 24:
                    fails.append('%s: from 1100 px the strategy list must be the right-hand panel beside the top block, level with the hero (list left %s top %s, '
                                 'top block right edge %s, hero top %s)' % (nm, lst['left'], lst['top'], right, byk['hero']['top']))
                rl = s.get('rail') or {}
                if not rl or 'sticky' in (rl.get('pos'), rl.get('sidePos')) or 'fixed' in (rl.get('pos'), rl.get('sidePos')):
                    fails.append('%s: the strategy list panel is sticky (or missing) at %d px (%r) - since LEDGER step 12 it sits level with the top block and '
                                 'scrolls inside it' % (nm, vw, rl))
            else:
                at = [x['top'] for x in sec]
                if any(b <= a for a, b in zip(at, at[1:])):
                    fails.append('%s: the page sections are not stacked top to bottom in the fixed order at %d px (tops %r)' % (nm, vw, at))
            if any((x['h'] or 0) <= 0 for x in sec):
                fails.append('%s: a page section is drawn with no height: %s' % (nm, ', '.join(x['k'] for x in sec if (x['h'] or 0) <= 0)))
            if not all(x.get('inBoard') for x in sec):
                fails.append('%s: a page section sits outside the board (.p2rh)' % nm)
            n_orders += 1
        # the folds as drawn: exactly the status fold, the five own folds and (below 1100 px) the strategy list fold
        folds = s.get('folds') or []
        fk = [f['k'] for f in folds]
        wantf = ['status'] + ([] if two else ['list']) + [k for k in OWN_FOLDS if not (nm == 'empty' and k == 'capture')]
        if sorted(fk) != sorted(wantf):
            fails.append('%s: the folds on the board read %r, expected %r at %d px' % (nm, sorted(fk), sorted(wantf), vw))
        seeded = nm in ('reports-open',) or any(k[:6] == 'el_lg_' and k[6:-4] in S11_KEYS for k in ((CASE_CFG.get(nm) or {}).get('ls') or {}))
        for f in folds:
            k = f['k']
            tag = '%s: the %s fold' % (nm, k)
            sm = (f.get('sum') or '').strip()
            if not sm:
                fails.append('%s has no summary line' % tag)
            else:
                if _re.search(r'undefined|NaN|\[object|[<>]|&[a-z#0-9]+;', sm):
                    fails.append('%s summary has stray markup or a bad value: %r' % (tag, sm))
                if f.get('clip') and k != 'status':
                    fails.append('%s summary is cut off at %d px: %r' % (tag, vw, sm))
            if (f.get('sumH') or 0) > 20:
                fails.append('%s summary is %s px tall - the summary must stay on one line (20 px or less)' % (tag, f.get('sumH')))
            if (f.get('hdH') or 0) > 60:
                fails.append('%s header is %s px tall' % (tag, f.get('hdH')))
            if not f.get('inSec'):
                fails.append('%s sits outside the board' % tag)
            if not f.get('bodyLen') and k not in ('list',):
                fails.append('%s has an empty body (nothing in it to show when it opens)' % tag)
            if not seeded:
                want_open = 'true' if (k == 'list' and vw > 600) else 'false'
                if f.get('exp') != want_open or (f.get('hidden') is not (want_open == 'false')):
                    fails.append('%s is %s to start with (aria-expanded=%r, body hidden=%r), expected %s' % (
                        tag, 'open' if f.get('exp') == 'true' else 'closed', f.get('exp'), f.get('hidden'), 'open' if want_open == 'true' else 'closed'))
            n_fold_reads += 1
        # the status line keeps every warning count: one token per warning chip, the total first, the counts the fixture holds
        st = [f for f in folds if f['k'] == 'status']
        if st:
            st = st[0]
            tok = st.get('tok') or []
            wc = s.get('warnChips') or []
            first = (tok[0]['t'] if tok else '')
            m = _re.match(r'^\u26a0 (\d+)$', first)
            if wc and (not m or int(m.group(1)) != len(wc)):
                fails.append('%s: the status line leads with %r but it holds %d warning chip(s)' % (nm, first, len(wc)))
            if not wc and first != 'all clear':
                fails.append('%s: no warning chip, the status line should lead with "all clear" (%r)' % (nm, first))
            wtok = tok[1:1 + len(wc)]
            if len(wtok) != len(wc):
                fails.append('%s: the status line has %d warning token(s) for %d warning chip(s): %r' % (nm, len(wtok), len(wc), [t['t'] for t in tok]))
            if (vw >= 1366 or 1000 <= vw < 1100) and any(t['line'] != 1 for t in tok):
                fails.append('%s: a token of the status line does not fit on its one line at %d px: %r' % (nm, vw, [t['t'] for t in tok if t['line'] != 1]))
            if any(t['line'] != 1 for t in wtok) or (tok and tok[0]['line'] != 1):
                fails.append('%s: a warning token of the status line does not fit on its one line at %d px (the states go first, never a warning): %r'
                             % (nm, vw, [t['t'] for t in tok[:1 + len(wc)] if t['line'] != 1]))
            stxt = ' '.join(t['t'] for t in tok)
            if nm == 'paper2' or nm.startswith('s11-') and 'mono' not in nm and nm != 's11-watchdog':
                if rec_n is not None and not _re.search(r'Recon %d\b' % rec_n, stxt):
                    fails.append('%s: the status line lost the reconcile warning count (%d problems in the fixture): %r' % (nm, rec_n, stxt))
                if fills_n and not _re.search(r'Fills %d\b' % fills_n, stxt):
                    fails.append('%s: the status line lost the fills log warning count (%d in the fixture): %r' % (nm, fills_n, stxt))
        # REFRESH stays on the page line, never inside a closed fold
        rf = s.get('refresh')
        if not rf or rf.get('n') != 1:
            fails.append('%s: the board must have exactly one REFRESH button (%r)' % (nm, rf))
        elif rf.get('inFold') or not rf.get('vis') or (rf.get('right') or 0) > vw:
            fails.append('%s: REFRESH is folded away or off the page (%r)' % (nm, rf))
        # one set of breakpoints
        bp = s.get('bp') or {}
        if not bp.get('n'):
            fails.append('%s: the breakpoint scan saw no media rule of the board (the scan has gone blind)' % nm)
        elif bp.get('bad'):
            fails.append('%s: the board has media or container rules at widths outside the house set %s: %s' % (nm, HOUSE_WIDTHS, '; '.join(sorted(set(bp['bad']))[:4])))
        # the calendar default is the house number: closed up to 600 px, open above (a stored choice overrides it)
        if not any(k == 'el_lg_cal_nt8' for k in ((CASE_CFG.get(nm) or {}).get('ls') or {})) and s.get('calOpen') is not None and nm not in ('stats-open',):
            wantc = 'true' if vw > 600 else 'false'
            if s.get('calOpen') != wantc:
                fails.append('%s: the calendar fold is %r at %d px, expected %r (open above 600 px, closed up to it - the house number)' % (nm, s.get('calOpen'), vw, wantc))
        # the keeps are all still there
        kp = s.get('keeps') or {}
        # the strategy list controls are on every board; the trade list controls are on every board that lists trades (a range with none has no tick boxes)
        miss = [k for k in ('base', 'kind', 'fam', 'sort', 'sw') if not kp.get(k)]
        if not nm.startswith('range-'):
            miss += [k for k in ('openBtn', 'allCharts', 'frame') if not kp.get(k)]
            if kp.get('rows') and not kp.get('ticks'):
                miss.append('ticks')
        if miss:
            fails.append('%s: something the board keeps is gone: %s (%r)' % (nm, ', '.join(miss), kp))
    # -- the width set: the order held at every width of the sweep
    for w_px in WIDTHS:
        for view in WIDTH_VIEWS:
            r = cases.get('wid-%d-%s' % (w_px, view)) or {}
            if not (r.get('s11') or {}).get('sec'):
                fails.append('wid-%d-%s: no page order readout' % (w_px, view))
    # -- the folds open on a click, show their content, close again and store the choice
    n_folds_run = 0
    for nm in ('s11-laptop', 's11-phone', 's11-tablet'):
        r = cases.get(nm) or {}
        f = r.get('s11f') or {}
        if not f or f.get('err'):
            fails.append('%s: the fold run did not finish (%s)' % (nm, str(f.get('err'))[:200]))
            continue
        two = ((r.get('s11') or {}).get('vw') or 0) >= 1100
        wantf = ['status'] + ([] if two else ['list']) + OWN_FOLDS
        fl = f.get('folds') or {}
        if sorted(fl) != sorted(wantf):
            fails.append('%s: the fold run saw %r, expected %r' % (nm, sorted(fl), sorted(wantf)))
        for k in wantf:
            o = fl.get(k) or {}
            tag = '%s: the %s fold' % (nm, k)
            if not o.get('btn'):
                fails.append('%s has no header button to click' % tag)
                continue
            n_folds_run += 1
            if o.get('closed') != 'false' or not o.get('closedHidden'):
                fails.append('%s did not close on a click from its start state (aria-expanded=%r, body hidden=%r)' % (tag, o.get('closed'), o.get('closedHidden')))
            if o.get('exp') != 'true' or o.get('hidden'):
                fails.append('%s: a click did not open it (aria-expanded=%r, body hidden=%r)' % (tag, o.get('exp'), o.get('hidden')))
                continue
            if not o.get('len') or not o.get('vis'):
                fails.append('%s opened with nothing to see in it (text %s chars, drawn: %s)' % (tag, o.get('len'), o.get('vis')))
            if o.get('ls') != '1' or o.get('lsClosed') not in (None, '0') or o.get('lsBack') != '0':
                fails.append('%s: the choice is not stored in localStorage (closed %r, open %r, closed again %r)' % (tag, o.get('lsClosed'), o.get('ls'), o.get('lsBack')))
            if o.get('back') != 'false' or not o.get('backHidden'):
                fails.append('%s: a second click did not close it again (aria-expanded=%r, body hidden=%r)' % (tag, o.get('back'), o.get('backHidden')))
        so = fl.get('status') or {}
        if so.get('chips') is not None:
            if (so.get('chipsVis') or 0) < 3 or so.get('chipsVis') != so.get('chips'):
                fails.append('%s: the status fold opened with %s of %s chips drawn' % (nm, so.get('chipsVis'), so.get('chips')))
            if not so.get('warn') or so.get('warnVis') != so.get('warn'):
                fails.append('%s: the status fold opened with %s of %s warning chips drawn' % (nm, so.get('warnVis'), so.get('warn')))
        wo = f.get('warnOpens') or {}
        if wo.get('exp') != 'true' or wo.get('hidden') or wo.get('ls') != '1':
            fails.append('%s: a warning chip did not open the card that explains it (%r)' % (nm, wo))
        for k in ('more', 'cal'):
            o = f.get(k) or {}
            if not o.get('btn') or o.get('exp') != 'true' or o.get('hidden') or not o.get('len') or not o.get('vis') or o.get('back') != 'false':
                fails.append('%s: the %s fold does not open on a click and show its content (%r)' % (nm, k, o))
    # -- remembered across a real reload, on a laptop and on a phone
    for tag, nm in (('lap', 'laptop'), ('pho', 'phone')):
        r = (data.get('s11reload') or {}).get(tag) or {}
        t = 'reload run (%s)' % nm
        if not r or r.get('err'):
            fails.append('%s did not finish: %s' % (t, str(r.get('err') or 'no readout')[:200]))
            continue
        for key in ('seed1', 'seed2', 'seed3'):
            if r.get(key) != 'OK':
                fails.append('%s: the board did not draw (%s: %s)' % (t, key, r.get(key)))
        for key in ('err1', 'err2'):
            for e in (r.get(key) or {}).get('errors', []) + (r.get(key) or {}).get('uncaught', []):
                fails.append('%s: a console error or an uncaught throw after a reload: %s' % (t, e[:160]))
        keys = sorted((r.get('start') or {}).keys())
        want_keys = sorted(['status'] + ([] if tag == 'lap' else ['list']) + OWN_FOLDS)
        if keys != want_keys:
            fails.append('%s: the folds on the fresh page read %r, expected %r' % (t, keys, want_keys))
        shut = dict((k, 'false') for k in want_keys)
        shown = dict((k, 'true') for k in want_keys)
        if r.get('start') != shut:
            fails.append('%s: the folds do not start closed on a fresh browser (%r)' % (t, r.get('start')))
        if r.get('opened') != shown:
            fails.append('%s: clicking every fold did not open them all (%r)' % (t, r.get('opened')))
        elif any(v != '1' for v in (r.get('lsOpened') or {}).values() if v is not None) or not any((r.get('lsOpened') or {}).values()):
            fails.append('%s: an opened fold was not written to localStorage (%r)' % (t, r.get('lsOpened')))
        if r.get('afterReload') != shown:
            fails.append('%s: after a reload the folds opened before it are not open (%r) - open / closed is not remembered' % (t, r.get('afterReload')))
        if r.get('closed') != shut:
            fails.append('%s: clicking every open fold did not close them all (%r)' % (t, r.get('closed')))
        if r.get('afterReload2') != shut:
            fails.append('%s: after a reload the folds closed before it are not closed (%r) - open / closed is not remembered' % (t, r.get('afterReload2')))
    # -- MONO: nothing the step drew has a hue
    for nm in ('s11-mono-laptop', 's11-mono-phone'):
        r = cases.get(nm) or {}
        hu = r.get('s11m') or {}
        if hu.get('err'):
            fails.append('%s: the colour scan threw -- %s' % (nm, str(hu['err'])[:200]))
        elif hu.get('theme') != 'mono' or not hu.get('checked') or not hu.get('roots'):
            fails.append('%s: the MONO colour scan looked at nothing (%r)' % (nm, hu))
        elif hu.get('bad'):
            fails.append('MONO has a hue in what steps 11 and 12 drew (%s, %d colours checked): %s' % (nm, hu['checked'], '; '.join(hu['bad'])))
        s = r.get('s11') or {}
        if any(f.get('exp') != 'true' for f in (s.get('folds') or [])):
            fails.append('%s: the MONO run must have every fold open (%r)' % (nm, [(f['k'], f.get('exp')) for f in (s.get('folds') or [])]))
    # -- the phone: the trade list is no lower than before the step
    g = (cases.get('phone375') or {}).get('tlGeo') or {}
    phone_top = None
    if g.get('frameTop') is not None and g.get('boardTop') is not None:
        phone_top = g['frameTop'] - g['boardTop']
        if phone_top > S11_PHONE_LIST_TOP:
            fails.append('phone375: the trade list starts %d px under the board top; it was %d before step 11 - it must not grow' % (phone_top, S11_PHONE_LIST_TOP))
    # -- the keeps that need a bridge with a watchdog: the auto-recover switch is a chip of the status row
    wd = ((cases.get('s11-watchdog') or {}).get('s11') or {}).get('keeps') or {}
    if not wd.get('wd') or not wd.get('wdInBody'):
        fails.append('s11-watchdog: the auto-recover switch is gone from the status chips (%r)' % wd)
    wsum = ' '.join(t['t'] for f in (((cases.get('s11-watchdog') or {}).get('s11') or {}).get('folds') or []) if f['k'] == 'status' for t in (f.get('tok') or []))
    if '1 / 1 live' not in wsum or 'gate up' not in wsum:
        fails.append('s11-watchdog: the status line does not carry the NinjaTrader states (live count, gate): %r' % wsum)
    # -- ?oldboards=1 draws the same board as the plain page: the same css and the same markup tree (text is left out: it carries the age of a report)
    pd_ = ((cases.get('paper2') or {}).get('s11') or {}).get('dig') or {}
    o = ((cases.get('flag-paper2') or {}).get('s11') or {}).get('dig') or {}
    if not pd_ or not o:
        fails.append('flag-paper2: no digest of the board to compare with the plain page (plain %s, ?oldboards=1 %s)' % (bool(pd_), bool(o)))
    else:
        if o.get('css') != pd_.get('css'):
            fails.append('flag-paper2: the css behind ?oldboards=1 is not the plain page css (digest %s, %d chars; plain %s, %d chars)'
                         % (o.get('css'), o.get('cssLen'), pd_.get('css'), pd_.get('cssLen')))
        if o.get('tree') != pd_.get('tree'):
            fails.append('flag-paper2: the markup tree behind ?oldboards=1 is not the plain page tree (digest %s, %d elements; plain %s, %d elements)'
                         % (o.get('tree'), o.get('treeN'), pd_.get('tree'), pd_.get('treeN')))
    return ('%d cases in the fixed page order (%d own folds + status + list), %d fold clicks run, remembered across a real reload (laptop + phone), house widths seen %s, '
            'phone list top %s px (was %d), ?oldboards=1 board = plain board (css %s, tree %s, %s elements)'
            % (n_orders, len(OWN_FOLDS), n_folds_run, '/'.join(str(int(x)) for x in sorted(set(
                px for n_, r_ in p2_cases for px in (((r_.get('s11') or {}).get('bp') or {}).get('widths') or [])))), phone_top, S11_PHONE_LIST_TOP,
               o.get('css'), o.get('tree'), o.get('treeN')))


def _filters_expected(cfg):
    """LEDGER step 12: what the Filters row of the NT8 strategy list must say for a case, from the case's OWN settings (prefs, window), never off the
    page: (the summary tokens, the controls shown on). A sort the row has no control for (the probe sets it straight on the window) is None."""
    pr, wn = cfg.get('prefs') or {}, cfg.get('win') or {}
    kind = wn.get('_paperKind') or pr.get('paperKind') or 'ALL'
    fam = wn.get('_paperFam') or pr.get('paperFam') or 'ALL'
    base = bool(wn['_paperBaseOnly']) if wn.get('_paperBaseOnly') is not None else bool(pr.get('paperBaseOnly'))
    col, arrow = wn.get('_legSortCol'), (' \u25b2' if wn.get('_legSortDir') == 'asc' else ' \u25bc')
    sort = {'leg': 'Name' + arrow, 'net': 'Net' + arrow}.get(col) or ('Board order' if col in (None, 'board') else None)
    kind_l = {'ALL': 'Both', 'RAW': 'Raw', 'ML': 'ML'}.get(kind, kind)
    toks = [kind_l, 'All families' if fam == 'ALL' else fam, sort] + (['Baselines only'] if base else [])
    return toks, {'kind': kind_l, 'fam': 'All' if fam == 'ALL' else fam, 'sort': sort, 'base': 'true' if base else 'false'}


def _judge_s12(cases, data, fails):
    """LEDGER step 12 on NT8 PAPER (see the docstring): ONE page frame, the status line under the hero, the chart foot, the Filters row of the strategy
    list. Every expectation is read off the live DOM of each case or worked out from the case's own settings. Returns the one line the PASS output prints."""
    n_frames = n_centred = n_wide = n_narrow = n_filt = n_runs = 0
    p2_cases = [(nm, r) for nm, r in cases.items() if (r.get('s11') or {}).get('board')]
    for nm, r in p2_cases:
        s = r['s11']
        if s.get('err'):
            continue                                   # the step 11 judge has listed it already
        vw = s.get('vw') or 0
        two = vw >= 1100
        cfg = CASE_CFG.get(nm) or {}
        byk = dict((x['k'], x) for x in (s.get('sec') or []))
        # -- ONE page frame: exactly one, at most 1320 px wide, centred in its parent; the markup in one order (top block, side panel, rest)
        if s.get('frameN') != 1:
            fails.append('%s: %s shared page frames [data-lgframe="p2"] on the board, expected exactly one' % (nm, s.get('frameN')))
            continue
        fm = s.get('frame') or {}
        n_frames += 1
        if fm.get('maxW') != FRAME_MAX_W:
            fails.append('%s: the page frame is not at most %s wide (max-width %r) - the board runs the full width again' % (nm, FRAME_MAX_W, fm.get('maxW')))
        if (fm.get('parW') or 0) - (fm.get('w') or 0) > 4:
            n_centred += 1
            if abs((fm.get('gapL') or 0) - (fm.get('gapR') or 0)) > 2:
                fails.append('%s: the page frame is not centred in its parent at %d px (left gap %s px, right gap %s px, the frame %s of %s px)'
                             % (nm, vw, fm.get('gapL'), fm.get('gapR'), fm.get('w'), fm.get('parW')))
        if not fm.get('inBoard'):
            fails.append('%s: the page frame sits outside the board (.p2rh)' % nm)
        if fm.get('topKids') != TOP_SECTIONS:
            fails.append('%s: the frame top block holds the sections %r, expected %r in that order' % (nm, fm.get('topKids'), TOP_SECTIONS))
        if fm.get('inSide') != ['list']:
            fails.append('%s: the strategy list is not in the frame side panel [data-lgframe-side] (the panel holds %r)' % (nm, fm.get('inSide')))
        want_rest = ['trades'] + [k for k in OWN_FOLDS if not (nm == 'empty' and k == 'capture')]
        if fm.get('inRest') != want_rest:
            fails.append('%s: the frame rest holds %r, expected the trades then the own folds %r' % (nm, fm.get('inRest'), want_rest))
        top, side, rest, sin = fm.get('top') or {}, fm.get('side') or {}, fm.get('rest') or {}, fm.get('sideIn') or {}
        if two:
            n_wide += 1
            if fm.get('disp') != 'grid':
                fails.append('%s: from 1100 px the page frame is not two columns (display %r at %d px)' % (nm, fm.get('disp'), vw))
            # the list panel: right of the top block and level with it, never taller than it, its list scrolling inside it
            if (side.get('left') or 0) < (top.get('right') or 0) or abs((side.get('top') or 0) - (top.get('top') or 0)) > 2:
                fails.append('%s: the strategy list panel is not beside the top block at %d px (panel left %s top %s, top block right %s top %s)'
                             % (nm, vw, side.get('left'), side.get('top'), top.get('right'), top.get('top')))
            if (side.get('h') or 0) > (top.get('h') or 0) + 2:
                fails.append('%s: the strategy list panel is taller than the top block at %d px (panel %s px, top block %s px) - the list must scroll inside it'
                             % (nm, vw, side.get('h'), top.get('h')))
            if sin.get('pos') != 'absolute' or sin.get('ov') not in ('auto', 'scroll') or (sin.get('bottom') or 0) > (top.get('bottom') or 0) + 2:
                fails.append('%s: the strategy list does not scroll inside its panel at %d px (position %r, overflow %r, its bottom %s, top block bottom %s)'
                             % (nm, vw, sin.get('pos'), sin.get('ov'), sin.get('bottom'), top.get('bottom')))
            # the trades and the own folds run the full width under both columns
            if abs((rest.get('left') or 0) - (top.get('left') or 0)) > 2 or abs((rest.get('right') or 0) - (side.get('right') or 0)) > 2 \
                    or (rest.get('top') or 0) < max(top.get('bottom') or 0, side.get('bottom') or 0) - 1:
                fails.append('%s: the trades list is not full width under both columns at %d px (rest %s..%s from %s; top block from %s, panel right %s, '
                             'bottoms %s / %s)' % (nm, vw, rest.get('left'), rest.get('right'), rest.get('top'), top.get('left'), side.get('right'),
                                                   top.get('bottom'), side.get('bottom')))
            # the drag bar is still there, on the panel
            if fm.get('handle') != 1 or fm.get('handleAll') != 1 or not (fm.get('handleBox') or {}).get('h'):
                fails.append('%s: the drag bar [data-p2side] is not on the strategy list panel at %d px (%s on the panel, %s on the page, %r)'
                             % (nm, vw, fm.get('handle'), fm.get('handleAll'), fm.get('handleBox')))
        else:
            n_narrow += 1
            if fm.get('disp') == 'grid':
                fails.append('%s: under 1100 px the page frame must be one column, it is a grid at %d px' % (nm, vw))
            c_, l_, t_ = byk.get('cal'), byk.get('list'), byk.get('trades')
            if not (c_ and l_ and t_) or c_['top'] + c_['h'] > l_['top'] + 3 or l_['top'] + l_['h'] > t_['top'] + 3:
                fails.append('%s: under 1100 px the strategy list must sit between the calendar and the trades (calendar %r, list %r, trades %r)' % (nm, c_, l_, t_))
        # -- ONE status line, directly under the hero numbers (above the pills), holding the status fold with REFRESH on its line; the hero chip row is empty
        if s.get('statusN') != 1:
            fails.append('%s: %s status lines [data-lgstatus="p2"] on the board, expected exactly one under the hero' % (nm, s.get('statusN')))
        else:
            st = s.get('status') or {}
            if not st.get('fold') or not st.get('refresh'):
                fails.append('%s: the status line does not hold the status fold with REFRESH on its line (%r)' % (nm, st))
            h_, s_, p_ = byk.get('hero'), byk.get('status'), byk.get('pills')
            gap = (s_['top'] - (h_['top'] + h_['h'])) if (h_ and s_) else None
            if st.get('prev') != 'hero' or st.get('next') != 'pills' or not st.get('inTop') or st.get('inHero') or gap is None or gap < -1 or gap > 40 \
                    or not p_ or s_['top'] >= p_['top']:
                fails.append('%s: the status line is not directly under the hero (above the pills) at %d px (after %r, before %r, in the top block %s, inside '
                             'the hero %s, %s px under the hero)' % (nm, vw, st.get('prev'), st.get('next'), st.get('inTop'), st.get('inHero'), gap))
        hc = s.get('heroChips')
        if hc is None or hc.get('kids') or hc.get('txt'):
            fails.append('%s: the hero chip row must be empty since LEDGER step 12 - the status chips are in the status line (%r)' % (nm, hc))
        # -- ONE chart foot under the chart: the caption shown on a laptop, hidden up to 600 px; it no longer rides on the pills row
        if s.get('chartDrawn'):
            if s.get('chartFootN') != 1:
                fails.append('%s: %s chart feet [data-lgchartfoot="p2"] on the board, expected exactly one under the chart' % (nm, s.get('chartFootN')))
            else:
                cf = s.get('chartFoot') or {}
                if not cf.get('inChart') or cf.get('chartBottom') is None or (cf.get('top') or 0) < cf['chartBottom'] - 1:
                    fails.append('%s: the chart foot is not under the chart at %d px (foot top %s, chart bottom %s, in the chart section %s)'
                                 % (nm, vw, cf.get('top'), cf.get('chartBottom'), cf.get('inChart')))
                if vw > 600 and (not cf.get('keyVis') or 'bold line' not in (cf.get('keyTxt') or '')):
                    fails.append('%s: the chart caption (.p2rhkey "bold line = ...") is not shown in the chart foot at %d px (%r)' % (nm, vw, cf))
                if vw <= 600 and cf.get('keyVis'):
                    fails.append('%s: the chart caption shows on a phone (%d px) - it is hidden up to 600 px' % (nm, vw))
        if s.get('keyOnPills'):
            fails.append('%s: the chart caption still rides on the pills row (%s)' % (nm, s.get('keyOnPills')))
        # -- ONE Filters row right after the list header: closed to start, the summary names the case's choices, every old control inside it
        if s.get('filtN') != 1:
            fails.append('%s: %s Filters rows [data-lgfilters="p2"] on the strategy list, expected exactly one' % (nm, s.get('filtN')))
            continue
        fl = s.get('filt') or {}
        n_filt += 1
        if not fl.get('inList') or not fl.get('afterHd'):
            fails.append('%s: the Filters row is not right after the strategy list header (in the list %s, after the header %s)' % (nm, fl.get('inList'), fl.get('afterHd')))
        if 'el_lg_filters_p2' not in (cfg.get('ls') or {}) and (fl.get('exp') != 'false' or fl.get('hidden') is not True):
            fails.append('%s: the Filters row is open to start with (aria-expanded=%r, body hidden=%r) - it starts closed' % (nm, fl.get('exp'), fl.get('hidden')))
        ins, out = fl.get('ins') or {}, fl.get('out') or {}
        if any(ins.get(k) != v for k, v in (('kind', 3), ('sort', 3), ('base', 1))) or (ins.get('fam') or 0) < 2 \
                or any(out.get(k) for k in ('kind', 'fam', 'sort', 'base')):
            fails.append('%s: a filter control is not inside the Filters row (inside %r, elsewhere on the board %r; expected Both / Raw / ML, All + the families, '
                         'Board order / Name / Net and Baselines only)' % (nm, ins, out))
        toks, want_on = _filters_expected(cfg)
        got = [x.strip() for x in (fl.get('sum') or '').split('\u00b7')]
        if len(got) != len(toks) or any(t is not None and g != t for g, t in zip(got, toks)):
            fails.append('%s: the Filters summary reads %r, expected %r (the current choices)' % (nm, fl.get('sum'), ' \u00b7 '.join(t or '(any sort)' for t in toks)))
        fo = fl.get('on') or {}
        bad_on = [k for k, v in want_on.items() if v is not None and fo.get(k) != v]
        if bad_on:
            fails.append('%s: the filter controls do not show the case choices (%s: shown %r, set %r)' % (nm, ', '.join(bad_on), fo, want_on))
    if not n_centred:
        fails.append('step 12: no case drew the page frame narrower than its parent, so its centring could not be judged')
    if not n_wide or not n_narrow:
        fails.append('step 12: the page frame was not judged both from 1100 px (%d cases) and under it (%d cases)' % (n_wide, n_narrow))
    # -- the Filters row opens on a click and shows every control, a control works from the open row, a second click closes it; each state stored
    for nm in ('s11-laptop', 's11-phone', 's11-tablet'):
        f = (cases.get(nm) or {}).get('s12f') or {}
        tag = '%s: the Filters row' % nm
        if not f or f.get('err') or not f.get('btn'):
            fails.append('%s run did not finish (%s)' % (tag, str(f.get('err') or 'no Filters button')[:200]))
            continue
        n_runs += 1
        st, op, cl = f.get('start') or {}, f.get('open') or {}, f.get('closed') or {}
        if st.get('exp') != 'false' or st.get('hidden') is not True:
            fails.append('%s is open to start with (aria-expanded=%r, body hidden=%r) - it starts closed' % (tag, st.get('exp'), st.get('hidden')))
        if op.get('exp') != 'true' or op.get('hidden') or not op.get('vis') or (op.get('ctlN') or 0) < 9 or op.get('ctlVis') != op.get('ctlN'):
            fails.append('%s: a click did not open it and show every control (aria-expanded=%r, hidden=%r, drawn %s, %s of %s controls drawn)'
                         % (tag, op.get('exp'), op.get('hidden'), op.get('vis'), op.get('ctlVis'), op.get('ctlN')))
        if (op.get('trayMax') or 0) > 40:
            fails.append('%s: a filter control tray is %spx tall - its chips are wrapping into a blob again' % (tag, op.get('trayMax')))
        if op.get('ls') != '1' or cl.get('ls') != '0':
            fails.append('%s: the open / closed choice is not stored in localStorage el_lg_filters_p2 (open %r, closed %r)' % (tag, op.get('ls'), cl.get('ls')))
        b1, b2 = f.get('base') or {}, f.get('baseBack') or {}
        if b1.get('on') != 'true' or 'Baselines only' not in (b1.get('sum') or '') or b2.get('on') != 'false' or 'Baselines only' in (b2.get('sum') or ''):
            fails.append('%s: a filter control does not work from the open row (Baselines only on: %r, summary %r; off again: %r, %r)'
                         % (tag, b1.get('on'), b1.get('sum'), b2.get('on'), b2.get('sum')))
        if b1.get('exp') != 'true' or b1.get('hidden') or b2.get('exp') != 'true':
            fails.append('%s did not stay open across a redraw of the board (a filter tap closed it: %r / %r)' % (tag, b1, b2))
        if cl.get('exp') != 'false' or cl.get('hidden') is not True:
            fails.append('%s: a second click did not close it (aria-expanded=%r, body hidden=%r)' % (tag, cl.get('exp'), cl.get('hidden')))
    # -- remembered across a real reload (the step 11 reload run, laptop and phone)
    for tag, nm in (('lap', 'laptop'), ('pho', 'phone')):
        r = (data.get('s11reload') or {}).get(tag) or {}
        if not r or r.get('err'):
            continue                                   # the step 11 judge has listed it already
        seq = (r.get('filtStart'), r.get('filtOpened'), r.get('filtAfter'), r.get('filtClosed'), r.get('filtAfter2'))
        if seq != ('false', 'true', 'true', 'false', 'false') or r.get('lsFiltOpened') != '1' or r.get('lsFiltClosed') != '0':
            fails.append('reload run (%s): the Filters row open / closed is not remembered across a real reload (start, opened, after the reload, closed, after '
                         'the reload = %r; stored %r / %r)' % (nm, seq, r.get('lsFiltOpened'), r.get('lsFiltClosed')))
    return ('%d cases in ONE page frame (max-width %s, centred in %d), %d with the list panel beside the top block, %d in one column; the status line under '
            'the hero, the chart foot under the chart, the Filters row closed in %d cases, %d click runs, remembered across a reload'
            % (n_frames, FRAME_MAX_W, n_centred, n_wide, n_narrow, n_filt, n_runs))


def _cap_trades(fixture):
    """LEDGER step 8: enough older book trades that the list has to stop at its row limit - 70 business days from 2026-07-31
    backwards, three ORB trades a day (so the 200th row falls inside a day and the list must finish that day). Built from
    a real fixture trade; every expectation is recomputed from them, never read off the page."""
    src = next((t for t in fixture['trades'] if t.get('leg') == 'ORB' and t.get('open') is not True), None)
    if src is None:
        return []
    out, day, tz = [], datetime.date(2026, 7, 31), datetime.timezone(datetime.timedelta(hours=-4))
    while len(out) < 210:
        if day.weekday() < 5:
            for k, (hh, usd, side) in enumerate(((10, 250.0, 1), (11, -125.0, -1), (13, 75.5, 1))):
                at = datetime.datetime(day.year, day.month, day.day, hh, 0, tzinfo=tz)
                end = at + datetime.timedelta(seconds=600 + 61 * k)
                out.append(dict(src, id='pt_ORB_cap_%s_%d' % (day.isoformat(), k), side=side,
                                pnl_usd=usd * (1 if len(out) % 2 else -1), pnl_pts=usd / 20.0, open=False,
                                close_day=day.isoformat(), exit_date=day.isoformat(),
                                entryTime=int(at.timestamp()), exitTime=int(end.timestamp()),
                                entryIso=at.isoformat(), exitIso=end.isoformat()))
        day -= datetime.timedelta(days=1)
    return out


def extra_cases(fixture):
    """Cases whose data is built from the fixture at run time: a board with more trades than the list shows at once."""
    return [('cap', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'more': _cap_trades(fixture)})]


# Builds this gate must catch, each made from the CURRENT index.html by one string replacement (so they never go stale the way a
# pinned old commit would): (name, anchor, replacement, what it breaks, text that must appear in the gate failures). A mutant that fails
# for some other reason does not count: the check that should catch it is blind. Anchors are single lines, found exactly once. A mutant
# that has to change two places names a tuple of anchors and a tuple of replacements (each anchor found exactly once, replaced in turn).
MUTANTS = [
    ('frame-missing',
     'return ledgerTradeListHtml({id:ID,view:m.view,rows:m.shown,total:m.closedAll.length,query:m.query,chip:m.chip,',
     'return (function(o){return \'<div class="p2tl-noframe">trades</div>\';})({id:ID,view:m.view,rows:m.shown,total:m.closedAll.length,query:m.query,chip:m.chip,',
     'the NT8 trades list is no longer drawn by the shared frame',
     'not drawn by the shared frame'),
    ('frame-twice',
     "const tradesHtml='<div id=\"nt8-tl\" class=\"p2tlbox\">'+_ntTl.build()+'</div>';",
     "const tradesHtml='<div id=\"nt8-tl\" class=\"p2tlbox\">'+_ntTl.build()+_ntTl.build()+'</div>';",
     'the board draws two trade list frames',
     'shared trade list frames on the NT8 board'),
    ('daynet-wrong',
     'pnl:r=>r.pnl,net:r=>r._unc?0:r.pnl,',
     'pnl:r=>r.pnl,net:r=>(r._unc?0:r.pnl)+1,',
     'a day header net is not the sum of its rows',
     'net reads'),
    ('daynet-counts-uncounted',
     'pnl:r=>r.pnl,net:r=>r._unc?0:r.pnl,',
     'pnl:r=>r.pnl,net:r=>r.pnl,',
     'a day net adds up the trades outside the book as well',
     'net reads'),
    ('daynet-unsigned',
     '\'">\'+ledgerSigned(net)+\'</span>\':\'\')',
     '\'">\'+ledgerMoney(net)+\'</span>\':\'\')',
     'a day header prints its net without a sign',
     'it needs a sign'),
    ('wins-includes-zero',
     "if(chip==='WINS')return p>0;",
     "if(chip==='WINS')return p>=0;",
     'the WINS chip lists a $0 trade as a win',
     'listed under WINS or LOSSES'),
    ('losses-includes-zero',
     "if(chip==='LOSSES')return p<0;",
     "if(chip==='LOSSES')return p<=0;",
     'the LOSSES chip lists a $0 trade as a loss',
     'listed under WINS or LOSSES'),
    ('long-chip-lists-all',
     "if(chip==='LONG')return ledgerTradeSide(t)==='LONG';",
     "if(chip==='LONG')return true;",
     'the LONG chip filters nothing',
     'the LONG chip lists'),
    ('tickbox-missing',
     'const tick=r=>\'<label class="p2tk" title="tick to chart this trade">',
     'const tick=r=>\'\';const tickGone=r=>\'<label class="p2tk" title="tick to chart this trade">',
     'the rows carry no tick box',
     'tick boxes'),
    ('tickall-missing',
     'const allTick=\'<label class="p2tk" title="tick every trade shown">',
     'const allTick=\'\';const allTickGone=\'<label class="p2tk" title="tick every trade shown">',
     'the table header has no tick for every row shown',
     'the tick for every row shown is missing'),
    ('open-count-stale',
     "if(ob){ob.textContent='OPEN '+n+' CHART'+(n===1?'':'S');",
     'if(ob){',
     'the count on OPEN N CHARTS does not follow the ticks',
     'OPEN 1 CHART'),
    ('open-gallery-all',
     'const picked=(window._paperCandleRows||[]).filter(x=>sel.has(x._pid));if(!picked.length)return;',
     'const picked=(window._paperCandleRows||[]).filter(x=>true);if(!picked.length)return;',
     'OPEN N CHARTS opens every trade, not the ticked ones',
     'hand the three ticked trades'),
    ('label-ORB-257-no-hash',
     "m?(m[1]+' #'+m[2]+(m[3]?",
     "m?(m[1]+' '+m[2]+(m[3]?",
     'a strategy without a listed row reads ORB 257 in the trades list, not ORB #257',
     'ORB #257'),
    ('hold-time-wrong-unit',
     'durationSecs:(a>0&&b>=a)?(b-a):null,',
     'durationSecs:(a>0&&b>=a)?(b-a)*1000:null,',
     'the hold time is handed to the shared reader in milliseconds, not seconds',
     'hold reads'),
    ('hold-time-zero-minutes',
     'td:r=>X(durStr(r))}',
     "td:r=>X(Math.floor((r.durationSecs||0)/60000)+'m')}",
     'the hold time divides seconds by 60000 and reads 0m again',
     'hold reads'),
    ('phone-list-too-low',
     '.p2tlbox{margin-top:-2px;',
     '.p2tlbox{margin-top:900px;',
     'the trades list starts a screen lower on a phone',
     'the trade list starts'),
    ('phone-six-cells',
     'const LEDGER_TL_PHONE={time:1,sym:1,side:1,pnl:1,chart:1};',
     'const LEDGER_TL_PHONE={time:1,sym:1,side:1,size:1,pnl:1,chart:1};',
     'a phone row keeps six cells instead of five',
     'a phone row must be five cells'),
    ('phone-ticks-hidden',
     "+'@media (max-width:600px){.p2tl-note,.p2tl-unr,.p2tl-to{display:none}",
     "+'@media (max-width:600px){.p2tk,.p2tl-note,.p2tl-unr,.p2tl-to{display:none}",
     'a phone has no tick boxes, so no trade can be picked for OPEN N CHARTS',
     'tick boxes and'),
    ('phone-table-header-wide',
     '.p2tl-hlong{display:none}.p2tl-hshort{display:inline}',
     '.p2tl-hlong{display:inline}.p2tl-hshort{display:none}',
     'the phone TABLE time heading is long again and the table scrolls sideways inside its box',
     'scrolls sideways inside its own box'),
    ('width-601-800-overflow',
     '.p2tlbox{margin-top:-2px;',
     '.p2tlbox{margin-top:-2px;}@media (min-width:601px) and (max-width:800px){.p2tlbox{min-width:900px}}.p2tlbox{',
     'the page scrolls sideways between 601 and 800 px',
     'the page scrolls sideways at'),
    # Since LEDGER step 9 the SHARED list css hides the points / strategy / slot cells by itself (max-width 920 / 800 / 740 px), so taking out
    # the board's narrow-box rule alone no longer overflows anything at 601-699 px (only the small size cell comes back, and it fits). The
    # build below takes the board's narrow-box rule out AND switches the shared hiding off for the NT8 frame (the rows get all four cells
    # back inside a box below 700 px): the rows then run past the box and the page scrolls sideways (788 px in a 601 px window, measured).
    ('list-rows-overflow-601-699',
     '@container p2tl (max-width:740px){.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-pts,.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-size{display:none}}',
     '@container p2tl (max-width:740px){@media (min-width:601px){.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-pts,.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-strat{display:block!important}.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-slot{display:flex!important}}}',
     'the list rows keep their points, size, strategy and slot cells on a narrow box (the board narrow-box rule is gone and the shared hiding rules are off for the NT8 frame, 601 px and up) and run past it',
     'the page scrolls sideways at'),
    ('page-scrolls-sideways',
     '.p2tlbox{margin-top:-2px;',
     '.p2tlbox{margin-top:-2px;min-width:640px;',
     'the trades list is wider than a phone and the page scrolls sideways',
     'scrolls sideways'),
    ('view-not-remembered',
     "function ledgerTradeViewSet(id,v){try{localStorage.setItem('el_lg_view_'+id,v==='table'?'table':'list');}catch(e){}}",
     'function ledgerTradeViewSet(id,v){}',
     'LIST | TABLE is not remembered',
     'does not switch and stay'),
    ('calendar-pick-no-tick',
     'model().display.forEach(r=>{if(r._cd===ds)sel.add(r.id);});',
     'model().display.forEach(r=>{if(r._cd===ds)void 0;});',
     'a calendar day tap no longer ticks that day rows',
     'a day tap ticked'),
    ('calendar-pick-no-scroll',
     "if(g){g.scrollIntoView({behavior:'smooth',block:'start'});g.classList.remove('lg-flash');",
     "if(g){g.classList.remove('lg-flash');",
     'a calendar day tap no longer scrolls the list to the day header',
     'should scroll the list to the day header'),
    ('cap-cuts-mid-day',
     'while(end<ord.length&&dayAt(end)===dayAt(end-1))end++;',
     '',
     'the 200 row limit cuts in the middle of a day, so that day net is not the whole day',
     'the count reads'),
    ('cap-reach-lost',
     'if(reach)while(end<ord.length&&dayAt(end-1)>reach)end++;',
     '',
     'a calendar tap on a day older than the list reaches nothing',
     'cap: tapping the older day'),
    ('row-click-lost',
     'onRow:id=>{window._ptRowId=id;window._ntPanelId=id;syncPanel();}});',
     'onRow:id=>{window._ntPanelId=id;syncPanel();}});',
     'a row click no longer records the trade id',
     'a row click must record its trade id'),
    ('search-focus-lost',
     "if(keep){const s=document.getElementById(ID+'-search');if(s){s.focus({preventScroll:true});",
     "if(false){const s=document.getElementById(ID+'-search');if(s){s.focus({preventScroll:true});",
     'the search box loses its focus and cursor while it filters',
     'lost its focus or cursor'),
    ('ticks-not-pruned',
     '[...sel].forEach(i=>{if(!have.has(i))sel.delete(i);});',
     '',
     'ticks on rows a filter hides stay counted on OPEN N CHARTS',
     'LONG chip should leave'),
    ('family-chips-missing',
     "chips:m.fams.map(f=>({k:'fam:'+f,label:f})),pnl:r=>r.pnl,",
     'chips:[],pnl:r=>r.pnl,',
     'the board own strategy-family chips are gone',
     'strategy-family chips'),
    ('console-error',
     'const paint=root=>{',
     "const paint=root=>{console.error('probe mutant');",
     'the list logs a console.error while it paints',
     'console.error'),
    # the clean-up of v73.1125: ?oldboards=1 and the previous board are gone, and nothing of them may come back
    ('oldflag-changes-the-board',
     'const _p2Narrow=!LEDGER_FRAME_SIDE||(window.innerWidth||1400)<1100;',
     "const _p2Narrow=!LEDGER_FRAME_SIDE||(window.innerWidth||1400)<1100||location.search.indexOf('old'+'boards=1')>=0;",
     '?oldboards=1 draws the stacked narrow page on a laptop: the page behind the flag is not the plain page',
     'behind ?oldboards=1'),
    ('old-marker-back-in-page',
     "body='<div class=\"p2rh\">'+_p2Head+ledgerFrameHtml({id:'p2',top:_p2Top,side:_p2ListFold,rest:_p2Main,sideW:_p2W})+'</div>';",
     "body='<div class=\"p2rh\">'+_p2Head+ledgerFrameHtml({id:'p2',top:_p2Top,side:_p2ListFold,rest:_p2Main,sideW:_p2W})+'<div id=\"ptrades-wrap\"></div></div>';",
     'a piece of the removed previous trades table (#ptrades-wrap) is back in the page',
     'markers of the removed previous board'),
    ('removed-flag-name-back',
     'const _p2Narrow=!LEDGER_FRAME_SIDE||(window.innerWidth||1400)<1100;',
     'const _p2New=true;const _p2Narrow=!LEDGER_FRAME_SIDE||(window.innerWidth||1400)<1100;',
     'the removed NT8 flag _p2New is defined again (the static lint of removed identifiers must fail)',
     'is back in index.html'),
    ('side-flipped',
     'side:r=>r.type?\'<span class="lg-side \'+(r.type===\'LONG\'?\'long\':\'short\')+\'">\'+r.type+\'</span>\'',
     'side:r=>r.type?\'<span class="lg-side \'+(r.type===\'LONG\'?\'long\':\'short\')+\'">\'+(r.type===\'LONG\'?\'SHORT\':\'LONG\')+\'</span>\'',
     'the side column reads the opposite side',
     'side reads'),
    ('hero-big-off',
     'big:ledgerMoney(_H.net),',
     'big:ledgerMoney(_H.net+5),',
     'the big number no longer equals the BOOK group total',
     'do not agree'),
    ('drawdown-negative',
     "tile('maxdd','Max drawdown',s?ledgerMoney(s.maxDD):'--'",
     "tile('maxdd','Max drawdown',s?ledgerMoney(-s.maxDD):'--'",
     'the shared stats strip prints max drawdown as a negative number',
     'max drawdown reads'),
    ('profit-factor-off',
     "ledgerPfText(s.pf):'--',s&&s.pf!=null",
     "ledgerPfText(s.pf+1):'--',s&&s.pf!=null",
     'the profit factor tile reads a wrong figure',
     'tile reads'),
    ('crowns-gone',
     'const _crownIc=k=>(k in _legCrown)',
     'const _crownIc=k=>(k in {})',
     'no strategy wears its crown',
     'crown drawn on'),
    ('red-cross-on-unrun-leg',
     ":!runs?_engChip('NT n/a','#8a8a8a',",
     ":!runs?_engChip('NT \\u2717','#e24b4a',",
     'a leg NinjaTrader does not run shows a red cross',
     'red NT cross'),
    ('calendar-month-total-wrong',
     'c.v+=+N(t)||0;c.n++;',
     'c.v+=(+N(t)||0)+1;c.n++;',
     'the calendar adds a dollar to every day',
     'the month header reads'),
    ('strategy-switch-dead',
     "s.onclick=ev=>{ev.stopPropagation();_wFlip(s.getAttribute('data-lgsw'));};",
     's.onclick=ev=>{ev.stopPropagation();};',
     'a strategy switch no longer moves the board',
     'switching ORB off moved the big number'),
    ('render-throws',
     'const _nUncounted=_fwdDefs.length+_otherKeys.length;',
     'const _nUncounted=_fwdDefs.length+_otherKeys.length+_probeNoSuchHelper();',
     'the NT8 board throws a ReferenceError while it draws',
     'renderApp threw'),
    ('hero-label-lost',
     "label:'BOOK #'+_bookRun+' \\u00b7 NT8 futures paper',",
     "label:'NT8 futures paper',",
     'the hero no longer says BOOK #463 - NT8 futures paper',
     'the hero label is not BOOK'),
    ('open-money-overlaps',
     '.lg-c-pnl small.p2tl-unr{display:block;',
     '.lg-c-pnl small.p2tl-unr{display:inline;',
     'the unrealised label of an open trade sits beside the money and runs into the points cell',
     'the money overflows its cell'),
    ('calendar-jump-lost',
     '<div class="lg-tl-day" data-lgday="\'+ds+\'">\'+dayHd(ds,ts)',
     '<div class="lg-tl-day">\'+dayHd(ds,ts)',
     'the trade list lost its day markers, so a calendar day tap no longer finds the day to scroll to',
     'the day headers read'),
    # LEDGER step 9: the NT8 trade panel
    ('nt8-panel-missing',
     'onRow:id=>{window._ptRowId=id;window._ntPanelId=id;syncPanel();}});',
     'onRow:id=>{window._ptRowId=id;}});',
     'a click on a trade row no longer opens the trade panel on NT8 (the id is still recorded)',
     'did not open the NT8 trade panel'),
    ('nt8-panel-takes-room-closed',
     'P.layer.remove();',
     "P.layer.style.cssText='position:absolute;top:0;left:100%;width:440px;height:900px;background:transparent;animation:none';",
     'a closed trade panel is parked off to the side instead of leaving the page, so it still takes room',
     'a closed trade panel takes room'),
    ('nt8-esc-dead',
     'if(e.defaultPrevented||e.isComposing||_lgPanelCovered(P.layer))return;',
     'return;',
     'Esc no longer closes the trade panel',
     'Esc did not close the NT8 trade panel'),
    ('nt8-outside-click-dead',
     "if(e.target===layer&&P.down!==false)ledgerTradePanelClose(id,'outside');",
     "if(false)ledgerTradePanelClose(id,'outside');",
     'a click or tap outside the trade panel no longer closes it',
     'outside the NT8 trade panel did not close it'),
    ('nt8-close-button-dead',
     "if(e.target.closest&&e.target.closest('[data-lgpanel-close]')){ledgerTradePanelClose(id,'button');return;}",
     "if(e.target.closest&&e.target.closest('[data-lgpanel-close]')){return;}",
     'the trade panel close button does nothing',
     'close button did not close the NT8 trade panel'),
    ('nt8-tickbox-opens-panel',
     "const skip=e=>!!(e.target&&e.target.closest&&e.target.closest('select,input,textarea,button,a,label,.lg-skip'));",
     'const skip=e=>false;',
     'a click on a tick box (or another control inside a row) opens the trade panel as well',
     'a click on a tick box (or another control in a row) opened'),
    ('nt8-wrong-trade-after-rerender',
     'const spec=panelSpec(String(id));',
     'const spec=panelSpec(String(ledgerTradePanelOf(PID)?((model().display[0]||{id:id}).id):id));',
     'after the list is redrawn the panel shows the first row of the list, not the trade that was opened',
     'the panel shows'),
    ('nt8-open-row-no-panel',
     "const rowOf=id=>{const t=_tSorted.find(x=>String(x.id)===String(id));return t?mk(t):null;};",
     "const rowOf=id=>{const t=_tSorted.find(x=>String(x.id)===String(id)&&x.open!==true);return t?mk(t):null;};",
     'the OPEN NOW row (a trade still open) opens no panel',
     'OPEN NOW row'),
    ('nt8-open-row-shows-net',
     "tag:r._open?'OPEN':(r._unc?'NOT BOOK':''),net:r._open?null:(+r.pnl||0)});",
     "tag:r._open?'OPEN':(r._unc?'NOT BOOK':''),net:(+r.pnl||0)});",
     'the panel of a trade still open shows its unrealised mark as a net',
     'must show no net'),
    ('nt8-panel-net-unsigned',
     "tag:r._open?'OPEN':(r._unc?'NOT BOOK':''),net:r._open?null:(+r.pnl||0)});",
     "tag:r._open?'OPEN':(r._unc?'NOT BOOK':''),net:r._open?null:Math.abs(+r.pnl||0)});",
     'the panel header shows a loser as a gain (the sign is lost)',
     'the panel net reads'),
    ('nt8-mono-hue-in-panel',
     "+'.lg-panel[data-lgpanel=\"nt8\"] .p2pn-hint{margin:0 0 8px;font-size:10px;line-height:1.6;color:var(--text3)}'",
     "+'.lg-panel[data-lgpanel=\"nt8\"] .p2pn-hint{margin:0 0 8px;font-size:10px;line-height:1.6;color:#7ac0ff}'",
     'a line in the NT8 part of the panel carries a hard-coded blue, so MONO is no longer hue-free',
     'in MONO the panel carries a colour with a hue'),
    ('nt8-panel-stays-when-trade-gone',
     "if(!spec){window._ntPanelId=null;ledgerTradePanelClose(PID,'gone');return;}",
     'if(!spec)return;',
     'the panel stays open on a trade that has left the board rows',
     'did not close when its trade left the list'),
    ('nt8-panel-stays-when-board-left',
     "try{if(!(activeTab==='augur'&&(augurSub==='paper2'||augurSub==='paper')))ledgerTradePanelClose('nt8','leave');}catch(e){}",
     '',
     'the panel stays on the page when the NT8 board is left',
     'leaving the NT8 board did not close its trade panel'),
    ('nt8-notes-editable',
     "return '<div class=\"p2pn-hint\" data-ntpnotes>NT8 PAPER keeps no notes.",
     "return '<textarea class=\"p2pn-ta\"></textarea><div class=\"p2pn-hint\" data-ntpnotes>NT8 PAPER keeps no notes.",
     'the notes slot has a box to type in, although NT8 keeps no notes',
     'editable control'),
    ('nt8-gallery-button-does-not-tick',
     'const sel=SEL();sel.add(r.id);',
     'const sel=SEL();',
     'OPEN IN GALLERY opens the gallery without ticking the trade on the list',
     'should tick this trade on the list first'),
    ('nt8-expand-missing',
     'class=\"p2pn-chip\" data-ntpexpand title',
     'class=\"p2pn-chip\" data-ntpexpandx title',
     'the chart slot has no EXPAND button',
     'the chart slot should have TRADE, FULL'),
    ('nt8-chart-chips-missing',
     '<button type=\"button\" class=\"p2pn-chip\" data-ntpz=\"trade\" title=\"frame the held window\">TRADE</button>',
     '',
     'the chart slot has no TRADE chip',
     'the chart slot should have TRADE, FULL'),
    ('nt8-cum-wrong',
     'run+=(+x.pnl||0);if(x.id===r.id)out=run;',
     'run+=(+x.pnl||0)+1;if(x.id===r.id)out=run;',
     'the panel CUM adds a dollar to every trade',
     'CUM reads'),
    ('nt8-slip-sign-flipped',
     "(sl>0?'lg-down':(sl<0?'lg-up':'lg-flat'))]",
     "(sl>0?'lg-up':(sl<0?'lg-down':'lg-flat'))]",
     'the panel colours a slip against us as a gain',
     'SLIP reads'),
    ('nt8-hold-in-wrong-unit',
     "['Hold',r._open?(X(durStr(r))+' so far'):X(durStr(r))],",
     "['Hold',r._open?(X(durStr(r))+' so far'):X(Math.floor((r.durationSecs||0)/60000)+'m')],",
     'the panel hold time divides seconds by 60000 and reads 0m',
     'numbers row Hold reads'),
    ('nt8-panel-in-the-page',
     'document.body.appendChild(layer);',
     "(document.getElementById('app')||document.body).appendChild(layer);",
     'the trade panel is put inside the page that every board redraw rebuilds',
     'the panel is inside #app'),
    ('nt8-phone-sheet-missing',
     '.lg-panel{top:auto;left:0;right:0;width:100%;max-height:88vh;',
     '.lg-panel{top:0;left:auto;right:0;width:440px;max-height:none;',
     'on a phone the trade panel is still a 440 px panel on the right instead of a bottom sheet',
     'on a phone the panel should be a bottom sheet'),
    ('nt8-panel-slot-order-wrong',
     "const LEDGER_PANEL_SLOTS=['chart','numbers','notes','actions'];",
     "const LEDGER_PANEL_SLOTS=['actions','chart','numbers','notes'];",
     'the trade panel slots come out in another order',
     'the panel slots come in the order'),
    ('nt8-chip-hues-fixed',
     ".replace(/#4a9edb/g,'var(--blue)').replace(/#e0a33a/g,'var(--yellow)').replace(/#8a8a8a/g,'var(--text4)')",
     '',
     'the EL / NT / TV chips in the panel keep their fixed blue and amber, so MONO is no longer hue-free',
     'in MONO the panel of the'),
    ('nt8-gallery-bars-by-position',
     "m.display.forEach(r=>{crow.push(crowOf(r,pno(r)));});",
     "m.display.forEach((r,i)=>{crow.push(crowOf(r,'P'+i));});",
     'the chart rows (CHART pill, gallery, viewer) key their bars by the place in the list, so after a chip, a search or a sort the chart draws another trade',
     'drew the bars of another trade'),
    ('nt8-chart-pill-bars-by-position',
     "x=rows.find(q=>String(q._pid)===key);",
     "x0=rows.find(q=>String(q._pid)===key),x=x0&&Object.assign({},x0,{_no:'P'+rows.indexOf(x0)});",
     'the CHART pill caches its bars by the place of its row in the list',
     'CHART pill drew the bars of another trade'),
    ('nt8-open-n-charts-bars-by-position',
     "const picked=(window._paperCandleRows||[]).filter(x=>sel.has(x._pid));if(!picked.length)return;",
     "const picked=(window._paperCandleRows||[]).filter(x=>sel.has(x._pid)).map(x=>Object.assign({},x,{_no:'P'+(window._paperCandleRows||[]).indexOf(x)}));if(!picked.length)return;",
     'OPEN N CHARTS caches the bars of its ticked trades by their place in the list',
     'OPEN N CHARTS gallery drew the bars of another trade'),
    # ---- LEDGER step 11: the fixed page order, the own folds, one set of breakpoints, the previous board unchanged ----
    ('section-order-wrong',
     "stats:_p2Sec('stats',_pnUi.strip),more:_p2Sec('more',_pnUi.more),cal:_p2Sec('cal',_pnUi.cal)};",
     "stats:_p2Sec('stats',_pnUi.strip),more:_p2Sec('cal',_pnUi.cal),cal:_p2Sec('more',_pnUi.more)};",
     'the calendar fold comes before the More stats fold',
     'the page sections run'),
    ('pills-under-chart',
     'const _P2_PILLS_FIRST=true;',
     'const _P2_PILLS_FIRST=false;',
     'the range pills sit under the chart instead of between the hero and the chart',
     'the page sections run'),
    ('list-below-trades',
     "body='<div class=\"p2rh\">'+_p2Head+ledgerFrameHtml({id:'p2',top:_p2Top,side:_p2ListFold,rest:_p2Main,sideW:_p2W})+'</div>';",
     "body='<div class=\"p2rh\">'+_p2Head+ledgerFrameHtml({id:'p2',top:_p2Top,side:'',rest:_p2Main+_p2ListFold,sideW:_p2W})+'</div>';",
     'on a page narrower than two columns the strategy list comes after the trades and the own folds',
     'the page sections run'),
    ('own-folds-above-trades',
     "const _p2Main=_p2Sec('trades',tradesHtml)+_p2Cards;",
     "const _p2Main=_p2Cards+_p2Sec('trades',tradesHtml);",
     'the own folds are drawn above the trades list',
     'the page sections run'),
    ('own-section-removed',
     "+_p2Fold('reports','Daily reports',_p2SumRep,reportsHtml)",
     '',
     'the daily reports section is gone from the board',
     'the folds on the board read'),
    ('fold-summary-empty',
     "+_p2Fold('nt','NinjaTrader \\u00b7 detail',_p2Xs(_p2SumNt),bridgeHtml)",
     "+_p2Fold('nt','NinjaTrader \\u00b7 detail','',bridgeHtml)",
     'the NinjaTrader detail fold has no summary line',
     'has no summary line'),
    ('fold-summary-stray-markup',
     "+_p2Fold('recon','Cross-engine \\u00b7 do they agree?',_p2Xs(_p2SumRec),reconcileHtml)",
     "+_p2Fold('recon','Cross-engine \\u00b7 do they agree?',_p2Xs(_p2Xs(_p2SumRec+' <b>')),reconcileHtml)",
     'the cross-engine summary shows escaped markup as text',
     'stray markup'),
    ('fold-summary-two-lines',
     ".p2fold-sum{flex:0 1 auto;min-width:0;text-transform:none;",
     ".p2fold-sum{max-width:70px;white-space:normal!important;flex:0 1 auto;min-width:0;text-transform:none;",
     'the summary of a fold wraps onto several lines',
     'the summary must stay on one line'),
    ('fold-does-not-open',
     "p2FoldApply(el,el.getAttribute('aria-expanded')!=='true')",
     "p2FoldApply(el,false)",
     'a click on a fold header never opens it',
     'a click did not open it'),
    ('fold-not-remembered',
     "try{localStorage.setItem('el_lg_'+key+'_nt8',on?'1':'0');}catch(e){}",
     "try{}catch(e){}",
     'the open / closed choice of a fold is not written to localStorage',
     'is not remembered'),
    ('fold-body-empty',
     "+_p2Fold('gate','Did the gate do its job?',_p2SumGate,gateAuditInner)",
     "+_p2Fold('gate','Did the gate do its job?',_p2SumGate,'')",
     'the gate audit fold opens on nothing',
     'has an empty body'),
    ('fold-open-by-default',
     'const on=p2FoldGet(key,o.open);',
     'const on=p2FoldGet(key,true);',
     'every fold starts open',
     'to start with'),
    ('phone-list-fold-open',
     "{cls:'p2fold-list',open:(window.innerWidth||1400)>600}",
     "{cls:'p2fold-list',open:true}",
     'the strategy list fold starts open on a phone, so the trades start a screen lower',
     'the trade list starts'),
    ('phone-folds-push-list-down',
     '.p2fold-row{display:flex;align-items:flex-start;gap:8px;min-width:0}',
     '.p2fold-row{display:flex;align-items:flex-start;gap:8px;min-width:0;min-height:260px}',
     'the closed folds above the trades take a screen of room on a phone',
     'the trade list starts'),
    ('private-breakpoint',
     "'.p2cw{position:relative;margin:12px 0 22px}'",
     "'.p2cw{position:relative;margin:12px 0 22px}@media (max-width:933px){.p2cw{margin-bottom:20px}}'",
     'the board brings a width of its own (933 px)',
     'outside the house set'),
    ('private-container-width',
     '@container p2tl (max-width:920px)',
     '@container p2tl (max-width:899px)',
     'the trade list narrow-box rule steps at a width of its own (899 px)',
     'outside the house set'),
    ('calendar-default-private-width',
     "if(v==='1'||v==='0')return v==='1';return (window.innerWidth||1200)>600;})();",
     "if(v==='1'||v==='0')return v==='1';return (window.innerWidth||1200)>=760;})();",
     'the calendar opens by default from 760 px instead of above 600',
     'the calendar fold is'),
    ('mono-hue-in-fold',
     "'.p2fold-sum b{font-weight:700;color:var(--text)}'",
     "'.p2fold-sum b{font-weight:700;color:#3fb88a}'",
     'a fold summary is drawn in a fixed green, so MONO is no longer hue-free',
     'MONO has a hue'),
    ('mono-chip-dot-hue',
     """'[data-theme="mono"] .p2rh .p2dot[style*="e0a33a"]{background:var(--text2)!important}'""",
     "''",
     'the amber dots of the status chips keep their hue in MONO',
     'MONO has a hue'),
    ('warning-count-dropped',
     "[/^Reconcile: (\\d+) problems?$/,'Recon $1']",
     "[/^Reconcile: (\\d+) problems?$/,'Recon']",
     'the status line says Recon but not how many problems',
     'lost the reconcile warning count'),
    ('warning-chips-lost',
     "'<div class=\"p2chips\">'+_p2Status+_p2WarnChips+'</div>'",
     "'<div class=\"p2chips\">'+_p2Status+'</div>'",
     'the warning chips are gone from the status fold',
     'the warning chips are not inside the status line'),
    ('refresh-missing',
     "{cls:'p2fold-status',sec:false,tip:tip,act:rf}",
     "{cls:'p2fold-status',sec:false,tip:tip}",
     'REFRESH is gone from the status line',
     'REFRESH'),
    ('refresh-folded',
     "'<div class=\"p2chips\">'+_p2Status+_p2WarnChips+'</div>',{cls:'p2fold-status',sec:false,tip:tip,act:rf}",
     "'<div class=\"p2chips\">'+_p2Status+_p2WarnChips+rf+'</div>',{cls:'p2fold-status',sec:false,tip:tip}",
     'REFRESH is inside the closed status fold',
     'REFRESH is folded away'),
    # ---- LEDGER step 12: ONE page frame, the status line under the hero, the chart foot, the Filters row of the strategy list ----
    ('frame-full-width',
     '.lg-frame{max-width:1320px;margin:0 auto;box-sizing:border-box}',
     '.lg-frame{max-width:none;margin:0 auto;box-sizing:border-box}',
     'the shared page frame has no max width any more: NT8 runs the full width of the window again',
     'the page frame is not at most 1320px wide'),
    ('frame-not-centred',
     '.lg-frame{max-width:1320px;margin:0 auto;box-sizing:border-box}',
     '.lg-frame{max-width:1320px;margin:0;box-sizing:border-box}',
     'the shared page frame sits on the left of a wide window instead of in the middle',
     'the page frame is not centred'),
    ('list-under-calendar-on-laptop',
     'const LEDGER_FRAME_SIDE=true;',
     'const LEDGER_FRAME_SIDE=false;',
     'from 1100 px the strategy list is no longer the right-hand panel: it stays under the calendar',
     'from 1100 px the strategy list must be the right-hand panel'),
    ('list-not-in-side-panel',
     ("body='<div class=\"p2rh\">'+_p2Head+ledgerFrameHtml({id:'p2',top:_p2Top,rest:_p2Main,sideW:_p2W,attr:'data-p2grid=\"right\"',",
      "side:'<div data-p2col=\"side\" data-p2sec=\"list\" style=\"min-width:0\">'+_p2Rail+'</div>'})"),
     ("body='<div class=\"p2rh\">'+_p2Head+ledgerFrameHtml({id:'p2',top:_p2Top,rest:_p2Main+'<div data-p2col=\"side\" data-p2sec=\"list\" style=\"min-width:0\">'+_p2Rail+'</div>',sideW:_p2W,attr:'data-p2grid=\"right\"',",
      "side:''})"),
     'on a laptop the strategy list is drawn in the rest of the frame (under the own folds), not in its right-hand panel',
     'the strategy list is not in the frame side panel'),
    ('grid-under-1100',
     '.lg-frame-top,.lg-frame-side,.lg-frame-side-in,.lg-frame-rest{min-width:0}',
     '.lg-frame-top,.lg-frame-side,.lg-frame-side-in,.lg-frame-rest{min-width:0}@media (min-width:601px) and (max-width:1099px){.lg-frame.lg-frame-2{display:grid;grid-template-columns:minmax(0,1fr) 260px;column-gap:20px;align-items:start}.lg-frame-2>.lg-frame-top{grid-column:1;grid-row:1}.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1}.lg-frame-2>.lg-frame-rest{grid-column:1/-1;grid-row:2}}',
     'the frame is a two-column grid below 1100 px as well, so a tablet page puts the list beside the calendar',
     'under 1100 px the page frame must be one column'),
    ('list-panel-sticky',
     '.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1;align-self:stretch;position:relative;min-height:320px}',
     '.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1;align-self:start;position:sticky;top:6px;height:320px;min-height:320px}',
     'the strategy list panel is sticky again instead of sitting level with the top block',
     'the strategy list panel is sticky'),
    ('list-panel-taller',
     '.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1;align-self:stretch;position:relative;min-height:320px}',
     '.lg-frame-2>.lg-frame-side{grid-column:2;grid-row:1;align-self:stretch;position:relative;min-height:4000px}',
     'the strategy list panel is taller than the top block and pushes the trades down',
     'the strategy list panel is taller than the top block'),
    ('list-not-scrolling-inside',
     '.lg-frame-2>.lg-frame-side>.lg-frame-side-in{position:absolute;top:6px;left:0;right:0;bottom:24px;overflow-y:auto;',
     '.lg-frame-2>.lg-frame-side>.lg-frame-side-in{position:static;top:6px;left:0;right:0;bottom:24px;overflow-y:visible;',
     'the strategy list no longer scrolls inside its panel: a long list makes the panel (and the page) taller',
     'the strategy list does not scroll inside its panel'),
    ('trades-not-full-width',
     '.lg-frame-2>.lg-frame-rest{grid-column:1/-1;grid-row:2}',
     '.lg-frame-2>.lg-frame-rest{grid-column:1;grid-row:2}',
     'the trades list and the own folds stay in the left column instead of running the full width under both',
     'the trades list is not full width under both columns'),
    ('drag-bar-lost',
     "handle:'<div data-p2side title=",
     "handle:'<div data-p2sidegone title=",
     'the drag bar that sets the width of the strategy list panel is gone',
     'the drag bar [data-p2side] is not on the strategy list panel'),
    ('status-under-chart',
     'const LEDGER_STATUS_UNDER_HERO=true;',
     'const LEDGER_STATUS_UNDER_HERO=false;',
     'the status line sits under the chart instead of directly under the hero',
     'the status line is not directly under the hero'),
    ('status-in-hero-chips',
     ("chips:''});", 'status:_p2StatFold,'),
     ('chips:_p2StatFold});', "status:'',"),
     'the status fold is back in the hero chip row (as in step 11) instead of the status line under the hero',
     'the status line is not directly under the hero'),
    ('hero-chips-not-empty',
     "chips:''});",
     'chips:_p2WarnChips});',
     'the warning chips are drawn in the hero chip row again (as well as in the status line)',
     'the hero chip row must be empty'),
    ('chart-foot-missing',
     'if(_rhN)return \'<div data-p2sec="chart"><div class="p2cw" id="p2-chart"></div>\'+_rhFoot+\'</div>\';',
     'if(_rhN)return \'<div data-p2sec="chart"><div class="p2cw" id="p2-chart"></div></div>\';',
     'the chart has no shared chart foot (and no caption) under it',
     'chart feet [data-lgchartfoot="p2"]'),
    ('chart-foot-above-chart',
     'if(_rhN)return \'<div data-p2sec="chart"><div class="p2cw" id="p2-chart"></div>\'+_rhFoot+\'</div>\';',
     'if(_rhN)return \'<div data-p2sec="chart">\'+_rhFoot+\'<div class="p2cw" id="p2-chart"></div></div>\';',
     'the chart foot is drawn above the chart',
     'the chart foot is not under the chart'),
    ('chart-caption-hidden',
     '@media (max-width:600px){.p2rh .p2rhkey{display:none}',
     '.p2rh .p2rhkey{display:none}@media (max-width:600px){.p2rh .p2rhkey{display:none}',
     'the chart caption (bold line = ...) is hidden on a laptop too',
     'is not shown in the chart foot'),
    ('chart-caption-on-phone',
     '@media (max-width:600px){.p2rh .p2rhkey{display:none}',
     '@media (max-width:600px){.p2rh .p2rhkeygone{display:none}',
     'the chart caption shows on a phone, where it is hidden up to 600 px',
     'the chart caption shows on a phone'),
    ('caption-back-on-pills',
     "const _rhTabs='<div class=\"p2ctl\" data-p2range data-p2sec=\"pills\">'+ledgerRangePillsHtml(_pcw,'data-pcwin')+'</div>';",
     "const _rhTabs='<div class=\"p2ctl\" data-p2range data-p2sec=\"pills\">'+ledgerRangePillsHtml(_pcw,'data-pcwin')+'<span class=\"p2rhkey\">bold line = the book legs together</span></div>';",
     'the chart caption rides on the pills row again',
     'the chart caption still rides on the pills row'),
    ('filters-open-by-default',
     'const LEDGER_FILTERS_OPEN=false;',
     'const LEDGER_FILTERS_OPEN=true;',
     'the Filters row of the strategy list starts open',
     'the Filters row is open to start with'),
    ('filters-control-lost',
     "+'<div class=\"p2pills\"><span class=\"p2pill'+(PBASE?' on':'')+'\" data-pbase role=\"switch\"",
     "+'<div class=\"p2pills\"><span class=\"p2pill'+(PBASE?' on':'')+'\" data-pbasegone role=\"switch\"",
     'the Baselines only pill is dropped from the Filters row',
     'a filter control is not inside the Filters row'),
    ('filters-not-after-header',
     ("filters:ledgerFiltersHtml({id:'p2',sum:_pnX(_pnFiltSum),body:_pnFilt}),", 'foot:_pnFoot})'),
     ("filters:'',", "foot:ledgerFiltersHtml({id:'p2',sum:_pnX(_pnFiltSum),body:_pnFilt})+_pnFoot})"),
     'the Filters row sits at the foot of the strategy list instead of right after its header',
     'the Filters row is not right after the strategy list header'),
    ('filters-summary-stale',
     "const _pnFiltSum=[{ALL:'Both',RAW:'Raw',ML:'ML'}[PKIND]||PKIND,",
     "const _pnFiltSum=['Both',",
     'the Filters summary says Both whatever Raw / ML is set to',
     'the Filters summary reads'),
    ('filters-dont-open',
     "const id=b.getAttribute('data-lgfilt'),on=b.getAttribute('aria-expanded')!=='true';",
     "const id=b.getAttribute('data-lgfilt'),on=false;",
     'a click on the Filters row never opens it',
     'a click did not open it and show every control'),
    ('filters-not-remembered',
     '  ledgerFiltersSet(id,on);',
     '  void 0;',
     'the open / closed choice of the Filters row is not stored',
     'is not stored in localStorage el_lg_filters_p2'),
    ('filters-open-not-read-back',
     'const open=o.open!=null?!!o.open:ledgerFiltersOpen(id),has=!!o.body;',
     'const open=o.open!=null?!!o.open:!!LEDGER_FILTERS_OPEN,has=!!o.body;',
     'the stored Filters choice is never read back: a filter tap (a redraw) or a reload closes the open row',
     'did not stay open across a redraw of the board'),
    ('mono-hue-in-filters',
     '.lg-filters-sum{flex:1 1 auto;min-width:0;letter-spacing:.3px;text-transform:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
     '.lg-filters-sum{flex:1 1 auto;min-width:0;letter-spacing:.3px;text-transform:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#3fb88a}',
     'the Filters summary is drawn in a fixed green, so MONO is no longer hue-free',
     'MONO has a hue'),
]


def _selftest_one(path):
    """One pass of the probe over a built copy. Other sessions render on this machine too, so a pass that comes back INCONCLUSIVE (a
    Chrome that timed out or died under load) is tried again, up to three times, with a longer wait."""
    code, lines = run(path, 420)
    for _ in range(2):
        if code != INCONCLUSIVE:
            break
        code, lines = run(path, 420)
    return code, lines


def selftest(jobs=3, only=None):
    """Exit 0 when the gate FAILS every MUTANT of the current index.html - each one for the reason it names - and PASSES the real
    file; 1 when an expectation breaks; 2 when a mutant cannot be built (its anchor moved). only = a comma separated list of mutant
    names: render just those (and skip the pass on the real file) - for quick work on a few checks; the full run is the gate."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='paperprobe-selftest-')
    todo = []
    only_set = set(x.strip() for x in only.split(',') if x.strip()) if only else None
    try:
        if only_set is not None and only_set - set(m[0] for m in MUTANTS):
            print('SELFTEST: INCONCLUSIVE -- no such mutant: %s' % ', '.join(sorted(only_set - set(m[0] for m in MUTANTS))))
            return INCONCLUSIVE
        for name, anchor, repl, why, expect in MUTANTS:
            if only_set is not None and name not in only_set:
                continue
            built = src
            for a_, r_ in (zip(anchor, repl) if isinstance(anchor, tuple) else [(anchor, repl)]):
                n = built.count(a_)
                if n != 1:
                    print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in index.html (expected once). '
                          'Update MUTANTS in tools/paper_render_probe.py: %r' % (name, n, a_))
                    return INCONCLUSIVE
                built = built.replace(a_, r_)
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(built)
            todo.append((name, why, expect, path))
        if only_set is None:
            todo.append(('(current index.html)', 'the real file must PASS', None, None))
        bad, unrendered = [], []

        def judge(t, code, lines):
            name, why, expect, path = t
            first = lines[0] if lines else '(no output)'
            if code == INCONCLUSIVE:             # Chrome never produced a readout (three tries): says nothing about the gate
                print('-- %s: could not be rendered (%s)' % (name, first[:120]), flush=True)
                unrendered.append(name)
                return
            if path is None:
                print('-- current index.html: %s' % first, flush=True)
                if code != PASS:
                    bad.append('the current index.html did not PASS (exit %d): %s' % (code, ' | '.join(lines[:3])))
                return
            hit = [l.strip() for l in lines if expect in l]
            if code != FAIL:
                print('-- mutant %s: NOT CAUGHT (exit %d)' % (name, code), flush=True)
                bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s' % (name, code, why))
            elif not hit:
                print('-- mutant %s: caught, but not for the reason it names' % name, flush=True)
                bad.append('mutant %s failed the gate, but %r is in none of its failures -- the check that should catch "%s" is blind: %s'
                           % (name, expect, why, ' | '.join(l.strip() for l in lines[1:3])))
            else:
                print('-- mutant %s: caught -- %s' % (name, ' '.join(hit[0].split())[:150]), flush=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            futs = dict((ex.submit(_selftest_one, t[3]), t) for t in todo)
            for f in concurrent.futures.as_completed(futs):       # each verdict is printed as soon as its build has been rendered
                try:
                    code, lines = f.result()
                except Exception as e:                       # a crash is not a catch
                    code, lines = INCONCLUSIVE, ['SELFTEST: the pass crashed: %s' % e]
                judge(futs[f], code, lines)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL (%.1fs)' % (time.time() - t0))
        for b in bad:
            print('  - ' + b)
        return FAIL
    if unrendered:
        print('SELFTEST: INCONCLUSIVE -- %d build(s) could not be rendered (Chrome timed out under load): %s' % (len(unrendered), ', '.join(unrendered)))
        return INCONCLUSIVE
    if only_set is not None:
        print('SELFTEST (only %d mutants): PASS -- each caught for the reason it names (%.1fs)' % (len(todo), time.time() - t0))
        return PASS
    print('SELFTEST: PASS -- gate caught %d/%d broken builds, each for the reason it names, and passed the current one (%.1fs)'
          % (len(MUTANTS), len(MUTANTS), time.time() - t0))
    return PASS


def main(argv=None):
    try:                       # leg labels carry non-ASCII; a cp1252 console must not crash the gate
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every MUTANT of index.html, each for the reason it names, then PASS on the real file')
    ap.add_argument('--jobs', type=int, default=4, help='--selftest: how many broken builds are rendered side by side (default 4)')
    ap.add_argument('--only', default=None, help='with --selftest: only these mutants (comma separated names), and skip the pass on the current file')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args.jobs, args.only)
    alt = os.path.abspath(args.file) if args.file else None
    if alt and not os.path.isfile(alt):
        print('PAPERPROBE: INCONCLUSIVE -- --file not found: %s' % alt)
        return INCONCLUSIVE
    code, lines = run(alt)
    for ln in lines:
        print(ln)
    return code


if __name__ == '__main__':
    sys.exit(main())
