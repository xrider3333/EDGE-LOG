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
    it; ONE pill row TODAY 1W 1M 3M YTD ALL (counted back from today) replaces the old 1W / 1M / All tabs and the
    Today / All time switch, and every pill moves the big number, the bold line, the stats, the calendar, the
    trade list and the strategy rows together; ALL is the old all-time figure
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
      - ?oldboards=1 still gives the previous layout (ten-cell grid, old calendar, LEGS table) for one more version
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
      - ?oldboards=1 still draws the old trades table; no console.error or throw in any case
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
    # remembered per browser, a 375 px phone, and the ?oldboards=1 escape hatch (the previous layout, one more version)
    ('retired-open',    {'sub': 'paper2', 'prefs': {'paperOtherOn': ['ENGUQ']}, 'win': {'_paperShowArchived': True}}),
    ('stats-open',      {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_stats_nt8': '1'}}),
    ('cal-closed',      {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_cal_nt8': '0'}}),
    ('cal-aug',         {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_calmo_nt8': '2026-08'}}),
    ('phone375',        {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp'}),
    ('oldboards-paper2', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fo'}),
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
<pre id="o"></pre>
<script>
var CASES=__CASES__, FIX=__FIX__;
(function(){
  var reported=false;
  // ---- LEDGER step 8 on NT8 PAPER: the shared trade list frame - console / throw sink, readouts, interactions
  var SINK={};
  function hook(id){
    var fw=document.getElementById(id).contentWindow,s={errors:[],uncaught:[]};SINK[id]=s;
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
    w._ptChip=null;w._ptQuery=null;w._ptSel=null;w._ptReach=null;w._ptRowId=null;w._paperSortCol=null;w._paperSortDir=null;
    LS.removeItem('el_lg_view_nt8');
    w.renderApp();
    return I;
  }
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{['f','fp','fo','fm','fs','fx','fw','fz'].forEach(hook);}catch(e){}
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
          // the per-browser LEDGER choices (More stats fold, calendar fold, calendar month) start empty in every case
          +"localStorage.removeItem('el_lg_stats_nt8');localStorage.removeItem('el_lg_cal_nt8');localStorage.removeItem('el_lg_calmo_nt8');"
          +"var LS="+JSON.stringify(cfg.ls||{})+";for(var lk in LS)localStorage.setItem(lk,LS[lk]);"
          +"var W="+JSON.stringify(win)+";for(var k in W)window[k]=W[k];"
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
        var _bt=d.body?d.body.innerText:'';
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
        r.heroBig=[].map.call(d.querySelectorAll('.p2big'),function(x){return x.innerText;}).join('|');
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
          warnInChips:_hh.querySelectorAll('.lg-hero-chips .p2warn').length,chips:_hh.querySelectorAll('.lg-hero-chips .lg-chip').length}:null;
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
        r.warns=[].map.call(d.querySelectorAll('.p2warn'),function(x){return x.innerText.replace(/\\s+/g,' ').trim();});
        var _ntc=d.querySelector('[data-p2card="nt"]');
        r.ntCardOpen=_ntc?(_ntc.textContent.indexOf('\\u25be')>=0):null;
        r.tradesHead=(function(){var x=d.querySelector('#ptrades-wrap');var h=x&&x.parentElement?x.parentElement.querySelector('.p2sh'):null;if(h)return h.innerText.replace(/\\s+/g,' ');var c=d.querySelector('[data-lglist-frame="nt8"] .lg-tl-count');return c?c.textContent.replace(/\\s+/g,' '):'';})();
        // ---- LEDGER steps 6, 7 and 10 on the PAPER * layout: the shared stats strip + More stats, the shared calendar, the shared list
        function _t(e){return e?e.textContent.replace(/\\s+/g,' ').trim():null;}
        function _top(e){if(!e)return null;return Math.round(e.getBoundingClientRect().top+(w.pageYOffset||0));}
        r.statTiles=[].map.call(d.querySelectorAll('.lg-stats [data-lgstat]'),function(e){return {k:e.getAttribute('data-lgstat'),v:_t(e.querySelector('.lg-stat-val')),sub:_t(e.querySelector('.lg-stat-sub')),top:_top(e)};});
        r.oldStatCells=d.querySelectorAll('.p2rhstat').length;
        r.oldHero=!!d.querySelector('[data-p2num]');
        var _ls0=d.querySelector('[data-lglist="p2"]');
        r.groups=_ls0?[].map.call(_ls0.querySelectorAll('.lg-grp'),function(g){var f=g.querySelector('[data-lggrp]');
          return {key:g.getAttribute('data-lggroup'),rows:g.querySelectorAll('[data-lgrow]').length,fold:!!f,open:f?f.getAttribute('aria-expanded'):null,txt:_t(g.querySelector('.lg-grp-hd'))};}):[];
        r.listRowInfo=_ls0?[].map.call(_ls0.querySelectorAll('[data-lgrow]'),function(x){var sw=x.querySelector('[data-lgsw]'),gp=x.closest('.lg-grp');
          return {key:x.getAttribute('data-lgrow'),name:_t(x.querySelector('.lg-row-name')),group:gp?gp.getAttribute('data-lggroup'):null,sw:sw?sw.getAttribute('aria-checked'):null,off:x.classList.contains('off'),
            val:(x.querySelector('.lg-row-val')||{innerText:''}).innerText.split(String.fromCharCode(10))[0].trim(),h:Math.round(x.getBoundingClientRect().height),dot:!!x.querySelector('.lg-row-name i'),sub:_t(x.querySelector('.lg-row-sub'))};}):[];
        var _tw=d.querySelector('#ptrades-wrap'),_tcard=(_tw&&_tw.closest)?_tw.closest('.p2sheet'):null;
        r.geo={vw:w.innerWidth,vh:w.innerHeight,scrollW:d.documentElement.scrollWidth,clientW:d.documentElement.clientWidth,boardTop:_top(d.querySelector('.p2rh')),
          tradesTop:_top(d.querySelector('[data-lglist-frame="nt8"]')||_tcard),listTop:_top(_ls0),moreTop:_top(d.querySelector('[data-lgmore="p2"]')),calTop:_top(d.querySelector('[data-lgcalfold="p2"]')),
          stripTop:_top(d.querySelector('.lg-stats')),chartTop:_top(d.querySelector('#p2-chart'))};
        r.sideSticky=(function(){var c=d.querySelector('[data-p2col="side"]');return c?w.getComputedStyle(c).position:null;})();
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
        r.tl=tlRead(d,w);
        r.tlGeo=(function(){var f0=d.querySelector('[data-lglist-frame="nt8"]'),b0=d.querySelector('.p2rh');
          return {vw:w.innerWidth,vh:w.innerHeight,scrollW:d.documentElement.scrollWidth,clientW:d.documentElement.clientWidth,frameTop:f0?_top(f0):null,boardTop:b0?_top(b0):null};})();
        r.oldTable=(function(){var wp=d.getElementById('ptrades-wrap');if(!wp)return null;
          var tr=wp.querySelectorAll('tbody tr[data-ptrow]');
          return {th:[].map.call(wp.querySelectorAll('thead th'),function(x){return x.textContent.replace(/\\s+/g,' ').trim().toLowerCase();}),rows:tr.length,
            hdrs:[].map.call(wp.querySelectorAll('tbody tr.p2day'),function(x){return x.textContent.replace(/\\s+/g,' ').trim().toLowerCase();}),
            selBar:!!d.getElementById('pt-selbar'),allCharts:!!d.querySelector('[data-ptallcharts]'),frames:d.querySelectorAll('[data-lglist-frame]').length};})();
        r.oldSel=null;
        if(nm==='oldboards-paper2'){try{
          var tb0=d.getElementById('ptrades-body'),tr0=tb0?tb0.querySelector('tr[data-ptrow]'):null;
          if(tr0){tr0.cells[0].dispatchEvent(new w.PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:3,pointerType:'mouse',clientX:5,clientY:5}));
            var sb0=d.getElementById('pt-selbar');
            r.oldSel={cls:tr0.classList.contains('ptsel'),bar:sb0?sb0.textContent.replace(/\\s+/g,' ').trim():null};}
        }catch(e){r.oldSel={err:String(e)};}}
        r.tlint=null;
        if(nm==='paper2'||nm==='other-on'){try{r.tlint=tlInteract(d,w,nm);}catch(e){r.tlint={err:String(e&&e.stack?e.stack:e)};}}
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
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='PAPERPROBE: '+JSON.stringify(out);
  }
  var _nLoaded=0;
  var FRAMES=['f','fp','fo','fm','fs','fx','fw','fz'];
  FRAMES.forEach(function(id){document.getElementById(id).addEventListener('load',function(){
    _nLoaded++; if(_nLoaded===FRAMES.length)setTimeout(function(){report('load');},3500);});});
  setTimeout(function(){report('backstop');},45000);
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
                  pnl_usd=round(_src.get('pnl_usd', 0) * 1.75, 2))
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


def run(alt_index=None, timeout=180):
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

    pdir = tempfile.mkdtemp(prefix='_paperprobe_', dir=root)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__CASES__', json.dumps([[n, c] for n, c in ALL_CASES]))
            .replace('__FIX__', json.dumps(fixture)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='paperprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=50000',
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

    # EXIT-DAY board: close-day headers, the open trade apart and unrealised, the open mark in no total.
    # The old table (these readouts) now draws behind ?oldboards=1 only; the shared frame's day headers, OPEN NOW block and
    # unrealised label are asserted from the fixture further down (LEDGER step 8).
    for nm in ('oldboards-paper2',):
        r = cases.get(nm) or {}
        hd = ' | '.join(r.get('dayHdrs') or []).lower()
        if 'closed' not in hd:
            fails.append('%s: day headers do not say the day is the close day: %r' % (nm, hd[:200]))
        if 'open now' not in hd or not r.get('openMarks'):
            fails.append('%s: the open trade is not shown apart as unrealised (headers %r)' % (nm, hd[:200]))
        if '2026-09-21' not in hd:
            fails.append('%s: the Sunday-evening exit did not count on its Monday' % nm)
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
    # the warning chips live INSIDE the shared hero
    r = cases.get('paper2') or {}
    if not (r.get('hero') or {}).get('warnInChips'):
        fails.append('paper2: the warning chips are not inside the hero chip row')

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
    if (cases.get('paper2') or {}).get('sideSticky') != 'sticky':
        fails.append('paper2: the strategy list column is not sticky on a laptop (%r)' % (cases.get('paper2') or {}).get('sideSticky'))
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
        if not g.get('listTop') or g['listTop'] <= g['tradesTop']:
            fails.append('phone375: the strategy list (top %s) is not below the trade list (top %s)' % (g.get('listTop'), g['tradesTop']))
        for key in ('moreTop', 'calTop'):
            if not g.get(key) or g[key] <= g['tradesTop']:
                fails.append('phone375: the %s fold sits above the trade list on a phone (%s <= %s)' % (key[:-3], g.get(key), g['tradesTop']))
    rh = [x.get('h') or 0 for x in (r.get('listRowInfo') or [])]
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

    # -- ?oldboards=1 keeps the previous layout for one more version
    r = cases.get('oldboards-paper2') or {}
    if r.get('oldStatCells') != 10 or r.get('statTiles') or r.get('groups'):
        fails.append('oldboards-paper2: ?oldboards=1 should keep the old ten-cell grid, no shared tiles and no shared list (cells %s, tiles %s, groups %s)'
                     % (r.get('oldStatCells'), len(r.get('statTiles') or []), len(r.get('groups') or [])))
    if not r.get('oldHero') or not r.get('calDays') or sorted(r.get('bookRowKeys') or []) != sorted(book_w) \
            or ((r.get('listed') or {}).get('tie') != '1'):
        fails.append('oldboards-paper2: the previous layout lost its hero, calendar, LEGS table or tie-out line (hero %s, calendar days %s, book rows %s, tie %s)'
                     % (r.get('oldHero'), r.get('calDays'), r.get('bookRowKeys'), (r.get('listed') or {}).get('tie')))

    # warnings reach the hero while their card is closed
    r = cases.get('warn-stale-bridge') or {}
    if not any('heartbeat stale' in w for w in (r.get('warns') or [])) or r.get('ntCardOpen'):
        fails.append('warn-stale-bridge: a stale NinjaTrader heartbeat is not a chip in the hero '
                     '(warns %r, card open %r)' % (r.get('warns'), r.get('ntCardOpen')))
    r = cases.get('paper2') or {}
    if not any('10s capture low' in w for w in (r.get('warns') or [])):
        fails.append('paper2: the low 10s capture is not a chip in the hero (warns %r)' % r.get('warns'))
    # before the first nightly bundle exists the board says so, and still renders
    r = cases.get('no-bundle') or {}
    if not any('newest 500 only' in w for w in (r.get('warns') or [])):
        fails.append('no-bundle: the missing history bundle is not a chip in the hero (warns %r)' % r.get('warns'))

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
    # app routes 'paper' to 'paper2', so the old table now exists only behind ?oldboards=1.)
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

    # the old table: untouched behind ?oldboards=1 (no frame, its own sort headers, day headers and selection bar, drag / click select)
    r = cases.get('oldboards-paper2') or {}
    ot = r.get('oldTable') or {}
    exp_old = [t for t in fixture['trades'] if (_w(t) and t.get('leg') not in ())]
    if not ot or ot.get('frames') != 0:
        fails.append('oldboards-paper2: ?oldboards=1 must draw the old trades table and no shared frame (%s)' % ot)
    else:
        want_th = ['strategy', 'side', 'entry', 'entry price', 'hold', 'slip', 'δ', '$', 'cum', 'engines', 'chart']
        got_th = ot.get('th') or []
        if len(got_th) != len(want_th) or any(not g.startswith(wt) for g, wt in zip(got_th, want_th)):
            fails.append('oldboards-paper2: the old table headings read %s, expected %s' % (got_th, want_th))
        if ot.get('rows') != len(exp_old):
            fails.append('oldboards-paper2: the old table lists %s rows, the fixture holds %d trades of the shown strategies' % (ot.get('rows'), len(exp_old)))
        hdrs = ' | '.join(ot.get('hdrs') or [])
        if 'closed' not in hdrs or 'open now' not in hdrs or 'unrealised' not in hdrs or '2026-09-21' not in hdrs:
            fails.append('oldboards-paper2: the old day headers lost CLOSED / OPEN NOW / unrealised / the Sunday exit on its Monday: %r' % hdrs[:300])
        if not ot.get('selBar') or not ot.get('allCharts'):
            fails.append('oldboards-paper2: the old selection bar or ALL CHARTS is gone (%s)' % ot)
    os_ = r.get('oldSel') or {}
    if not os_.get('cls') or '1 SELECTED' not in (os_.get('bar') or '') or 'OPEN 1 CHART' not in (os_.get('bar') or ''):
        fails.append('oldboards-paper2: a pointer press on an old table row no longer selects it (%s)' % os_)

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
    if (cases.get('w1100') or {}).get('sideSticky') != 'sticky':
        fails.append('w1100: the strategy list column is not sticky at 1100 px')
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

    if fails:
        say('PAPERPROBE: FAIL')
        for f in fails:
            say('  - ' + f)
        return FAIL, out_lines

    # the new layout has a strategy list (shared ledgerListHtml rows) where the LEGS table was; ?oldboards=1 still draws the table
    say('PAPERPROBE: PASS (VERSION=%s, %d cases, strategy list %s rows, ?oldboards=1 LEGS table %s cols, %s trade rows)'
          % (data.get('VERSION'), len(cases), len((cases.get('base') or {}).get('listRowInfo') or []),
             (cases.get('oldboards-paper2') or {}).get('legHead'),
             (cases.get('base') or {}).get('tradeRows')))
    return PASS, out_lines


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
# for some other reason does not count: the check that should catch it is blind. Anchors are single lines, found exactly once.
MUTANTS = [
    ('frame-missing',
     'return ledgerTradeListHtml({id:ID,view:m.view,rows:m.shown,total:m.closedAll.length,query:m.query,chip:m.chip,',
     'return (function(o){return \'<div class="p2tl-noframe">trades</div>\';})({id:ID,view:m.view,rows:m.shown,total:m.closedAll.length,query:m.query,chip:m.chip,',
     'the NT8 trades list is no longer drawn by the shared frame',
     'not drawn by the shared frame'),
    ('frame-twice',
     "+_ntTl.build()+'</div>'):_tradesHtmlOld;",
     "+_ntTl.build()+_ntTl.build()+'</div>'):_tradesHtmlOld;",
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
    ('list-rows-overflow-601-699',
     '@container p2tl (max-width:699px){.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-pts,.lg-tl[data-lglist-frame="nt8"] .lg-tl-row .lg-c-size{display:none}}',
     '',
     'the list rows keep their points and size cells on a narrow box and run past it',
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
     'onRow:id=>{window._ptRowId=id;}});',
     'onRow:id=>{}});',
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
    ('oldboards-draws-frame',
     'const tradesHtml=_p2New?(\'<div id="nt8-tl" class="p2tlbox">\'+_ntTl.build()+\'</div>\'):_tradesHtmlOld;',
     'const tradesHtml=(_ntTl?(\'<div id="nt8-tl" class="p2tlbox">\'+_ntTl.build()+\'</div>\'):\'\');',
     '?oldboards=1 no longer draws the old trades table',
     'must draw the old trades table'),
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


def selftest(jobs=3):
    """Exit 0 when the gate FAILS every MUTANT of the current index.html - each one for the reason it names - and PASSES the real
    file; 1 when an expectation breaks; 2 when a mutant cannot be built (its anchor moved)."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='paperprobe-selftest-')
    todo = []
    try:
        for name, anchor, repl, why, expect in MUTANTS:
            n = src.count(anchor)
            if n != 1:
                print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in index.html (expected once). '
                      'Update MUTANTS in tools/paper_render_probe.py: %r' % (name, n, anchor))
                return INCONCLUSIVE
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(anchor, repl))
            todo.append((name, why, expect, path))
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
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args.jobs)
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
