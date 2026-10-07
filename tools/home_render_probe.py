#!/usr/bin/env python3
"""
tools/home_render_probe.py -- render gate for HOME > REAL (the trading log's landing view).

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS, and the other render probes prove STUDIES,
PAPER, the run report, COMPARE beta and the importer draw. None of them ever opens HOME, which
is the view the owner lands on every time, on a laptop and on a phone. HOME grew a lot in
v73.96x-v73.97x (SHOULD HAVE TRADED list and form, the paste box, EL's own chart in the trade
panel with pan / zoom, the POINTS block) and every one of those paths could throw behind a green
boot gate.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe exactly as the boot gate does, waits
for the signed-out screen and keeps it off the page, then seeds HOME's globals the way the
Firestore listeners would: seven synthetic trades (six futures MNQ / MES on 1m, 10s, 5m and
"10s, 1m" with ps1.1 point scores - full, partial, all-NA and none - plus one stock trade) and,
per case, zero or two SHOULD HAVE TRADED entries. Nothing touches the network: the trade-bars
reader is fed through its own test hook (window._rtBarsSource) with synthetic packed bars in the
api/trade_bars.py _pack shape, and window._missedRef / colRef are in-memory stubs that only record
writes. requestAnimationFrame is replaced with a 0 ms timer, since a headless page may never run
animation frames.

Every case is its own fresh render (all HOME state reset, then renderApp()). After the 24+ cases and the two interaction runs the
same index.html is loaded three times more: with ?oldboards=1 (a flag that changes nothing any more), for the shared trade panel (PANEL_CASES,
LEDGER unify step 9) and for the width sweep (WIDTH_RUNS, the step 8 follow-up):
  viewport  laptop 1366x768 | phone 375x812        (the iframe IS the viewport)
  theme     glass (the owner's dark theme) | paper (light), via prefs.theme + applyTheme()
  missed    no entries | two (an MNQ entry with a point score, a stock entry)
  ledger    TABLE + SIMPLE | TABLE + FULL | FEED
= 24 cases. Then two interaction runs, one laptop (glass) and one phone (paper).

WHAT IT ASSERTS
---------------
Per case:
  * renderApp returned, and no uncaught exception, unhandled rejection or console.error
  * window._loadError never fired and no LOAD ERROR overlay is on the page
  * #hm-missed exists, with one row per SHOULD HAVE TRADED entry
  * the ledger exists with one row per seeded trade (SIMPLE / FULL table, or the feed)
  * on a phone the page does not scroll sideways (scrollWidth <= clientWidth + 1)
  * LEDGER step 8, the shared trade list frame ([data-lglist-frame="hm"]): exactly one frame, in the right mode
    (list / table), the chips ALL LONG SHORT WINS LOSSES FUTURES STOCKS, the LIST | TABLE toggle with the right half
    pressed, a search box, a count, one day header [data-lgday] per CLOSE day with a signed net that adds up to the
    trades' own P&L (an overnight trade sits under the day it closed), one row per trade, the PASTE box, and on a
    phone five cells per row with the list starting within ONE screen of the top of the board (mistake #12)
  * rows come out newest close first, a deposit sits in its day under BY TRADE, the AI ASSESSMENT is a closed fold, the
    account list is one line on a phone (a list on a laptop), and the SIMPLE table fits its box with no sideways scroll
  * the legacy TRADES and JOURNAL tabs (?oldtabs=1) draw on a phone without scrolling the page sideways (mistake #14)
  * ?oldboards=1 (a second page load) draws the NEW board like the plain page: the shared trade list frame, the page sections in the fixed
    order, the same markup digest as the matching plain case, none of the removed previous board's markers (#hm-sheet, the FEED / TABLE
    button, the old chips, ...) and no LEDGER_OLDBOARDS name left in the page
  * static lint (tools/ledger_removed.py): none of the identifiers the clean-up removed is back in index.html
  * LEDGER step 9: while nothing is open the shared trade panel is not in the page at all (no node, no layer)
Per trade panel case (a third page load: laptop 1366x768 and phone 375x812, glass / paper / MONO, PANEL_CASES):
  * a click on a row of the list opens the shared trade panel ([data-lgpanel="hm"]) with that trade's symbol, side tag and signed net
    (coloured by the lg-up / lg-down token); on a laptop it is a right-hand panel (380-460 px, the full height), on a phone a bottom
    sheet (full width, on the bottom edge, at most 90% of the height so a strip of page is left to tap); its slots come in the fixed
    order head, chart, (IGNORE IN METRICS), numbers, notes, actions; it sits in <body>, outside the page every redraw rebuilds
  * a CLOSED panel is not in the page: after Esc, a tap outside and the close button the page is exactly as wide and tall as
    before the first open and <body> holds the same elements (no leftover node, no reserved column or height)
  * Esc, a tap outside and the close button each close it, a tap inside does not; focus moves into it; a click on a control inside
    a TABLE row (the grade select, the notes box) does not open it; DELETE asks first (a no keeps the panel, a yes deletes, and the
    panel closes once the trade is gone from the list); 600 px is still a bottom sheet and 601 px already a right-hand panel
  * the open trade survives a redraw of the list (a search, then cleared) and a LIST | TABLE switch and never shows another
    trade; a note typed meanwhile is still in its box; a note typed and then closed is saved; opening another trade in the open
    panel switches it and saves the first trade's note
  * the grade and setup selects, IGNORE IN METRICS, the notes box, EDIT / OPEN IN TV / DELETE, the POINTS block and the chart
    (with EXPAND on a laptop only) are in it; in MONO no colour in it carries a hue; no sideways scroll at 375; no console.error
Per width sweep (a fourth page load: the LIST, the SIMPLE table and the FULL table, each resized through WIDTH_SET - 375 480 600 601 700 701 741
800 801 860 901 921 975 1000 1011 1200 1366 px - and drawn again at every width; 601 / 741 / 801 / 921 are the widths just above where a list
cell comes back, 701 / 901 / 1011 just above where a SIMPLE column comes back, 860 / 975 sit in the two bands where the SIMPLE table used to
scroll inside its box):
  * the PAGE never scrolls sideways at any of those widths, in any of the three views (scrollWidth <= clientWidth + 1 and <= the window
    width + 1)
  * LIST rows: TIME, SYMBOL, SIDE, NET and the chart icon (and SIZE above 600 px) always stay; the lowest-priority cells go first as the
    window narrows - POINTS, then STRATEGY, then the board's end slot - and a cell that is gone stays gone at every narrower width; from
    1000 px up nothing is hidden; no row is wider than the frame; every seeded trade still has its row
  * the SIMPLE table fits its box at every one of them; the FULL table (26 columns) scrolls inside its own box, never the page
LEDGER unify step 11 (REAL: one page order, own sections as closed folds, one set of breakpoints), per case:
  * the page sections come in the FIXED order top to bottom (SECTION_ORDER: hero, range pills, equity chart, stats strip, More stats, calendar,
    accounts, trade list, then the own folds PASTE, SHOULD HAVE TRADED, DEPOSITS, AI ASSESSMENT, JOURNAL) at every width of every case and of the
    width sweep, each one drawn with a height, all inside the board
  * every own fold ([data-hmfold]) starts CLOSED (no body in the page), carries a non-empty ONE-LINE summary (one line tall, no stray markup, the
    number or state it should show for the seeded data), opens on a click and shows its content (the paste box, the setups and the + ADD button,
    the deposit chips, the AI read, the journal form and entry), and closes again; the phone account line has its summary too
  * on a 375 px phone the trade list starts no lower than the previous build (PHONE_LIST_TOP_MAX) and within one screen
  * the board's own media rules (every @media whose selector names .hm- or #hm- and matches something on the page) use only the house widths
    (HOUSE_WIDTHS: 600 phone, 740 / 800 / 920 list cells, 1100 rail) and the scan has to see some of them (a blind scan fails)
  * MONO (laptop and phone, every fold open): no colour on the board has a hue
  * no marker of the removed previous board (OLD_MARKS: #hm-sheet, .hm-backdrop, the FEED / TABLE button ...) is in the page, in any case
Per fold run (a fifth page load, FOLD_RUNS): every own fold is opened with a click, the page is RELOADED and the same folds are open without a
click; they are closed with a click, the page is reloaded again and they are closed (open / closed remembered per browser in localStorage)
Per interaction run:
  * a futures trade's panel opens, its chart body ends up holding an <svg> and the info line
    is filled in (the chart really drew), and the POINTS block shows the trade's score
  * the chart's - (zoom out) and DAY buttons redraw it without an error
  * a SHOULD HAVE TRADED panel opens with its symbol, POINTS block and chart
  * + ADD opens the form, SAVE with the fields empty shows a message and writes nothing
  * hmFileChartLink(<a TradingView link>) shows the paste note with its SHOULD HAVE TRADED
    button, and that button opens the form with the link filled in
  * nothing was written to the trades or missed_trades stubs
  * the shared frame: each chip lists the right trades (a $0 trade is neither a WINS nor a LOSSES row), the search
    box filters and keeps the cursor, LIST | TABLE is remembered, BY DAY shows one row per day, SIMPLE | FULL
    switches the table; a grade and a note edited in the TABLE reach the database stubs and every row keeps its
    EDIT (opens the edit window) and DELETE cells; the ANALYTICS calendar
    jump (gotoTradesByDate) opens the LEDGER table on that day and flashes its rows; the LEDGER calendar day tap
    flashes that day's header in the list and in the table; a TABLE header menu still sorts (no day headers once
    sorted by NET); the trade panel keeps EDIT / SNAPSHOT / OPEN IN TV / DELETE and edits the grade and the setup;
    the AI ASSESSMENT fold opens and fills

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks). A non-PASS
attempt is rendered once more before it blocks (as in report_render_probe.py); a retry that
passes is printed as a FLAKE line. --no-retry turns that off.

Usage:
  python tools/home_render_probe.py                # gates this repo's index.html
  python tools/home_render_probe.py --file X.html  # gates X as if it were index.html
  python tools/home_render_probe.py --selftest     # builds deliberately broken copies of the
                                                   # current index.html (MUTANTS below), asserts
                                                   # FAIL on each, then PASS on the real file

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import calendar
import http.server
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

VIEWPORTS = {'laptop': [1366, 768], 'phone': [375, 812], 'narrow': [1000, 768], 'edge600': [600, 800], 'edge601': [601, 800]}
THEMES = ['glass', 'paper']
LEDGERS = [('simple', 'table', 'simple'), ('full', 'table', 'full'), ('feed', 'feed', 'simple')]

LEDGER_RANGES = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']    # the shared range pills (LEDGER unify step 4)
CASES = []
for _vp in ('laptop', 'phone'):
    for _th in THEMES:
        for _mi in (0, 2):
            for _nm, _view, _led in LEDGERS:
                CASES.append(['%s/%s/missed%d/%s' % (_vp, _th, _mi, _nm),
                              {'vp': _vp, 'theme': _th, 'missed': _mi, 'view': _view, 'ledger': _led}])

# MONO: no colour on the board may carry a hue (the own folds are opened for it)
for _vp in ('laptop', 'phone'):
    CASES.append(['%s/mono/missed2/feed' % _vp, {'vp': _vp, 'theme': 'mono', 'missed': 2, 'view': 'feed', 'ledger': 'simple'}])
# a narrower laptop window: the SIMPLE table (it fits its box with no sideways scroll) and the list
for _nm, _view, _led in (LEDGERS[0], LEDGERS[2]):
    CASES.append(['narrow/glass/missed0/%s' % _nm, {'vp': 'narrow', 'theme': 'glass', 'missed': 0, 'view': _view, 'ledger': _led}])
# LEDGER unify step 8 / mistake #14: the legacy TRADES and JOURNAL tabs (?oldtabs=1) on a phone
for _th in THEMES:
    for _tab in ('trades', 'journal'):
        CASES.append(['phone/%s/legacy-%s' % (_th, _tab),
                      {'vp': 'phone', 'theme': _th, 'kind': 'legacy', 'tab': _tab, 'missed': 0,
                       'view': 'feed', 'ledger': 'simple'}])
# ?oldboards=1 (a second page load, see _attempt) no longer changes anything: the SIMPLE table and the list on a laptop and a phone must draw the
# same board as the plain page does for the same case (FLAG_PLAIN names that case)
FLAG_CASES = [['flag/%s/%s' % (_vp, _nm), {'vp': _vp, 'theme': 'glass', 'missed': 0, 'view': _view, 'ledger': _led}]
              for _vp in ('laptop', 'phone') for _nm, _view, _led in (LEDGERS[0], LEDGERS[2])]
FLAG_PLAIN = {'flag/%s/%s' % (_vp, _nm): '%s/glass/missed0/%s' % (_vp, _nm)
              for _vp in ('laptop', 'phone') for _nm, _view, _led in (LEDGERS[0], LEDGERS[2])}
FRAME_CHIPS = 'ALL,LONG,SHORT,WINS,LOSSES,FUTURES,STOCKS'
# LEDGER unify step 9: the shared trade panel, opened from the list (a third page load, see _attempt). `tid` is a futures trade with a
# positive net, `tid2` one with a negative net. The laptop runs once from the TABLE (glass) and from the LIST in glass / paper / MONO;
# 600 px (still a bottom sheet) and 601 px (already a right-hand panel) are the two widths either side of the rule.
PANEL_CASES = []
for _vp, _th, _view in (('laptop', 'glass', 'feed'), ('laptop', 'paper', 'feed'), ('laptop', 'mono', 'feed'),
                        ('laptop', 'glass', 'table'), ('phone', 'glass', 'feed'), ('phone', 'paper', 'feed'),
                        ('phone', 'mono', 'feed'), ('edge600', 'glass', 'feed'), ('edge601', 'glass', 'feed')):
    PANEL_CASES.append(['panel/%s/%s/%s' % (_vp, _th, 'table' if _view == 'table' else 'list'),
                        {'vp': _vp, 'theme': _th, 'view': _view, 'tid': 'probe_t1', 'tid2': 'probe_t2'}])
# LEDGER unify step 8 follow-up: the PAGE never scrolls sideways at any width from a phone to a laptop. A fourth page load seeds the LIST,
# the SIMPLE table and the FULL table once each and resizes the window through WIDTH_SET, drawing the board again at every width. 375 /
# 601 / 700 / 800 / 1000 / 1366 are the widths the owner asked for; 480 and 600 are the phone rule; 601 / 741 / 801 / 921 are the widths
# just above where a list cell comes back (the tightest a list row ever is), 701 / 901 / 1011 just above where a SIMPLE column comes back,
# and 860 / 975 sit in the two bands where the SIMPLE table used to scroll inside its own box.
WIDTH_SET = [375, 480, 600, 601, 700, 701, 741, 800, 801, 860, 901, 921, 975, 1000, 1011, 1200, 1366]
WIDTH_RUNS = [[_nm, {'theme': 'glass', 'view': _view, 'ledger': _led}, WIDTH_SET]
              for _nm, _view, _led in (('list', 'feed', 'simple'), ('table-simple', 'table', 'simple'), ('table-full', 'table', 'full'))]
LIST_HIDE_ORDER = ['pts', 'strat', 'slot']      # the optional cells of a LIST row, the first to go first
JUMP_DAY = '2026-09-30'

# LEDGER unify step 11
SECTION_ORDER = ['hero', 'pills', 'chart', 'stats', 'more', 'cal', 'acct', 'list', 'paste', 'missed', 'deps', 'ai', 'journal']
OWN_FOLDS = ['paste', 'missed', 'deps', 'ai', 'journal']
HOUSE_WIDTHS = [600, 740, 800, 920, 1100]     # the one set of breakpoints (contract section 5b)
PHONE_LIST_TOP_MAX = 652                      # px from the top of the board to the trade list on a 375 px phone: the build before step 11
# what the removed previous board drew: none of it may be in the page (the page-side readout lists the ones it finds)
OLD_MARKS = ['#hm-sheet', '.hm-backdrop', '#hm-view-toggle', '[data-hmchip]', '#hm-morestats-toggle', '.hm-morestats-panel', '.hm-stat-strip',
             '.hm-toolbar', '.hm-range-pills', '.hm-day-header', '.hm-ms-grid']
FOLD_RUNS = [['laptop', {'vp': 'laptop', 'theme': 'glass', 'cal': True}], ['phone', {'vp': 'phone', 'theme': 'glass'}]]

PASTE_URL = 'https://www.tradingview.com/x/TEST1/'

# Two interaction runs. `tid` is the futures trade whose panel is opened (a 1m trade on the
# laptop, a 10s trade on the phone, so both bar sizes the reader serves are drawn).
INTERACTIONS = [
    ['laptop', {'vp': 'laptop', 'theme': 'glass', 'view': 'table', 'ledger': 'simple',
                'tid': 'probe_t1', 'pts': '7/8', 'mid': 'probe_m1', 'msym': 'MNQ', 'mpts': '5/9',
                'jumpday': JUMP_DAY}],
    ['phone', {'vp': 'phone', 'theme': 'paper', 'view': 'feed', 'ledger': 'simple',
               'tid': 'probe_t3', 'pts': '6/9', 'mid': 'probe_m1', 'msym': 'MNQ', 'mpts': '5/9',
               'jumpday': JUMP_DAY}],
]

# Builds this gate must catch, made from the CURRENT index.html by one string replacement each
# (so they never go stale the way a pinned old commit would). (name, anchor, replacement, why)
MUTANTS = [
    ('missed-section-throws',
     'function _hmMissedSectionHtml(){',
     'function _hmMissedSectionHtml(){_hmProbeNoSuchHelper();',
     'the SHOULD HAVE TRADED section builder throws a ReferenceError - HOME does not draw at all'),
    ('missed-row-dropped',
     'const rows=list.map(m=>`<tr data-hmmissed=',
     'const rows=list.slice(1).map(m=>`<tr data-hmmissed=',
     'the SHOULD HAVE TRADED table silently drops an entry'),
    ('points-block-gone',
     '${_hmPtsSheetHtml(t)}',
     '',
     "the trade panel lost its POINTS block"),
    ('chart-reader-silent',
     'const doc=await window._rtBarsDoc(x._tid);if(!doc)return null;',
     'const doc=null;if(!doc)return null;',
     'the trade-bars reader returns nothing, so no trade panel ever draws a chart (no error thrown)'),
    ('zoom-out-throws',
     "if(z==='out')zoomAt(1.6,0.5);else if(z==='in')zoomAt(1/1.6,0.5);else if(z==='trade')setV(tradeV[0],tradeV[1]);",
     "if(z==='out')zoomAt(1.6,0.5,_hmProbeNoSuchHelper());else if(z==='in')zoomAt(1/1.6,0.5);else if(z==='trade')setV(tradeV[0],tradeV[1]);",
     'the chart\'s zoom-out button throws when clicked'),
    ('drawdown-negative',
     "tile('maxdd','Max drawdown',s?ledgerMoney(s.maxDD):'--'",
     "tile('maxdd','Max drawdown',s?ledgerMoney(-s.maxDD):'--'",
     'the shared stats strip prints max drawdown as a negative number again'),
    ('calendar-jump-lost',
     '<div class="lg-tl-day" data-lgday="\'+ds+\'">\'+dayHd(ds,ts)',
     '<div class="lg-tl-day">\'+dayHd(ds,ts)',
     'the trade list lost its day markers, so a calendar day no longer jumps the list there'),
    ('legend-swatch-giant',
     '.lg-chart .lg-legend svg{display:inline-block;width:16px;height:4px;flex:none}',
     '.lg-chart .lg-legend svg{display:block;width:100%;height:260px}',
     'a chart-size rule reaches the legend swatches again, so each legend name is a block the height of the chart'),
    # the clean-up of v73.1125: ?oldboards=1 and the previous board are gone, and nothing of them may come back
    ('oldflag-changes-the-board',
     "return '<div class=\"hm-wrap lg-flow\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     "return '<div class=\"hm-wrap'+(location.search.indexOf('old'+'boards=1')>=0?'':' lg-flow')+'\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     '?oldboards=1 changes the board again: the page behind the flag is not the plain page'),
    ('old-marker-back-in-page',
     "return '<div class=\"hm-wrap lg-flow\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     "return '<div class=\"hm-wrap lg-flow\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'<div id=\"hm-'+'sheet\"></div></div>';",
     'a piece of the removed previous trade sheet (#hm-sheet) is back in the page'),
    ('removed-flag-defined-again',
     "const LEDGER_RANGES=['TODAY','1W','1M','3M','YTD','ALL'];",
     "const LEDGER_RANGES=['TODAY','1W','1M','3M','YTD','ALL'];\nconst LEDGER_OLDBOARDS=false;",
     'LEDGER_OLDBOARDS is defined again (the static lint of removed identifiers must fail)'),
    ('account-row-dead',
     "if(k!==(activeBroker||''))setBroker(k);",
     "if(k===null)setBroker(k);",
     'tapping an account row in the list no longer scopes the board'),
    ('phone-overflow',
     "return '<div class=\"hm-wrap lg-flow\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     "return '<div class=\"hm-wrap lg-flow\" style=\"min-width:640px\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     'HOME is wider than a phone and the page scrolls sideways'),
    # LEDGER step 8: the shared trade list frame
    ('frame-day-net-unsigned',
     "+(n?'<span class=\"lg-tl-daymeta\">'+n+' trade'+(n===1?'':'s')+'</span><span class=\"lg-tl-daynet '+ledgerPnlCls(net)+'\">'+ledgerSigned(net)+'</span>':'')",
     "+(n?'<span class=\"lg-tl-daymeta\">'+n+' trade'+(n===1?'':'s')+'</span><span class=\"lg-tl-daynet '+ledgerPnlCls(net)+'\">'+ledgerMoney(net)+'</span>':'')",
     'a day header prints its net without a sign, so MONO cannot tell a good day from a bad one'),
    ('wins-chip-counts-flat',
     "if(chip==='WINS')return p>0;",
     "if(chip==='WINS')return p>=0;",
     'the WINS chip lists a $0 trade as a win'),
    ('phone-six-cells',
     'const LEDGER_TL_PHONE={time:1,sym:1,side:1,pnl:1,chart:1};',
     'const LEDGER_TL_PHONE={time:1,sym:1,side:1,size:1,pnl:1,chart:1};',
     'a phone row keeps six cells instead of five'),
    ('view-not-remembered',
     "function ledgerTradeViewSet(id,v){try{localStorage.setItem('el_lg_view_'+id,v==='table'?'table':'list');}catch(e){}}",
     "function ledgerTradeViewSet(id,v){try{}catch(e){}}",
     'LIST | TABLE is no longer remembered per board'),
    ('list-below-the-fold',
     "'<div id=\"hm-feed-container\" data-hmsec=\"list\">'+_hmFrameHtml(list)+'</div>'",
     "'<div style=\"height:900px\"></div><div id=\"hm-feed-container\" data-hmsec=\"list\">'+_hmFrameHtml(list)+'</div>'",
     'something tall sits above the trade list, so it starts more than a screen down on a phone (mistake #12)'),
    ('ai-box-open-by-default',
     "homeAiOpen=localStorage.getItem('el_lg_ai_real')==='1'",
     "homeAiOpen=localStorage.getItem('el_lg_ai_real')!=='0'",
     'the AI ASSESSMENT box is open again and fills the top of the page'),
    ('grade-edit-lost',
     'const field=sel.dataset.hmfield,id=sel.dataset.hmid,val=sel.value;',
     "const field=sel.dataset.hmfield,id=sel.dataset.hmid,val=sel.value+'x';",
     'the inline grade select saves the wrong value'),
    ('table-edit-cell-dead',
     "td.onclick=(e)=>{e.stopPropagation();openEditModal(td.dataset.hmedit);};",
     "td.onclick=(e)=>{e.stopPropagation();};",
     'the pencil cell on a TABLE row no longer opens the edit window'),
    ('header-menu-dead',
     "    case 'pnl':return _hmThCell(label,'pnl',cls+' num',_hmThFRange('minPnl','maxPnl'));",
     "    case 'pnl':return null;",
     'the NET header lost its sort / filter menu'),
    ('paste-box-gone',
     '<input type="text" id="hm-paste-chart" class="hm-feed-search hm-paste"',
     '<input type="text" id="hm-paste-chart-gone" class="hm-feed-search hm-paste"',
     'the PASTE box for snapshot links is gone from the toolbar'),
    ('analytics-jump-dead',
     "activeTab='home';homeView='table';",
     "activeTab='home';",
     'a jump from the ANALYTICS calendar no longer opens the LEDGER table'),
    ('legacy-journal-wide',
     ';margin-bottom:8px;overflow-wrap:anywhere}',
     ';margin-bottom:8px}',
     'a long unbroken line in a journal entry widens the page on a phone again (mistake #14)'),
    ('legacy-trades-wide',
     '@media(max-width:600px){#trd-tbl{min-width:0}',
     '@media(max-width:0px){#trd-tbl{min-width:0}',
     'the legacy TRADES table keeps its 24 columns on a phone (mistake #14)'),
    # LEDGER step 9: the shared trade panel
    ('panel-takes-room-when-closed',
     'P.layer.remove();',
     "P.layer.style.cssText='position:absolute;top:0;left:100%;width:440px;height:900px;background:transparent;animation:none';",
     'a closed trade panel is parked off to the side instead of leaving the page, so it still takes room'),
    ('esc-does-not-close',
     'if(e.defaultPrevented||e.isComposing||_lgPanelCovered(P.layer))return;',
     'return;',
     'Esc no longer closes the trade panel'),
    ('panel-outside-click-dead',
     "if(e.target===layer&&P.down!==false)ledgerTradePanelClose(id,'outside');",
     "if(false)ledgerTradePanelClose(id,'outside');",
     'a click or tap outside the trade panel no longer closes it'),
    ('panel-close-button-dead',
     "if(e.target.closest&&e.target.closest('[data-lgpanel-close]')){ledgerTradePanelClose(id,'button');return;}",
     "if(e.target.closest&&e.target.closest('[data-lgpanel-close]')){return;}",
     'the trade panel close button does nothing'),
    ('wrong-trade-after-rerender',
     'const spec=_hmPanelSpec(String(id));',
     "const spec=_hmPanelSpec(String(ledgerTradePanelOf('hm')?((_hmFeedList()[0]||{id:id}).id):id));",
     'after the list is redrawn (a search) the panel shows the first row of the list, not the trade that was opened'),
    ('notes-lost-on-close',
     'try{if(P.o&&P.o.onBeforeClose)P.o.onBeforeClose(why);}catch(e){console.error(e);}',
     '',
     'closing the trade panel no longer saves a half-typed note'),
    ('phone-sheet-missing',
     '.lg-panel{top:auto;left:0;right:0;width:100%;max-height:88vh;',
     '.lg-panel{top:0;left:auto;right:0;width:440px;max-height:none;',
     'on a phone the trade panel is still a 440 px panel on the right instead of a bottom sheet'),
    ('mono-hue-in-panel',
     ".lg-panel-sym{font-family:'Bebas Neue','JetBrains Mono',monospace;font-size:30px;line-height:1.05;color:var(--text);",
     ".lg-panel-sym{font-family:'Bebas Neue','JetBrains Mono',monospace;font-size:30px;line-height:1.05;color:var(--text);color:#7ac0ff;",
     'the trade panel header carries a hard-coded blue, so MONO is no longer hue-free'),
    ('panel-slot-order-wrong',
     "const LEDGER_PANEL_SLOTS=['chart','numbers','notes','actions'];",
     "const LEDGER_PANEL_SLOTS=['actions','chart','numbers','notes'];",
     'the trade panel slots come out in another order (actions first)'),
    ('panel-lost-on-redraw',
     'document.body.appendChild(layer);',
     "(document.getElementById('app')||document.body).appendChild(layer);",
     'the trade panel is put inside the page that every board redraw rebuilds, so a redraw wipes it'),
    ('panel-row-click-opens-nothing',
     'onRow:rid=>{homeSheetId=rid;_hmSyncPanel();}});',
     'onRow:rid=>{}});',
     'a click on a row of the trade list no longer opens the trade panel'),
    ('panel-ignore-box-dead',
     'try{await updateTrade(tid,{statsExcluded:exclBox.checked});}',
     'try{await updateTrade(tid,{});}',
     'the IGNORE IN METRICS box in the trade panel no longer saves'),
    ('panel-grade-select-missing',
     "const ed=r[0]==='GRADE'?sheetSel('grade',GRADES,t.grade):(r[0]==='SETUP'?sheetSel('setup',customSetups,t.setup):null);",
     'const ed=null;',
     'the trade panel has no grade or setup select (a phone row keeps only five cells, so nothing else edits them)'),
    ('panel-opens-from-a-control',
     "const skip=e=>!!(e.target&&e.target.closest&&e.target.closest('select,input,textarea,button,a,label,.lg-skip'));",
     'const skip=e=>false;',
     'a click on a select or a box inside a trade row opens the trade panel as well'),
    ('frame-wide-at-700',
     '@media (max-width:920px){.lg-tl-row .lg-c-pts{display:none}}',
     '@media (min-width:601px) and (max-width:850px){.lg-tl-row .lg-c-pts,.lg-tl-row .lg-c-strat,.lg-tl-row .lg-c-slot{display:flex!important}}',
     'the trade list rows are wider than the window again between 601 and 850 px (no cell hides as it narrows), so the PAGE scrolls sideways at 700 px'),
    ('frame-drops-net-to-fit',
     '@media (max-width:740px){.lg-tl-row .lg-c-slot{display:none}}',
     '@media (max-width:740px){.lg-tl-row .lg-c-slot{display:none}}@media (min-width:601px) and (max-width:740px){.lg-tl-row .lg-c-pnl{display:none}}',
     'a list row between 601 and 740 px fits by dropping its NET cell instead of a low-priority one'),
    ('simple-box-scrolls-at-860',
     '@media (max-width:920px){.hm-wrap.lg-flow .hm-dtable.hm-simple .hm-s2{display:none}}',
     '@media (max-width:840px){.hm-wrap.lg-flow .hm-dtable.hm-simple .hm-s2{display:none}}',
     'the SIMPLE table brings its IN / POINTS / SETUP columns back too early, so it scrolls inside its own box at 860 px'),
    ('simple-box-scrolls-at-975',
     '@media (max-width:1100px){.hm-wrap.lg-flow .hm-dtable.hm-simple .hm-s3{display:none}}',
     '@media (max-width:960px){.hm-wrap.lg-flow .hm-dtable.hm-simple .hm-s3{display:none}}',
     'the SIMPLE table brings its # and PTS columns back too early, so it scrolls inside its own box at 975 px'),
    # LEDGER step 11: one page order, the own sections as closed folds with a one-line summary, one set of breakpoints
    ('section-order-wrong',
     "const _HM_PAGE_ORDER=['hero','pills','chart','stats','more','cal','acct','list','paste','missed','deps','ai','journal'];",
     "const _HM_PAGE_ORDER=['hero','pills','chart','stats','more','cal','acct','ai','list','paste','missed','deps','journal'];",
     'the AI ASSESSMENT fold sits above the trade list again, so the page sections are no longer in the fixed order'),
    ('pills-under-chart',
     "const _HM_PAGE_ORDER=['hero','pills','chart','stats','more','cal','acct','list','paste','missed','deps','ai','journal'];",
     "const _HM_PAGE_ORDER=['hero','chart','pills','stats','more','cal','acct','list','paste','missed','deps','ai','journal'];",
     'the range pills are under the chart again instead of between the hero and the chart'),
    ('own-section-removed',
     "const _HM_PAGE_ORDER=['hero','pills','chart','stats','more','cal','acct','list','paste','missed','deps','ai','journal'];",
     "const _HM_PAGE_ORDER=['hero','pills','chart','stats','more','cal','acct','list','paste','missed','ai','journal'];",
     'the DEPOSITS section is gone from the page - an own section was removed instead of folded'),
    ('fold-summary-empty',
     'data-hmsum="\'+k+\'">\'+sum+\'</span>',
     'data-hmsum="\'+k+\'">\'+\'\'+\'</span>',
     'every own fold header prints an empty summary line'),
    ('fold-does-not-open',
     "_hmFoldSet(k,!_hmFoldIsOpen(k));renderApp();};});",
     "renderApp();};});",
     'a click on an own fold header does nothing - the fold never opens'),
    ('fold-not-remembered',
     "try{localStorage.setItem(_HM_FOLD_LS[k],on?'1':'0');}catch(e){}",
     "try{}catch(e){}",
     'an own fold no longer remembers open / closed: after a reload it is closed again'),
    ('fold-body-empty',
     '\'<div class="lg-more-panel hm-fold-body" id="hm-fold-\'+k+\'">\'+body()+\'</div>\'',
     '\'<div class="lg-more-panel hm-fold-body" id="hm-fold-\'+k+\'">\'+\'\'+\'</div>\'',
     'an own fold opens but shows nothing - its content is lost'),
    ('phone-list-too-low',
     '\'<div id="hm-feed-container" data-hmsec="list">\'+_hmFrameHtml(list)+\'</div>\'',
     '\'<div style="height:60px"></div><div id="hm-feed-container" data-hmsec="list">\'+_hmFrameHtml(list)+\'</div>\'',
     'something 60 px tall sits above the trade list: still inside one screen on a phone, but lower than the build before step 11'),
    ('fold-summary-two-lines',
     '.hm-fold .hm-fold-sum{flex:0 1 auto;min-width:0;text-transform:none;letter-spacing:.3px;color:var(--text5);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
     '.hm-fold .hm-fold-sum{flex:0 1 auto;min-width:0;text-transform:none;letter-spacing:.3px;color:var(--text5);white-space:normal}',
     'a fold summary may wrap onto a second line on a phone instead of being cut with an ellipsis'),
    ('private-breakpoint',
     '@media (max-width:920px){.hm-wrap.lg-flow .hm-dtable.hm-simple .hm-s2{display:none}}',
     '@media (max-width:910px){.hm-wrap.lg-flow .hm-dtable.hm-simple .hm-s2{display:none}}',
     'the board has a media rule at a width that is not a house number (910 px)'),
    ('mono-hue-in-fold',
     '.hm-fold .hm-fold-sum{flex:0 1 auto;min-width:0;text-transform:none;letter-spacing:.3px;color:var(--text5);',
     '.hm-fold .hm-fold-sum{flex:0 1 auto;min-width:0;text-transform:none;letter-spacing:.3px;color:var(--text5);color:#7ac0ff;',
     'the fold summaries carry a hard-coded blue, so MONO is no longer hue-free'),
    ('paste-question-keeps-fold-closed',
     "_hmFoldSet('paste',true);   // the question (FILE ON, HOLD ...) is in the PASTE fold: it opens",
     "",
     'the question that asks which trade a pasted link is for is written into the PASTE fold but the fold stays closed'),
    ('paste-note-keeps-fold-closed',
     "_hmFoldSet('paste',true);   // the note (UNDO, MOVE ...) is in the PASTE fold: it opens",
     "",
     'a paste note is written into the PASTE fold but the fold stays closed, so the note (UNDO, MOVE) cannot be seen'),
    ('phone-overflow-board',
     "return '<div class=\"hm-wrap lg-flow\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     "return '<div class=\"hm-wrap lg-flow\" style=\"min-width:640px\">'+_HM_PAGE_ORDER.map(k=>S[k]||'').join('')+'</div>';",
     'the new board is wider than a phone and the page scrolls sideways'),
    ('acct-line-summary-empty',
     'data-hmsum="acct">${_hmAcctSummary()}</span>',
     'data-hmsum="acct">${""}</span>',
     'the phone account line prints no summary (the account in view and its balance)'),
    ('calendar-default-private-width',
     "if(v==='1'||v==='0')return v==='1';}catch(e){}return (window.innerWidth||1200)>600;})();",
     "if(v==='1'||v==='0')return v==='1';}catch(e){}return (window.innerWidth||1200)>=760;})();",
     'the calendar default switches at a private width of 760 px instead of the house number 600'),
    ('acct-line-does-not-open',
     'b.onclick=()=>{homeAcctOpen=!homeAcctOpen;',
     'b.onclick=()=>{',
     'a tap on the phone account line does not open the account list'),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>home probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html__QS__" style="width:1366px;height:768px;border:0;display:block"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__, INTER=__INTER__, VP=__VP__, DATA=__DATA__, BARS=__BARS__, PASTE=__PASTE__, PANELS=__PANELS__, WIDTHS=__WIDTHS__, FOLDS=__FOLDS__, HOUSE=__HOUSE__, OWN=__OWN__, OLDMARKS=__OLDMARKS__;
(function(){
  var out={cases:{},inter:{},panels:{},widths:{},folds:{},notes:[]}, reported=false, t0=Date.now(), sink=null;
  function finish(why){
    if(reported)return; reported=true;
    out.why=why; out.ms=Date.now()-t0;
    document.getElementById('o').textContent='HOMEPROBE: '+JSON.stringify(out);
  }
  setTimeout(function(){finish('backstop');},80000);   // virtual ms: a page that only waits on timers costs no wall time
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
      if(/ResizeObserver loop/.test(String(ev&&ev.message||'')))return;   // a browser notice, as the app treats it
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
  function seed(cfg){
    return W().__probeSeed(JSON.stringify(cfg));
  }
  // LEDGER step 11: every @media rule that has a width in it and a selector of the board's own (.hm- / #hm-) that matches something on the page now;
  // each width must be a house number. n counts the live rules, so a scan that sees nothing can be told from a clean one.
  function bpScan(){
    var d=D(),res={n:0,bad:[],widths:[]};
    Array.prototype.forEach.call(d.styleSheets,function(ss){
      var rules;try{rules=ss.cssRules;}catch(e){return;}
      (function walk(list){
        Array.prototype.forEach.call(list,function(rule){
          if(rule.media&&rule.cssRules){
            var cond=rule.media.mediaText||'',ws=cond.match(/(?:min|max)-width:\\s*[\\d.]+px/g);
            if(ws){
              var live=[];
              Array.prototype.forEach.call(rule.cssRules,function(ir){
                if(!ir.selectorText)return;
                ir.selectorText.split(',').forEach(function(sel){
                  sel=sel.trim();
                  if(!/[.#]hm-/.test(sel))return;
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
  // a reload of the page under test: the app boots again (a fresh window), the stubs go back in, the console sink is hooked again
  async function reloadFrame(){
    var w0=W();
    await new Promise(function(res){fr.addEventListener('load',function h(){fr.removeEventListener('load',h);res();});w0.location.reload();});
    await sleep(2500);
    var w2=W();
    sink=hook(w2);
    await waitFor(function(){return !!D().getElementById('tsu');},12000);
    w2.eval('renderAuth=function(){};');
    await sleep(200);
    drain();overlays();
    w2.__probeDataJson=JSON.stringify(DATA);w2.__probeBarsJson=JSON.stringify(BARS);
    w2.eval(__INSTALL__);
  }
  function offenders(d){
    // the outermost elements past the right edge; a fixed one is listed only when nothing in the
    // flow is (the closed trade panel is always parked off the right edge and is not the cause)
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
  function sample(cfg){
    var d=D(),w=W(),r={};
    r.innerW=w.innerWidth;
    r.theme=d.documentElement.getAttribute('data-theme');
    r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
    if(cfg.kind==='legacy'){
      // LEDGER step 8 (mistake #14): the legacy TRADES / JOURNAL tabs on a phone must not scroll the page sideways
      r.legacy={tab:w.eval('activeTab'),table:!!d.getElementById('trd-tbl'),journalForm:!!d.getElementById('lt'),
        rows:d.querySelectorAll('#trd-tbl tbody tr.tr-row').length,lessons:d.querySelectorAll('.lesson-card').length};
      var tbl0=d.getElementById('trd-tbl'),box0=tbl0?tbl0.parentElement:null;
      r.legacy.boxScrollW=box0?box0.scrollWidth:null;r.legacy.boxClientW=box0?box0.clientWidth:null;
      r.scrollW=d.documentElement.scrollWidth;r.clientW=d.documentElement.clientWidth;
      if(r.scrollW>r.clientW+1)r.wide=offenders(d);
      r.overlay=overlays();
      return r;
    }
    // markers of the removed previous board: none of them may be in the page, with or without ?oldboards=1; and the flag's name is gone
    r.oldMarks=OLDMARKS.filter(function(s){return !!d.querySelector(s);});
    r.flagConst=(function(){try{return w.eval('typeof LEDGER_OLDBOARDS');}catch(e){return 'error';}})();
    // LEDGER step 11: the board's markup as a digest (the ?oldboards=1 page must draw the same one), the page sections in the order they are drawn, and the own folds
    // as they are drawn (all closed)
    function digest(s){var h1=0xdeadbeef,h2=0x41c6ce57;
      for(var i=0;i<s.length;i++){var c=s.charCodeAt(i);h1=Math.imul(h1^c,2654435761);h2=Math.imul(h2^c,1597334677);}
      h1=Math.imul(h1^(h1>>>16),2246822507)^Math.imul(h2^(h2>>>13),3266489909);h2=Math.imul(h2^(h2>>>16),2246822507)^Math.imul(h1^(h1>>>13),3266489909);
      return (h2>>>0).toString(16)+(h1>>>0).toString(16);}
    var hwrap=d.querySelector('.hm-wrap'),wtop=hwrap?hwrap.getBoundingClientRect().top:0;
    r.boardDigest=hwrap?digest(hwrap.outerHTML):null;
    var secEls=Array.prototype.slice.call(d.querySelectorAll('[data-hmsec]'));
    r.sec=secEls.map(function(e){var b=e.getBoundingClientRect();return {k:e.getAttribute('data-hmsec'),top:Math.round(b.top-wtop),h:Math.round(b.height)};});
    r.secInWrap=secEls.every(function(e){return !!hwrap&&hwrap.contains(e);});
    r.foldsClosed=Array.prototype.map.call(d.querySelectorAll('[data-hmfold]'),function(b){
      var k=b.getAttribute('data-hmfold'),s=b.querySelector('[data-hmsum]'),bb=b.getBoundingClientRect(),sb=s?s.getBoundingClientRect():null;
      return {k:k,exp:b.getAttribute('aria-expanded'),sum:s?(s.textContent||'').replace(/\\s+/g,' ').trim():null,h:Math.round(bb.height),
        sumH:sb?Math.round(sb.height):null,body:!!d.getElementById('hm-fold-'+k)};});
    var acb0=d.querySelector('[data-hmacct-fold]'),acs0=acb0?acb0.querySelector('[data-hmsum]'):null;
    r.acctSum=acs0?(acs0.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.acctBtnH=acb0?Math.round(acb0.getBoundingClientRect().height):null;
    // LEDGER shared trade list frame (unify step 8): toolbar, day headers with a signed net, rows, five cells on a phone.
    // Measured first, before the folds below are opened and move the page about.
    var fr=d.querySelector('[data-lglist-frame="hm"]');
    r.frameN=d.querySelectorAll('[data-lglist-frame]').length;
    r.frame=!!fr;
    function dayOf(row){var g=row.closest('[data-lgday]');if(g)return g.getAttribute('data-lgday');
      var p=row.previousElementSibling;while(p){if(p.hasAttribute&&p.hasAttribute('data-lgday'))return p.getAttribute('data-lgday');p=p.previousElementSibling;}
      return null;}
    if(fr){
      var txt1=function(e){return e?(e.textContent||'').replace(/\\s+/g,' ').trim():'';};
      r.mode=fr.getAttribute('data-lgmode');
      r.chipTxt=Array.prototype.map.call(fr.querySelectorAll('[data-lgchip]'),txt1).join(',');
      r.chipOn=Array.prototype.map.call(fr.querySelectorAll('[data-lgchip].active'),txt1).join(',');
      r.viewBtns=Array.prototype.map.call(fr.querySelectorAll('[data-lgview]'),function(b){return b.getAttribute('data-lgview')+(b.getAttribute('aria-pressed')==='true'?'*':'');}).join(',');
      r.searchBox=!!fr.querySelector('input[data-lgsearch]');
      r.count=txt1(fr.querySelector('[data-lgcount]'));
      r.days=Array.prototype.map.call(fr.querySelectorAll('[data-lgday]'),function(g){return g.getAttribute('data-lgday')+'='+txt1(g.querySelector('.lg-tl-daynet'));});
      r.frameRows=fr.querySelectorAll('[data-lgtrade]').length;
      var ov=fr.querySelector('[data-lgtrade="probe_o1"]');r.ovDay=ov?dayOf(ov):null;
      var row1=fr.querySelector('[data-lgtrade]'),vis=0;
      if(row1)Array.prototype.forEach.call(row1.children,function(c){if(w.getComputedStyle(c).display!=='none')vis++;});
      r.visCells=vis;
      var wrapEl=d.querySelector('.hm-wrap'),fb=fr.getBoundingClientRect(),wb=wrapEl?wrapEl.getBoundingClientRect():null;
      r.listTop=wb?Math.round(fb.top-wb.top):null;
      r.rowTop=(wb&&row1)?Math.round(row1.getBoundingClientRect().top-wb.top):null;
      r.viewH=w.innerHeight;
    }
    var wrap0=d.querySelector('.hm-wrap'),wb0=wrap0?wrap0.getBoundingClientRect():null,fc0=d.getElementById('hm-feed-container');
    r.feedTop=(wb0&&fc0)?Math.round(fc0.getBoundingClientRect().top-wb0.top):null;
    // the AI ASSESSMENT is a closed fold and the account list is one line on a phone (mistake #12)
    var aib=d.querySelector('[data-hmai-fold]');
    r.aiFold=aib?{closed:aib.getAttribute('aria-expanded')==='false',out:!!d.getElementById('overview-ai-output')}:null;
    var acb=d.querySelector('[data-hmacct-fold]'),acl=d.querySelector('.hm-sec-acct .lg-list');
    r.acctFold=acb?{btn:w.getComputedStyle(acb).display,list:acl?w.getComputedStyle(acl).display:null}:null;
    // the frame's own table box must not scroll sideways (SIMPLE fits the row), rows in close order, the deposit row
    var tb2=d.querySelector('table.lg-tl-table'),bx2=tb2?tb2.parentElement:null;
    r.tblBox=bx2?{sw:bx2.scrollWidth,cw:bx2.clientWidth,simple:tb2.classList.contains('hm-simple')}:null;
    r.order=Array.prototype.map.call(d.querySelectorAll('[data-lglist-frame="hm"] [data-lgtrade]'),function(e){return e.getAttribute('data-lgtrade');});
    r.depositRows=d.querySelectorAll('[data-lglist-frame="hm"] .hm-row-static').length;
    var pb=d.getElementById('hm-paste-chart');r.paste=!!pb;r.pasteVisible=!!(pb&&pb.getBoundingClientRect().width>0);
    var ms=d.getElementById('hm-missed');
    r.missed=!!ms;
    r.missedRows=ms?ms.querySelectorAll('tr[data-hmmissed]').length:-1;
    var fc=d.getElementById('hm-feed-container');
    r.feed=!!fc;
    if(cfg.view==='table'){
      var tb=fc?fc.querySelector('table.hm-dtable'):null;
      r.ledgerKind=tb?(tb.classList.contains('hm-simple')?'simple':'full'):'';
      r.ledgerRows=tb?tb.querySelectorAll('tbody tr[data-hmid]').length:0;
    }else{
      // the shared frame's LIST rows
      r.ledgerKind=fc&&fc.querySelector('.hm-row[data-hmid],.lg-tl-row[data-lgtrade]')?'feed':'';
      r.ledgerRows=fc?fc.querySelectorAll('.hm-row[data-hmid],.lg-tl-row[data-lgtrade]').length:0;
    }
    // LEDGER shared hero + range pills (unify step 4): the big number, the today line, the six pills
    var hv=d.getElementById('hm-hero-value'),ht=d.getElementById('hm-hero-today');
    r.heroBig=hv?(hv.textContent||'').trim():null;
    r.heroToday=ht?(ht.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.pills=Array.prototype.map.call(d.querySelectorAll('.hm-ctl [data-hmrange], .hm-range-row [data-hmrange]'),function(b){return b.getAttribute('data-hmrange');}).join(',');
    // LEDGER shared equity chart (unify step 5): real height on every width, dates and a price scale
    var csv=d.querySelector('#hm-chart-wrap svg');
    // the DRAWN height: a viewBox scaled down to fit a narrow box draws a short band in a tall box (the old phone bug)
    r.chartH=0;
    if(csv){var cr=csv.getBoundingClientRect(),vb=(csv.getAttribute('viewBox')||'').split(/[ ,]+/).map(Number);
      r.chartH=Math.round(vb.length===4&&vb[2]>0&&vb[3]>0?vb[3]*Math.min(cr.width/vb[2],cr.height/vb[3]):cr.height);}
    r.chartDates=csv?csv.querySelectorAll('[data-lgdate]').length:0;
    r.chartTicks=csv?csv.querySelectorAll('[data-lgtick]').length:0;
    // LEDGER shared stats strip (unify step 6): four tiles in order, drawdown positive, the More stats fold opens
    r.stats=Array.prototype.map.call(d.querySelectorAll('#hm-stat-strip [data-lgstat]'),function(e){
      var v=e.querySelector('.lg-stat-val');return e.getAttribute('data-lgstat')+'='+(v?(v.textContent||'').trim():'');});
    var mb=d.querySelector('[data-lgmore="hm"]');
    r.moreGroups='';
    if(mb){mb.click();
      r.moreGroups=Array.prototype.map.call(d.querySelectorAll('#hm-more [data-lgmsgroup]'),function(g){return g.getAttribute('data-lgmsgroup');}).join(',');
      var mb2=d.querySelector('[data-lgmore="hm"]');if(mb2)mb2.click();}
    // LEDGER shared calendar (unify step 7): the fold opens, the month's day counts add up to its header, and
    // tapping a day in the feed flashes that day's group
    var cf=d.querySelector('[data-lgcalfold="hm"]');
    r.cal=null;
    if(cf){var wasOpen=cf.getAttribute('aria-expanded')==='true';
      if(!wasOpen){cf.click();}
      var cg=d.querySelector('[data-lgcal="hm"].lg-cal'),c={days:0,sumN:0,hdN:null};
      if(cg){var ds=cg.querySelectorAll('[data-lgcalday]');c.days=ds.length;
        Array.prototype.forEach.call(ds,function(b){var n=b.querySelector('.n');c.sumN+=n?parseInt(n.textContent,10)||0:0;});
        var sm=(cg.querySelector('.lg-cal-sum')||{textContent:''}).textContent.match(/(\\d+) trades?/);c.hdN=sm?+sm[1]:0;
        c.cells=cg.querySelectorAll('.lg-cal-grid > *').length;
        if(ds.length&&(cfg.view!=='table'||r.frame)){var pick=ds[ds.length-1].getAttribute('data-lgcalday');ds[ds.length-1].click();
          var g=d.querySelector('#hm-feed-container [data-hmday="'+pick+'"],#hm-feed-container [data-lgday="'+pick+'"]');c.jump=!!(g&&g.classList.contains('lg-flash'));}}
      r.cal=c;
      if(!wasOpen){var cf2=d.querySelector('[data-lgcalfold="hm"]');if(cf2)cf2.click();}}
    // LEDGER step 11: every own fold opens on a click and shows its content, then closes again
    r.foldOpen={};
    function ownBtn(k){return d.querySelector('[data-hmfold="'+k+'"]');}
    OWN.forEach(function(k){
      var o={},b=ownBtn(k);o.btn=!!b;
      if(b){
        b.click();
        var b2=ownBtn(k),body=d.getElementById('hm-fold-'+k);
        o.exp=b2?b2.getAttribute('aria-expanded'):null;o.body=!!body;o.len=body?(body.innerHTML||'').trim().length:0;
        if(k==='paste'){var pb=d.getElementById('hm-paste-chart');o.paste=!!pb;o.pasteVisible=!!(pb&&pb.getBoundingClientRect().width>0);}
        if(k==='missed'){var ms1=d.getElementById('hm-missed');o.missed=!!ms1;o.missedRows=ms1?ms1.querySelectorAll('tr[data-hmmissed]').length:-1;o.add=!!d.getElementById('hm-missed-add');}
        if(k==='deps'){o.strip=!!d.querySelector('.hm-ledger-strip');o.chips=d.querySelectorAll('.hm-ledger-chip').length;}
        if(k==='ai'){var ao=d.getElementById('overview-ai-output');o.out=!!ao;o.text=ao?(ao.textContent||'').trim().slice(0,60):'';o.refresh=!!d.querySelector('#hm-fold-ai .btn-d');}
        if(k==='journal'){o.form=!!d.getElementById('hm-journal-form');o.entries=d.querySelectorAll('.lesson-card').length;o.save=!!d.getElementById('hladd');}
        var b3=ownBtn(k);if(b3)b3.click();
        var b4=ownBtn(k);o.back=b4?b4.getAttribute('aria-expanded'):null;o.bodyGone=!d.getElementById('hm-fold-'+k);
      }
      r.foldOpen[k]=o;
    });
    // the phone account line (the strategy / account list slot): one line that opens the list on a click and closes it again
    r.acctOpen=null;
    var ab1=d.querySelector('[data-hmacct-fold]');
    if(ab1&&w.getComputedStyle(ab1).display!=='none'){
      ab1.click();
      var ab2=d.querySelector('[data-hmacct-fold]'),al2=d.querySelector('.hm-sec-acct .lg-list');
      r.acctOpen={exp:ab2?ab2.getAttribute('aria-expanded'):null,list:al2?w.getComputedStyle(al2).display:null};
      if(ab2)ab2.click();
      var ab3=d.querySelector('[data-hmacct-fold]'),al3=d.querySelector('.hm-sec-acct .lg-list');
      r.acctOpen.back=ab3?ab3.getAttribute('aria-expanded'):null;r.acctOpen.listBack=al3?w.getComputedStyle(al3).display:null;
    }
    // all five open: the board's own media rules use only the house widths, and under MONO nothing has a hue
    OWN.forEach(function(k){var b=ownBtn(k);if(b&&b.getAttribute('aria-expanded')!=='true')b.click();});
    try{r.bp=bpScan();}catch(e){r.bp={err:String(e&&e.stack?e.stack:e)};}
    if(cfg.theme==='mono'){var hw=d.querySelector('.hm-wrap');r.hue=hw?hueScan(hw):null;}
    OWN.forEach(function(k){var b=ownBtn(k);if(b&&b.getAttribute('aria-expanded')==='true')b.click();});
    // the legend under the chart (P&L view, two brokers): each name is one short line - a chart-size rule once
    // made every swatch 260px tall. Switch to P&L, measure, switch back.
    W().eval("homeChartMode='pnl';renderApp();");
    var lgb=d.querySelectorAll('#hm-chart-wrap .lg-legend button');r.legendN=lgb.length;
    r.legendH=Math.max.apply(null,[0].concat(Array.prototype.map.call(lgb,function(b){return Math.round(b.getBoundingClientRect().height);})));
    W().eval("homeChartMode='equity';renderApp();");
    // LEDGER step 9: while nothing is open the shared trade panel is not in the page at all (no node, no layer); that is also what keeps a closed
    // panel from taking room or widening the page (LEDGER mistake #13)
    r.panelsInDom=d.querySelectorAll('.lg-panel,.lg-panel-layer').length;
    // LEDGER shared account list (unify step 10): ALL + one row per broker, the tab-row ACCOUNT pill gone on LEDGER,
    // and tapping a broker row scopes the board (the hero label names it), then ALL again
    var lr=d.querySelectorAll('[data-lglist="hm"] [data-lgrow]');r.acctRows=lr.length;
    r.acctSel=(d.querySelector('[data-lglist="hm"] [data-lgrow].sel')||{getAttribute:function(){return null;}}).getAttribute('data-lgrow');
    r.acctPill=Array.prototype.some.call(d.querySelectorAll('button'),function(b){return /setBroker\\(/.test(b.getAttribute('onclick')||'');});
    var nb=d.querySelector('[data-lglist="hm"] [data-lgrow="NinjaTrader"]');r.acctScoped=null;
    if(nb){nb.click();var hl=d.getElementById('hm-hero-label');r.acctScoped=hl?(hl.textContent||'').indexOf('NINJATRADER')>=0:false;
      var ab=d.querySelector('[data-lglist="hm"] [data-lgrow=""]');if(ab)ab.click();}
    r.scrollW=d.documentElement.scrollWidth;
    r.clientW=d.documentElement.clientWidth;
    if(r.scrollW>r.clientW+1)r.wide=offenders(d);
    r.overlay=overlays();
    return r;
  }
  async function runCase(nm,cfg){
    var r={};
    await setVp(cfg.vp);
    drain();
    try{r.call=seed(cfg);}catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);   // deferred work (hold check, chart wiring) gets to run, and to throw
    try{Object.assign(r,sample(cfg));}catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
    Object.assign(r,drain());
    out.cases[nm]=r;
  }
  function q(sel){return D().querySelector(sel);}
  function txt(sel){var e=q(sel);return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;}
  async function step(res,name,fn){
    var st={};
    try{await fn(st);}catch(e){st.threw=String(e&&e.stack?e.stack:e);}
    await sleep(60);
    Object.assign(st,drain());
    st.overlay=overlays();
    res.steps[name]=st;
  }
  async function interact(nm,I){
    var w=W(),res={steps:{}};
    await setVp(I.vp);
    drain();
    try{res.seed=seed({vp:I.vp,theme:I.theme,missed:2,view:I.view,ledger:I.ledger});}
    catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    Object.assign(res,{seedErr:drain()});
    // 1. a futures trade's panel: the chart draws and the POINTS block shows the score
    await step(res,'panel',async function(st){
      w.eval('homeSheetId='+JSON.stringify(I.tid)+';renderApp();');
      st.drew=await waitFor(function(){
        var b=q('.lg-panel[data-lgpanel="hm"] [data-rtcandlesbody]'),inf=q('.lg-panel[data-lgpanel="hm"] [data-rtcandlesinfo]');
        return b&&b.querySelector('svg')&&inf&&(inf.textContent||'').trim();},6000);
      st.open=!!q('.lg-panel[data-lgpanel="hm"]');
      st.body=txt('.lg-panel[data-lgpanel="hm"] [data-rtcandlesbody]');
      if(st.body&&st.body.length>160)st.body=st.body.slice(0,160);
      st.info=txt('.lg-panel[data-lgpanel="hm"] [data-rtcandlesinfo]');
      var s=q('.lg-panel[data-lgpanel="hm"] [data-rtcandlesbody] svg');st.svg0=s?s.outerHTML.length:0;
      res._svg0=s?s.outerHTML:'';
      st.points=txt('.lg-panel[data-lgpanel="hm"] .hm-sheet-points');
      if(st.points)st.points=st.points.slice(0,80);
    });
    // 2. zoom out, then DAY: each redraws (on a timer when frames do not run), neither throws
    await step(res,'zoom',async function(st){
      var o=q('.lg-panel[data-lgpanel="hm"] [data-rtz="out"]'),dy=q('.lg-panel[data-lgpanel="hm"] [data-rtz="day"]');
      st.buttons=(o?1:0)+(dy?1:0);
      if(o)o.click();
      await sleep(120);
      st.infoOut=txt('.lg-panel[data-lgpanel="hm"] [data-rtcandlesinfo]');
      if(dy)dy.click();
      await sleep(120);
      st.infoDay=txt('.lg-panel[data-lgpanel="hm"] [data-rtcandlesinfo]');
      var s=q('.lg-panel[data-lgpanel="hm"] [data-rtcandlesbody] svg');
      st.svg=!!s;
      st.redrew=!!(s&&res._svg0&&s.outerHTML!==res._svg0);
    });
    delete res._svg0;
    // 3. a SHOULD HAVE TRADED entry's panel
    await step(res,'missedPanel',async function(st){
      w.eval('homeSheetId='+JSON.stringify('missed:'+I.mid)+';renderApp();');
      st.drew=await waitFor(function(){
        var b=q('.lg-panel[data-lgpanel="hm"] [data-rtcandlesbody]');return b&&b.querySelector('svg');},6000);
      st.open=!!q('.lg-panel[data-lgpanel="hm"]');
      st.sym=txt('.lg-panel[data-lgpanel="hm"] [data-lgpanel-sym]');
      st.sub=txt('.lg-panel[data-lgpanel="hm"] [data-lgpanel-sub]');
      st.points=txt('.lg-panel[data-lgpanel="hm"] .hm-sheet-points');
      if(st.points)st.points=st.points.slice(0,80);
      st.body=txt('.lg-panel[data-lgpanel="hm"] [data-rtcandlesbody]');
      if(st.body&&st.body.length>160)st.body=st.body.slice(0,160);
    });
    // 4. + ADD opens the form; SAVE with the fields empty explains itself and writes nothing
    await step(res,'addForm',async function(st){
      w.eval('homeSheetId=null;renderApp();');
      await sleep(60);
      var mf0=q('[data-hmfold="missed"]');st.missedFold=!!mf0;
      if(mf0&&mf0.getAttribute('aria-expanded')!=='true'){mf0.click();await sleep(60);}
      var add=q('#hm-missed-add');st.addBtn=!!add;
      if(add)add.click();
      await sleep(80);
      st.form=!!q('#hm-missed-form');
      st.msg0=txt('#hmmf-msg');
      var sv=q('#hmmf-save');st.saveBtn=!!sv;
      if(sv)sv.click();
      await sleep(120);
      st.form2=!!q('#hm-missed-form');
      st.msg=txt('#hmmf-msg');
      st.writes=JSON.parse(w.eval('JSON.stringify(window.__probeWrites)'));
    });
    // 5. a pasted TradingView link: the note asks where it goes and offers SHOULD HAVE TRADED,
    //    which opens the form with the link filled in
    await step(res,'paste',async function(st){
      w.eval('window._hmMissedEdit=null;renderApp();');
      await sleep(40);
      // a plain note (not a link) is written into the PASTE fold and opens it; closed again, the note is cleared, and then the real link asks where it goes
      var pf2=q('[data-hmfold="paste"]');
      if(pf2&&pf2.getAttribute('aria-expanded')==='true'){pf2.click();await sleep(40);}
      w.eval('window._hmPasteNote=null;window._hmPasteLast=null;window._hmPasteAsk=null;renderApp();');
      await w.hmFileChartLink('not a link');
      await sleep(80);
      var pf3=q('[data-hmfold="paste"]');st.foldOpenMsg=pf3?pf3.getAttribute('aria-expanded'):null;
      if(pf3&&pf3.getAttribute('aria-expanded')==='true'){pf3.click();await sleep(40);}
      w.eval('window._hmPasteNote=null;window._hmPasteLast=null;window._hmPasteAsk=null;renderApp();');
      await sleep(40);
      await w.hmFileChartLink(PASTE);
      await sleep(80);
      var pf1=q('[data-hmfold="paste"]');st.foldOpen=pf1?pf1.getAttribute('aria-expanded'):null;   // a paste note opens its fold
      st.note=!!q('#hm-paste-msg');
      st.noteText=txt('#hm-paste-msg');
      if(st.noteText&&st.noteText.length>160)st.noteText=st.noteText.slice(0,160);
      var b=q('#hm-paste-msg #hm-paste-missed');st.missedBtn=!!b;
      if(b){b.click();await sleep(150);}
      st.form=!!q('#hm-missed-form');
      var u=q('#hmmf-url');st.url=u?u.value:null;
      st.writes=JSON.parse(w.eval('JSON.stringify(window.__probeWrites)'));
    });
    // 6. LEDGER step 8, the shared trade list frame: the chips (a $0 trade is neither a win nor a loss), the search
    //    box, BY DAY, LIST | TABLE (remembered per board) and SIMPLE | FULL
    await step(res,'frame',async function(st){
      function fr1(){return q('[data-lglist-frame="hm"]');}
      function ids(){var f=fr1();return f?Array.prototype.map.call(f.querySelectorAll('[data-lgtrade]'),function(e){return e.getAttribute('data-lgtrade');}).sort():null;}
      function mode(){var f=fr1();return f?f.getAttribute('data-lgmode'):null;}
      function ls(k){try{return w.localStorage.getItem(k);}catch(e){return 'ERR';}}
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeFeedMode="trade";homeView="feed";renderApp();');
      st.chips={};
      ['WINS','LOSSES','LONG','SHORT','FUTURES','STOCKS','ALL'].forEach(function(c){
        var b=q('[data-lgchip="'+c+'"]');if(b){b.click();st.chips[c]=ids();}else st.chips[c]=null;});
      var inp=q('#hm-search');st.searchBox=!!inp;
      if(inp){inp.focus();inp.value='aapl';inp.dispatchEvent(new Event('input',{bubbles:true}));}
      st.search=ids();
      st.searchFocus=(D().activeElement&&D().activeElement.id)||'';
      inp=q('#hm-search');
      if(inp){inp.value='';inp.dispatchEvent(new Event('input',{bubbles:true}));}
      st.searchCleared=(ids()||[]).length;
      var bd=q('[data-hmfeed="day"]');st.byDayBtn=!!bd;
      if(bd){bd.click();var f1=fr1();st.byDayDays=f1?f1.querySelectorAll('[data-lgday]').length:-1;st.byDayTrades=f1?f1.querySelectorAll('[data-lgtrade]').length:-1;}
      var bt=q('[data-hmfeed="trade"]');if(bt)bt.click();
      var tbn=q('[data-lgview="table"]');st.viewBtn=!!tbn;
      if(tbn)tbn.click();
      st.modeTable=mode();st.savedTable=ls('el_lg_view_hm');
      var fl=q('[data-hmledger="full"]');st.fullBtn=!!fl;
      if(fl){fl.click();var tf=q('table.lg-tl-table');st.fullTable=!!(tf&&!tf.classList.contains('hm-simple'));st.fullCols=tf?tf.querySelectorAll('thead th').length:0;}
      var sm=q('[data-hmledger="simple"]');if(sm)sm.click();
      var ts=q('table.lg-tl-table');st.simpleTable=!!(ts&&ts.classList.contains('hm-simple'));st.simpleCols=ts?ts.querySelectorAll('thead th').length:0;
      var lbn=q('[data-lgview="list"]');if(lbn)lbn.click();
      st.modeList=mode();st.savedList=ls('el_lg_view_hm');
      var pf0=q('[data-hmfold="paste"]');st.pasteFold=!!pf0;
      if(pf0&&pf0.getAttribute('aria-expanded')!=='true'){pf0.click();await sleep(60);}
      st.paste=!!q('#hm-paste-chart');
      st.buttons={add:!!q('#hm-add-deposit'),scan:!!q('#hm-scan-dupes'),all:!!q('#hm-open-all'),nt:!!q('#hm-newtrade-toggle')};
      // NEW TRADE opens the form under the toolbar and closes it again
      var nt=q('#hm-newtrade-toggle');
      if(nt){nt.click();st.formOpen=!!q('#hm-newtrade-form #hnfsym');var nt2=q('#hm-newtrade-toggle');if(nt2)nt2.click();st.formClosed=!q('#hm-newtrade-form #hnfsym');}
      // the ... button (a phone only) opens the four action buttons; a laptop always shows them
      var tt=q('#hm-tools-toggle'),ta=q('#hm-tools');
      st.tools={toggle:tt?w.getComputedStyle(tt).display:null,box:ta?w.getComputedStyle(ta).display:null};
      if(tt&&st.tools.toggle!=='none'){tt.click();var ta2=q('#hm-tools');st.tools.boxOpen=ta2?w.getComputedStyle(ta2).display:null;tt=q('#hm-tools-toggle');if(tt)tt.click();var ta3=q('#hm-tools');st.tools.boxShut=ta3?w.getComputedStyle(ta3).display:null;}
    });
    // 7. REAL keeps its inline edits: a grade and a note saved from the TABLE reach the database stubs
    await step(res,'edits',async function(st){
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeView="table";homeLedger="simple";renderApp();');
      await sleep(40);
      w.eval('window.__probeData.length=0;');
      var sel=q('select[data-hmfield="grade"][data-hmid="probe_t1"]');st.gradeSel=!!sel;
      if(sel){sel.value='A';sel.dispatchEvent(new Event('change',{bubbles:true}));await sleep(80);}
      var ni=q('input[data-field="notes"][data-id="probe_t1"]');st.noteInput=!!ni;
      if(ni){ni.value='probe note edit';ni.dispatchEvent(new Event('blur'));await sleep(80);}
      st.data=JSON.parse(w.eval('JSON.stringify(window.__probeData)'));
      // every row keeps its EDIT and DELETE cells: EDIT opens the edit window (closed again here), DELETE is wired (it asks first, so it is not clicked)
      st.rowsN=D().querySelectorAll('table.lg-tl-table tbody tr[data-lgtrade]').length;
      st.editCells=D().querySelectorAll('table.lg-tl-table td[data-hmedit]').length;
      st.delCells=D().querySelectorAll('table.lg-tl-table td[data-hmdel]').length;
      var dcell=q('table.lg-tl-table td[data-hmdel]');st.delWired=!!(dcell&&typeof dcell.onclick==='function');
      var ecell=q('table.lg-tl-table td[data-hmedit]');
      if(ecell){var mb0=D().querySelectorAll('.modal-bg[id^="em_"]').length;ecell.click();await sleep(60);var mb1=D().querySelectorAll('.modal-bg[id^="em_"]');st.editOpened=mb1.length-mb0;Array.prototype.forEach.call(mb1,function(m){m.remove();});}
    });
    // 8. jumps into the list: the ANALYTICS calendar (gotoTradesByDate) opens the LEDGER table on that day and flashes its
    //    rows; a LEDGER calendar day tap in the table flashes that day's header
    await step(res,'jump',async function(st){
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeView="feed";activeTab="analytics";renderApp();');
      await sleep(40);
      st.analyticsShown=w.eval('activeTab');
      w.gotoTradesByDate(I.jumpday);
      await sleep(160);
      st.tab=w.eval('activeTab');st.view=w.eval('homeView');
      st.flashed=D().querySelectorAll('#hm-feed-container tbody tr.hm-flash').length;
      st.dayHeader=!!q('[data-lglist-frame="hm"] [data-lgday="'+I.jumpday+'"]');
      st.tableShown=!!q('table.lg-tl-table');
      // a flashed row of the jump day opens the right trade in the shared panel
      var fr0=D().querySelector('#hm-feed-container tbody tr.hm-flash');st.jumpRow=fr0?fr0.getAttribute('data-lgtrade'):null;
      if(fr0){(fr0.querySelector('.lg-c-sym')||fr0).click();await sleep(300);}
      var jp0=q('.lg-panel[data-lgpanel="hm"]');st.jumpPanel=jp0?jp0.getAttribute('data-lgpanel-trade'):null;
      st.jumpSym=txt('.lg-panel[data-lgpanel="hm"] [data-lgpanel-sym]');
      w.eval('homeSheetId=null;renderApp();');
    });
    // 9. the TABLE header menus still sort through the frame: NET opens its menu, Sort ascending re-orders the rows and the
    //    day headers go (rows are no longer in day order)
    await step(res,'sortmenu',async function(st){
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeView="table";homeLedger="simple";sortCol="date";sortDir=-1;window._thMenu=null;renderApp();');
      await sleep(40);
      var th=q('table.lg-tl-table th[data-thcol="pnl"] .thh');st.header=!!th;
      if(th){th.click();await sleep(120);}
      var menu=D().getElementById('_thFloatMenu');st.menu=!!menu;
      var asc=menu?Array.prototype.filter.call(menu.querySelectorAll('div'),function(e){return /Sort ascending/.test(e.textContent||'');})[0]:null;
      st.ascItem=!!asc;
      if(asc){asc.click();await sleep(120);}
      st.label=txt('#hm-sort-label');
      st.nets=Array.prototype.map.call(D().querySelectorAll('table.lg-tl-table tbody tr[data-lgtrade] .lg-c-pnl'),function(c){return (c.textContent||'').trim();});
      st.dayRows=D().querySelectorAll('table.lg-tl-table tr[data-lgday]').length;
      w.eval('sortCol="date";sortDir=-1;window._thMenu=null;renderApp();');
    });
    // 10. the trade panel keeps EDIT / SNAPSHOT / OPEN IN TV / DELETE and also edits the grade and the setup (a phone row
    //     keeps five cells, the rest is edited here)
    await step(res,'sheet',async function(st){
      w.eval('window.__probeData.length=0;homeSheetId="probe_t2";renderApp();');
      await sleep(80);
      st.buttons={edit:!!q('#hm-sheet-edit'),snap:!!q('#hm-sheet-chart'),tv:!!q('#hm-sheet-tv'),del:!!q('#hm-sheet-del')};
      var gs=q('.lg-panel[data-lgpanel="hm"] select[data-hmsheetfield="grade"]'),ss=q('.lg-panel[data-lgpanel="hm"] select[data-hmsheetfield="setup"]');
      st.sel=!!gs&&!!ss;
      if(gs){gs.value='A';gs.dispatchEvent(new Event('change',{bubbles:true}));await sleep(60);}
      if(ss&&ss.options.length>1){ss.selectedIndex=1;st.setupPicked=ss.value;ss.dispatchEvent(new Event('change',{bubbles:true}));await sleep(60);}
      // IGNORE IN METRICS in the panel saves {statsExcluded: true}
      var ex=q('#hm-sheet-excl');st.excl=!!ex;
      if(ex){ex.checked=true;ex.dispatchEvent(new Event('change',{bubbles:true}));await sleep(60);}
      st.data=JSON.parse(w.eval('JSON.stringify(window.__probeData)'));
      w.eval('homeSheetId=null;renderApp();');
    });
    // 11. the AI ASSESSMENT fold: closed, then open (the box is drawn and filled), then closed again
    await step(res,'aiFold',async function(st){
      w.eval('homeSheetId=null;homeView="feed";renderApp();');
      var b=q('[data-hmai-fold]');st.fold=!!b;
      st.closed=b?b.getAttribute('aria-expanded')==='false':null;st.outputBefore=!!q('#overview-ai-output');
      if(b){b.click();await sleep(80);}
      var b2=q('[data-hmai-fold]');st.open=b2?b2.getAttribute('aria-expanded')==='true':null;
      st.outputAfter=!!q('#overview-ai-output');st.text=txt('#overview-ai-output');
      if(st.text&&st.text.length>120)st.text=st.text.slice(0,120);
      if(b2){b2.click();await sleep(40);}
      var b3=q('[data-hmai-fold]');st.closedAgain=b3?b3.getAttribute('aria-expanded')==='false':null;
    });
    try{w.eval('homeSheetId=null;window._hmMissedEdit=null;window._hmPasteNote=null;renderApp();');}catch(_e){}
    drain();
    out.inter[nm]=res;
  }
  // ---- LEDGER unify step 9: the shared trade panel, opened from the list ------------------------------------------------------
  // every colour the panel draws (text, background, borders, outline, svg fill and stroke) must be a grey: MONO has no hue
  function hueScan(root){
    var cv=document.createElement('canvas');cv.width=1;cv.height=1;var cx=cv.getContext('2d');
    function rgba(css){try{cx.clearRect(0,0,1,1);cx.fillStyle='#000';cx.fillStyle=css;cx.fillRect(0,0,1,1);var a=cx.getImageData(0,0,1,1).data;return [a[0],a[1],a[2],a[3]];}catch(e){return null;}}
    var w=W(),els=[root].concat(Array.prototype.slice.call(root.querySelectorAll('*'))),n=0,bad=[];
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
  async function panelRun(nm,cfg){
    var w=W(),d=D(),res={steps:{}},PN='.lg-panel[data-lgpanel="hm"]';
    await setVp(cfg.vp);
    drain();
    try{res.seed=seed({vp:cfg.vp,theme:cfg.theme,missed:2,view:cfg.view,ledger:'simple'});}
    catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    res.seedErr=drain();
    w.eval('window.__probeData.length=0;');   // the database stubs keep every write of every case: start this case clean
    function geo(){var de=d.documentElement;
      return {sw:de.scrollWidth,cw:de.clientWidth,sh:de.scrollHeight,kids:d.body.children.length,nodes:d.querySelectorAll('.lg-panel,.lg-panel-layer').length};}
    function openRow(id){var row=q('[data-lgtrade="'+id+'"]');if(!row)return false;(row.querySelector('.lg-c-sym')||row).click();return true;}
    function shut(){try{w.ledgerTradePanelClose('hm','api');}catch(e){}}
    function notesWrites(id){
      return JSON.parse(w.eval('JSON.stringify(window.__probeData)')).filter(function(x){return x.n==='trades'&&x.id===id&&x.d&&x.d.notes!==undefined;});}
    function rows(){var f=q('[data-lglist-frame="hm"]');return f?f.querySelectorAll('[data-lgtrade]').length:-1;}
    // reads the open panel: where it is, what it says, which slots it has
    function look(st){
      // a headless page may never produce the frames a CSS animation needs: finish the slide-in so the panel is measured where it ends up
      try{d.getAnimations().forEach(function(a){try{a.finish();}catch(e1){}});}catch(e){}
      var p=q(PN);st.exists=!!p;
      if(!p)return;
      var r=p.getBoundingClientRect(),cs=w.getComputedStyle(p),nel=q(PN+' [data-lgpanel-net]'),b=p.querySelector('[data-lgpanel-body]');
      st.rect={l:Math.round(r.left),t:Math.round(r.top),r:Math.round(r.right),b:Math.round(r.bottom),w:Math.round(r.width),h:Math.round(r.height)};
      st.vw=w.innerWidth;st.vh=w.innerHeight;
      st.vis=cs.display+','+cs.visibility+','+cs.opacity;
      st.mode=p.getAttribute('data-lgpanel-mode');st.trade=p.getAttribute('data-lgpanel-trade');
      st.role=p.getAttribute('role');st.modal=p.getAttribute('aria-modal');
      st.sym=txt(PN+' [data-lgpanel-sym]');st.net=txt(PN+' [data-lgpanel-net]');st.netCls=nel?nel.className:'';
      st.side=txt(PN+' [data-lgpanel-side]');st.sub=txt(PN+' [data-lgpanel-sub]');
      st.slots=Array.prototype.map.call(p.querySelectorAll('[data-lgpanel-slot]'),function(e){return e.getAttribute('data-lgpanel-slot');}).join(',');
      st.inApp=!!p.closest('#app');
      st.bodyWide=b?b.scrollWidth>b.clientWidth+1:null;
      st.g=geo();
    }
    res.base=geo();
    // 0. a click on a control inside a row (a select, an input) is that control's own click: it must not open the panel
    if(cfg.view==='table'){
      await step(res,'skip',async function(st){
        var s1=q('[data-lgtrade="'+cfg.tid+'"] select[data-hmfield="grade"]'),i1=q('[data-lgtrade="'+cfg.tid+'"] input[data-field="notes"]');
        st.found=[!!s1,!!i1];
        if(s1)s1.click();
        if(i1)i1.click();
        await sleep(100);
        st.nodes=geo().nodes;
        if(st.nodes)shut();
      });
    }
    // 1. a click on a row of the list opens the panel: header, geometry, slots, the board's own pieces
    await step(res,'open',async function(st){
      st.clicked=openRow(cfg.tid);
      await sleep(200);
      look(st);
      var p=q(PN);
      st.focusIn=!!p&&p.contains(d.activeElement);
      st.expand=!!q(PN+' [data-rtcandlesexpand]');
      st.grade=!!q(PN+' select[data-hmsheetfield="grade"]');
      st.setup=!!q(PN+' select[data-hmsheetfield="setup"]');
      st.ignore=!!q(PN+' #hm-sheet-excl');
      st.notes=!!q(PN+' #hm-sheet-notes');
      st.buttons={edit:!!q(PN+' #hm-sheet-edit'),tv:!!q(PN+' #hm-sheet-tv'),del:!!q(PN+' #hm-sheet-del')};
      st.drew=await waitFor(function(){var b=q(PN+' [data-rtcandlesbody]');return b&&b.querySelector('svg');},6000);
      st.points=txt(PN+' .hm-sheet-points');if(st.points)st.points=st.points.slice(0,60);
      if(cfg.theme==='mono'&&q(PN))st.hue=hueScan(q(PN));
    });
    // 2. the open trade survives a redraw of the list (a search, then cleared) and a LIST | TABLE switch; a typed note is not lost
    await step(res,'rerender',async function(st){
      var ta=q(PN+' #hm-sheet-notes');st.hasNotes=!!ta;
      if(ta){ta.value='probe panel note';ta.dispatchEvent(new Event('input',{bubbles:true}));}
      var inp=q('#hm-search');st.searchBox=!!inp;
      st.rowsBefore=rows();
      if(inp){inp.value='aapl';inp.dispatchEvent(new Event('input',{bubbles:true}));}
      await sleep(140);
      st.search={rows:rows()};look(st.search);
      var ta2=q(PN+' #hm-sheet-notes');st.search.note=ta2?ta2.value:null;
      inp=q('#hm-search');
      if(inp){inp.value='';inp.dispatchEvent(new Event('input',{bubbles:true}));}
      await sleep(140);
      st.cleared={rows:rows()};look(st.cleared);
      var other=cfg.view==='table'?'list':'table',vb=q('[data-lgview="'+other+'"]');st.viewBtn=!!vb;
      if(vb)vb.click();
      await sleep(140);
      st.toggled={rows:rows(),mode:(q('[data-lglist-frame="hm"]')||{getAttribute:function(){return null;}}).getAttribute('data-lgmode')};look(st.toggled);
      var vb2=q('[data-lgview="'+(cfg.view==='table'?'table':'list')+'"]');
      if(vb2)vb2.click();
      await sleep(100);
    });
    // 3. Esc closes it, and the note typed in step 2 is saved on the way out
    await step(res,'esc',async function(st){
      d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      await sleep(80);
      st.open=!!q(PN);st.g=geo();
      st.sheetId=w.eval('homeSheetId');
      st.writes=notesWrites(cfg.tid);
      if(st.open)shut();
    });
    // 4. a tap or click outside closes it, a tap inside does not
    await step(res,'outside',async function(st){
      st.clicked=openRow(cfg.tid);
      await sleep(200);
      st.opened=!!q(PN);
      var s=q(PN+' [data-lgpanel-sym]');
      if(s){s.click();await sleep(40);}
      st.keptOnInside=!!q(PN);
      var pt=cfg.vp==='phone'?[Math.round(w.innerWidth/2),20]:[30,Math.round(w.innerHeight/2)];
      var el=d.elementFromPoint(pt[0],pt[1]);
      st.hit=(el&&el.classList&&el.classList.contains('lg-panel-layer'))?'layer':(el?el.tagName+'.'+el.className:null);
      if(el){el.dispatchEvent(new w.PointerEvent('pointerdown',{bubbles:true,pointerType:cfg.vp==='phone'?'touch':'mouse'}));el.click();}
      await sleep(80);
      st.open=!!q(PN);st.g=geo();
      if(st.open)shut();
    });
    // 5. the close button closes it
    await step(res,'button',async function(st){
      st.clicked=openRow(cfg.tid);
      await sleep(200);
      var x=q(PN+' [data-lgpanel-close]');st.btn=!!x;
      if(x)x.click();
      await sleep(80);
      st.open=!!q(PN);st.g=geo();
      if(st.open)shut();
    });
    // 6. another trade while it is open: the panel switches to that trade, and the first trade's note is saved
    await step(res,'switch',async function(st){
      st.clicked=openRow(cfg.tid);
      await sleep(200);
      w.eval('window.__probeData.length=0;');
      var ta=q(PN+' #hm-sheet-notes');
      if(ta){ta.value='probe switch note';ta.dispatchEvent(new Event('input',{bubbles:true}));}
      w.eval('homeSheetId='+JSON.stringify(cfg.tid2)+';renderApp();');
      await sleep(200);
      look(st);
      st.writes=notesWrites(cfg.tid).filter(function(x){return x.d.notes==='probe switch note';});
      st.nodesNow=geo().nodes;
    });
    // 7. closed again: nothing left in the page
    await step(res,'room',async function(st){
      shut();
      await sleep(60);
      st.g=geo();
      st.sheetId=w.eval('homeSheetId');
    });
    // 8. DELETE asks first: a no keeps the panel and deletes nothing, a yes deletes the trade; once the trade is gone from the
    //    list (the database snapshot) the board redraws without it and the panel closes by itself
    await step(res,'delete',async function(st){
      var oc=w.confirm,asked=0;
      st.clicked=openRow(cfg.tid);
      await sleep(200);
      w.eval('window.__probeWrites.length=0;');
      w.confirm=function(){asked++;return false;};
      var db=q(PN+' #hm-sheet-del');st.btn=!!db;
      if(db)db.click();
      await sleep(80);
      st.declined={asked:asked,open:!!q(PN),writes:JSON.parse(w.eval('JSON.stringify(window.__probeWrites)'))};
      w.confirm=function(){asked++;return true;};
      db=q(PN+' #hm-sheet-del');
      if(db)db.click();
      await sleep(80);
      st.accepted={asked:asked,writes:JSON.parse(w.eval('JSON.stringify(window.__probeWrites)'))};
      w.confirm=oc;
      w.eval('trades=trades.filter(function(t){return String(t.id)!==' + JSON.stringify(cfg.tid) + '});renderApp();');
      await sleep(120);
      st.afterSnapshot={open:!!q(PN),sheetId:w.eval('homeSheetId'),g:geo()};
      shut();
    });
    out.panels[nm]=res;
  }
  // ---- LEDGER unify step 8 follow-up: the PAGE never scrolls sideways at any width ----------------------------------------------
  // one seed per view, then the window is resized through the widths and the board is drawn again at each one: the list drops its
  // lowest-priority cells as the window narrows, the SIMPLE table fits its box, the FULL table scrolls inside its own box
  async function setWidth(px){
    fr.style.width=px+'px';fr.style.height='800px';
    await waitFor(function(){return W().innerWidth===px;},2000);
    await sleep(60);
  }
  function cellKey(c){var m=/lg-c-([a-z0-9]+)/.exec(typeof c.className==='string'?c.className:'');return m?m[1]:'?';}
  async function widthRun(nm,cfg,widths){
    var w=W(),d=D(),res={widths:{}};
    await setWidth(widths[widths.length-1]);
    drain();
    try{res.seed=seed({vp:'laptop',theme:cfg.theme,missed:2,view:cfg.view,ledger:cfg.ledger});}
    catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    res.seedErr=drain();
    for(var i=0;i<widths.length;i++){
      var px=widths[i],st={};
      try{
        await setWidth(px);
        w.eval('renderApp();');
        await sleep(150);
        var wr0=d.querySelector('.hm-wrap'),wt0=wr0?wr0.getBoundingClientRect().top:0;
        st.sec=Array.prototype.map.call(d.querySelectorAll('[data-hmsec]'),function(e){var b=e.getBoundingClientRect();return {k:e.getAttribute('data-hmsec'),top:Math.round(b.top-wt0),h:Math.round(b.height)};});
        if(i===0){try{res.bp=bpScan();}catch(e0){res.bp={err:String(e0)};}}
        var de=d.documentElement;
        st.innerW=w.innerWidth;st.scrollW=de.scrollWidth;st.clientW=de.clientWidth;
        if(st.scrollW>st.clientW+1||st.scrollW>st.innerW+1)st.wide=offenders(d);
        var frm=q('[data-lglist-frame="hm"]');
        st.frame=!!frm;
        if(frm){
          st.mode=frm.getAttribute('data-lgmode');
          var fright=frm.getBoundingClientRect().right;
          if(st.mode==='list'){
            var rws=Array.prototype.slice.call(frm.querySelectorAll('.lg-tl-row[data-lgtrade]'));
            st.rows=rws.length;st.rowOver=0;st.lastOver=0;st.cells=null;
            rws.forEach(function(r){
              var vis=Array.prototype.filter.call(r.children,function(c){return w.getComputedStyle(c).display!=='none';});
              if(r.scrollWidth>r.clientWidth+1)st.rowOver++;
              var last=vis[vis.length-1];
              if(last&&last.getBoundingClientRect().right>fright+1)st.lastOver++;
              var ks=vis.map(cellKey).join(',');
              if(st.cells===null)st.cells=ks;else if(st.cells!==ks)st.cellsVary=true;
            });
          }else{
            var wrap=frm.querySelector('.lg-tl-wrap');
            st.box=wrap?{sw:wrap.scrollWidth,cw:wrap.clientWidth}:null;
            st.rows=frm.querySelectorAll('tr[data-lgtrade]').length;
          }
        }
      }catch(e){st.threw=String(e&&e.stack?e.stack:e);}
      Object.assign(st,drain());
      res.widths[px]=st;
    }
    out.widths[nm]=res;
  }
  var LSK=['el_lg_paste_real','el_lg_missed_real','el_lg_deps_real','el_lg_ai_real','el_home_journal_open'];
  function lsRead(){var o={};LSK.forEach(function(k){try{o[k]=W().localStorage.getItem(k);}catch(e){o[k]='ERR';}});return o;}
  function foldStates(){var o={};Array.prototype.forEach.call(D().querySelectorAll('[data-hmfold]'),function(b){o[b.getAttribute('data-hmfold')]=b.getAttribute('aria-expanded');});return o;}
  function clickAll(){OWN.forEach(function(k){var b=D().querySelector('[data-hmfold="'+k+'"]');if(b)b.click();});}
  async function foldRun(nm,cfg){
    var res={};
    await setVp(cfg.vp);
    drain();
    var sc={vp:cfg.vp,theme:cfg.theme,missed:2,view:'feed',ledger:'simple'};
    // the folds exactly as the app starts them on a fresh browser, before the seed (which resets them) touches anything
    try{res.init=JSON.parse(W().eval('JSON.stringify({paste:!!homeOwnOpen.paste,missed:!!homeOwnOpen.missed,deps:!!homeOwnOpen.deps,ai:!!homeAiOpen,journal:!!homeJournalOpen})'));}
    catch(e){res.init='ERR '+(e&&e.stack?e.stack:e);}
    try{res.seed=seed(sc);}catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    res.seedErr=drain();
    res.start=foldStates();res.lsStart=lsRead();
    clickAll();                       // every own fold opens ...
    await sleep(80);
    res.opened=foldStates();res.lsOpened=lsRead();
    await reloadFrame();              // ... and a reload brings the page back with them open
    var sc2=Object.assign({keepLs:true},sc);
    try{res.seed2=seed(sc2);}catch(e){res.seed2='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    res.afterReload=foldStates();res.lsAfter=lsRead();res.err1=drain();
    clickAll();                       // every own fold closes ...
    await sleep(80);
    res.closed=foldStates();res.lsClosed=lsRead();
    await reloadFrame();              // ... and a reload brings it back with them closed
    try{res.seed3=seed(sc2);}catch(e){res.seed3='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    res.afterReload2=foldStates();res.err2=drain();
    if(cfg.cal){
      // the calendar default is a width test in the app's own script (it runs at page load): closed up to 600 px, open above - the house number
      res.cal={};
      var CW=[600,601];
      for(var ci=0;ci<CW.length;ci++){
        await setWidth(CW[ci]);
        await reloadFrame();
        res.cal[CW[ci]]=W().eval('homeCalOpen');
      }
      res.errCal=drain();
    }
    out.folds[nm]=res;
  }
  var started=false;
  fr.addEventListener('load',function(){
    if(started)return;started=true;   // a reload inside a fold run is not another run
    setTimeout(async function(){
      var w=W();
      try{
        out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
        out.renderApp=typeof w.renderApp;
        sink=hook(w);
      }catch(e){out.err=String(e);finish('hookfail');return;}
      if(out.renderApp!=='function'){finish('noboot');return;}
      // Firebase auth settles with no user and paints the SIGN IN screen; wait for it, then make
      // renderAuth a no-op so a late callback cannot paint over a case (report probe, 2026-09-28).
      out.authSettled=await waitFor(function(){return !!D().getElementById('tsu');},12000);
      try{w.eval('renderAuth=function(){};');}catch(e){out.notes.push('renderAuth stub: '+e);}
      await sleep(200);
      out.bootNoise=drain();
      overlays();
      try{
        w.__probeDataJson=JSON.stringify(DATA);
        w.__probeBarsJson=JSON.stringify(BARS);
        w.eval(__INSTALL__);
      }catch(e){out.err='install failed: '+(e&&e.stack?e.stack:e);finish('installfail');return;}
      out.hidden=!!D().hidden;
      for(var i=0;i<CASES.length;i++)await runCase(CASES[i][0],CASES[i][1]);
      for(var j=0;j<INTER.length;j++){
        try{await interact(INTER[j][0],INTER[j][1]);}
        catch(e){out.inter[INTER[j][0]]={threw:String(e&&e.stack?e.stack:e)};}
      }
      for(var k=0;k<PANELS.length;k++){
        try{await panelRun(PANELS[k][0],PANELS[k][1]);}
        catch(e){out.panels[PANELS[k][0]]={threw:String(e&&e.stack?e.stack:e)};}
      }
      for(var m=0;m<WIDTHS.length;m++){
        try{await widthRun(WIDTHS[m][0],WIDTHS[m][1],WIDTHS[m][2]);}
        catch(e){out.widths[WIDTHS[m][0]]={threw:String(e&&e.stack?e.stack:e)};}
      }
      for(var f=0;f<FOLDS.length;f++){
        try{await foldRun(FOLDS[f][0],FOLDS[f][1]);}
        catch(e){out.folds[FOLDS[f][0]]={threw:String(e&&e.stack?e.stack:e)};}
      }
      out.barReads=W().__probeBarReads||0;
      finish('done');
    },2500);
  });
})();
</script>
</body></html>
"""

# Runs inside the app's own realm (indirect eval), so it can reach its top-level `let` bindings
# (trades, missedTrades, homeView, colRef, prefs ...), which are not window properties.
INSTALL_JS = r"""
(function(){
  window.__probeWrites=[];window.__probeData=[];
  function mkRef(name){
    var log=function(op){window.__probeWrites.push(name+'.'+op);return Promise.resolve();};
    var ref={
      add:function(){window.__probeWrites.push(name+'.add');return Promise.resolve({id:'probe_new'});},
      doc:function(id){return {
        update:function(d){window.__probeData.push({n:name,id:String(id),d:d});return log('update '+id);},
        set:function(){return log('set '+id);},
        delete:function(){return log('delete '+id);},
        get:function(){return Promise.resolve({exists:false,id:id,data:function(){return null;}});},
        onSnapshot:function(){return function(){};}};},
      where:function(){return ref;},orderBy:function(){return ref;},limit:function(){return ref;},
      get:function(){return Promise.resolve({docs:[],empty:true,size:0,forEach:function(){}});},
      onSnapshot:function(){return function(){};}
    };
    return ref;
  }
  window._missedRef=mkRef('missed_trades');
  colRef=mkRef('trades');
  var BARS=JSON.parse(window.__probeBarsJson);
  window._rtBarsSource=async function(tid){
    window.__probeBarReads=(window.__probeBarReads||0)+1;
    var d=BARS[String(tid)];return d?JSON.parse(JSON.stringify(d)):null;};
  // a headless page may never run animation frames; the chart's pan / zoom redraw waits on one
  window.requestAnimationFrame=function(cb){return setTimeout(function(){cb(performance.now());},0);};
  window.cancelAnimationFrame=function(h){clearTimeout(h);};
  window.__probeSeed=function(cj){
    var C=JSON.parse(cj),S=JSON.parse(window.__probeDataJson);
    prefs.theme=C.theme;applyTheme();
    trades=S.trades;missedTrades=C.missed?S.missed:[];
    ledgerEvents=S.ledger||[];lessons=S.lessons||[];
    // the legacy TRADES / JOURNAL tabs only draw behind ?oldtabs=1 (the app reads this flag on every render)
    window.LOG_OLDTABS_ESCAPE_HATCH=!!C.tab;window._lastLogTab=C.tab||undefined;
    activeTab=C.tab||'home';homeView=C.view;homeLedger=C.ledger;homeSheetId=null;
    homeRange='ALL';homeChip='ALL';homeQuery='';homeFeedMode='trade';homeChartMode='equity';
    homeStatsOpen=false;homeExtras=false;homeNewTradeOpen=false;
    // LEDGER step 11: every own fold starts closed and the calendar on its default for this width (open above 600 px), unless the case keeps what the page remembered
    if(!C.keepLs){
      homeAiOpen=false;homeAcctOpen=false;homeJournalOpen=false;homeOwnOpen.paste=false;homeOwnOpen.missed=false;homeOwnOpen.deps=false;
      try{['el_lg_ai_real','el_lg_acct_real','el_home_journal_open','el_lg_paste_real','el_lg_missed_real','el_lg_deps_real','el_lg_cal_real'].forEach(function(k){localStorage.removeItem(k);});}catch(e){}
      homeCalOpen=(window.innerWidth||1200)>600;
    }
    window._hmMissedEdit=null;window._hmPasteNote=null;window._hmPasteLast=null;window._hmPasteAsk=null;
    window._thMenu=null;window._hmTblScrollL=0;window._hmTblScrollT=0;window._hmNote=null;
    window._hmJumpPrevView=null;window._hmSearchTyping=false;window._rtSheetTfFor={};
    try{localStorage.removeItem('el_paste_hold');}catch(e){}
    window.__probeWrites.length=0;
    try{window.scrollTo(0,0);}catch(e){}
    // Same tab as the last render, so no tab-switch fade: while .fade's transform animates, the
    // closed trade panel (position:fixed, parked off the right edge) is laid out inside the
    // animated wrapper and the page measures 720px wide on a phone for those 0.2s. That is a
    // transient of the tab switch, not of HOME, and only the first case would ever see it.
    window._lastRenderTab='home';
    renderApp();
    return 'OK';
  };
})();
"""


# ---------------------------------------------------------------- synthetic data

def _et_epoch(date, hms):
    """New York wall clock -> epoch seconds. Every probe date sits in late Sept / early Oct 2026,
    inside daylight time (EDT, UTC-4, until 2026-11-01), so a fixed offset is exact here."""
    y, m, d = (int(x) for x in date.split('-'))
    hh, mm, ss = (int(x) for x in (hms.split(':') + ['0'])[:3])
    return calendar.timegm((y, m, d, hh, mm, ss)) + 4 * 3600


def _q(px):
    return round(px * 4) / 4.0


def _pack(t0, step, n, px, rng):
    """The api/trade_bars.py _pack shape: 'off,o,h,l,c,v;...' with off = (bar start - t0) / step."""
    parts = []
    for i in range(n):
        o = _q(px)
        c = _q(px + rng.uniform(-3.0, 3.0))
        h = _q(max(o, c) + rng.uniform(0, 1.5))
        lo = _q(min(o, c) - rng.uniform(0, 1.5))
        parts.append('%d,%s,%s,%s,%s,%d' % (i, ('%.2f' % o).rstrip('0').rstrip('.'),
                                            ('%.2f' % h).rstrip('0').rstrip('.'),
                                            ('%.2f' % lo).rstrip('0').rstrip('.'),
                                            ('%.2f' % c).rstrip('0').rstrip('.'),
                                            rng.randint(40, 900)))
        px = c
    return {'t0': t0, 'step': step, 's': ';'.join(parts)}


def _bars_doc(date, t_in, t_out, px, with10s, seed, overnight=False):
    rng = random.Random(seed)
    e = _et_epoch(date, t_in)
    x = (_et_epoch(date, t_out) + (86400 if overnight else 0)) if t_out else None
    m0 = (e // 60) * 60 - 30 * 60
    last = (x if x else e) + 30 * 60
    n1 = (last - m0) // 60 + 1
    doc = {'v': 1, 'entry': {'t': e, 'px': px}, 'exit': ({'t': x, 'px': px + 5} if x else None),
           'b1m': dict(_pack(m0, 60, n1, px, rng), src='probe 1m', shift=0), 'complete': True}
    if with10s:
        s0 = (e // 10) * 10 - 600            # 60 bars before the entry: the trade view is a slice
        s_last = (x if x else e) + 600
        doc['b10s'] = dict(_pack(s0, 10, (s_last - s0) // 10 + 1, px, rng), src='probe 10s', shift=0)
    return doc


def _ps(date, t_in, hits, na=0, trend=True):
    """A ps1.1 point score: nine points, `hits` of them hit, `na` of them NA (never a 0)."""
    keys = [('ma200_10s', 'Above 200 EMA (10s)'), ('ma200_1m', 'Above 200 EMA (1m)'),
            ('ma200_5m', 'Above 200 EMA (5m)'), ('ma200_30m', 'Above 200 EMA (30m)'),
            ('y_low', "Above yesterday's low"), ('y_close', "Above yesterday's close"),
            ('y_high', "Above yesterday's high"), ('big_body', "Largest body since today's low"),
            ('big_vol', "Largest volume since today's low")]
    pts = []
    for i, (k, label) in enumerate(keys):
        if i < na:
            pts.append({'k': k, 'label': label, 'hit': None, 'val': None, 'ref': None,
                        'na_reason': 'no 10-second data'})
        else:
            pts.append({'k': k, 'label': label, 'hit': (i - na) < hits, 'val': 20012.25 + i,
                        'ref': 20001.5 + i, 'na_reason': None})
    hh, mm = (int(v) for v in t_in.split(':')[:2])
    sig = '%02d:%02d' % ((hh * 60 + mm - 1) // 60, (hh * 60 + mm - 1) % 60)
    rec = {'v': 'ps1.1', 'side': 'LONG', 'total': hits, 'max': 9 - na, 'na_count': na,
           'signal_bar': '%s %s:00' % (date, sig), 'fill': '%s %s' % (date, (t_in + ':00')[:8]),
           'tf': '1m', 'points': pts, 'src': 'probe', 'notes': []}
    if trend:
        rec['trend'] = {'k': 'd_trend', 'label': 'Daily trend up', 'hit': True, 'val': 5801.25,
                        'ref': 5760.0, 'na_reason': None}
    return rec


def build_data():
    T = []

    def tr(i, sym, side, date, t_in, t_out, tf, entry, exit_, size, mult, fees, **kw):
        d = 1 if side == 'LONG' else -1
        gross = round((exit_ - entry) * d * size * mult, 2)
        t = {'id': i, 'symbol': sym, 'type': side, 'date': date, 'entryTime': t_in, 'exitTime': t_out,
             'timeframe': tf, 'entry': entry, 'exit': exit_, 'size': size, 'grossPnl': gross, 'fees': fees,
             'pnl': round(gross - fees, 2), 'setup': 'CBU', 'grade': 'B', 'broker': 'NinjaTrader',
             'account': 'probe', 'notes': '', 'tags': [], 'source': 'probe', 'durationMins': 7}
        t.update(kw)
        T.append(t)

    tr('probe_t1', 'MNQ', 'LONG', '2026-09-30', '10:00:00', '10:07:00', '1m', 20000.25, 20012.5, 2, 2, 1.48,
       pointScore=_ps('2026-09-30', '10:00:00', 7, na=1),
       notes='probe trade with a note')
    tr('probe_t2', 'MNQ', 'SHORT', '2026-09-30', '11:15:00', '11:21:30', '10s, 1m', 20040.0, 20046.75, 1, 2,
       0.74, pointScore=_ps('2026-09-30', '11:15:00', 3, na=2), chartUrl='https://www.tradingview.com/x/PROBE0/')
    tr('probe_t3', 'MES', 'LONG', '2026-10-01', '09:45:10', '09:52:40', '10s', 5801.0, 5804.25, 3, 5, 2.22,
       pointScore=_ps('2026-10-01', '09:45:10', 6, na=0, trend=False))
    tr('probe_t4', 'MES', 'SHORT', '2026-09-29', '14:02:00', '14:30:00', '5m', 5790.5, 5786.0, 1, 5, 0.74,
       statsExcluded=True, grade='C')
    tr('probe_t5', 'MNQ', 'LONG', '2026-09-28', '09:31:00', '09:33:00', '1m', 19950.0, 19947.25, 1, 2, 0.74,
       pointScore=_ps('2026-09-28', '09:31:00', 0, na=9))
    tr('probe_t6', 'MNQ', 'SHORT', '2026-10-01', '13:05:00', '13:12:00', '1m', 20110.5, 20101.0, 1, 2, 0.74,
       pointScore=_ps('2026-10-01', '13:05:00', 5, na=1))
    tr('probe_s1', 'AAPL', 'LONG', '2026-09-30', '15:30:00', '15:55:00', '5m', 231.4, 232.1, 50, 1, 0.0,
       broker='Webull', setup='Breakout')
    # a flat trade (entry == exit, no fee): neither a win nor a loss - the WINS and LOSSES chips must leave it out
    tr('probe_z1', 'MNQ', 'LONG', '2026-09-29', '15:10:00', '15:15:00', '1m', 20000.0, 20000.0, 1, 2, 0.0,
       notes='a flat trade: neither a win nor a loss')
    # entered 09-30 at 23:55, held 25 minutes: it CLOSES on 10-01 (the New York day it belongs to)
    tr('probe_o1', 'MNQ', 'SHORT', '2026-09-30', '23:55:00', '00:20:00', '1m', 20050.0, 20044.5, 1, 2, 0.74,
       durationMins=25)
    T.sort(key=lambda t: (t['date'], t['entryTime']))

    missed = [
        {'id': 'probe_m1', 'url': 'https://www.tradingview.com/x/PROBEM1/', 'setup': 'CBU', 'symbol': 'MNQ',
         'date': '2026-09-30', 'entryTime': '10:30', 'type': 'LONG', 'entry': 20030.0, 'stop': 20015.0,
         'target': 20060.0, 'note': 'probe: saw it, did not take it', 'source': 'form',
         'pointScore': _ps('2026-09-30', '10:30', 5, na=0)},
        {'id': 'probe_m2', 'url': '', 'setup': 'Fade', 'symbol': 'TSLA', 'date': '2026-10-01',
         'entryTime': '14:10', 'type': 'SHORT', 'entry': None, 'stop': None, 'target': None, 'note': '',
         'source': 'paste'},
    ]

    bars = {}
    px = {'MNQ': 20000.0, 'MES': 5800.0}
    for i, t in enumerate(T):
        if t['symbol'] in px:
            bars[t['id']] = _bars_doc(t['date'], t['entryTime'], t['exitTime'], px[t['symbol']],
                                      True, 1000 + i, overnight=(t['id'] == 'probe_o1'))
    bars['missed_probe_m1'] = _bars_doc('2026-09-30', '10:30:00', None, 20030.0, True, 77)
    ledger = [{'date': '2026-09-29', 'amount': 1000.0, 'desc': 'probe deposit', 'broker': 'NinjaTrader'}]
    lessons = [{'id': 'probe_l1', 'title': 'Chased a breakout and overtraded the open', 'date': '2026-09-30',
                'tags': ['psychology', 'risk management', 'entries'],
                'body': 'Entered the first push without waiting for the pullback. ' * 6
                        + 'A_very_long_unbroken_word_that_has_no_spaces_in_it_at_all_' * 4}]
    return {'trades': T, 'missed': missed, 'ledger': ledger, 'lessons': lessons}, bars


# ---------------------------------------------------------------- harness

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


def _render_page(chrome, root, alt_index, cases, inter, qs, data_obj, bars, panels=None, widths=None, folds=None):
    """One render of the probe page in a fresh headless Chrome. Returns (data, error message or None)."""
    pdir = tempfile.mkdtemp(prefix='_homeprobe_', dir=root)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__QS__', qs)
            .replace('__CASES__', json.dumps(cases))
            .replace('__INTER__', json.dumps(inter))
            .replace('__VP__', json.dumps(VIEWPORTS))
            .replace('__DATA__', json.dumps(data_obj))
            .replace('__BARS__', json.dumps(bars))
            .replace('__PASTE__', json.dumps(PASTE_URL))
            .replace('__PANELS__', json.dumps(panels or []))
            .replace('__WIDTHS__', json.dumps(widths or []))
            .replace('__FOLDS__', json.dumps(folds or []))
            .replace('__HOUSE__', json.dumps(HOUSE_WIDTHS))
            .replace('__OWN__', json.dumps(OWN_FOLDS))
            .replace('__OLDMARKS__', json.dumps(OLD_MARKS))
            .replace('__INSTALL__', json.dumps(INSTALL_JS)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='homeprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
             '--user-data-dir=' + prof, '--virtual-time-budget=84000', '--window-size=1500,1000',
             '--dump-dom', 'http://127.0.0.1:%d/%s/probe.html' % (port, os.path.basename(pdir))],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300).stdout
    except Exception as e:
        return None, 'chrome failed: %s' % e
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'HOMEPROBE: (\{.*?\})</pre>', out or '', re.S)
    if not m:
        return None, 'probe produced no readout'
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return None, 'unreadable readout: %s' % e
    return data, None


def _attempt(chrome, root, alt_index):
    """Lint index.html for identifiers the clean-up removed, render every case and interaction once in a fresh headless Chrome, then the
    ?oldboards=1 page (which must draw the same board) in a second page load.
    Returns (verdict, fails, notes, data, retry_worthy)."""
    probs = _removed_lint(root, alt_index)
    if probs:
        return FAIL, probs, [], None, False
    data_obj, bars = build_data()
    data, err = _render_page(chrome, root, alt_index, CASES, INTERACTIONS, '', data_obj, bars)
    if err:
        return INCONCLUSIVE, [err], [], None, True
    flag, err = _render_page(chrome, root, alt_index, FLAG_CASES, [], '?oldboards=1', data_obj, bars)
    if err:
        return INCONCLUSIVE, ['?oldboards=1 pass: %s' % err], [], data, True
    pnl, err = _render_page(chrome, root, alt_index, [], [], '', data_obj, bars, PANEL_CASES)
    if err:
        return INCONCLUSIVE, ['trade panel pass: %s' % err], [], data, True
    wid, err = _render_page(chrome, root, alt_index, [], [], '', data_obj, bars, None, WIDTH_RUNS)
    if err:
        return INCONCLUSIVE, ['width sweep pass: %s' % err], [], data, True
    fld, err = _render_page(chrome, root, alt_index, [], [], '', data_obj, bars, None, None, FOLD_RUNS)
    if err:
        return INCONCLUSIVE, ['fold pass (reload): %s' % err], [], data, True
    if os.environ.get('HOMEPROBE_DUMP'):
        io.open(os.path.join(root, '_homeprobe_dump.json'), 'w', encoding='utf-8').write(
            json.dumps({'main': data, 'flag': flag, 'panels': pnl, 'widths': wid, 'folds': fld}, indent=1, ensure_ascii=False))
    data['flag'] = flag
    data['panels'] = pnl
    data['widths'] = wid
    data['folds'] = fld
    return _judge(data, data_obj)


def _close_day(t):
    """The New York day a trade closed - the same rule as the app's ledgerCloseDay."""
    import datetime
    if t.get('exitDate'):
        return t['exitDate'][:10]
    parts = [int(x) for x in (t.get('entryTime') or '').split(':')]
    dur = t.get('durationMins') or 0
    if t.get('date') and parts and dur > 0:
        e = parts[0] * 3600 + (parts[1] if len(parts) > 1 else 0) * 60 + (parts[2] if len(parts) > 2 else 0)
        add = (e + dur * 60) // 86400
        if add > 0:
            return (datetime.date.fromisoformat(t['date']) + datetime.timedelta(days=add)).isoformat()
    return t['date']


def _close_key(t):
    parts = [int(x) for x in (t.get('exitTime') or t.get('entryTime') or '0').split(':')]
    secs = parts[0] * 3600 + (parts[1] if len(parts) > 1 else 0) * 60 + (parts[2] if len(parts) > 2 else 0)
    return '%s %05d' % (_close_day(t), secs)


def _signed(v):
    return '%s$%s' % ('+' if v >= 0 else '-', format(abs(v), ',.2f'))


def expected_days(trades):
    """{close day: signed net} - what each day header of the frame must read."""
    nets = {}
    for t in trades:
        k = _close_day(t)
        nets[k] = nets.get(k, 0.0) + t['pnl']
    return {k: _signed(round(v, 2)) for k, v in nets.items()}


def _judge_panels(panels, data_obj):
    """LEDGER unify step 9: the shared trade panel opened from the list, on a laptop and a phone, in glass / paper / MONO."""
    fails, unfinished = [], []
    cases = (panels or {}).get('panels') or {}
    T = {t['id']: t for t in data_obj['trades']}
    n_trades = len(data_obj['trades'])
    for nm, cfg in PANEL_CASES:
        r = cases.get(nm)
        tag = 'trade panel %s' % nm
        if r is None:
            unfinished.append('%s: never ran' % tag)
            continue
        if r.get('threw'):
            fails.append('%s: the probe itself threw -- %s' % (tag, _first(r['threw'])))
            continue
        if r.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('seed'))))
            continue
        _errs(tag + ' (render)', r.get('seedErr') or {}, fails)
        st = r.get('steps') or {}
        base = r.get('base') or {}
        phone = cfg['vp'] == 'phone'
        sheet = cfg['vp'] in ('phone', 'edge600')      # 600 px and under: a bottom sheet; above: a right-hand panel
        t1, t2 = T[cfg['tid']], T[cfg['tid2']]
        want = {cfg['tid']: (t1['symbol'], _signed(t1['pnl']), t1['type'], 'lg-up' if t1['pnl'] > 0 else 'lg-down'),
                cfg['tid2']: (t2['symbol'], _signed(t2['pnl']), t2['type'], 'lg-up' if t2['pnl'] > 0 else 'lg-down')}
        for step_name in ('open', 'rerender', 'esc', 'outside', 'button', 'switch', 'room', 'delete'):
            s = st.get(step_name) or {}
            _errs('%s, %s' % (tag, step_name), s, fails)
            if s.get('threw'):
                fails.append('%s, %s: %s' % (tag, step_name, _first(s['threw'])))

        def says(label, s, tid):
            """The panel in `s` shows trade `tid`: its id, symbol, signed net (with the right colour token) and side."""
            sym, net, side, cls = want[tid]
            if s.get('trade') != tid:
                fails.append('%s: %s - the panel is tied to trade %r, expected %r' % (tag, label, s.get('trade'), tid))
            if s.get('sym') != sym:
                fails.append('%s: %s - the panel header shows %r, expected %s' % (tag, label, s.get('sym'), sym))
            if s.get('net') != net:
                fails.append('%s: %s - the panel net reads %r, expected %s' % (tag, label, s.get('net'), net))
            elif cls not in (s.get('netCls') or '').split():
                fails.append('%s: %s - the panel net is not coloured with %s (class %r)' % (tag, label, cls, s.get('netCls')))
            if s.get('side') != side:
                fails.append('%s: %s - the panel side tag reads %r, expected %s' % (tag, label, s.get('side'), side))

        def room(label, g):
            """A page with no panel open: nothing of it left behind, the page exactly as big as before the first open."""
            g = g or {}
            if g.get('nodes'):
                fails.append('%s: %s - %s trade panel node(s) are still in the page (a closed panel must not be in it)'
                             % (tag, label, g.get('nodes')))
            for k, nice in (('sw', 'width'), ('sh', 'height')):
                if g.get(k) is None or base.get(k) is None or abs(g[k] - base[k]) > 1:
                    fails.append('%s: %s - the page is %s px %s, it was %s before the panel opened (a closed panel takes room)'
                                 % (tag, label, g.get(k), nice, base.get(k)))
            if g.get('kids') != base.get('kids'):
                fails.append('%s: %s - <body> holds %s elements, it held %s before the panel opened'
                             % (tag, label, g.get('kids'), base.get('kids')))

        if base.get('nodes'):
            fails.append('%s: the panel is in the page before anything was opened (%s node(s))' % (tag, base.get('nodes')))
        # -- a control inside a row
        if cfg['view'] == 'table':
            sk = st.get('skip') or {}
            _errs('%s, a click on a control in a row' % tag, sk, fails)
            if sk.get('found') != [True, True]:
                fails.append('%s: the TABLE row has no grade select or notes box to click (%r)' % (tag, sk.get('found')))
            elif sk.get('nodes'):
                fails.append('%s: a click on the grade select or the notes box inside a row opened the trade panel' % tag)
        # -- open
        o = st.get('open') or {}
        if not o.get('clicked') or not o.get('exists'):
            fails.append('%s: a click on the row of %s did not open the trade panel (row found=%s)' % (tag, cfg['tid'], o.get('clicked')))
            continue
        says('open', o, cfg['tid'])
        want_mode = 'sheet' if sheet else 'side'
        if o.get('mode') != want_mode:
            fails.append('%s: the panel mode is %r, expected %r (%s)' % (tag, o.get('mode'), want_mode, 'phone = bottom sheet, laptop = right-hand panel'))
        vis = (o.get('vis') or ',,0').split(',')
        if vis[0] not in ('block', 'flex') or vis[1] != 'visible' or float(vis[2] or 0) < 0.5:
            fails.append('%s: the open panel is not visible (display,visibility,opacity = %s)' % (tag, o.get('vis')))
        if o.get('role') != 'dialog' or o.get('modal') != 'true':
            fails.append('%s: the panel is not marked role=dialog aria-modal=true (%r, %r)' % (tag, o.get('role'), o.get('modal')))
        rc, vw, vh = o.get('rect') or {}, o.get('vw') or 0, o.get('vh') or 0
        if sheet:
            if not (rc.get('l') == 0 and rc.get('w') == vw and rc.get('b') == vh):
                fails.append('%s: on a phone the panel should be a bottom sheet the full width and sitting on the bottom edge '
                             '(left=%s width=%s bottom=%s, screen %sx%s)' % (tag, rc.get('l'), rc.get('w'), rc.get('b'), vw, vh))
            if (rc.get('h') or 0) > 0.9 * vh or (rc.get('t') or 0) < 0.1 * vh:
                fails.append('%s: the phone sheet is %spx tall with its top at %spx on a %spx screen: it must leave a strip of '
                             'page above it to tap (at most 90%% of the height)' % (tag, rc.get('h'), rc.get('t'), vh))
        else:
            if not (abs((rc.get('r') or 0) - vw) <= 1 and abs((rc.get('h') or 0) - vh) <= 1 and 380 <= (rc.get('w') or 0) <= 460):
                fails.append('%s: on a laptop the panel should be a right-hand panel 380-460px wide and the full height '
                             '(right=%s width=%s height=%s, screen %sx%s)' % (tag, rc.get('r'), rc.get('w'), rc.get('h'), vw, vh))
            if cfg['vp'] == 'laptop' and (rc.get('l') or 0) < 200:
                fails.append('%s: the laptop panel starts %spx from the left, it covers the page' % (tag, rc.get('l')))
        if o.get('inApp'):
            fails.append('%s: the panel is inside #app, which every redraw rebuilds - it must live in <body>' % tag)
        slots = (o.get('slots') or '').split(',')
        if [x for x in slots if x != 'ignore'] != ['head', 'chart', 'numbers', 'notes', 'actions']:
            fails.append('%s: the panel slots come in the order %r, expected head, chart, numbers, notes, actions' % (tag, o.get('slots')))
        elif slots != ['head', 'chart', 'ignore', 'numbers', 'notes', 'actions']:
            fails.append('%s: the IGNORE IN METRICS block should sit between the chart and the numbers (slots: %r)' % (tag, o.get('slots')))
        if o.get('bodyWide'):
            fails.append('%s: the panel body scrolls sideways' % tag)
        g = o.get('g') or {}
        # the page never scrolls sideways while the panel is open, at any of the panel widths (375, 600, 601, 1366)
        if (g.get('sw') or 0) > (g.get('cw') or 0) + 1:
            fails.append('%s: the page scrolls sideways while the panel is open (scrollWidth %s > %s)' % (tag, g.get('sw'), g.get('cw')))
        if abs((g.get('sw') or 0) - (base.get('sw') or 0)) > 1 or abs((g.get('sh') or 0) - (base.get('sh') or 0)) > 1:
            fails.append('%s: opening the panel changed the page size from %sx%s to %sx%s (it must sit over the page)'
                         % (tag, base.get('sw'), base.get('sh'), g.get('sw'), g.get('sh')))
        if not o.get('focusIn'):
            fails.append('%s: focus did not move into the panel when it opened' % tag)
        if not o.get('grade') or not o.get('setup'):
            fails.append('%s: the panel has no grade / setup select (grade=%s setup=%s)' % (tag, o.get('grade'), o.get('setup')))
        if not o.get('ignore') or not o.get('notes'):
            fails.append('%s: the panel lost IGNORE IN METRICS or the notes box (ignore=%s notes=%s)' % (tag, o.get('ignore'), o.get('notes')))
        b = o.get('buttons') or {}
        if not (b.get('edit') and b.get('tv') and b.get('del')):
            fails.append('%s: the panel lost one of EDIT / OPEN IN TV / DELETE (%r)' % (tag, b))
        if not sheet and not o.get('expand'):
            fails.append('%s: the laptop chart has no EXPAND button' % tag)
        if phone and o.get('expand'):
            fails.append('%s: the phone chart shows EXPAND (it opens the full viewer, which a phone does not get)' % tag)
        if not o.get('drew'):
            fails.append('%s: the chart in the panel never drew an <svg>' % tag)
        if 'POINTS' not in (o.get('points') or ''):
            fails.append('%s: the POINTS block is missing from the panel (%r)' % (tag, o.get('points')))
        if cfg['theme'] == 'mono':
            hue = o.get('hue') or {}
            if (hue.get('checked') or 0) < 40:
                fails.append('%s: the MONO hue scan read only %s colours - it did not run' % (tag, hue.get('checked')))
            if hue.get('bad'):
                fails.append('%s: the panel carries a hue in MONO: %s' % (tag, '; '.join(hue['bad'])))
        # -- a redraw of the list, a search, a LIST | TABLE switch: the same trade, the typed note still there
        rr = st.get('rerender') or {}
        if not rr.get('hasNotes') or not rr.get('searchBox'):
            fails.append('%s: the redraw test could not find the notes box or the search box (%r)' % (tag, rr))
        else:
            if (rr.get('search') or {}).get('rows') != 1:
                fails.append('%s: searching "aapl" left %s rows in the list, expected the one AAPL trade'
                             % (tag, (rr.get('search') or {}).get('rows')))
            for key, nice, rows_want in (('search', 'after a search redrew the list', 1), ('cleared', 'after the search was cleared', n_trades),
                                         ('toggled', 'after LIST | TABLE was switched', n_trades)):
                s = rr.get(key) or {}
                if not s.get('exists'):
                    fails.append('%s: the trade panel closed %s (it must stay open on its trade)' % (tag, nice))
                    continue
                says(nice, s, cfg['tid'])
                if s.get('rows') != rows_want:
                    fails.append('%s: %s the list shows %s rows, expected %s' % (tag, nice, s.get('rows'), rows_want))
            if (rr.get('search') or {}).get('note') != 'probe panel note':
                fails.append('%s: the half-typed note was lost when the list redrew (box now says %r)' % (tag, (rr.get('search') or {}).get('note')))
        # -- Esc
        e = st.get('esc') or {}
        room('after Esc', e.get('g'))
        if e.get('open'):
            fails.append('%s: Esc did not close the panel' % tag)
        if e.get('sheetId') is not None:
            fails.append('%s: after Esc the board still says trade %r is open' % (tag, e.get('sheetId')))
        ew = [x['d']['notes'] for x in (e.get('writes') or [])]
        if ew != ['probe panel note']:
            fails.append('%s: a note typed in the panel should be saved once, as it closes (notes written: %r)' % (tag, ew))
        # -- tap outside
        ou = st.get('outside') or {}
        if not ou.get('opened'):
            fails.append('%s: the panel did not open a second time' % tag)
        else:
            if ou.get('hit') != 'layer':
                fails.append('%s: the point outside the panel is %r, not the dim layer' % (tag, ou.get('hit')))
            if not ou.get('keptOnInside'):
                fails.append('%s: a click inside the panel closed it' % tag)
            if ou.get('open'):
                fails.append('%s: a click or tap outside the panel did not close it' % tag)
            room('after a tap outside', ou.get('g'))
        # -- close button
        bt = st.get('button') or {}
        if not bt.get('btn'):
            fails.append('%s: the panel has no close button' % tag)
        elif bt.get('open'):
            fails.append('%s: the close button did not close the panel' % tag)
        else:
            room('after the close button', bt.get('g'))
        # -- another trade while open
        sw = st.get('switch') or {}
        if not sw.get('exists'):
            fails.append('%s: the panel closed when another trade was opened in it' % tag)
        else:
            says('after switching to another trade', sw, cfg['tid2'])
            if len(sw.get('writes') or []) != 1:
                fails.append('%s: the note typed on the first trade should be saved once when the panel switches to the second '
                             '(writes: %r)' % (tag, sw.get('writes')))
            if sw.get('nodesNow') != 2:
                fails.append('%s: switching trades left %s panel node(s) (one layer and one panel expected)' % (tag, sw.get('nodesNow')))
        # -- DELETE asks first; a no keeps the panel and deletes nothing, a yes deletes, and a trade gone from the list closes it
        dl = st.get('delete') or {}
        if not dl.get('btn'):
            fails.append('%s: the panel has no DELETE button' % tag)
        else:
            d1, d2, d3 = dl.get('declined') or {}, dl.get('accepted') or {}, dl.get('afterSnapshot') or {}
            if d1.get('asked') != 1:
                fails.append('%s: DELETE did not ask first (confirm called %s times)' % (tag, d1.get('asked')))
            if not d1.get('open') or any('delete' in x for x in (d1.get('writes') or [])):
                fails.append('%s: answering no to DELETE closed the panel or deleted the trade (open=%s writes=%r)'
                             % (tag, d1.get('open'), d1.get('writes')))
            if 'trades.delete %s' % cfg['tid'] not in (d2.get('writes') or []):
                fails.append('%s: answering yes to DELETE did not delete %s (writes: %r)' % (tag, cfg['tid'], d2.get('writes')))
            if d3.get('open') or d3.get('sheetId') is not None or (d3.get('g') or {}).get('nodes'):
                fails.append('%s: the panel stayed open on a trade that is gone from the list (open=%s sheetId=%r nodes=%s)'
                             % (tag, d3.get('open'), d3.get('sheetId'), (d3.get('g') or {}).get('nodes')))
        # -- finally closed
        rm = st.get('room') or {}
        room('at the end', rm.get('g'))
        if rm.get('sheetId') is not None:
            fails.append('%s: the board still says trade %r is open after the panel was closed' % (tag, rm.get('sheetId')))
        if phone:
            for key in ('open', 'esc', 'room'):
                gg = (st.get(key) or {}).get('g') or {}
                if (gg.get('sw') or 0) > (gg.get('cw') or 0) + 1:
                    fails.append('%s: the page scrolls sideways on a phone (step %s: %s > %s)' % (tag, key, gg.get('sw'), gg.get('cw')))
    return fails, unfinished


def _judge_widths(wd, data_obj):
    """LEDGER unify step 8 follow-up: the PAGE never scrolls sideways at any width from a phone to a laptop. The LIST, the SIMPLE table
    and the FULL table are each seeded once and the window is resized through WIDTH_SET, the board drawn again at every width. The LIST
    rows drop their lowest-priority cells (POINTS, then STRATEGY, then the board's end slot) as the window narrows instead of growing
    wider than the screen; the SIMPLE table fits its box; the FULL table may scroll inside its own box, never the page."""
    fails, unfinished = [], []
    runs = (wd or {}).get('widths') or {}
    n_trades = len(data_obj['trades'])
    core = ['time', 'sym', 'side', 'pnl', 'chart']
    everything = ['time', 'sym', 'side', 'size', 'pnl', 'pts', 'strat', 'chart', 'slot']
    for nm, cfg, widths in WIDTH_RUNS:
        tag = 'width sweep %s' % nm
        r = runs.get(nm)
        if r is None:
            unfinished.append('%s: never ran' % tag)
            continue
        if r.get('threw'):
            fails.append('%s: the probe itself threw -- %s' % (tag, _first(r['threw'])))
            continue
        if r.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('seed'))))
            continue
        _errs(tag + ' (render)', r.get('seedErr') or {}, fails)
        want_mode = 'list' if cfg['view'] == 'feed' else 'table'
        bp = r.get('bp') or {}
        if bp.get('err'):
            fails.append('%s: the breakpoint scan threw -- %s' % (tag, _first(bp['err'])))
        elif not bp.get('n'):
            fails.append('%s: the breakpoint scan saw no media rule of the board (the scan has gone blind)' % tag)
        elif bp.get('bad'):
            fails.append('%s: the board has media rules at widths outside the house set %s: %s'
                         % (tag, HOUSE_WIDTHS, '; '.join(sorted(set(bp['bad']))[:4])))
        hidden_wider = set()            # the optional list cells already gone at the next wider width
        for px in sorted(widths, reverse=True):
            t = '%s at %d px' % (tag, px)
            s = (r.get('widths') or {}).get(str(px))
            if s is None:
                unfinished.append('%s: never ran' % t)
                continue
            _errs(t, s, fails)
            if s.get('threw'):
                fails.append('%s: %s' % (t, _first(s['threw'])))
                continue
            if s.get('innerW') != px:
                unfinished.append('%s: the window is %spx wide, not %spx' % (t, s.get('innerW'), px))
                continue
            # 1. the PAGE never scrolls sideways, whatever the view
            sw, cw = s.get('scrollW') or 0, s.get('clientW') or 0
            if sw > cw + 1 or sw > px + 1:
                fails.append('%s: the page scrolls sideways (scrollWidth %s > the %s px window; sticking out: %s)'
                             % (t, sw, min(cw, px) if cw else px, ', '.join(s.get('wide') or []) or '?'))
            ks = [e['k'] for e in (s.get('sec') or [])]
            if ks != SECTION_ORDER:
                fails.append('%s: the page sections run %r, expected %r at every width' % (t, ks, SECTION_ORDER))
            else:
                tp = [e['top'] for e in s['sec']]
                if any(b <= a for a, b in zip(tp, tp[1:])):
                    fails.append('%s: the page sections are not stacked top to bottom in the fixed order (tops %r)' % (t, tp))
            if not s.get('frame') or s.get('mode') != want_mode:
                fails.append('%s: the trade list frame is %s, expected one in %s mode (it says %r)'
                             % (t, 'missing' if not s.get('frame') else 'on the page', want_mode, s.get('mode')))
                continue
            if s.get('rows') != n_trades:
                fails.append('%s: the %s shows %s rows, expected one per seeded trade (%d)' % (t, want_mode, s.get('rows'), n_trades))
            if want_mode == 'list':
                cells = [c for c in (s.get('cells') or '').split(',') if c]
                if s.get('cellsVary'):
                    fails.append('%s: the rows of the list do not all show the same cells' % t)
                lost = [c for c in core + (['size'] if px > 600 else []) if c not in cells]
                if lost:
                    fails.append('%s: a list row lost %s (TIME, SYMBOL, SIDE, NET and the chart icon always stay, SIZE too above 600 px; '
                                 'it shows %s)' % (t, ', '.join(lost).upper(), ', '.join(cells) or 'nothing'))
                if px <= 600 and sorted(cells) != sorted(core):
                    fails.append('%s: a phone row keeps %s, expected the five cells %s' % (t, ', '.join(cells) or 'nothing', ', '.join(core)))
                hidden = [c for c in LIST_HIDE_ORDER if c not in cells]
                if hidden != LIST_HIDE_ORDER[:len(hidden)]:
                    fails.append('%s: the list row hides %s while it still shows %s (the lowest-priority cells go first: %s)'
                                 % (t, ', '.join(hidden), ', '.join(c for c in LIST_HIDE_ORDER if c in cells), ', then '.join(LIST_HIDE_ORDER)))
                if not hidden_wider <= set(hidden):
                    fails.append('%s: %s were hidden at a wider window and are back here (a hidden cell stays hidden as the window narrows)'
                                 % (t, ', '.join(sorted(hidden_wider - set(hidden)))))
                hidden_wider = set(hidden)
                if px >= 1000 and [c for c in everything if c not in cells]:
                    fails.append('%s: a wide window hides %s from the list row (nothing goes from 1000 px up)'
                                 % (t, ', '.join(c for c in everything if c not in cells)))
                if s.get('rowOver'):
                    fails.append('%s: %s list row(s) are wider than the frame (their cells overflow it)' % (t, s.get('rowOver')))
                if s.get('lastOver'):
                    fails.append('%s: the last cell of %s list row(s) ends outside the frame' % (t, s.get('lastOver')))
            else:
                box = s.get('box')
                if not box:
                    fails.append('%s: the table has no scroll box (.lg-tl-wrap)' % t)
                elif cfg['ledger'] == 'simple' and (box.get('sw') or 0) > (box.get('cw') or 0) + 1:
                    fails.append('%s: the SIMPLE table scrolls sideways inside its box (scrollWidth %s > clientWidth %s)'
                                 % (t, box.get('sw'), box.get('cw')))
    return fails, unfinished


def _removed_lint(root, alt_index):
    """Static lint (tools/ledger_removed.py): nothing the LEDGER clean-up removed (LEDGER_OLDBOARDS, the previous sheet / table / feed
    builders and their classes and hooks) is back in the file being gated. [] when clean."""
    sys.path.insert(0, os.path.join(root, 'tools'))
    try:
        import ledger_removed
    finally:
        sys.path.pop(0)
    return ledger_removed.lint_file(alt_index or os.path.join(root, 'index.html'), ['shared', 'real'])


def _judge_flag(flag, main, data_obj):
    """?oldboards=1 no longer changes anything: the page behind it is the NEW board - the shared frame, the page sections in the fixed order,
    the same markup digest as the plain page draws for the same case, none of the removed previous board's markers - and LEDGER_OLDBOARDS
    is not a name in the page any more."""
    fails, unfinished = [], []
    cases = (flag or {}).get('cases') or {}
    plain = (main or {}).get('cases') or {}
    n_trades = len(data_obj['trades'])
    for nm, cfg in FLAG_CASES:
        r = cases.get(nm)
        tag = '?oldboards=1 %s' % nm
        if r is None:
            unfinished.append('%s: never ran' % tag)
            continue
        before = len(fails)
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('call'))))
        _errs(tag, r, fails)
        if len(fails) > before:
            continue
        if r.get('flagConst') != 'undefined':
            fails.append('%s: LEDGER_OLDBOARDS is still a name in the page (typeof %s)' % (tag, r.get('flagConst')))
        if r.get('frameN') != 1 or not r.get('frame'):
            fails.append('%s: the shared trade list frame is not drawn behind ?oldboards=1 (frames %s)' % (tag, r.get('frameN')))
        if r.get('oldMarks'):
            fails.append('%s: markers of the removed previous board are in the page: %s' % (tag, ', '.join(r['oldMarks'])))
        keys = [s.get('k') for s in (r.get('sec') or [])]
        if keys != SECTION_ORDER:
            fails.append('%s: the page sections are %s, expected %s' % (tag, ','.join(map(str, keys)), ','.join(SECTION_ORDER)))
        want_mode = 'table' if cfg['view'] == 'table' else 'list'
        if r.get('mode') != want_mode or r.get('frameRows') != n_trades:
            fails.append('%s: the frame is in %r mode with %s rows, expected %s with %d'
                         % (tag, r.get('mode'), r.get('frameRows'), want_mode, n_trades))
        want_kind = cfg['ledger'] if cfg['view'] == 'table' else 'feed'
        if r.get('ledgerKind') != want_kind or r.get('ledgerRows') != n_trades:
            fails.append('%s: the ledger is %r with %s rows, expected %s with %d'
                         % (tag, r.get('ledgerKind'), r.get('ledgerRows'), want_kind.upper(), n_trades))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone' % tag)
        base = plain.get(FLAG_PLAIN[nm])
        if base is None:
            unfinished.append('%s: the plain case %s never ran' % (tag, FLAG_PLAIN[nm]))
        elif not r.get('boardDigest') or r.get('boardDigest') != base.get('boardDigest'):
            fails.append('%s: the board behind ?oldboards=1 is not the plain page (markup digest %s, plain %s)'
                         % (tag, r.get('boardDigest'), base.get('boardDigest')))
    return fails, unfinished


def _first(s, n=300):
    return (s or '').strip().splitlines()[0][:n] if (s or '').strip() else ''


def _errs(tag, r, fails):
    for e in r.get('errors') or []:
        fails.append('%s: console.error -- %s' % (tag, _first(e)))
    for e in r.get('uncaught') or []:
        fails.append('%s: uncaught -- %s' % (tag, _first(e)))
    for e in r.get('loadErr') or []:
        fails.append('%s: window._loadError fired -- %s' % (tag, _first(e)))
    if r.get('overlay'):
        fails.append('%s: the LOAD ERROR overlay is on the page' % tag)


def _judge_step11(nm, cfg, r, fails, n_missed):
    """LEDGER unify step 11 on one case: the fixed order, the own folds (closed, one-line summary, open on a click, content), the breakpoints
    and MONO."""
    sec = r.get('sec') or []
    ks = [s['k'] for s in sec]
    if ks != SECTION_ORDER:
        fails.append('%s: the page sections run %r, expected the fixed order %r' % (nm, ks, SECTION_ORDER))
    else:
        tp = [s['top'] for s in sec]
        if any(b <= a for a, b in zip(tp, tp[1:])):
            fails.append('%s: the page sections are not stacked top to bottom in the fixed order (tops %r)' % (nm, tp))
        if any((s['h'] or 0) <= 0 for s in sec):
            fails.append('%s: a page section is drawn with no height: %s' % (nm, ', '.join(s['k'] for s in sec if (s['h'] or 0) <= 0)))
    if not r.get('secInWrap'):
        fails.append('%s: a page section sits outside the board (.hm-wrap)' % nm)
    fc = r.get('foldsClosed') or []
    if [f['k'] for f in fc] != OWN_FOLDS:
        fails.append('%s: the own folds read %r, expected %r' % (nm, [f['k'] for f in fc], OWN_FOLDS))
    want_sum = {'paste': r'^the next link goes on \S+',
                'missed': (r'^%d setups not taken' % n_missed) if cfg['missed'] else r'^none filed yet$',
                'deps': r'^1 event \u00b7 net \+\$1,000\.00$',
                'ai': r'^last 9 trades \u00b7 71% won \u00b7 profit factor ',
                'journal': r'^1 entry \u00b7 newest 2026-09-30$'}
    for f in fc:
        k = f['k']
        if f.get('exp') != 'false' or f.get('body'):
            fails.append('%s: the %s fold is not closed to start with (aria-expanded=%r, body in the page: %s)' % (nm, k, f.get('exp'), f.get('body')))
        sm = (f.get('sum') or '').strip()
        if not sm:
            fails.append('%s: the %s fold has no summary line' % (nm, k))
            continue
        if re.search(r'undefined|NaN|\[object|[<>]|&[a-z#0-9]+;', sm):
            fails.append('%s: the %s fold summary has stray markup or a bad value: %r' % (nm, k, sm))
        if (f.get('sumH') or 0) > 20 or (f.get('h') or 0) > 40:
            fails.append('%s: the %s fold header is %spx tall (summary %spx) - the summary must stay on one line' % (nm, k, f.get('h'), f.get('sumH')))
        if k in want_sum and not re.search(want_sum[k], sm):
            fails.append('%s: the %s fold summary reads %r, expected it to match %r' % (nm, k, sm, want_sum[k]))
    fo = r.get('foldOpen') or {}
    for k in OWN_FOLDS:
        o = fo.get(k) or {}
        if not o.get('btn'):
            fails.append('%s: the %s fold has no header button to click' % (nm, k))
            continue
        if o.get('exp') != 'true' or not o.get('body'):
            fails.append('%s: a click on the %s fold did not open it (aria-expanded=%r, body=%s)' % (nm, k, o.get('exp'), o.get('body')))
            continue
        if not o.get('len'):
            fails.append('%s: the %s fold opened with nothing in it' % (nm, k))
        if o.get('back') != 'false' or not o.get('bodyGone'):
            fails.append('%s: a second click on the %s fold did not close it again (aria-expanded=%r, body gone: %s)' % (nm, k, o.get('back'), o.get('bodyGone')))
    o = fo.get('missed') or {}
    if o.get('body') and not o.get('add'):
        fails.append('%s: the SHOULD HAVE TRADED fold lost its + ADD button' % nm)
    o = fo.get('deps') or {}
    if o.get('body') and (not o.get('strip') or o.get('chips') != 1):
        fails.append('%s: the DEPOSITS fold shows %s deposit chips (strip=%s), expected the one deposit' % (nm, o.get('chips'), o.get('strip')))
    o = fo.get('ai') or {}
    if o.get('body') and (not o.get('out') or not o.get('text') or not o.get('refresh')):
        fails.append('%s: the AI ASSESSMENT fold opened without its read or its REFRESH button (%r)' % (nm, o))
    o = fo.get('journal') or {}
    if o.get('body') and (not o.get('form') or o.get('entries') != 1 or not o.get('save')):
        fails.append('%s: the JOURNAL fold opened without its form or its entry (%r)' % (nm, o))
    bp = r.get('bp') or {}
    if bp.get('err'):
        fails.append('%s: the breakpoint scan threw -- %s' % (nm, _first(bp['err'])))
    elif not bp.get('n'):
        fails.append('%s: the breakpoint scan saw no media rule of the board (the scan has gone blind)' % nm)
    elif bp.get('bad'):
        fails.append('%s: the board has media rules at widths outside the house set %s: %s'
                     % (nm, HOUSE_WIDTHS, '; '.join(sorted(set(bp['bad']))[:4])))
    if cfg['theme'] == 'mono':
        hu = r.get('hue') or {}
        if not hu.get('checked'):
            fails.append('%s: the MONO colour scan looked at nothing' % nm)
        elif hu.get('bad'):
            fails.append('%s: MONO has a hue on the board (%d colours checked): %s' % (nm, hu['checked'], '; '.join(hu['bad'])))


def _judge_folds(fd):
    """LEDGER unify step 11: open / closed is remembered per browser - every own fold opened with a click is open after a reload, and closed
    after it is closed and the page reloaded again."""
    fails, unfinished = [], []
    runs = (fd or {}).get('folds') or {}
    for nm, cfg in FOLD_RUNS:
        tag = 'fold run %s' % nm
        r = runs.get(nm)
        if r is None:
            unfinished.append('%s: never ran' % tag)
            continue
        if r.get('threw'):
            fails.append('%s: the probe itself threw -- %s' % (tag, _first(r['threw'])))
            continue
        for key in ('seed', 'seed2', 'seed3'):
            if r.get(key) != 'OK':
                fails.append('%s: renderApp threw (%s) -- %s' % (tag, key, _first(r.get(key))))
        _errs(tag + ' (render)', r.get('seedErr') or {}, fails)
        _errs(tag + ' (after the first reload)', r.get('err1') or {}, fails)
        _errs(tag + ' (after the second reload)', r.get('err2') or {}, fails)
        shut = {k: 'false' for k in OWN_FOLDS}
        shown = {k: 'true' for k in OWN_FOLDS}
        if r.get('init') != {k: False for k in OWN_FOLDS}:
            fails.append('%s: on a fresh browser the own folds start as %r - every one must start closed (the AI ASSESSMENT box filled the top '
                         'of the page when it started open)' % (tag, r.get('init')))
        if r.get('start') != shut:
            fails.append('%s: the own folds do not start closed on a fresh browser (%r)' % (tag, r.get('start')))
        if r.get('opened') != shown:
            fails.append('%s: clicking every own fold did not open them all (%r)' % (tag, r.get('opened')))
        elif any(v != '1' for v in (r.get('lsOpened') or {}).values()):
            fails.append('%s: an opened fold was not written to localStorage (%r)' % (tag, r.get('lsOpened')))
        if r.get('afterReload') != shown:
            fails.append('%s: after a reload the folds opened before it are not open (%r) - open / closed is not remembered' % (tag, r.get('afterReload')))
        if r.get('closed') != shut:
            fails.append('%s: clicking every open fold did not close them all (%r)' % (tag, r.get('closed')))
        elif any(v != '0' for v in (r.get('lsClosed') or {}).values()):
            fails.append('%s: a closed fold was not written to localStorage (%r)' % (tag, r.get('lsClosed')))
        if r.get('afterReload2') != shut:
            fails.append('%s: after a reload the folds closed before it are not closed (%r) - open / closed is not remembered' % (tag, r.get('afterReload2')))
        if cfg.get('cal'):
            _errs(tag + ' (calendar default)', r.get('errCal') or {}, fails)
            cal = r.get('cal') or {}
            if cal.get('600') is not False or cal.get('601') is not True:
                fails.append('%s: the calendar default is open=%r at 600 px and open=%r at 601 px, expected closed at 600 and open at 601 '
                             '(the house number, not a private width)' % (tag, cal.get('600'), cal.get('601')))
    return fails, unfinished


def _judge(data, data_obj):
    why = data.get('why')
    if why == 'noboot':
        return (INCONCLUSIVE, ['app did not boot (renderApp=%s); see preflight_boot' % data.get('renderApp')],
                [], data, False)
    if data.get('err'):
        return FAIL, ['probe could not run: %s' % _first(data['err'])], [], data, True
    n_trades = len(data_obj['trades'])
    n_missed = len(data_obj['missed'])
    fails, notes, unfinished = [], [], []
    boot = data.get('bootNoise') or {}
    for e in (boot.get('errors') or []) + (boot.get('uncaught') or []):
        notes.append('before any case (boot, not judged): %s' % _first(e, 200))

    cases = data.get('cases') or {}
    for nm, cfg in CASES:
        r = cases.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (nm, why))
            continue
        before = len(fails)
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, _first(r.get('call'))))
        if r.get('sampleErr'):
            fails.append('%s: could not read the page -- %s' % (nm, _first(r['sampleErr'])))
        _errs(nm, r, fails)
        if len(fails) > before:
            continue                     # one crash explains everything below it
        want_w = VIEWPORTS[cfg['vp']][0]
        if r.get('innerW') != want_w:
            unfinished.append('%s: the viewport is %spx, not %spx' % (nm, r.get('innerW'), want_w))
            continue
        if r.get('theme') != cfg['theme']:
            fails.append('%s: data-theme is %r, not %r' % (nm, r.get('theme'), cfg['theme']))
        if cfg.get('kind') == 'legacy':
            # LEDGER step 8 / mistake #14: the legacy TRADES and JOURNAL tabs draw on a phone, in one column
            lg = r.get('legacy') or {}
            if lg.get('tab') != cfg['tab']:
                fails.append('%s: the %s tab did not open (activeTab=%r)' % (nm, cfg['tab'], lg.get('tab')))
            elif cfg['tab'] == 'trades' and (not lg.get('table') or lg.get('rows') != n_trades):
                fails.append('%s: the legacy TRADES table shows %s rows for %s trades (table present: %s)'
                             % (nm, lg.get('rows'), n_trades, lg.get('table')))
            elif cfg['tab'] == 'journal' and (not lg.get('journalForm') or not lg.get('lessons')):
                fails.append('%s: the legacy JOURNAL tab drew no form or no entry (form=%s entries=%s)'
                             % (nm, lg.get('journalForm'), lg.get('lessons')))
            if (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
                fails.append('%s: the legacy %s tab scrolls sideways on a phone (scrollWidth %s > clientWidth %s; '
                             'sticking out: %s)' % (nm, cfg['tab'].upper(), r.get('scrollW'), r.get('clientW'),
                                                    ', '.join(r.get('wide') or []) or '?'))
            if cfg['tab'] == 'trades' and lg.get('boxScrollW') is not None \
                    and lg['boxScrollW'] > (lg.get('boxClientW') or 0) + 1:
                fails.append('%s: the legacy TRADES table scrolls sideways inside its box on a phone (box scrollWidth '
                             '%s > clientWidth %s)' % (nm, lg.get('boxScrollW'), lg.get('boxClientW')))
            if (r.get('appLen') or 0) < 3000:
                fails.append('%s: the legacy tab rendered almost nothing (%s chars)' % (nm, r.get('appLen')))
            continue
        fo = r.get('foldOpen') or {}
        mo = fo.get('missed') or {}
        if not mo.get('missed'):
            fails.append('%s: no #hm-missed (SHOULD HAVE TRADED) section in its fold once it is open' % nm)
        elif mo.get('missedRows') != (n_missed if cfg['missed'] else 0):
            fails.append('%s: SHOULD HAVE TRADED shows %s rows for %s entries'
                         % (nm, mo.get('missedRows'), n_missed if cfg['missed'] else 0))
        _judge_step11(nm, cfg, r, fails, n_missed)
        want_kind = cfg['ledger'] if cfg['view'] == 'table' else 'feed'
        if not r.get('feed'):
            fails.append('%s: no ledger container (#hm-feed-container)' % nm)
        elif r.get('ledgerKind') != want_kind:
            fails.append('%s: the ledger is %r, expected the %s view' % (nm, r.get('ledgerKind') or 'missing',
                                                                        want_kind.upper()))
        elif r.get('ledgerRows') != n_trades:
            fails.append('%s: the ledger shows %s rows for %s trades' % (nm, r.get('ledgerRows'), n_trades))
        # LEDGER unify step 8: the shared trade list frame (toolbar, day headers, rows, five cells on a phone)
        if r.get('frameN') != 1 or not r.get('frame'):
            fails.append('%s: the page draws %s trade list frames ([data-lglist-frame]), expected exactly one'
                         % (nm, r.get('frameN')))
        else:
            want_mode = 'table' if cfg['view'] == 'table' else 'list'
            if r.get('mode') != want_mode:
                fails.append('%s: the trade list frame is in %r mode, expected %r' % (nm, r.get('mode'), want_mode))
            if r.get('chipTxt') != FRAME_CHIPS:
                fails.append('%s: the frame chips read %r, not %s' % (nm, r.get('chipTxt'), FRAME_CHIPS))
            if r.get('chipOn') != 'ALL':
                fails.append('%s: the active chip is %r, expected ALL' % (nm, r.get('chipOn')))
            if r.get('viewBtns') != ('list,table*' if want_mode == 'table' else 'list*,table'):
                fails.append('%s: the LIST | TABLE toggle reads %r (a * marks the pressed half)' % (nm, r.get('viewBtns')))
            if not r.get('searchBox'):
                fails.append('%s: the frame has no search box' % nm)
            if r.get('count') != '%d / %d trades' % (n_trades, n_trades):
                fails.append('%s: the frame count reads %r, expected %d / %d trades' % (nm, r.get('count'), n_trades, n_trades))
            exp = expected_days(data_obj['trades'])
            got_days = [x.split('=', 1) for x in (r.get('days') or [])]
            if [g[0] for g in got_days] != sorted(exp, reverse=True):
                fails.append('%s: the day headers read %r, expected the close days %r newest first'
                             % (nm, [g[0] for g in got_days], sorted(exp, reverse=True)))
            else:
                for day, net in got_days:
                    if not re.match(r'^[+-]\$[\d,]+\.\d\d$', net):
                        fails.append('%s: the %s day header net reads %r (needs a sign and a dollar amount)' % (nm, day, net))
                    elif net != exp[day]:
                        fails.append('%s: the %s day header net is %s, expected %s' % (nm, day, net, exp[day]))
            if r.get('ovDay') != '2026-10-01':
                fails.append('%s: the overnight trade (entered 09-30 23:55, held 25 min) sits under %r, it closed on 2026-10-01'
                             % (nm, r.get('ovDay')))
            if r.get('frameRows') != n_trades:
                fails.append('%s: the frame draws %s trade rows for %s trades' % (nm, r.get('frameRows'), n_trades))
            if cfg['vp'] == 'phone':
                if r.get('visCells') != 5:
                    fails.append('%s: a phone row shows %s cells, expected five (time, symbol, side, net, chart)'
                                 % (nm, r.get('visCells')))
                if r.get('listTop') is None or r.get('listTop') > (r.get('viewH') or 0):
                    fails.append('%s: the trade list starts %spx below the top of the board on a phone, more than one '
                                 'screen (%spx) - mistake #12' % (nm, r.get('listTop'), r.get('viewH')))
                elif r.get('listTop') > PHONE_LIST_TOP_MAX:
                    fails.append('%s: the trade list starts %spx below the top of the board on a 375 px phone; it began at %spx before '
                                 'step 11 and must not grow' % (nm, r.get('listTop'), PHONE_LIST_TOP_MAX))
        if cfg['view'] == 'feed' and r.get('frame'):
            exp_order = [t['id'] for t in sorted(data_obj['trades'], key=_close_key, reverse=True)]
            if r.get('order') != exp_order:
                fails.append('%s: the list rows run %r, expected newest close first %r' % (nm, r.get('order'), exp_order))
            if r.get('depositRows') != 1:
                fails.append('%s: the list shows %s deposit rows, expected the one deposit in its day' % (nm, r.get('depositRows')))
        ai = r.get('aiFold')
        if not ai or not ai.get('closed') or ai.get('out'):
            fails.append('%s: the AI ASSESSMENT is not a closed fold (%r) - it filled the top of the page' % (nm, ai))
        if cfg['vp'] == 'phone' and not (r.get('acctSum') or '').strip():
            fails.append('%s: the phone account line has no summary (the account in view and its balance)' % nm)
        elif cfg['vp'] == 'phone' and (r.get('acctBtnH') or 0) > 40:
            fails.append('%s: the phone account line is %spx tall - it must be one line' % (nm, r.get('acctBtnH')))
        ao = r.get('acctOpen')
        if cfg['vp'] == 'phone' and (not ao or ao.get('exp') != 'true' or ao.get('list') == 'none' or ao.get('back') != 'false' or ao.get('listBack') != 'none'):
            fails.append('%s: the phone account line should open the account list on a click and close it again (%r)' % (nm, ao))
        af = r.get('acctFold')
        if not af:
            fails.append('%s: the account line / list section is missing' % nm)
        elif cfg['vp'] == 'phone' and (af.get('btn') == 'none' or af.get('list') != 'none'):
            fails.append('%s: on a phone the account list should be one closed line (button display=%r, list display=%r)'
                         % (nm, af.get('btn'), af.get('list')))
        elif cfg['vp'] != 'phone' and (af.get('btn') != 'none' or af.get('list') == 'none'):
            fails.append('%s: on a laptop the account list is always drawn (button display=%r, list display=%r)'
                         % (nm, af.get('btn'), af.get('list')))
        tbx = r.get('tblBox')
        if cfg['view'] == 'table' and cfg['ledger'] == 'simple' and tbx and tbx['sw'] > tbx['cw'] + 1:
            fails.append('%s: the SIMPLE table scrolls sideways inside its box (scrollWidth %s > clientWidth %s)'
                         % (nm, tbx['sw'], tbx['cw']))
        po = fo.get('paste') or {}
        if not po.get('paste'):
            fails.append('%s: the PASTE box for snapshot links (#hm-paste-chart) is gone from its fold' % nm)
        elif not po.get('pasteVisible'):
            fails.append('%s: the PASTE box is in its open fold but not visible' % nm)
        if (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1 and cfg['vp'] != 'phone':
            fails.append('%s: the page scrolls sideways on a laptop (scrollWidth %s > clientWidth %s; sticking out: %s)'
                         % (nm, r.get('scrollW'), r.get('clientW'), ', '.join(r.get('wide') or []) or '?'))
        if r.get('oldMarks'):
            fails.append('%s: markers of the removed previous board are in the page: %s' % (nm, ', '.join(r['oldMarks'])))
        if r.get('panelsInDom'):
            fails.append('%s: %s trade panel node(s) are in the page while nothing is open - a closed panel must not be in it'
                         % (nm, r.get('panelsInDom')))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (scrollWidth %s > clientWidth %s; '
                         'sticking out: %s)' % (nm, r.get('scrollW'), r.get('clientW'),
                                                ', '.join(r.get('wide') or []) or '?'))
        if not re.match(r'^-?\$[\d,]+\.\d\d$', r.get('heroBig') or ''):
            fails.append('%s: the hero big number reads %r, not a dollar amount' % (nm, r.get('heroBig')))
        if not (r.get('heroToday') or '').endswith('today'):
            fails.append('%s: the hero has no "today" line (got %r)' % (nm, r.get('heroToday')))
        if r.get('pills') != ','.join(LEDGER_RANGES):
            fails.append('%s: the range pills read %r, not %s' % (nm, r.get('pills'), ' '.join(LEDGER_RANGES)))
        min_h = 150 if cfg['vp'] == 'phone' else 200
        if (r.get('chartH') or 0) < min_h:
            fails.append('%s: the equity chart is %spx tall (squashed; needs %s+)' % (nm, r.get('chartH'), min_h))
        if r.get('acctRows') != 3 or r.get('acctSel') != '':
            fails.append('%s: the account list shows %s rows with %r selected (expected ALL + 2 brokers, ALL selected)'
                         % (nm, r.get('acctRows'), r.get('acctSel')))
        if r.get('acctPill'):
            fails.append('%s: the tab-row ACCOUNT pill still shows on LEDGER (the account list replaces it there)' % nm)
        if r.get('acctScoped') is not True:
            fails.append('%s: tapping the NinjaTrader row did not scope the board (hero label)' % nm)
        if (r.get('legendN') or 0) < 2:
            fails.append('%s: the P&L chart shows %s broker lines in its legend (the probe data has two brokers)' % (nm, r.get('legendN')))
        if (r.get('legendH') or 0) > 40:
            fails.append('%s: a chart legend entry is %spx tall (should be one short line)' % (nm, r.get('legendH')))
        if (r.get('chartDates') or 0) < 2 or (r.get('chartTicks') or 0) < 2:
            fails.append('%s: the equity chart has %s date labels and %s price labels (needs 2+ of each)'
                         % (nm, r.get('chartDates'), r.get('chartTicks')))
        st = r.get('stats') or []
        if [x.split('=')[0] for x in st] != ['winrate', 'pf', 'maxdd', 'trades']:
            fails.append('%s: the stats strip reads %r, not the four tiles win rate, profit factor, max drawdown, '
                         'trades' % (nm, st))
        else:
            vals = dict(x.split('=', 1) for x in st)
            if not re.match(r'^\$[\d,]+\.\d\d$', vals['maxdd']):
                fails.append('%s: max drawdown reads %r (must be a positive dollar amount)' % (nm, vals['maxdd']))
            if not re.match(r'^(\d+\.\d\d|no losses|--)$', vals['pf']):
                fails.append('%s: profit factor reads %r' % (nm, vals['pf']))
        if r.get('moreGroups') != 'Returns,Risk,Mix,Account':
            fails.append('%s: More stats opened with groups %r, not Returns, Risk, Mix, Account'
                         % (nm, r.get('moreGroups')))
        cal = r.get('cal')
        if not cal:
            fails.append('%s: the LEDGER calendar fold is missing' % nm)
        else:
            if not cal.get('days') or cal.get('cells', 0) % 8:
                fails.append('%s: the calendar shows %s traded days in %s cells (needs 1+ days, rows of 7 days + a week)'
                             % (nm, cal.get('days'), cal.get('cells')))
            elif cal.get('sumN') != cal.get('hdN'):
                fails.append('%s: the calendar days add up to %s trades but its header says %s'
                             % (nm, cal.get('sumN'), cal.get('hdN')))
            if cfg['view'] != 'table' and not cal.get('jump'):
                fails.append('%s: tapping a calendar day did not jump the trade list to that day' % nm)
        if (r.get('appLen') or 0) < 3000:
            fails.append('%s: HOME rendered almost nothing (%s chars)' % (nm, r.get('appLen')))

    inter = data.get('inter') or {}
    for nm, I in INTERACTIONS:
        res = inter.get(nm)
        tag = 'interaction %s' % nm
        if res is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if res.get('threw'):
            fails.append('%s: the probe itself threw -- %s' % (tag, _first(res['threw'])))
            continue
        if res.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get('seed'))))
            continue
        _errs(tag + ' (render)', res.get('seedErr') or {}, fails)
        st = res.get('steps') or {}
        p = st.get('panel') or {}
        _errs(tag + ' trade panel', p, fails)
        if p.get('threw'):
            fails.append('%s trade panel: %s' % (tag, _first(p['threw'])))
        if not p.get('open'):
            fails.append('%s: the trade panel for %s did not open' % (tag, I['tid']))
        if not p.get('drew'):
            body = p.get('body') or ''
            if 'loading the candles' in body and not any(p.get(k) for k in ('errors', 'uncaught')):
                unfinished.append('%s: the chart was still loading after 6s with no error' % tag)
            else:
                fails.append('%s: the trade panel chart never drew an <svg> (chart body says: %r)'
                             % (tag, body[:120]))
        pts = p.get('points') or ''
        if 'POINTS' not in pts or I['pts'] not in pts:
            fails.append('%s: the trade panel POINTS block is missing or does not show %s (%r)'
                         % (tag, I['pts'], pts[:80]))
        z = st.get('zoom') or {}
        _errs(tag + ' zoom out / DAY', z, fails)
        if z.get('threw'):
            fails.append('%s zoom: %s' % (tag, _first(z['threw'])))
        if p.get('drew'):
            if z.get('buttons') != 2:
                fails.append('%s: the chart has no - / DAY buttons' % tag)
            elif not z.get('svg'):
                fails.append('%s: the chart vanished after - / DAY' % tag)
            elif not z.get('redrew'):
                fails.append('%s: - and DAY did not redraw the chart (it still shows the trade view)' % tag)
        mp = st.get('missedPanel') or {}
        _errs(tag + ' SHOULD HAVE TRADED panel', mp, fails)
        if mp.get('threw'):
            fails.append('%s SHOULD HAVE TRADED panel: %s' % (tag, _first(mp['threw'])))
        if not mp.get('open') or mp.get('sym') != I['msym'] or 'SHOULD HAVE TRADED' not in (mp.get('sub') or ''):
            fails.append('%s: the SHOULD HAVE TRADED panel did not render (open=%s sym=%r sub=%r)'
                         % (tag, mp.get('open'), mp.get('sym'), (mp.get('sub') or '')[:60]))
        else:
            if 'POINTS' not in (mp.get('points') or '') or I['mpts'] not in (mp.get('points') or ''):
                fails.append('%s: the SHOULD HAVE TRADED panel has no POINTS block showing %s'
                             % (tag, I['mpts']))
            if not mp.get('drew'):
                fails.append('%s: the SHOULD HAVE TRADED panel chart never drew (%r)'
                             % (tag, (mp.get('body') or '')[:120]))
        af = st.get('addForm') or {}
        _errs(tag + ' + ADD / SAVE', af, fails)
        if af.get('threw'):
            fails.append('%s + ADD: %s' % (tag, _first(af['threw'])))
        if not af.get('addBtn') or not af.get('form') or not af.get('saveBtn'):
            fails.append('%s: + ADD did not open the SHOULD HAVE TRADED form (button=%s form=%s save=%s)'
                         % (tag, af.get('addBtn'), af.get('form'), af.get('saveBtn')))
        elif not af.get('msg') or af.get('msg') == af.get('msg0'):
            fails.append('%s: SAVE with empty fields showed no message (#hmmf-msg=%r)' % (tag, af.get('msg')))
        if af.get('writes'):
            fails.append('%s: SAVE with empty fields wrote to the database: %s' % (tag, af['writes']))
        ps = st.get('paste') or {}
        _errs(tag + ' paste box', ps, fails)
        if ps.get('threw'):
            fails.append('%s paste: %s' % (tag, _first(ps['threw'])))
        if not ps.get('note') or not ps.get('missedBtn'):
            fails.append('%s: hmFileChartLink showed no paste note with a SHOULD HAVE TRADED button '
                         '(note=%s button=%s)' % (tag, ps.get('note'), ps.get('missedBtn')))
        elif not ps.get('form') or ps.get('url') != PASTE_URL:
            fails.append('%s: the paste note SHOULD HAVE TRADED button did not open the form with the '
                         'link filled in (form=%s url=%r)' % (tag, ps.get('form'), ps.get('url')))
        elif ps.get('foldOpen') != 'true' or ps.get('foldOpenMsg') != 'true':
            fails.append('%s: a paste note is drawn in the PASTE fold but the fold stayed closed (question: aria-expanded=%r, plain note: %r)'
                         % (tag, ps.get('foldOpen'), ps.get('foldOpenMsg')))
        if ps.get('writes'):
            fails.append('%s: the paste box wrote to the database before anyone chose: %s'
                         % (tag, ps['writes']))
        # LEDGER step 8: the shared frame's chips, search, view toggle, BY DAY and SIMPLE | FULL
        T = data_obj['trades']
        fs = st.get('frame') or {}
        _errs(tag + ' trade list frame', fs, fails)
        if fs.get('threw'):
            fails.append('%s trade list frame: %s' % (tag, _first(fs['threw'])))
        else:
            def ids(pred):
                return sorted(t['id'] for t in T if pred(t))
            futs = ('MNQ', 'MES')
            want = {'WINS': ids(lambda t: t['pnl'] > 0), 'LOSSES': ids(lambda t: t['pnl'] < 0),
                    'LONG': ids(lambda t: t['type'] == 'LONG'), 'SHORT': ids(lambda t: t['type'] == 'SHORT'),
                    'FUTURES': ids(lambda t: t['symbol'] in futs), 'STOCKS': ids(lambda t: t['symbol'] not in futs),
                    'ALL': ids(lambda t: True)}
            chips = fs.get('chips') or {}
            for c, w_ in want.items():
                if chips.get(c) != w_:
                    fails.append('%s: the %s chip lists %r, expected %r' % (tag, c, chips.get(c), w_))
            flat = [t['id'] for t in T if t['pnl'] == 0]
            for c in ('WINS', 'LOSSES'):
                if set(flat) & set(chips.get(c) or []):
                    fails.append('%s: the %s chip lists the $0 trade %s - a $0 trade is neither a win nor a loss'
                                 % (tag, c, flat))
            if not fs.get('searchBox'):
                fails.append('%s: the frame has no search box' % tag)
            elif fs.get('search') != ['probe_s1']:
                fails.append('%s: searching "aapl" lists %r, expected the one AAPL trade' % (tag, fs.get('search')))
            elif fs.get('searchFocus') != 'hm-search':
                fails.append('%s: typing in the search box lost the cursor (focus is on %r)' % (tag, fs.get('searchFocus')))
            elif fs.get('searchCleared') != len(T):
                fails.append('%s: clearing the search lists %s trades, expected %d' % (tag, fs.get('searchCleared'), len(T)))
            if not fs.get('byDayBtn'):
                fails.append('%s: the BY DAY button is missing in the list view' % tag)
            elif fs.get('byDayDays') != len(expected_days(T)) or fs.get('byDayTrades') != 0:
                fails.append('%s: BY DAY shows %s day rows and %s trade rows, expected %d and 0'
                             % (tag, fs.get('byDayDays'), fs.get('byDayTrades'), len(expected_days(T))))
            if not fs.get('viewBtn') or fs.get('modeTable') != 'table' or fs.get('savedTable') != 'table':
                fails.append('%s: the TABLE button did not switch the frame to the table and remember it '
                             '(mode=%r saved=%r)' % (tag, fs.get('modeTable'), fs.get('savedTable')))
            if fs.get('modeList') != 'list' or fs.get('savedList') != 'list':
                fails.append('%s: the LIST button did not switch the frame back and remember it (mode=%r saved=%r)'
                             % (tag, fs.get('modeList'), fs.get('savedList')))
            if not fs.get('fullBtn') or not fs.get('fullTable') or not fs.get('simpleTable'):
                fails.append('%s: SIMPLE | FULL did not switch the table (full button=%s full=%s simple=%s)'
                             % (tag, fs.get('fullBtn'), fs.get('fullTable'), fs.get('simpleTable')))
            elif (fs.get('fullCols') or 0) <= (fs.get('simpleCols') or 0):
                fails.append('%s: FULL shows %s columns, SIMPLE %s - FULL must show more'
                             % (tag, fs.get('fullCols'), fs.get('simpleCols')))
            if not fs.get('pasteFold') or not fs.get('paste'):
                fails.append('%s: the PASTE box is gone (fold=%s box=%s)' % (tag, fs.get('pasteFold'), fs.get('paste')))
            bt = fs.get('buttons') or {}
            if not (bt.get('add') and bt.get('scan') and bt.get('all') and bt.get('nt')):
                fails.append('%s: the toolbar lost one of NEW TRADE / ADD DEPOSIT / SCAN DUPLICATES / OPEN ALL (%r)' % (tag, bt))
            elif not fs.get('formOpen') or not fs.get('formClosed'):
                fails.append('%s: NEW TRADE did not open and close its form (open=%s closed=%s)'
                             % (tag, fs.get('formOpen'), fs.get('formClosed')))
            tl = fs.get('tools') or {}
            if I['vp'] == 'phone':
                if tl.get('toggle') == 'none' or tl.get('box') != 'none' or tl.get('boxOpen') != 'flex' or tl.get('boxShut') != 'none':
                    fails.append('%s: the ... button on a phone should open and close the four action buttons (%r)' % (tag, tl))
            elif tl.get('toggle') != 'none' or tl.get('box') == 'none':
                fails.append('%s: on a laptop the four action buttons are always shown and the ... button is not (%r)' % (tag, tl))
        sm = st.get('sortmenu') or {}
        _errs(tag + ' header sort menu', sm, fails)
        if sm.get('threw'):
            fails.append('%s header sort menu: %s' % (tag, _first(sm['threw'])))
        elif I['vp'] == 'laptop':
            if not sm.get('header') or not sm.get('menu') or not sm.get('ascItem'):
                fails.append('%s: the NET header did not open its sort / filter menu (header=%s menu=%s ascending=%s)'
                             % (tag, sm.get('header'), sm.get('menu'), sm.get('ascItem')))
            else:
                vals = [float(x.replace('$', '').replace(',', '').replace('+', '')) for x in (sm.get('nets') or [])]
                if len(vals) != len(data_obj['trades']) or vals != sorted(vals):
                    fails.append('%s: sorting NET ascending left the rows in this order: %r' % (tag, sm.get('nets')))
                if sm.get('dayRows'):
                    fails.append('%s: day headers are still drawn after sorting by NET (%s)' % (tag, sm.get('dayRows')))
                if 'NET' not in (sm.get('label') or '') or '\u25b2' not in (sm.get('label') or ''):
                    fails.append('%s: the sort label reads %r, expected SORTED BY NET with an up arrow' % (tag, sm.get('label')))
        sh = st.get('sheet') or {}
        _errs(tag + ' trade panel editors', sh, fails)
        if sh.get('threw'):
            fails.append('%s trade panel editors: %s' % (tag, _first(sh['threw'])))
        else:
            b = sh.get('buttons') or {}
            if not (b.get('edit') and b.get('snap') and b.get('tv') and b.get('del')):
                fails.append('%s: the trade panel lost one of EDIT / SNAPSHOT / OPEN IN TV / DELETE (%r)' % (tag, b))
            if not sh.get('sel'):
                fails.append('%s: the trade panel has no grade / setup editors' % tag)
            else:
                wr = sh.get('data') or []
                g = [x for x in wr if x.get('id') == 'probe_t2' and 'grade' in (x.get('d') or {})]
                s_ = [x for x in wr if x.get('id') == 'probe_t2' and 'setup' in (x.get('d') or {})]
                if not g or g[-1]['d']['grade'] != 'A':
                    fails.append('%s: changing the grade in the trade panel did not save {grade: A} (writes: %r)' % (tag, wr))
                if not s_ or s_[-1]['d']['setup'] != sh.get('setupPicked'):
                    fails.append('%s: changing the setup in the trade panel did not save it (picked %r, writes: %r)'
                                 % (tag, sh.get('setupPicked'), wr))
                x_ = [x for x in wr if x.get('id') == 'probe_t2' and 'statsExcluded' in (x.get('d') or {})]
                if not sh.get('excl') or not x_ or x_[-1]['d']['statsExcluded'] is not True:
                    fails.append('%s: ticking IGNORE IN METRICS in the trade panel did not save {statsExcluded: true} (writes: %r)'
                                 % (tag, wr))
        ai = st.get('aiFold') or {}
        _errs(tag + ' AI assessment fold', ai, fails)
        if ai.get('threw'):
            fails.append('%s AI assessment fold: %s' % (tag, _first(ai['threw'])))
        elif not ai.get('fold') or ai.get('closed') is not True or ai.get('outputBefore'):
            fails.append('%s: the AI ASSESSMENT fold is not closed to start with (%r)' % (tag, ai))
        elif ai.get('open') is not True or not ai.get('outputAfter') or not ai.get('text') or ai.get('closedAgain') is not True:
            fails.append('%s: the AI ASSESSMENT fold did not open, fill and close again (%r)' % (tag, ai))
        ed = st.get('edits') or {}
        _errs(tag + ' inline edits', ed, fails)
        if ed.get('threw'):
            fails.append('%s inline edits: %s' % (tag, _first(ed['threw'])))
        elif I['vp'] == 'laptop':
            if not ed.get('gradeSel') or not ed.get('noteInput'):
                fails.append('%s: the TABLE has no inline grade select or note box for the first trade (grade=%s note=%s)'
                             % (tag, ed.get('gradeSel'), ed.get('noteInput')))
            else:
                wr = ed.get('data') or []
                g = [x for x in wr if x.get('id') == 'probe_t1' and 'grade' in (x.get('d') or {})]
                n = [x for x in wr if x.get('id') == 'probe_t1' and 'notes' in (x.get('d') or {})]
                if not g or g[-1]['d']['grade'] != 'A':
                    fails.append('%s: changing a grade in the TABLE did not save {grade: A} (writes: %r)' % (tag, wr))
                if not n or n[-1]['d']['notes'] != 'probe note edit':
                    fails.append('%s: editing a note in the TABLE did not save it (writes: %r)' % (tag, wr))
                if not ed.get('rowsN') or ed.get('editCells') != ed.get('rowsN') or ed.get('delCells') != ed.get('rowsN'):
                    fails.append('%s: every TABLE row should keep an EDIT and a DELETE cell (rows=%s edit=%s delete=%s)'
                                 % (tag, ed.get('rowsN'), ed.get('editCells'), ed.get('delCells')))
                elif not ed.get('delWired') or ed.get('editOpened') != 1:
                    fails.append('%s: the TABLE EDIT cell should open the edit window (opened=%s) and DELETE should be wired (wired=%s)'
                                 % (tag, ed.get('editOpened'), ed.get('delWired')))
        jp = st.get('jump') or {}
        _errs(tag + ' ANALYTICS jump', jp, fails)
        if jp.get('threw'):
            fails.append('%s ANALYTICS jump: %s' % (tag, _first(jp['threw'])))
        else:
            if jp.get('analyticsShown') != 'analytics':
                fails.append('%s: the ANALYTICS tab did not open before the jump (activeTab=%r)'
                             % (tag, jp.get('analyticsShown')))
            if jp.get('tab') != 'home' or jp.get('view') != 'table' or not jp.get('tableShown'):
                fails.append('%s: the ANALYTICS calendar jump did not land on the LEDGER table (tab=%r view=%r table=%s)'
                             % (tag, jp.get('tab'), jp.get('view'), jp.get('tableShown')))
            want_flash = len([t for t in T if t['date'] == JUMP_DAY])
            if jp.get('flashed') != want_flash:
                fails.append('%s: the jump to %s flashed %s rows, expected that day\'s %d trades'
                             % (tag, JUMP_DAY, jp.get('flashed'), want_flash))
            if not jp.get('dayHeader'):
                fails.append('%s: the LEDGER table has no day header for %s after the jump' % (tag, JUMP_DAY))
            on_day = {t['id']: t['symbol'] for t in T if t['date'] == JUMP_DAY}
            if jp.get('jumpRow') not in on_day:
                fails.append('%s: after the jump to %s no flashed row to click was found (%r)' % (tag, JUMP_DAY, jp.get('jumpRow')))
            elif jp.get('jumpPanel') != jp.get('jumpRow') or jp.get('jumpSym') != on_day[jp['jumpRow']]:
                fails.append('%s: clicking the flashed row %s after the jump opened %r showing %r in the trade panel'
                             % (tag, jp.get('jumpRow'), jp.get('jumpPanel'), jp.get('jumpSym')))

    of, ou = _judge_flag(data.get('flag'), data, data_obj)
    fails += of
    unfinished += ou
    pf, pu = _judge_panels(data.get('panels'), data_obj)
    fails += pf
    unfinished += pu
    wf, wu = _judge_widths(data.get('widths'), data_obj)
    fails += wf
    unfinished += wu
    ff, fu = _judge_folds(data.get('folds'))
    fails += ff
    unfinished += fu
    if fails:
        return FAIL, fails, notes, data, True
    if unfinished:
        return INCONCLUSIVE, unfinished, notes, data, True
    return PASS, [], notes, data, False


def _report(t0, attempt, may_retry, chrome, root, alt_index):
    verdict, msgs, notes, data, retry = attempt
    first = None
    if verdict != PASS and retry and may_retry:
        first = (verdict, msgs)
        print('HOMEPROBE: attempt 1 did not pass, retrying once before blocking -- %s'
              % ('; '.join(msgs[:2]) or 'no detail'))
        verdict, msgs, notes, data, retry = _attempt(chrome, root, alt_index)
    elapsed = time.time() - t0
    data = data or {}
    if verdict == INCONCLUSIVE:
        print('HOMEPROBE: INCONCLUSIVE -- %s' % ('; '.join(msgs[:3]) if msgs else 'no detail'))
        return INCONCLUSIVE
    if verdict == FAIL:
        print('HOMEPROBE: FAIL (VERSION=%s, %.1fs%s, %d problem(s))'
              % (data.get('VERSION'), elapsed, ', both attempts' if first else '', len(msgs)))
        seen = set()
        for f in msgs:
            if f not in seen and len(seen) < 25:
                seen.add(f)
                print('  - ' + f)
        if len(set(msgs)) > 25:
            print('  - ... %d more' % (len(set(msgs)) - 25))
        for n in notes[:6]:
            print('  note: ' + n)
        return FAIL
    inter = data.get('inter') or {}
    zl = ((inter.get('laptop') or {}).get('steps') or {}).get('zoom') or {}
    n_wide = sum(len((v or {}).get('widths') or {}) for v in (((data.get('widths') or {}).get('widths')) or {}).values())
    print('HOMEPROBE: PASS (VERSION=%s, %d cases + %d ?oldboards=1 cases + %d interaction runs + %d trade panel cases + %d width samples + %d fold reload runs, %.1fs)'
          % (data.get('VERSION'), len(data.get('cases') or {}), len(((data.get('flag') or {}).get('cases')) or {}),
             len(inter), len(((data.get('panels') or {}).get('panels')) or {}), n_wide,
             len(((data.get('folds') or {}).get('folds')) or {}), elapsed))
    if first:
        print('  FLAKE: attempt 1 did not pass on this same file, the retry did. It said:')
        for f in first[1][:4]:
            print('    - ' + f)
    if os.environ.get('HOMEPROBE_VERBOSE'):
        print('  laptop chart after DAY: %s' % zl.get('infoDay'))
    for n in notes[:6]:
        print('  note: ' + n)
    return PASS


def selftest():
    """Exit 0 when the gate FAILS every MUTANT of the current index.html and PASSES the real file;
    1 when any expectation breaks; 2 when a mutant cannot be built (its anchor moved)."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='homeprobe-selftest-')
    bad = []
    try:
        for name, anchor, repl, why in MUTANTS:
            n = src.count(anchor)
            if n != 1:
                print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in '
                      'index.html (expected once). Update MUTANTS in tools/home_render_probe.py: %r'
                      % (name, n, anchor))
                return INCONCLUSIVE
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(anchor, repl))
            print('-- mutant %s (%s): expect FAIL' % (name, why))
            code = main(['--file', path, '--no-retry'])
            if code == INCONCLUSIVE:          # a Chrome hiccup is not a verdict: look once more (a PASS is never retried into a FAIL)
                print('   (inconclusive - looking once more)')
                code = main(['--file', path, '--no-retry'])
            if code != FAIL:
                bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s'
                           % (name, code, why))
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
    print('SELFTEST: PASS -- gate caught %d/%d broken builds and passed the current one (%.1fs)'
          % (len(MUTANTS), len(MUTANTS), time.time() - t0))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--no-retry', action='store_true', help='do not re-render a failed attempt')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every MUTANT of index.html, then PASS on the real file')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    t0 = time.time()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('HOMEPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print('HOMEPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    return _report(t0, _attempt(chrome, root, alt_index), not args.no_retry, chrome, root, alt_index)


if __name__ == '__main__':
    sys.exit(main())
